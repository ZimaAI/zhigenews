"""Deletion progress and concurrency through real MySQL and administrator HTTP."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

import pytest
from sqlalchemy import delete, select
from test_source_management import BASE, create_source

from zhigenews.db import Outbox, Resource, SourceDeletionJob, transaction, utcnow
from zhigenews.source_deletions import execute_job, recover_jobs
from zhigenews.sources import source_lock

pytestmark = pytest.mark.mysql


@pytest.fixture(autouse=True)
def deletion_sandbox(api_sandbox, tmp_path, monkeypatch):
    from zhigenews.settings import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)


def latest(admin):
    response = admin.get("/api/v1/admin/source-deletions/current")
    assert response.status_code == 200, response.text
    return response.json()["job"]


def start(admin, ids):
    response = admin.post(BASE + "/batch", json={"action": "delete", "ids": ids})
    assert response.status_code == 200, response.text
    return response.json()


def test_persisted_progress_does_not_block_same_admin_and_skips_busy(api_sandbox, tmp_path, monkeypatch):
    import shutil

    admin = api_sandbox.admin()
    sources = sorted(
        [create_source(api_sandbox, admin, api_sandbox.prefix + str(n)) for n in range(3)],
        key=lambda s: s["id"],
    )
    ids = [s["id"] for s in sources]
    for ident in ids:
        path = tmp_path / "rss" / ident
        path.mkdir(parents=True)
        (path / "snapshot.json").write_text("{}")
    entered, release = Event(), Event()
    original = shutil.rmtree

    def blocked(path, *args, **kwargs):
        if path.name == ids[1]:
            entered.set()
            assert release.wait(10)
        return original(path, *args, **kwargs)

    job = start(admin, ids)
    assert job["status"] == "queued" and job["processed"] == 0
    assert latest(admin)["id"] == job["id"]
    assert admin.put(BASE + "/" + ids[1] + "/enabled", json={"enabled": False}).status_code == 409
    assert admin.post(BASE + "/batch", json={"action": "delete", "ids": ids}).status_code == 409
    with monkeypatch.context() as patch, source_lock(ids[2]), ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(shutil, "rmtree", blocked)
        task = pool.submit(execute_job, job["id"])
        assert entered.wait(5)
        try:
            progress = pool.submit(latest, admin).result(timeout=3)
            assert progress["deleted"] == 1 and progress["processed"] == 1
            assert progress["items"][1]["status"] == "running"
            assert pool.submit(lambda: admin.get(BASE).status_code).result(timeout=3) == 200
        finally:
            release.set()
        assert task.result(timeout=5)["status"] == "completed"
    result = latest(admin)
    assert result["deleted"] == 2 and result["skipped"] == 1 and result["processed"] == 3
    assert result["items"][2]["code"] == "SOURCE_BUSY"
    assert not (tmp_path / "rss" / ids[0]).exists()
    assert (tmp_path / "rss" / ids[2]).exists()
    # Revisiting uses server state; a new batch is allowed only after termination.
    again = start(admin, [ids[2]])
    execute_job(again["id"])
    assert latest(admin)["deleted"] == 1


def test_failure_continues_and_worker_restart_resumes_without_repeating_completed(
    api_sandbox, tmp_path, monkeypatch
):
    import shutil

    admin = api_sandbox.admin()
    sources = sorted(
        [create_source(api_sandbox, admin, api_sandbox.prefix + str(n)) for n in range(3)],
        key=lambda s: s["id"],
    )
    ids = [s["id"] for s in sources]
    for ident in ids:
        (tmp_path / "rss" / ident).mkdir(parents=True)
    original = shutil.rmtree
    calls = []

    def interrupted(path, *args, **kwargs):
        calls.append(path.name)
        if path.name == ids[1]:
            raise SystemExit("Synthetic process termination")
        return original(path, *args, **kwargs)

    job = start(admin, ids)
    with monkeypatch.context() as patch:
        patch.setattr(shutil, "rmtree", interrupted)
        with pytest.raises(SystemExit):
            execute_job(job["id"])
    assert latest(admin)["deleted"] == 1
    with transaction() as session:
        row = session.get(SourceDeletionJob, job["id"])
        row.dispatched_at = utcnow() - timedelta(minutes=2)
        session.execute(delete(Outbox).where(Outbox.target_id == job["id"]))
    recover_jobs()
    with transaction() as session:
        assert session.scalar(select(Outbox).where(Outbox.target_id == job["id"]))

    def failed(path, *args, **kwargs):
        calls.append(path.name)
        if path.name == ids[1]:
            raise PermissionError("Synthetic filesystem failure")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "rmtree", failed)
        execute_job(job["id"])
        execute_job(job["id"])  # Redelivery of the terminal job is harmless.
    result = latest(admin)
    assert result["deleted"] == 2 and result["failed"] == 1
    assert calls.count(ids[0]) == 1
    assert result["items"][1]["code"] == "CLEANUP_FAILED"


def test_global_uniqueness_across_admins_and_non_target_mutation(api_sandbox):
    from conftest import ApiSandbox

    admin = api_sandbox.admin()
    other_sandbox = ApiSandbox(api_sandbox.app)
    try:
        other = other_sandbox.admin()
        source = create_source(api_sandbox, admin, api_sandbox.prefix)
        untouched = create_source(api_sandbox, admin, api_sandbox.prefix + " other")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(client.post, BASE + "/batch", json={"action": "delete", "ids": [source["id"]]})
                for client in (admin, other)
            ]
            responses = [future.result(timeout=5) for future in futures]
        assert sorted(r.status_code for r in responses) == [200, 409]
        assert latest(admin)["id"] == latest(other)["id"]
        assert (
            other.put(BASE + "/" + untouched["id"] + "/enabled", json={"enabled": False}).status_code == 200
        )
        execute_job(latest(admin)["id"])
    finally:
        other_sandbox.cleanup()


def test_edit_version_conflict_preserves_newer_configuration(api_sandbox):
    admin = api_sandbox.admin()
    source = create_source(api_sandbox, admin, api_sandbox.prefix)
    fields = {k: source[k] for k in ("name", "kind", "sourceId", "url", "interval", "version")}
    first = admin.put(BASE + "/" + source["id"], json={**fields, "name": "New configuration"})
    assert first.status_code == 200, first.text
    stale = admin.put(BASE + "/" + source["id"], json={**fields, "name": "Old draft"})
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert admin.get(BASE + "/" + source["id"]).json()["name"] == "New configuration"


def test_invalid_candidates_are_fixed_and_recovered_sources_are_skipped(api_sandbox):
    import os

    from zhigenews.db import engine

    if engine().url.database != os.environ.get("ZHIGENEWS_DISPOSABLE_SOURCE_DB"):
        pytest.skip("Global deletion only in an explicitly disposable database")
    admin = api_sandbox.admin()
    candidates = [create_source(api_sandbox, admin, api_sandbox.prefix + str(n)) for n in range(2)]
    with transaction() as session:
        for source in candidates:
            row = session.get(Resource, source["id"])
            row.private = {"state": {"failure_count": 3}}
    response = admin.delete(BASE + "/invalid")
    assert response.status_code == 202
    job = response.json()
    newcomer = create_source(api_sandbox, admin, api_sandbox.prefix + " newly invalid")
    with transaction() as session:
        recovered = session.get(Resource, candidates[0]["id"])
        recovered.private = {"state": {"failure_count": 0}}
        recovered.data = {**recovered.data, "health": "healthy"}
        session.get(Resource, newcomer["id"]).private = {"state": {"failure_count": 3}}
    execute_job(job["id"])
    result = latest(admin)
    assert result["total"] == 2 and result["deleted"] == 1 and result["skipped"] == 1
    assert any(item["code"] == "SOURCE_RECOVERED" for item in result["items"])
    assert admin.get(BASE + "/" + newcomer["id"]).status_code == 200


def test_terminal_job_failure_releases_global_slot(api_sandbox, monkeypatch):
    from zhigenews import source_deletions

    admin = api_sandbox.admin()
    source = create_source(api_sandbox, admin, api_sandbox.prefix)
    other = create_source(api_sandbox, admin, api_sandbox.prefix + " other")
    job = start(admin, [source["id"], other["id"]])
    with monkeypatch.context() as patch:

        def fail(*args, **kwargs):
            raise RuntimeError("Synthetic worker failure")

        patch.setattr(source_deletions, "batch_sources", fail)
        assert execute_job(job["id"])["status"] == "failed"
    result = latest(admin)
    assert result["status"] == "failed" and result["items"][0]["code"] == "JOB_FAILED"
    assert result["processed"] == 1 and result["items"][1]["status"] == "unprocessed"
    retry = start(admin, [source["id"], other["id"]])
    assert execute_job(retry["id"])["status"] == "completed"
