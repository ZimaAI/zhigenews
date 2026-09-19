"""HTTP adapter registered from the approved OpenAPI operation inventory."""

import asyncio
import json
import logging
from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from .application import ACTIVE, Application, resource
from .contract import CONTRACT, schema, validate
from .db import Idempotency, Run, RunEvent, iso, transaction, utcnow
from .errors import AppError
from .models import ModelConfigurationError, build_model
from .security import audit, authenticated, canonical, decrypt, digest, locked_bucket, policy
from .settings import get_settings

logger = logging.getLogger(__name__)
app = FastAPI(title="知更 API", version="1.0.0", openapi_url="/openapi.json")
app.openapi = lambda: CONTRACT
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Zhige-Request", "Idempotency-Key", "Last-Event-ID"],
    expose_headers=["Retry-After", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request, call_next):
    request.state.request_id = uuid4().hex
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(AppError)
async def domain_error(request, exc):
    data = dict(code=exc.public_code, message=exc.message, requestId=request.state.request_id)
    if exc.fields:
        data["fields"] = exc.fields
    validate(schema("Error"), data, output=True)
    return JSONResponse(
        data,
        status_code=exc.status,
        headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return await domain_error(
        request,
        AppError(
            "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
            "请求的资源不存在" if exc.status_code == 404 else "请求无法处理",
            exc.status_code,
        ),
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    logger.error("Database request failed: %s [%s]", type(exc).__name__, request.state.request_id)
    return await domain_error(request, AppError("DEPENDENCY_UNAVAILABLE", "服务暂时不可用，请稍后重试", 503))


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    logger.error("Request failed: %s [%s]", type(exc).__name__, request.state.request_id)
    return await domain_error(request, AppError("SERVICE_ERROR", "服务暂时无法完成请求", 503))


@app.get("/healthz", include_in_schema=False)
def health():
    with transaction() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ok", "version": "1.0.0"}


def csrf(request):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    origin = request.headers.get("origin")
    if origin and origin not in settings.allowed_origins or request.headers.get("x-zhige-request") != "1":
        raise AppError("CSRF_REJECTED", "请求来源校验失败", 403)
    if request.headers.get("sec-fetch-site") == "cross-site" and not origin:
        raise AppError("CSRF_REJECTED", "请求来源校验失败", 403)


def count_request(request, operation):
    if operation == "adminLogin":
        return
    admin = operation in ADMIN_OPERATIONS
    error = None
    with transaction() as session:
        user = authenticated(
            session, request, admin, lock=True, optional=operation == "ensureAnonymousSession"
        )
        if user is None:
            return
        user.last_seen_at = utcnow()
        if not admin:
            now = utcnow()
            minute = now.replace(second=0, microsecond=0)
            bucket = locked_bucket(
                session, "request:" + user.id + ":" + minute.isoformat(), minute + timedelta(minutes=1)
            )
            if bucket.count >= policy(session)["requestsPerMinute"]:
                user.rate_limit_hits += 1
                audit(session, user.id, "rate_limited", "账号每分钟请求额度已用尽")
                error = AppError(
                    "RATE_LIMITED",
                    "请求过于频繁，请稍后重试",
                    429,
                    retry_after=max(1, int((bucket.expires_at - now).total_seconds())),
                )
            bucket.count += 1
    if error:
        raise error


def model_test(request, ident):
    # Credentials and config are captured in a short transaction; no DB lock spans a model call.
    with transaction() as session:
        authenticated(session, request, True)
        row = resource(session, ident, "model")
        data, secret = dict(row.data), row.secret
        fingerprint = digest(canonical(data) + (secret or ""))
    verified, capabilities, message = False, [], "连接测试失败"
    if secret:
        try:
            thinking_enabled = data.get("thinkingEnabled", False)
            model = build_model(
                data,
                api_key=decrypt(secret),
                timeout=120 if thinking_enabled else 25,
                max_tokens=min(16384, max(256, data["contextWindow"] // 4)) if thinking_enabled else 100,
            )
            tool = {
                "type": "function",
                "function": {
                    "name": "connection_probe",
                    "description": "Verify tool calling",
                    "parameters": {
                        "type": "object",
                        "properties": {"value": {"type": "string"}},
                        "required": ["value"],
                    },
                },
            }
            answer = model.bind_tools([tool], tool_choice="connection_probe").invoke(
                "Call connection_probe with value ok."
            )
            verified = any(
                t["name"] == "connection_probe" and t["args"].get("value") == "ok" for t in answer.tool_calls
            )
            capabilities = ["chat", "tool_calling"] if verified else ["chat"]
            message = "模型工具调用能力验证通过" if verified else "模型没有返回要求的工具调用"
        except ModelConfigurationError as exc:
            message = str(exc)
        except Exception:
            message = "模型请求失败，请检查端点、模型名称和凭据"
    else:
        message = "请先配置模型密钥"
    with transaction() as session:
        row = resource(session, ident, "model", True)
        if digest(canonical(row.data) + (row.secret or "")) != fingerprint:
            raise AppError("VERSION_CONFLICT", "模型配置已改变，请重新测试", 409)
        row.data = {**row.data, "verified": verified}
    return dict(verified=verified, message=message, testedAt=iso(utcnow()), capabilities=capabilities)


def execute(request, response, operation, body, params):
    count_request(request, operation)
    if operation == "testModel":
        return model_test(request, params["id"])
    saved_error = None
    with transaction() as session:
        user = (
            None
            if operation in ("ensureAnonymousSession", "adminLogin")
            else authenticated(session, request, operation in ADMIN_OPERATIONS, lock=True)
        )
        idempotency = request.headers.get("idempotency-key")
        idem_key = (
            digest((user.id if user else "") + ":" + request.url.path + ":" + idempotency)
            if idempotency
            else None
        )
        body_hash = digest(canonical(body))
        if idem_key:
            old = session.get(Idempotency, idem_key)
            if old:
                if old.request_hash != body_hash:
                    raise AppError("IDEMPOTENCY_CONFLICT", "同一请求标识不能用于不同内容", 409)
                return old.response
        service = Application(session, request, response, user, body, params, operation)
        try:
            # A savepoint rolls back partial business writes on validation failures.
            # Login has its own failed-attempt counter, retained across rejection.
            if operation == "adminLogin":
                result = service.execute()
            else:
                with session.begin_nested():
                    result = service.execute()
        except AppError as exc:
            saved_error = exc
            if user and exc.status == 429:
                user.rate_limit_hits += 1
                audit(session, user.id, "generation_rejected", exc.message)
        if not saved_error and idem_key:
            session.add(
                Idempotency(
                    key=idem_key, request_hash=body_hash, response=result, status_code=response.status_code
                )
            )
    if saved_error:
        raise saved_error
    return result


async def event_stream(request, run_id, after):
    while not await request.is_disconnected():
        with transaction() as session:
            authenticated(session, request, True)
            run = session.get(Run, run_id)
            if not run:
                return
            rows = list(
                session.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.seq > after)
                    .order_by(RunEvent.seq)
                    .limit(100)
                )
            )
            ended = run.status not in ACTIVE
            events = [(r.seq, r.data) for r in rows]
        for seq, data in events:
            after = seq
            yield f"id: {seq}\nevent: run.event\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        if ended and len(events) < 100:
            return
        if not events:
            yield ": heartbeat\n\n"
        await asyncio.sleep(1)


def make_handler(operation):
    op_id = operation["operationId"]
    response_code = next(int(c) for c in operation["responses"] if c.isnumeric() and int(c) < 300)

    async def handler(request: Request):
        csrf(request)
        params = {**dict(request.query_params), **request.path_params}
        for parameter in operation.get("parameters", []):
            name, location = parameter["name"], parameter["in"]
            value = request.headers.get(name) if location == "header" else params.get(name)
            if value is None:
                if parameter.get("required"):
                    raise AppError("INVALID_INPUT", f"缺少参数 {name}")
                continue
            if parameter["schema"].get("type") == "integer":
                try:
                    value = int(value)
                except ValueError:
                    raise AppError("INVALID_INPUT", f"参数 {name} 必须为整数")
                params[name] = value
            validate(parameter["schema"], value)
        body = {}
        if operation.get("requestBody"):
            if not request.headers.get("content-type", "").startswith("application/json"):
                raise AppError("INVALID_INPUT", "请求必须使用 JSON")
            try:
                body = await request.json()
            except (ValueError, UnicodeDecodeError):
                raise AppError("INVALID_INPUT", "无法解析 JSON")
            validate(operation["requestBody"]["content"]["application/json"]["schema"], body)
        if op_id == "adminRunEvents":
            await run_in_threadpool(count_request, request, op_id)
            with transaction() as session:
                if not session.get(Run, params["id"]):
                    raise AppError("NOT_FOUND", "运行不存在", 404)
            try:
                after = max(0, int(request.headers.get("last-event-id", params.get("after", 0))))
            except ValueError:
                raise AppError("INVALID_INPUT", "事件游标无效")
            return StreamingResponse(
                event_stream(request, params["id"], after),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        response = Response(status_code=response_code)
        result = await run_in_threadpool(execute, request, response, op_id, body, params)
        definition = operation["responses"][str(response_code)]
        output = definition.get("content", {}).get("application/json", {}).get("schema")
        if output:
            validate(output, result, output=True)
            rendered = JSONResponse(result, status_code=response_code)
            for name, value in response.raw_headers:
                if name == b"set-cookie":
                    rendered.raw_headers.append((name, value))
            return rendered
        return response

    return handler


ADMIN_OPERATIONS = {
    op["operationId"]
    for path, methods in CONTRACT["paths"].items()
    if path.startswith("/admin/")
    for method, op in methods.items()
    if method in ("get", "post", "put", "delete")
}
# Static paths must precede /{id}, including the current-generation recovery endpoint.
for path, methods in sorted(CONTRACT["paths"].items(), key=lambda x: ("{" in x[0], x[0])):
    for method, operation in methods.items():
        if method in ("get", "post", "put", "delete"):
            app.add_api_route(
                "/api/v1" + path,
                make_handler(operation),
                methods=[method.upper()],
                name=operation["operationId"],
                include_in_schema=False,
            )
