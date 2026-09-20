"""Durable source cleanup. File locks cover each source's database commit."""

import logging
from datetime import timedelta

from filelock import FileLock, Timeout
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from .db import Outbox, Resource, SourceDeletionItem, SourceDeletionJob, iso, transaction, uid, utcnow
from .errors import AppError
from .settings import get_settings
from .sources import batch_sources, source_lock, source_state

logger = logging.getLogger(__name__)
PENDING = ("pending", "running")


def job_view(session, job):
    if job is None:
        return None
    items = [
        dict(id=row.source_id, name=row.name, status=row.status, code=row.code, message=row.message)
        for row in session.scalars(
            select(SourceDeletionItem)
            .where(SourceDeletionItem.job_id == job.id)
            .order_by(SourceDeletionItem.source_id)
        )
    ]
    counts = {
        status: sum(item["status"] == status for item in items) for status in ("deleted", "skipped", "failed")
    }
    return dict(
        id=job.id,
        mode=job.mode,
        status=job.status,
        total=len(items),
        processed=sum(counts.values()),
        **counts,
        items=items,
        error=job.error,
        createdAt=iso(job.created_at),
        updatedAt=iso(job.updated_at),
    )


def current_job(session):
    job = session.scalar(
        select(SourceDeletionJob)
        .order_by(
            SourceDeletionJob.active_slot.desc(),
            SourceDeletionJob.created_at.desc(),
            SourceDeletionJob.id.desc(),
        )
        .limit(1)
    )
    return job_view(session, job)


def create_job(session, ids=None):
    job = SourceDeletionJob(
        id=uid("del_"), active_slot="sources", mode="invalid" if ids is None else "selected"
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError as exc:
        raise AppError("SOURCE_BUSY", "已有来源批量删除任务正在执行，请查看当前进度", 409) from exc
    query = select(Resource).where(Resource.kind == "source")
    if ids is not None:
        query = query.where(Resource.id.in_(ids))
    rows = list(session.scalars(query))
    names = {
        row.id: row.data["name"]
        for row in rows
        if ids is not None or source_state(row)["health"] == "invalid"
    }
    # Preserve missing selected IDs in the report rather than silently dropping them.
    if ids is not None:
        for ident in ids:
            names.setdefault(ident, ident)
    session.add_all(
        SourceDeletionItem(job_id=job.id, source_id=ident, name=name) for ident, name in names.items()
    )
    session.add(Outbox(id=uid("out_"), kind="source_deletion", target_id=job.id))
    session.flush()
    return job_view(session, job)


def _result(session, job_id, ident, status, code="", message=""):
    item = session.get(SourceDeletionItem, (job_id, ident))
    item.status, item.code, item.message = status, code, message
    session.get(SourceDeletionJob, job_id).updated_at = utcnow()


def execute_job(job_id):
    lock = None
    acquired = False
    try:
        directory = get_settings().data_dir / "locks"
        directory.mkdir(parents=True, exist_ok=True)
        # One worker owns cleanup even after duplicate delivery or recovery dispatch.
        lock = FileLock(directory / "source-deletion-worker.lock", timeout=0)
        try:
            lock.acquire()
        except Timeout:
            return {"status": "busy"}
        acquired = True
        with transaction() as session:
            job = session.get(SourceDeletionJob, job_id)
            if job is None or job.active_slot is None:
                return {"status": "finished"}
            job.status, job.updated_at = "running", utcnow()
            invalid_only = job.mode == "invalid"
            ids = list(
                session.scalars(
                    select(SourceDeletionItem.source_id)
                    .where(SourceDeletionItem.job_id == job_id, SourceDeletionItem.status.in_(PENDING))
                    .order_by(SourceDeletionItem.source_id)
                )
            )
        for ident in ids:
            with transaction() as session:
                _result(session, job_id, ident, "running")
            try:
                with source_lock(ident):
                    with transaction() as session:
                        result = batch_sources(
                            session, [ident], "delete", invalid_only=invalid_only, lock_held=True
                        )
                        if result["succeeded"]:
                            _result(session, job_id, ident, "deleted")
                        else:
                            failure = result["failed"][0]
                            status = (
                                "skipped"
                                if failure["code"] in ("SOURCE_BUSY", "SOURCE_RECOVERED", "NOT_FOUND")
                                else "failed"
                            )
                            _result(session, job_id, ident, status, failure["code"], failure["message"])
            except Timeout:
                with transaction() as session:
                    _result(session, job_id, ident, "skipped", "SOURCE_BUSY", "来源仍在采集，本轮已跳过")
            except AppError as exc:
                with transaction() as session:
                    _result(session, job_id, ident, "failed", exc.code, exc.message)
            except OSError:
                with transaction() as session:
                    _result(
                        session,
                        job_id,
                        ident,
                        "failed",
                        "CLEANUP_FAILED",
                        "来源锁或采集文件无法访问，请重试删除",
                    )
        with transaction() as session:
            job = session.get(SourceDeletionJob, job_id)
            job.status, job.active_slot, job.updated_at = "completed", None, utcnow()
        return {"status": "completed"}
    except OperationalError:
        # A DB outage cannot safely be recorded as completion. Beat redispatches
        # the persisted active job once the database is reachable again.
        raise
    except Exception:
        logger.exception("Source deletion job failed: %s", job_id)
        with transaction() as session:
            job = session.get(SourceDeletionJob, job_id)
            if job:
                job.status, job.active_slot, job.updated_at = "failed", None, utcnow()
                job.error = "删除任务无法继续，未处理项保留，请重新发起删除"
                for item in session.scalars(
                    select(SourceDeletionItem).where(
                        SourceDeletionItem.job_id == job_id, SourceDeletionItem.status.in_(PENDING)
                    )
                ):
                    was_running = item.status == "running"
                    item.status = "failed" if was_running else "unprocessed"
                    item.code = "JOB_FAILED"
                    item.message = "任务中断，清理未确认完成" if was_running else "任务已中断，本项尚未处理"
        return {"status": "failed"}
    finally:
        if acquired:
            lock.release()


def recover_jobs():
    """Periodic redispatch also covers a worker that died without acknowledging."""
    with transaction() as session:
        job = session.scalar(
            select(SourceDeletionJob)
            .where(
                SourceDeletionJob.active_slot == "sources",
                SourceDeletionJob.dispatched_at <= utcnow() - timedelta(seconds=60),
            )
            .with_for_update(skip_locked=True)
        )
        if job:
            pending = session.scalar(
                select(Outbox.id)
                .where(Outbox.kind == "source_deletion", Outbox.target_id == job.id, Outbox.sent_at.is_(None))
                .limit(1)
            )
            if not pending:
                session.add(Outbox(id=uid("out_"), kind="source_deletion", target_id=job.id))
            job.dispatched_at = utcnow()
