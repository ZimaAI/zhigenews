"""Durable scheduling, outbox delivery and isolated worker entry points.

HTTP and broker calls run outside database transactions. Consumers tolerate
redelivery; source publication is additionally fenced by a lease and file lock.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from celery import Celery
from filelock import FileLock, Timeout
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from .application import CN, add_outbox, cancel_run, create_run, next_slot, public_brief
from .contract import schema, validate
from .db import Brief, Delivery, Outbox, Resource, Run, RunEvent, User, iso, transaction, uid, utcnow
from .errors import AppError
from .ingestion import fetch_source
from .ingestion.service import SAFE_ID, IngestionError
from .settings import get_settings
from .sources import pending_deletion, source_state

logger = logging.getLogger(__name__)
SOURCE_LEASE_SECONDS = 120
TASK_NAMES = {kind: "zhigenews." + kind for kind in ("source", "run", "evaluation", "delivery", "source_deletion")}

celery_app = Celery("zhigenews", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 3600},
    result_expires=3600,
    beat_schedule={"due-and-outbox-every-ten-seconds": {"task": "zhigenews.tick", "schedule": 10.0}},
)
app = celery_app


def _date(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo else parsed


def dispatch_outbox(*, outbox_ids=None, send=None, limit=100):
    """Publish before marking sent; an uncertain publish may safely be repeated."""
    with transaction() as session:
        query = (
            select(Outbox).where(Outbox.sent_at.is_(None)).order_by(Outbox.created_at, Outbox.id).limit(limit)
        )
        if outbox_ids is not None:
            query = query.where(Outbox.id.in_(outbox_ids))
        pending = [(row.id, row.kind, row.target_id) for row in session.scalars(query)]
    sent, failed = [], []
    sender = send or celery_app.send_task
    for ident, kind, target in pending:
        if kind not in TASK_NAMES:
            failed.append(ident)
            logger.error("Unknown outbox task kind %s for %s", kind, ident)
            continue
        try:
            sender(TASK_NAMES[kind], args=[target], task_id=ident)
        except Exception:
            # Keep the command durable if broker availability/acknowledgment is uncertain.
            failed.append(ident)
            logger.warning("Outbox publish failed for %s", ident)
            continue
        with transaction() as session:
            row = session.get(Outbox, ident)
            if row and row.sent_at is None:
                row.sent_at = utcnow()
        sent.append(ident)
    return {"sent": sent, "failed": failed}


def schedule_due(*, source_ids=None, user_ids=None, now=None, limit=100):
    """Claim due rows using short MySQL locks; old daily slots are never backfilled."""
    now = _date(now) or utcnow()
    queued_sources, queued_runs, failures = [], [], []
    with transaction() as session:
        query = select(Resource).where(
            Resource.kind == "source",
            Resource.due_at <= now,
            Resource.lease_until.is_(None) | (Resource.lease_until <= now),
        )
        if source_ids is not None:
            query = query.where(Resource.id.in_(source_ids))
        query = query.order_by(Resource.due_at, Resource.id).limit(limit).with_for_update(skip_locked=True)
        for row in session.scalars(query):
            data = source_state(row)
            if not data["enabled"] or data["health"] == "invalid":
                row.due_at = None
                continue
            if row.lease_until and row.lease_until > now:
                continue
            add_outbox(session, "source", row.id)
            row.data = {**data, "status": "syncing", "collectionStatus": "queued"}
            # A durable command survives restarts. Requeue after a minute if no
            # consumer takes it; the consumer lease and interval deduplicate it.
            row.due_at = now + timedelta(seconds=60)
            queued_sources.append(row.id)
    with transaction() as session:
        query = select(User).where(User.role == "anonymous", User.next_run_at <= now)
        if user_ids is not None:
            query = query.where(User.id.in_(user_ids))
        query = query.order_by(User.next_run_at, User.id).limit(limit).with_for_update(skip_locked=True)
        for user in session.scalars(query):
            if user.status != "active" or not user.onboarding:
                user.next_run_at = None
                continue
            slot = user.next_run_at
            if slot.replace(tzinfo=UTC).astimezone(CN).date() < now.replace(tzinfo=UTC).astimezone(CN).date():
                user.next_run_at = next_slot(user.delivery_time, now)
                continue
            business_key = f"daily:{user.id}:{iso(slot)}"
            try:
                # User remains locked while quota, run and outbox are created.
                run = create_run(session, user, business_key)
            except AppError as exc:
                failures.append({"user_id": user.id, "code": exc.code})
                continue
            user.next_run_at = next_slot(user.delivery_time, now)
            queued_runs.append(run.id)
    return {"sources": queued_sources, "runs": queued_runs, "failures": failures}


def recover_runs(*, run_ids=None, evaluation_ids=None, now=None, limit=100):
    """Restore abandoned work without rerunning a model after a brief exists."""
    now = _date(now) or utcnow()
    queued = []
    with transaction() as session:
        query = select(Run).where(
            Run.status.in_(("queued", "running", "cancelling")),
            Run.cancel_requested.is_(True) | Run.lease_until.is_(None) | (Run.lease_until <= now),
        )
        if run_ids is not None:
            query = query.where(Run.id.in_(run_ids))
        for run in session.scalars(
            query.order_by(Run.created_at).limit(limit).with_for_update(skip_locked=True)
        ):
            if run.cancel_requested:
                cancel_run(run, now=now)
                continue
            if run.lease_until and run.lease_until > now:
                continue
            last_queued = _date(run.private.get("lastRecoveryQueuedAt"))
            if last_queued and last_queued > now - timedelta(seconds=60):
                continue
            brief = session.scalar(select(Brief).where(Brief.run_id == run.id))
            if brief:
                delivery = session.scalar(select(Delivery).where(Delivery.brief_id == brief.id))
                if not delivery or delivery.status != "pending" or brief.published:
                    continue
                kind, target = "delivery", delivery.id
            else:
                kind, target = "run", run.id
            pending = session.scalar(
                select(Outbox.id)
                .where(Outbox.kind == kind, Outbox.target_id == target, Outbox.sent_at.is_(None))
                .limit(1)
            )
            if not pending:
                add_outbox(session, kind, target)
                queued.append({"kind": kind, "id": target})
            run.private = {**run.private, "lastRecoveryQueuedAt": iso(now)}
    with transaction() as session:
        query = select(Resource).where(
            Resource.kind == "evaluation",
            Resource.data["status"].as_string().in_(("queued", "running")),
            Resource.lease_until.is_(None) | (Resource.lease_until <= now),
        )
        if evaluation_ids is not None:
            query = query.where(Resource.id.in_(evaluation_ids))
        for row in session.scalars(
            query.order_by(Resource.created_at).limit(limit).with_for_update(skip_locked=True)
        ):
            if row.data["status"] not in ("queued", "running") or row.lease_until and row.lease_until > now:
                continue
            last_queued = _date(row.private.get("lastRecoveryQueuedAt"))
            if last_queued and last_queued > now - timedelta(seconds=60):
                continue
            pending = session.scalar(
                select(Outbox.id)
                .where(Outbox.kind == "evaluation", Outbox.target_id == row.id, Outbox.sent_at.is_(None))
                .limit(1)
            )
            if not pending:
                add_outbox(session, "evaluation", row.id)
                queued.append({"kind": "evaluation", "id": row.id})
            row.private = {**row.private, "lastRecoveryQueuedAt": iso(now)}
    return queued


def _source_input(row):
    data = row.data
    state = deepcopy(row.private.get("state", {}))
    if state and any(
        (state.get("kind"), state.get("source_id", ""), state.get("url"))[i] != value
        for i, value in enumerate((data["kind"], data["sourceId"], data["url"]))
    ):
        state = {}
    configured = data["interval"]
    if configured == state.get("effective_interval_seconds"):
        configured = state["configured_interval_seconds"]
    state.update(
        {
            "id": row.id,
            "name": data["name"],
            "kind": data["kind"],
            "source_id": data["sourceId"],
            "url": data["url"],
            "configured_interval_seconds": configured,
            "enabled": source_state(row)["enabled"],
        }
    )
    return state


def migrate_news_indexes():
    """Offline upgrade preflight; finish before this worker consumes queued runs."""
    from .ingestion.upgrade import migrate_source_news

    storage = get_settings().data_dir
    lock_dir = storage / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with transaction() as session:
        sources = [
            _source_input(row) for row in session.scalars(select(Resource).where(Resource.kind == "source"))
        ]
    migrated = []
    for source in sources:
        if not SAFE_ID.fullmatch(source["id"]):
            raise ValueError("Invalid source ID")
        with FileLock(lock_dir / ("source-" + source["id"] + ".lock"), timeout=SOURCE_LEASE_SECONDS):
            if migrate_source_news(source, storage):
                migrated.append(source["id"])
    return {"migratedSources": migrated}


def _source_dto(old, state):
    return {
        **old,
        "id": state["id"],
        "name": state["name"],
        "kind": state["kind"],
        "sourceId": state.get("source_id", ""),
        "url": state["url"],
        "interval": state["effective_interval_seconds"],
        "status": state["status"] if old.get("enabled", old["status"] != "disabled") else "disabled",
        "enabled": old.get("enabled", old["status"] != "disabled"),
        "health": state["status"],
        "failureCount": state.get("failure_count", 0),
        "collectionStatus": "idle",
        "lastSuccess": state.get("last_success_at", ""),
        "nextFetch": state.get("next_fetch_at", ""),
        "lastChanged": state.get("last_changed_at", ""),
        "items": state["items"],
        "error": state["error"],
        "snapshotId": state["snapshot_id"],
        "snapshotFetchedAt": state["snapshot_fetched_at"],
        "lastFetchedAt": state["last_fetched_at"],
        "cacheAgeSeconds": state["cache_age_seconds"],
        "stale": state["stale"],
    }


def _check_source_lease(ident, token):
    with transaction() as session:
        row = session.scalar(
            select(Resource).where(Resource.id == ident, Resource.kind == "source").with_for_update()
        )
        if not row or row.lease_token != token:
            raise IngestionError("LEASE_LOST", "Source collection lease no longer belongs to this worker")
        if row.private.get("stop_requested"):
            raise IngestionError("SOURCE_STOPPED", "Source collection was stopped by an administrator")
        row.lease_until = utcnow() + timedelta(seconds=SOURCE_LEASE_SECONDS)


class _SourceHeartbeat:
    def __init__(self, ident, token):
        self.ident, self.token = ident, token
        self.stop = Event()
        self.thread = Thread(target=self._renew, name="source-lease-" + ident, daemon=True)

    def _renew(self):
        while not self.stop.wait(30):
            try:
                _check_source_lease(self.ident, self.token)
            except Exception:
                logger.warning("Source lease renewal stopped for %s", self.ident)
                return

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)


def collect_source(source_id, *, collector=None):
    settings = get_settings()
    lock_dir = settings.data_dir / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    # The DB source ID is opaque, but reject separators before any path operation.
    from .ingestion.service import SAFE_ID

    if not SAFE_ID.fullmatch(source_id):
        raise ValueError("Invalid source ID")
    lock = FileLock(lock_dir / ("source-" + source_id + ".lock"), timeout=0)
    try:
        lock.acquire()
    except Timeout:
        return {"status": "busy", "retry_after": 30}
    token = None
    try:
        with transaction() as session:
            row = session.scalar(
                select(Resource).where(Resource.id == source_id, Resource.kind == "source").with_for_update()
            )
            if not row:
                return {"status": "missing"}
            data = source_state(row)
            if row.private.get("stop_requested") or row.private.get("delete_pending") or pending_deletion(session, source_id):
                return {"status": "stopped"}
            manual = row.private.get("manual_request", False)
            if not manual and not data["enabled"]:
                return {"status": "disabled"}
            if not manual and data["health"] == "invalid":
                row.due_at = None
                return {"status": "invalid"}
            now = utcnow()
            if row.lease_until and row.lease_until > now:
                return {"status": "busy", "retry_after": max(1, int((row.lease_until - now).total_seconds()))}
            source = _source_input(row)
            if manual:
                source["enabled"] = True
                source["status"] = data["health"]
            last_fetch = _date(source.get("last_fetched_at"))
            interval = max(
                source.get("effective_interval_seconds", 0),
                source["configured_interval_seconds"],
            )
            earliest = last_fetch + timedelta(seconds=interval) if last_fetch else None
            scheduled = _date(source.get("next_fetch_at"))
            if scheduled and earliest:
                earliest = max(earliest, scheduled)
            if not (manual and data["health"] == "invalid") and earliest and earliest > now:
                row.private = {**row.private, "manual_request": False}
                row.due_at = max(earliest, row.due_at or earliest)
                row.data = {
                    **row.data,
                    "status": source.get("status", "healthy"),
                    "collectionStatus": "idle",
                    "nextFetch": iso(row.due_at),
                }
                return {"status": "deferred", "next_fetch_at": iso(row.due_at)}
            token = uid()
            row.lease_token = token
            row.lease_until = now + timedelta(seconds=SOURCE_LEASE_SECONDS)
            row.private = {**row.private, "manual_request": False}
            row.data = {**data, "status": "syncing", "collectionStatus": "running"}
        with _SourceHeartbeat(source_id, token):
            result = (collector or fetch_source)(
                source,
                settings.data_dir,
                before_publish=lambda: _check_source_lease(source_id, token),
            )
        with transaction() as session:
            row = session.scalar(
                select(Resource).where(Resource.id == source_id, Resource.kind == "source").with_for_update()
            )
            if not row or row.lease_token != token:
                return {"status": "superseded"}
            if row.private.get("stop_requested"):
                row.lease_token = row.lease_until = None
                row.due_at = None
                return {"status": "stopped"}
            dto = _source_dto(source_state(row), result["source"])
            if not dto["enabled"]:
                dto["nextFetch"] = ""
            validate(schema("Source"), dto, output=True)
            snapshot = result["snapshot"]
            if snapshot and session.get(Resource, snapshot["snapshot_id"]) is None:
                session.add(
                    Resource(
                        id=snapshot["snapshot_id"],
                        kind="snapshot",
                        data=snapshot,
                        private={"items": result["items"]},
                    )
                )
            attempt = result["attempt"]
            session.add(Resource(id="fetch_" + attempt["id"], kind="source_fetch", data=attempt))
            row.data = dto
            row.private = {**row.private, "state": result["source"], "last_attempt": attempt}
            row.due_at = _date(dto["nextFetch"])
            row.lease_until = row.lease_token = None
        return {"status": dto["status"], "source_id": source_id, "snapshot_id": dto["snapshotId"]}
    except Exception as exc:
        stopped = isinstance(exc, IngestionError) and exc.code == "SOURCE_STOPPED"
        if token:
            with transaction() as session:
                row = session.scalar(select(Resource).where(Resource.id == source_id).with_for_update())
                if row and row.lease_token == token:
                    if row.private.get("stop_requested"):
                        stopped = True
                        row.due_at = None
                    elif source_state(row)["enabled"]:
                        retry_at = utcnow() + timedelta(seconds=row.data["interval"])
                        row.data = {
                            **row.data,
                            "status": "failed",
                            "health": "failed",
                            "collectionStatus": "idle",
                            "error": "采集工作进程失败，请查看服务日志",
                            "stale": True,
                            "nextFetch": iso(retry_at),
                        }
                        row.due_at = retry_at
                    else:
                        row.data = {**row.data, "status": "disabled", "collectionStatus": "idle"}
                        row.due_at = None
                    row.lease_until = row.lease_token = None
        if stopped:
            return {"status": "stopped"}
        raise
    finally:
        lock.release()


def _publication_event(session, run, title, detail, status):
    seq = (session.scalar(select(func.max(RunEvent.seq)).where(RunEvent.run_id == run.id)) or 0) + 1
    session.add(
        RunEvent(
            run_id=run.id,
            seq=seq,
            data={
                "id": seq,
                "time": iso(utcnow()),
                "title": title,
                "detail": detail,
                "status": status,
                "duration": "",
            },
        )
    )


def _publish_in_app(session, delivery, brief, run):
    data = {**brief.data, "deliveryStatus": "submitted"}
    brief.data = data
    validate(schema("Brief"), public_brief(brief), output=True)
    if data["generationStatus"] not in ("completed", "partial"):
        raise AppError("BRIEF_NOT_READY", "简报内容尚未完成", 409)
    brief.published = True
    delivery.status, delivery.error = "submitted", ""
    run.status = data["generationStatus"]
    run.percent, run.remaining_seconds, run.brief_id = 100, 0, brief.id
    run.error = ""
    run.updated_at = utcnow()
    run.private = {**run.private, "outputBriefId": brief.id}
    run.lease_until = run.lease_token = None
    _publication_event(session, run, "站内发布完成", "简报版本已发布，可在用户站内阅读。", "completed")


def publish_delivery(delivery_id):
    with transaction() as session:
        initial = session.execute(
            select(Delivery.user_id, Delivery.brief_id).where(Delivery.id == delivery_id)
        ).first()
        if not initial:
            return {"status": "missing"}
        initial_brief = session.execute(select(Brief.run_id).where(Brief.id == initial.brief_id)).first()
        # Match Gateway/execution's User -> Run lock order to avoid a publication race
        # deadlocking with the final content transaction.
        user = session.scalar(select(User).where(User.id == initial.user_id).with_for_update())
        run = (
            session.scalar(select(Run).where(Run.id == initial_brief.run_id).with_for_update())
            if initial_brief
            else None
        )
        brief = session.scalar(select(Brief).where(Brief.id == initial.brief_id).with_for_update())
        delivery = session.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update())
        if delivery.status != "pending":
            return {"status": delivery.status, "attempts": delivery.attempts}
        delivery.attempts += 1
        delivery.updated_at = utcnow()
        if not user or user.status != "active" or run and run.cancel_requested:
            delivery.status, delivery.error = "disabled", "账号已停用或本次生成已取消，未发布简报"
            if brief:
                brief.data = {**brief.data, "deliveryStatus": "disabled"}
            if run:
                run.status = "cancelled" if run.cancel_requested else "failed"
                run.error, run.updated_at = delivery.error, utcnow()
                run.remaining_seconds = run.lease_token = run.lease_until = None
                _publication_event(session, run, "站内发布已停止", delivery.error, run.status)
            return {"status": delivery.status, "attempts": delivery.attempts}
        if not brief or not run or brief.user_id != delivery.user_id or run.user_id != delivery.user_id:
            delivery.status, delivery.error = "failed", "发布记录关联无效"
            return {"status": delivery.status, "attempts": delivery.attempts}
        try:
            _publish_in_app(session, delivery, brief, run)
        except AppError:
            # Application validation failures are durable and require an explicit retry.
            delivery.status, delivery.error = "failed", "简报发布校验失败，请检查记录后重试"
            brief.data = {**brief.data, "deliveryStatus": "failed"}
            run.status, run.error, run.updated_at = "failed", delivery.error, utcnow()
            _publication_event(session, run, "站内发布失败", delivery.error, "failed")
        return {"status": delivery.status, "attempts": delivery.attempts, "brief_id": delivery.brief_id}


@celery_app.task(name="zhigenews.tick")
def tick():
    from .source_deletions import recover_jobs

    recover_jobs()
    scheduled = schedule_due()
    recovered = recover_runs()
    return {"scheduled": scheduled, "recovered": recovered, "outbox": dispatch_outbox()}


@celery_app.task(
    bind=True,
    name="zhigenews.source",
    autoretry_for=(OperationalError, OSError),
    retry_backoff=True,
    max_retries=5,
)
def source_task(self, source_id):
    result = collect_source(source_id)
    if result["status"] == "busy":
        raise self.retry(countdown=result.get("retry_after", 30), max_retries=None)
    return result


@celery_app.task(
    bind=True, name="zhigenews.run", autoretry_for=(OperationalError,), retry_backoff=True, max_retries=5
)
def run_task(self, run_id):
    from .execution import execute_run

    result = execute_run(run_id)
    if isinstance(result, dict) and result.get("status") == "busy":
        raise self.retry(countdown=result.get("retry_after", 30), max_retries=None)
    return result


@celery_app.task(
    bind=True,
    name="zhigenews.evaluation",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=5,
)
def evaluation_task(self, evaluation_id):
    from .execution import execute_evaluation

    result = execute_evaluation(evaluation_id)
    if isinstance(result, dict) and result.get("status") == "busy":
        raise self.retry(countdown=result.get("retry_after", 30), max_retries=None)
    return result


@celery_app.task(
    name="zhigenews.delivery", autoretry_for=(OperationalError,), retry_backoff=True, max_retries=5
)
def delivery_task(delivery_id):
    return publish_delivery(delivery_id)


@celery_app.task(name="zhigenews.source_deletion")
def source_deletion_task(job_id):
    from .source_deletions import execute_job

    return execute_job(job_id)
