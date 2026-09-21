"""Source health and administrative state, including legacy document projection."""

import shutil
from contextlib import nullcontext

from filelock import FileLock, Timeout
from sqlalchemy import delete, select

from .db import Outbox, Resource, SourceDeletionItem, SourceDeletionJob, iso, utcnow
from .errors import AppError
from .ingestion.service import SAFE_ID
from .settings import get_settings


def source_lock(ident):
    if not SAFE_ID.fullmatch(ident):
        raise AppError("INVALID_SOURCE", "来源标识无效")
    directory = get_settings().data_dir / "locks"
    directory.mkdir(parents=True, exist_ok=True)
    return FileLock(directory / ("source-" + ident + ".lock"), timeout=0)


def is_collecting(ident):
    try:
        with source_lock(ident):
            return False
    except Timeout:
        return True


def source_state(row):
    data = {key: value for key, value in row.data.items() if key not in ("upstreamInterval", "upstreamRevision")}
    state = row.private.get("state", {})
    failures = int(state.get("failure_count", 0))
    enabled = data.get("enabled", data["status"] != "disabled")
    health = "invalid" if failures >= 3 else data.get("health", state.get("status", data["status"]))
    if health not in ("healthy", "failed", "invalid", "unverified"):
        health = "healthy" if data.get("snapshotId") else "unverified"
    collection = data.get("collectionStatus", "queued" if data["status"] == "syncing" else "idle")
    if "collectionStatus" not in data and collection == "queued" and health == "invalid":
        # Legacy automatic commands are no longer eligible; keep manual recovery available.
        collection = "running" if is_collecting(row.id) else "idle"
    if row.private.get("stop_requested"):
        collection = "stopping" if is_collecting(row.id) else "stopped"
    status = (
        "syncing"
        if collection in ("queued", "running")
        else "stopping"
        if collection == "stopping"
        else health
        if enabled
        else "disabled"
    )
    return {
        **data,
        "enabled": enabled,
        "health": health,
        "failureCount": failures,
        "collectionStatus": collection,
        "status": status,
        "nextFetch": data.get("nextFetch", "") if enabled and health != "invalid" else "",
    }


def set_enabled(row, enabled, now):
    data = source_state(row)
    if enabled and (data["collectionStatus"] == "stopping" or row.private.get("delete_pending")):
        raise AppError("SOURCE_BUSY", "请先等待采集停止或完成删除清理", 409)
    if enabled:
        row.private = {**row.private, "stop_requested": False}
        if data["collectionStatus"] == "stopped":
            data["collectionStatus"] = "idle"
    data["enabled"] = enabled
    if data["collectionStatus"] not in ("queued", "running", "stopping"):
        data["status"] = data["health"] if enabled else "disabled"
    row.due_at = now if enabled and data["health"] != "invalid" else None
    data["nextFetch"] = iso(row.due_at) or ""
    row.data = data


def stop_collection(row):
    set_enabled(row, False, utcnow())
    row.private = {**row.private, "stop_requested": True, "manual_request": False}
    row.data = {**row.data, "collectionStatus": "stopping"}
    row.due_at = None
    return source_state(row)


def pending_deletion(session, ident):
    return (
        session.scalar(
            select(SourceDeletionItem.source_id)
            .join(SourceDeletionJob)
            .where(
                SourceDeletionItem.source_id == ident,
                SourceDeletionItem.status.in_(("pending", "running")),
                SourceDeletionJob.active_slot == "sources",
            )
            .limit(1)
        )
        is not None
    )


def require_available(session, ident):
    if pending_deletion(session, ident):
        raise AppError("SOURCE_BUSY", "来源正在等待或执行删除，请查看删除进度", 409)


def batch_sources(session, ids, action, *, invalid_only=False, lock_held=False):
    succeeded, failed = [], []
    for ident in sorted(set(ids)):
        try:
            # Never wait for a collector while holding a source database row.
            with source_lock(ident) if action == "delete" and not lock_held else nullcontext():
                row = session.scalar(
                    select(Resource)
                    .where(Resource.kind == "source", Resource.id == ident)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if not row:
                    raise AppError("NOT_FOUND", "来源已不存在", 404)
                data = source_state(row)
                if invalid_only and data["health"] != "invalid":
                    raise AppError("SOURCE_RECOVERED", "来源已恢复，不再属于失效来源", 409)
                if action == "disable":
                    require_available(session, ident)
                    set_enabled(row, False, utcnow())
                else:
                    # Holding the shared file lock proves no collector can still write.
                    set_enabled(row, False, utcnow())
                    row.private = {**row.private, "delete_pending": True, "manual_request": False}
                    storage = get_settings().data_dir.resolve()
                    target = (storage / "rss" / ident).resolve()
                    if not target.is_relative_to(storage / "rss") or target == storage / "rss":
                        raise AppError("INVALID_SOURCE", "来源存储路径无效")
                    if target.exists():
                        shutil.rmtree(target)
                    session.execute(
                        delete(Resource).where(
                            Resource.kind.in_(("snapshot", "source_fetch")),
                            Resource.data["source_id"].as_string() == ident,
                        )
                    )
                    session.execute(delete(Outbox).where(Outbox.kind == "source", Outbox.target_id == ident))
                    session.delete(row)
                    session.flush()
                succeeded.append(ident)
        except Timeout:
            failed.append(dict(id=ident, code="SOURCE_BUSY", message="来源仍在采集或停止中，请先停止采集"))
        except AppError as exc:
            failed.append(dict(id=ident, code=exc.code, message=exc.message))
        except OSError:
            failed.append(
                dict(id=ident, code="CLEANUP_FAILED", message="采集文件清理未完成，来源已停用，请重试删除")
            )
    return dict(succeeded=succeeded, failed=failed)
