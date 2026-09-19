"""Gateway use cases: short database transactions and durable outbox commands."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

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
from .security import (
    ADMIN_COOKIE,
    audit,
    authenticated,
    canonical,
    check_password,
    digest,
    encrypt,
    ip_hash,
    issue_session,
    locked_bucket,
    policy,
    public_session,
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
    return dict(
        id=run.id,
        status=run.status,
        percent=run.percent,
        remainingSeconds=run.remaining_seconds,
        updatedAt=iso(run.updated_at),
        briefId=run.brief_id,
        error=run.error,
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
    return {k: v for k, v in brief.data.items() if k in keys}


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
    configs = session.scalars(
        select(Resource).where(Resource.kind == "config").order_by(Resource.created_at.desc())
    ).all()
    selected = next((x for x in configs if x.data["status"] == "published"), None)
    if not selected:
        raise AppError("CONFIGURATION_REQUIRED", "管理员尚未发布可用配置", 503)
    models = {}
    for key in ("modelId", "summaryModelId"):
        m = resource(session, selected.data[key], "model")
        if not m.data["enabled"] or not m.data["verified"] or not m.secret:
            raise AppError("MODEL_UNAVAILABLE", "运行模型暂不可用", 503)
        models[key] = {"data": deepcopy(m.data), "encryptedSecret": m.secret}
    run = Run(
        id=uid("gen_"),
        user_id=user.id,
        business_key=business_key,
        preferences=deepcopy(user.preference),
        config=deepcopy(selected.data),
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
        # Explicitly supplied preferences are trusted memory; online text never enters here.
        ident = "pref_" + self.user.id
        row = self.db.get(Resource, ident)
        data = dict(id=ident, text=canonical(body), source="explicit_preferences", updatedAt=iso(utcnow()))
        if row:
            row.data = data
        else:
            self.db.add(Resource(id=ident, kind="memory", owner_id=self.user.id, data=data))
        return body

    def getDeliverySettings(self):
        return dict(time=self.user.delivery_time)

    def saveDeliverySettings(self):
        self.user.delivery_time = self.body["time"]
        if self.user.onboarding:
            self.user.next_run_at = next_slot(self.user.delivery_time)
        return self.getDeliverySettings()

    def listMemories(self):
        return paginated(
            [
                r.data
                for r in self.db.scalars(
                    select(Resource)
                    .where(Resource.kind == "memory", Resource.owner_id == self.user.id)
                    .order_by(Resource.created_at.desc())
                )
            ],
            self.params,
        )

    def deleteMemory(self):
        row = resource(self.db, self.ident, "memory", True)
        if row.owner_id != self.user.id:
            raise AppError("NOT_FOUND", "记录不存在", 404)
        self.db.delete(row)

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
            failedSources=sum(s.data["status"] == "failed" for s in sources),
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
        data = deepcopy(row.data)
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
                data["status"] == "failed" or (utcnow() - checked_at).total_seconds() > data["interval"]
            )
        return data

    def listSources(self):
        return self.listing("source")

    def listModels(self):
        result = self.listing("model")
        result["items"] = [{"thinkingEnabled": False, **item} for item in result["items"]]
        return result

    def listConfigs(self):
        return self.listing("config")

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
        from .ingestion import catalog_source

        try:
            catalog = catalog_source(b["sourceId"]) if b["kind"] == "newsnow" else None
        except ValueError as exc:
            raise AppError("INVALID_SOURCE", "未知或已禁用的 NewsNow 来源") from exc
        upstream = (catalog or {}).get("upstream_interval_seconds", 0)
        # The adapter owns source metadata and validates catalog identifiers.
        if isinstance(upstream, dict):
            upstream = 0
        b["interval"] = max(b["interval"], int(upstream))
        if old and all(old.get(k) == b[k] for k in ("kind", "sourceId", "url")):
            return {**old, **b, "upstreamInterval": int(upstream)}
        return {
            **b,
            "id": self.ident or uid("src_"),
            "upstreamInterval": int(upstream),
            "status": "unverified",
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
            "upstreamRevision": (catalog or {}).get("upstream_revision"),
        }

    def createSource(self):
        data = self.source_data()
        self.db.add(Resource(id=data["id"], kind="source", data=data, due_at=utcnow()))
        return data

    def saveSource(self):
        row = resource(self.db, self.ident, "source", True)
        if row.lease_until and row.lease_until > utcnow():
            raise AppError("SOURCE_BUSY", "来源采集中，请稍后保存", 409)
        previous = row.data
        row.data = self.source_data(row.data)
        if any(row.data[k] != previous.get(k) for k in ("kind", "sourceId", "url")):
            row.private = {}
        row.due_at = utcnow() + timedelta(seconds=row.data["interval"])
        return row.data

    def setSourceEnabled(self):
        row = resource(self.db, self.ident, "source", True)
        row.data = {**row.data, "status": "unverified" if self.body["enabled"] else "disabled"}
        row.due_at = utcnow() if self.body["enabled"] else None
        return row.data

    def fetchSource(self):
        row = resource(self.db, self.ident, "source", True)
        if row.data["status"] == "disabled":
            raise AppError("SOURCE_DISABLED", "请先启用来源", 409)
        if row.data["status"] != "syncing":
            row.data = {**row.data, "status": "syncing"}
            add_outbox(self.db, "source", row.id)
        return self.source_view(row)

    def write_model(self, row=None):
        body = deepcopy(self.body)
        key = body.pop("apiKey", None)
        old = row.data if row else {}
        body.setdefault("thinkingEnabled", old.get("thinkingEnabled", False))
        changed = (
            key is not None
            or any(body[k] != old.get(k) for k in ("endpoint", "modelId", "contextWindow"))
            or body["thinkingEnabled"] != old.get("thinkingEnabled", False)
        )
        data = {
            **body,
            "id": row.id if row else uid("model_"),
            "keyMasked": "已设置" if key or row and row.secret else "未设置",
            "enabled": old.get("enabled", True),
            "verified": False if changed else old.get("verified", False),
        }
        if not row:
            row = Resource(id=data["id"], kind="model", data=data)
            self.db.add(row)
        row.data = data
        if key:
            row.secret = encrypt(key)
        return data

    def createModel(self):
        return self.write_model()

    def saveModel(self):
        return self.write_model(resource(self.db, self.ident, "model", True))

    def setModelEnabled(self):
        row = resource(self.db, self.ident, "model", True)
        row.data = {"thinkingEnabled": False, **row.data, "enabled": self.body["enabled"]}
        return row.data

    def revokeModelSecret(self):
        row = resource(self.db, self.ident, "model", True)
        row.secret = None
        row.data = {**row.data, "keyMasked": "未设置", "verified": False}

    def createConfig(self):
        ident = uid("cfg_")
        data = {**self.body, "id": ident, "version": ident[-12:], "status": "draft"}
        self.db.add(Resource(id=ident, kind="config", data=data))
        return data

    def saveConfig(self):
        row = resource(self.db, self.ident, "config", True)
        if row.data["status"] != "draft":
            raise AppError("IMMUTABLE_CONFIG", "已发布版本不可修改，请创建新草稿", 409)
        row.data = {**self.body, "id": row.id, "version": row.data["version"], "status": "draft"}
        return row.data

    def publishConfig(self):
        row = resource(self.db, self.ident, "config", True)
        if row.data["status"] == "published":
            return row.data
        for field in ("modelId", "summaryModelId"):
            m = resource(self.db, row.data[field], "model")
            if not m.data["enabled"] or not m.data["verified"] or not m.secret:
                raise AppError("MODEL_UNVERIFIED", "主模型与摘要模型必须启用并通过能力测试", 409)
        row.data = {**row.data, "status": "published"}
        return row.data

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

        configs = self.db.scalars(select(Resource).where(Resource.kind == "config")).all()
        cfg = next(
            (
                c
                for c in configs
                if c.data["version"] == self.body["configVersion"] and c.data["status"] == "published"
            ),
            None,
        )
        if not cfg:
            raise AppError("CONFIGURATION_REQUIRED", "请选择已发布配置", 409)
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
            configVersion=cfg.data["version"],
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
            modelId=cfg.data["modelId"],
            results=[],
        )
        models = {
            k: {
                "data": resource(self.db, cfg.data[k], "model").data,
                "encryptedSecret": resource(self.db, cfg.data[k], "model").secret,
            }
            for k in ("modelId", "summaryModelId")
        }
        if any(
            not m["data"]["enabled"] or not m["data"]["verified"] or not m["encryptedSecret"]
            for m in models.values()
        ):
            raise AppError("MODEL_UNAVAILABLE", "评估使用的模型暂不可用", 503)
        judges = self.db.scalars(select(Resource).where(Resource.kind == "model")).all()
        judge = next(
            (
                m
                for m in judges
                if m.data["role"] == "评估模型" and m.data["enabled"] and m.data["verified"] and m.secret
            ),
            None,
        )
        data["scorerVersion"] = "rules-v1+judge-v1-" + (
            digest(canonical(judge.data))[:24] if judge else "unavailable"
        )
        private = dict(
            snapshot=dict(cases=cases, sources=sources),
            config=deepcopy(cfg.data),
            models=models,
            judge={"data": judge.data, "encryptedSecret": judge.secret} if judge else None,
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
