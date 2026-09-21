"""Gateway use cases: short database transactions and durable outbox commands."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Integer, cast, func, or_, select

from .contract import CONTRACT, schema, validate
from .db import (
    Brief,
    Bucket,
    Delivery,
    Outbox,
    PreferenceRevision,
    Resource,
    Run,
    RunEvent,
    SessionToken,
    User,
    iso,
    uid,
    utcnow,
)
from .errors import AppError
from .runtime_config import agent_config, evaluation_judge, runtime_models
from .security import (
    ADMIN_COOKIE,
    audit,
    authenticated,
    canonical,
    check_password,
    digest,
    ip_hash,
    issue_session,
    locked_bucket,
    policy,
    public_session,
)
from .sources import (
    batch_sources,
    is_collecting,
    require_available,
    set_enabled,
    source_state,
    stop_collection,
)

ACTIVE = ("queued", "running", "cancelling")
CN = ZoneInfo("Asia/Shanghai")


def next_slot(time, after=None):
    now = (after or utcnow()).replace(tzinfo=UTC).astimezone(CN)
    hour, minute = map(int, time.split(":"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC).replace(tzinfo=None)


def resource(session, ident, kind, lock=False):
    q = select(Resource).where(Resource.id == ident, Resource.kind == kind)
    row = session.scalar(q.with_for_update() if lock else q)
    if not row:
        raise AppError("NOT_FOUND", "记录不存在", 404)
    return row


def progress(run):
    phase = None
    if run.status in ACTIVE:
        phase = "publishing" if run.private.get("outputBriefId") else (
            "researching" if run.private.get("harnessStarted") else "preparing"
        )
    return dict(
        id=run.id,
        status=run.status,
        percent=run.percent,
        remainingSeconds=run.remaining_seconds,
        updatedAt=iso(run.updated_at),
        briefId=run.brief_id,
        error="生成失败，请重试" if run.status == "failed" else "",
        phase=phase,
        phaseStartedAt=run.private.get("phaseStartedAt", iso(run.updated_at)) if phase else None,
        emptyResult=bool(run.private.get("emptyResult")),
    )


def cancel_run(run, *, now=None):
    """End this task immediately and fence any worker still awaiting its model.

    Callers hold the run row lock. An in-flight upstream request may still return,
    but its cleared lease prevents further events or publication from that worker.
    """
    if run.status not in ACTIVE:
        return
    now = now or utcnow()
    run.cancel_requested = True
    run.remaining_seconds = None
    run.updated_at = now
    run.status, run.error = "cancelled", ""
    run.lease_token = run.lease_until = None


def public_brief(brief):
    keys = CONTRACT["components"]["schemas"]["Brief"]["properties"]
    data = {k: v for k, v in brief.data.items() if k in keys}
    item_keys = CONTRACT["components"]["schemas"]["NewsItem"]["properties"]
    data["items"] = [{k: v for k, v in item.items() if k in item_keys} for item in data["items"]]
    return data


def public_delivery(session, delivery):
    user = session.get(User, delivery.user_id)
    return dict(
        id=delivery.id,
        briefId=delivery.brief_id,
        userName=user.name,
        destination="/briefs/" + delivery.brief_id,
        channel="in_app",
        status=delivery.status,
        attempts=delivery.attempts,
        time=iso(delivery.updated_at),
        error=delivery.error,
    )


def run_view(session, run):
    user = session.get(User, run.user_id)
    events = [
        e.data
        for e in session.scalars(select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq))
    ]
    return dict(
        id=run.id,
        userName=user.name,
        status=run.status,
        model=run.private.get("modelName", run.config.get("modelId", "")),
        configVersion=run.config.get("version", ""),
        startedAt=iso(run.created_at),
        elapsedSeconds=run.elapsed_seconds,
        inputTokens=run.input_tokens,
        outputTokens=run.output_tokens,
        cost=run.cost,
        searchCount=run.search_count,
        events=events,
        subtasks=run.private.get("subtasks", []),
    )


def paginated(items, params):
    limit = int(params.get("limit", 20))
    cursor = params.get("cursor")
    if cursor:
        position = next((i for i, x in enumerate(items) if x["id"] == cursor), None)
        if position is None:
            raise AppError("INVALID_CURSOR", "分页位置已失效，请刷新列表")
        items = items[position + 1 :]
    batch = items[:limit]
    return dict(items=batch, nextCursor=batch[-1]["id"] if len(items) > limit and batch else None)


def add_outbox(session, kind, target):
    session.add(Outbox(id=uid("job_"), kind=kind, target_id=target))


def create_run(session, user, business_key, preference_version=None):
    existing = session.scalar(select(Run).where(Run.business_key == business_key))
    if existing:
        return existing
    if user.status != "active":
        raise AppError("ACCOUNT_BLOCKED", "账号已停用", 403)
    if not user.onboarding:
        raise AppError("PREFERENCES_REQUIRED", "请先保存订阅偏好", 409)
    if preference_version is not None and preference_version != user.preference["version"]:
        raise AppError("VERSION_CONFLICT", "偏好已更新，请刷新后重试", 409)
    p = policy(session)
    active = session.scalar(
        select(func.count()).select_from(Run).where(Run.user_id == user.id, Run.status.in_(ACTIVE))
    )
    if active >= p["maxConcurrentGenerations"]:
        raise AppError("CONCURRENCY_LIMIT", "已有简报正在生成", 429, retry_after=15)
    now = utcnow()
    day = now.replace(tzinfo=UTC).astimezone(CN).date().isoformat()
    bucket = locked_bucket(session, "generate:" + user.id + ":" + day, next_slot("00:00", now))
    if bucket.count >= p["generationsPerDay"]:
        raise AppError(
            "GENERATION_LIMIT",
            "今日生成次数已达上限",
            429,
            retry_after=max(1, int((bucket.expires_at - now).total_seconds())),
        )
    config = agent_config()
    models = runtime_models()
    run = Run(
        id=uid("gen_"),
        user_id=user.id,
        business_key=business_key,
        preferences=deepcopy(user.preference),
        config=config,
        private={"models": models, "modelName": models["modelId"]["data"]["name"]},
        status="queued",
        percent=None,
        remaining_seconds=None,
    )
    session.add(run)
    session.flush()
    bucket.count += 1
    add_outbox(session, "run", run.id)
    return run


class Application:
    def __init__(self, session, request, response, user, body, params, operation):
        self.db, self.request, self.response = session, request, response
        self.user, self.body, self.params, self.operation = user, body, params, operation
        self.ident = params.get("id")

    def execute(self):
        method = getattr(self, self.operation, None)
        if not method:
            raise RuntimeError("Unimplemented contract operation: " + self.operation)
        return method()

    def ensureAnonymousSession(self):
        user = authenticated(self.db, self.request, optional=True, lock=True)
        if user:
            return public_session(user)
        ip = ip_hash(self.request)
        now = utcnow()
        hour = now.replace(minute=0, second=0, microsecond=0)
        bucket = locked_bucket(self.db, "account:" + ip + ":" + hour.isoformat(), hour + timedelta(hours=1))
        if bucket.count >= policy(self.db)["accountsPerIpHour"]:
            raise AppError(
                "ACCOUNT_CREATION_LIMIT",
                "创建账号过于频繁，请稍后重试",
                429,
                retry_after=max(1, int((bucket.expires_at - now).total_seconds())),
            )
        ident = uid("anon_")
        user = User(id=ident, name="读者 " + ident[-6:], role="anonymous", ip_hash=ip)
        self.db.add(user)
        self.db.flush()
        bucket.count += 1
        issue_session(self.db, user, self.response)
        return public_session(user)

    def getSession(self):
        return public_session(self.user)

    def adminLogin(self):
        ip = ip_hash(self.request)
        now = utcnow()
        minute = now.replace(second=0, microsecond=0)
        bucket = locked_bucket(
            self.db, "login:" + ip + ":" + minute.isoformat(), minute + timedelta(minutes=1)
        )
        if bucket.count >= 10:
            raise AppError("LOGIN_LIMIT", "登录尝试过于频繁", 429, retry_after=60)
        bucket.count += 1
        user = self.db.scalar(
            select(User).where(User.email == self.body["email"].lower(), User.role == "admin")
        )
        if not user or not check_password(self.body["password"], user.password_hash):
            # The Gateway commits rejected-auth counters before returning the error.
            raise AppError("INVALID_CREDENTIALS", "邮箱或密码错误", 401)
        issue_session(self.db, user, self.response)
        return public_session(user)

    def getAdminSession(self):
        return public_session(self.user)

    def adminLogout(self):
        token = self.request.cookies.get(ADMIN_COOKIE)
        if token:
            row = self.db.get(SessionToken, digest(token))
            if row:
                row.revoked = True
        self.response.delete_cookie(ADMIN_COOKIE, path="/")
        return None

    def getPreferences(self):
        return self.user.preference

    def savePreferences(self):
        body = deepcopy(self.body)
        body["topics"] = list(dict.fromkeys(x.strip() for x in body["topics"]))
        body["keywords"] = list(dict.fromkeys(x.strip() for x in body["keywords"]))
        body["role"] = body["role"].strip()
        validate(schema("PreferencesWrite"), body)
        if body["version"] != self.user.preference["version"]:
            raise AppError("VERSION_CONFLICT", "偏好已被更新，请刷新后重试", 409)
        body["version"] += 1
        self.user.preference = body
        self.db.add(PreferenceRevision(user_id=self.user.id, version=body["version"], data=body))
        if not self.user.onboarding:
            self.user.next_run_at = next_slot(self.user.delivery_time)
        self.user.onboarding = True
        return body

    def getDeliverySettings(self):
        return dict(time=self.user.delivery_time)

    def saveDeliverySettings(self):
        self.user.delivery_time = self.body["time"]
        if self.user.onboarding:
            self.user.next_run_at = next_slot(self.user.delivery_time)
        return self.getDeliverySettings()

    def generateBrief(self):
        key = digest(self.user.id + ":" + self.request.headers["idempotency-key"])
        return progress(create_run(self.db, self.user, "manual:" + key, self.body["preferenceVersion"]))

    def own_run(self):
        run = self.db.scalar(
            select(Run).where(Run.id == self.ident, Run.user_id == self.user.id).with_for_update()
        )
        if not run:
            raise AppError("NOT_FOUND", "生成记录不存在", 404)
        return run

    def getGenerationProgress(self):
        return progress(self.own_run())

    def getCurrentGeneration(self):
        run = self.db.scalar(
            select(Run).where(Run.user_id == self.user.id).order_by(Run.created_at.desc()).limit(1)
        )
        return progress(run) if run else None

    def cancelGeneration(self):
        run = self.own_run()
        cancel_run(run)
        return progress(run)

    def listBriefs(self):
        rows = self.db.scalars(
            select(Brief)
            .where(Brief.user_id == self.user.id, Brief.published.is_(True))
            .order_by(Brief.created_at.desc(), Brief.id.desc())
        )
        data = []
        for row in rows:
            b = public_brief(row)
            if self.params.get("date") and b["date"] != self.params["date"]:
                continue
            if self.params.get("status") and b["generationStatus"] != self.params["status"]:
                continue
            if self.params.get("topic") and not any(x["topic"] == self.params["topic"] for x in b["items"]):
                continue
            if self.params.get("q") and self.params["q"].casefold() not in canonical(b).casefold():
                continue
            data.append(b)
        return paginated(data, self.params)

    def getBrief(self):
        row = self.db.scalar(
            select(Brief).where(
                Brief.id == self.ident, Brief.user_id == self.user.id, Brief.published.is_(True)
            )
        )
        if not row:
            raise AppError("NOT_FOUND", "简报不存在", 404)
        return public_brief(row)

    def listOwnDeliveries(self):
        rows = self.db.scalars(
            select(Delivery).where(Delivery.user_id == self.user.id).order_by(Delivery.updated_at.desc())
        )
        return paginated([public_delivery(self.db, row) for row in rows], self.params)

    def retryOwnDelivery(self):
        return self.retry_delivery(own=True)

    def retry_delivery(self, own=False):
        q = select(Delivery).where(Delivery.id == self.ident)
        if own:
            q = q.where(Delivery.user_id == self.user.id)
        row = self.db.scalar(q.with_for_update())
        if not row:
            raise AppError("NOT_FOUND", "发布记录不存在", 404)
        if row.status not in ("pending", "submitted"):
            row.status = "pending"
            row.updated_at = utcnow()
            add_outbox(self.db, "delivery", row.id)
        return public_delivery(self.db, row)

    def getOverview(self):
        runs = self.db.scalars(select(Run)).all()
        ended = [r for r in runs if r.status not in ACTIVE]
        sources = self.db.scalars(select(Resource).where(Resource.kind == "source")).all()
        return dict(
            activeRuns=sum(r.status in ACTIVE for r in runs),
            failedSources=sum(source_state(s)["health"] in ("failed", "invalid") for s in sources),
            failedDeliveries=self.db.scalar(
                select(func.count()).select_from(Delivery).where(Delivery.status.in_(["failed", "unknown"]))
            ),
            sampleCount=len(ended),
            completionRate=sum(r.status in ("completed", "partial") for r in ended) / len(ended)
            if ended
            else None,
            generatedAt=iso(utcnow()),
        )

    def listing(self, kind):
        rows = self.db.scalars(
            select(Resource)
            .where(Resource.kind == kind)
            .order_by(Resource.created_at.desc(), Resource.id.desc())
        )
        return paginated([self.source_view(r) if kind == "source" else r.data for r in rows], self.params)

    def source_view(self, row):
        data = source_state(row)
        data["version"] = row.data.get("version", 0)
        at = data.get("snapshotFetchedAt")
        if at:
            age = max(
                0,
                int(
                    (
                        utcnow() - datetime.fromisoformat(at.replace("Z", "+00:00")).replace(tzinfo=None)
                    ).total_seconds()
                ),
            )
            data["cacheAgeSeconds"] = age
            checked = row.private.get("state", {}).get("last_checked_at") or at
            checked_at = datetime.fromisoformat(checked.replace("Z", "+00:00")).replace(tzinfo=None)
            data["stale"] = (
                data["health"] in ("failed", "invalid")
                or (utcnow() - checked_at).total_seconds() > data["interval"]
            )
        return data

    def listSources(self):
        query = select(Resource).where(Resource.kind == "source")
        name = self.params.get("q", "").strip()
        if name:
            query = query.where(
                func.lower(Resource.data["name"].as_string()).contains(name.lower(), autoescape=True)
            )
        if self.params.get("kind"):
            query = query.where(Resource.data["kind"].as_string() == self.params["kind"])
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        total_pages = (total + 9) // 10
        page = min(int(self.params.get("page", 1)), max(1, total_pages))
        rows = self.db.scalars(
            query.order_by(Resource.created_at.desc(), Resource.id.desc()).offset((page - 1) * 10).limit(10)
        )
        invalid_total = self.db.scalar(select(func.count()).select_from(Resource).where(
            Resource.kind == "source",
            or_(
                cast(Resource.private["state"]["failure_count"].as_string(), Integer) >= 3,
                func.coalesce(Resource.data["health"].as_string(),
                              Resource.private["state"]["status"].as_string(),
                              Resource.data["status"].as_string()) == "invalid",
            ),
        ))
        return dict(
            items=[self.source_view(r) for r in rows],
            total=total,
            page=page,
            pageSize=10,
            totalPages=total_pages,
            invalidTotal=invalid_total,
        )

    def listEvalCases(self):
        return self.listing("case")

    def listEvaluations(self):
        return self.listing("evaluation")

    def getSource(self):
        return self.source_view(resource(self.db, self.ident, "source"))

    def getEvaluation(self):
        return resource(self.db, self.ident, "evaluation").data

    def source_data(self, old=None):
        b = deepcopy(self.body)
        b["version"] = (old or {}).get("version", 0) + 1
        if old and all(old.get(k) == b[k] for k in ("kind", "sourceId", "url")):
            return {**old, **b}
        return {
            **b,
            "id": self.ident or uid("src_"),
            "status": "unverified" if not old or old.get("enabled", True) else "disabled",
            "enabled": old.get("enabled", True) if old else True,
            "health": "unverified",
            "failureCount": 0,
            "collectionStatus": "idle",
            "lastSuccess": "",
            "nextFetch": iso(utcnow()),
            "lastChanged": "",
            "items": 0,
            "error": "",
            "snapshotId": None,
            "snapshotFetchedAt": None,
            "lastFetchedAt": None,
            "cacheAgeSeconds": None,
            "stale": True,
        }

    def createSource(self):
        data = self.source_data()
        self.db.add(Resource(id=data["id"], kind="source", data=data, due_at=utcnow()))
        return data

    def saveSource(self):
        require_available(self.db, self.ident)
        row = resource(self.db, self.ident, "source", True)
        if self.body["version"] != row.data.get("version", 0):
            raise AppError("VERSION_CONFLICT", "来源配置已被其他管理员修改，请核对最新配置后再保存", 409)
        if row.private.get("delete_pending"):
            raise AppError("SOURCE_BUSY", "来源采集文件尚未清理完成，请先重试删除", 409)
        if is_collecting(row.id):
            raise AppError("SOURCE_BUSY", "来源采集中，请稍后保存", 409)
        previous = source_state(row)
        row.data = self.source_data(previous)
        if any(row.data[k] != previous.get(k) for k in ("kind", "sourceId", "url")):
            row.private = {}
        row.due_at = (
            utcnow() + timedelta(seconds=row.data["interval"])
            if row.data["enabled"] and row.data["health"] != "invalid"
            else None
        )
        row.data = {**row.data, "nextFetch": iso(row.due_at) or ""}
        return self.source_view(row)

    def setSourceEnabled(self):
        require_available(self.db, self.ident)
        row = resource(self.db, self.ident, "source", True)
        set_enabled(row, self.body["enabled"], utcnow())
        return self.source_view(row)

    def fetchSource(self):
        require_available(self.db, self.ident)
        row = resource(self.db, self.ident, "source", True)
        data = source_state(row)
        if row.private.get("delete_pending") or data["collectionStatus"] == "stopping":
            raise AppError("SOURCE_BUSY", "请先等待停止或完成删除清理", 409)
        if not data["enabled"] and data["health"] != "invalid":
            raise AppError("SOURCE_DISABLED", "请先启用来源", 409)
        if data["collectionStatus"] not in ("queued", "running", "stopping"):
            row.data = {**data, "status": "syncing", "collectionStatus": "queued"}
            row.private = {**row.private, "manual_request": True, "stop_requested": False}
            add_outbox(self.db, "source", row.id)
        return self.source_view(row)

    def stopSource(self):
        require_available(self.db, self.ident)
        return stop_collection(resource(self.db, self.ident, "source", True))

    def batchSources(self):
        if self.body["action"] == "delete":
            from .source_deletions import create_job

            return create_job(self.db, self.body["ids"])
        return batch_sources(self.db, self.body["ids"], self.body["action"])

    def deleteInvalidSources(self):
        from .source_deletions import create_job

        return create_job(self.db)

    def currentSourceDeletion(self):
        from .source_deletions import current_job

        return {"job": current_job(self.db)}

    def write_case(self, row=None):
        body = deepcopy(self.body)
        if row:
            data = {**row.data, **body, "revision": row.data["revision"] + 1}
        else:
            snapshots = [
                s.data["snapshotId"]
                for s in self.db.scalars(select(Resource).where(Resource.kind == "source"))
                if s.data.get("snapshotId")
            ]
            data = {
                "id": uid("case_"),
                "preferenceSnapshot": dict(version=0, role=body["preference"], topics=[], keywords=[]),
                "fixedAt": iso(utcnow()),
                "sourceSnapshotIds": snapshots,
                **body,
                "revision": 1,
            }
        for sid in data["sourceSnapshotIds"]:
            resource(self.db, sid, "snapshot")
        if row:
            row.data = data
        else:
            self.db.add(Resource(id=data["id"], kind="case", data=data))
        return data

    def createEvalCase(self):
        return self.write_case()

    def saveEvalCase(self):
        return self.write_case(resource(self.db, self.ident, "case", True))

    def runEvaluation(self):
        from .evaluation import freeze_dataset

        config = agent_config()
        models = runtime_models()
        judge = evaluation_judge()
        cases = [deepcopy(c.data) for c in self.db.scalars(select(Resource).where(Resource.kind == "case"))]
        if not cases:
            raise AppError("EMPTY_DATASET", "请先保存评估用例")
        sources = {
            s: resource(self.db, s, "snapshot").private["items"]
            for c in cases
            for s in c["sourceSnapshotIds"]
        }
        frozen = freeze_dataset(cases, sources)
        ident = uid("eval_")
        data = dict(
            id=ident,
            name="评估 " + iso(utcnow()),
            configVersion=config["version"],
            status="queued",
            relevance=None,
            faithfulness=None,
            citations=None,
            cost=None,
            latency=None,
            cases=len(cases),
            createdAt=iso(utcnow()),
            datasetVersion=frozen.version,
            scorerVersion="rules-v1",
            modelId=models["modelId"]["data"]["modelId"],
            results=[],
        )
        data["scorerVersion"] = "rules-v1+judge-v1-" + (
            digest(canonical(judge["data"]))[:24] if judge else "unavailable"
        )
        private = dict(
            snapshot=dict(cases=cases, sources=sources),
            config=config,
            models=models,
            judge=judge,
        )
        self.db.add(Resource(id=ident, kind="evaluation", data=data, private=private))
        add_outbox(self.db, "evaluation", ident)
        return dict(evaluationId=ident)

    def listAdminRuns(self):
        query = select(Run).order_by(Run.created_at.desc(), Run.id.desc())
        if self.params.get("status"):
            query = query.where(Run.status == self.params["status"])
        rows = [run_view(self.db, r) for r in self.db.scalars(query)]
        for key in ("model", "modelId"):
            if self.params.get(key):
                rows = [r for r in rows if self.params[key] in r["model"]]
        if self.params.get("from"):
            boundary = datetime.fromisoformat(self.params["from"].replace("Z", "+00:00"))
            rows = [
                r for r in rows if datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00")) >= boundary
            ]
        if self.params.get("to"):
            boundary = datetime.fromisoformat(self.params["to"].replace("Z", "+00:00"))
            rows = [
                r for r in rows if datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00")) <= boundary
            ]
        return paginated(rows, self.params)

    def getAdminRun(self):
        run = self.db.get(Run, self.ident)
        if not run:
            raise AppError("NOT_FOUND", "运行不存在", 404)
        return run_view(self.db, run)

    def cancelAdminRun(self):
        run = self.db.scalar(select(Run).where(Run.id == self.ident).with_for_update())
        if not run:
            raise AppError("NOT_FOUND", "运行不存在", 404)
        cancel_run(run)
        return run_view(self.db, run)

    def listAdminDeliveries(self):
        q = select(Delivery).order_by(Delivery.updated_at.desc())
        if self.params.get("status"):
            q = q.where(Delivery.status == self.params["status"])
        return paginated([public_delivery(self.db, r) for r in self.db.scalars(q)], self.params)

    def retryAdminDelivery(self):
        return self.retry_delivery()

    def account_view(self, u):
        now = utcnow()
        minute = now.replace(second=0, microsecond=0).isoformat()
        day = now.replace(tzinfo=UTC).astimezone(CN).date().isoformat()
        requests = self.db.get(Bucket, "request:" + u.id + ":" + minute)
        gens = self.db.get(Bucket, "generate:" + u.id + ":" + day)
        active = self.db.scalar(
            select(func.count()).select_from(Run).where(Run.user_id == u.id, Run.status.in_(ACTIVE))
        )
        return dict(
            id=u.id,
            name=u.name,
            createdAt=iso(u.created_at),
            lastSeenAt=iso(u.last_seen_at),
            status=u.status,
            risk="high" if u.rate_limit_hits >= 5 else "watch" if u.rate_limit_hits else "normal",
            requestsLastMinute=requests.count if requests else 0,
            generationsToday=gens.count if gens else 0,
            rateLimitHits=u.rate_limit_hits,
            activeGenerations=active,
            ipLabel="ip:" + u.ip_hash[:10],
            blockReason=u.block_reason,
        )

    def listAnonymousAccounts(self):
        rows = self.db.scalars(select(User).where(User.role == "anonymous").order_by(User.created_at.desc()))
        data = [self.account_view(u) for u in rows]
        for key in ("status", "risk"):
            if self.params.get(key):
                data = [x for x in data if x[key] == self.params[key]]
        return paginated(data, self.params)

    def setAnonymousAccountStatus(self):
        u = self.db.scalar(
            select(User).where(User.id == self.ident, User.role == "anonymous").with_for_update()
        )
        if not u:
            raise AppError("NOT_FOUND", "账号不存在", 404)
        u.status, u.block_reason = self.body["status"], self.body["reason"]
        u.next_run_at = next_slot(u.delivery_time) if u.status == "active" and u.onboarding else None
        audit(
            self.db,
            u.id,
            "account_blocked" if u.status == "blocked" else "account_unblocked",
            self.body["reason"],
            self.user.id,
        )
        return self.account_view(u)

    def listAbuseEvents(self):
        data = [
            r.data
            for r in self.db.scalars(
                select(Resource).where(Resource.kind == "abuse").order_by(Resource.created_at.desc())
            )
        ]
        for key in ("accountId", "kind"):
            if self.params.get(key):
                data = [x for x in data if x[key] == self.params[key]]
        return paginated(data, self.params)

    def getAnonymousPolicy(self):
        return policy(self.db)

    def saveAnonymousPolicy(self):
        row = self.db.get(Resource, "anonymous-policy")
        if row:
            row.data = deepcopy(self.body)
        else:
            self.db.add(Resource(id="anonymous-policy", kind="policy", data=deepcopy(self.body)))
        # Kept as an administrator audit record; no fake user risk event is invented.
        self.db.add(
            Resource(
                id=uid("audit_"),
                kind="audit",
                owner_id=self.user.id,
                data={"action": "policy_changed", "time": iso(utcnow()), "policy": self.body},
            )
        )
        return self.body
