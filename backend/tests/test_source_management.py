"""Source management through the administrator HTTP boundary."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, timedelta
from threading import Event

import httpx
import pytest
from sqlalchemy import select

from zhigenews import workers
from zhigenews.db import Resource, transaction, utcnow
from zhigenews.ingestion import fetch_source

pytestmark = pytest.mark.mysql
BASE = "/api/v1/admin/sources"


def complete_deletion(admin, ids=None):
    """Accept the asynchronous command, then exercise the real worker boundary."""
    from zhigenews.source_deletions import execute_job

    response = admin.delete(BASE + "/invalid") if ids is None else admin.post(
        BASE + "/batch", json={"action": "delete", "ids": ids}
    )
    assert response.status_code == (202 if ids is None else 200), response.text
    job = response.json()
    assert job["status"] == "queued"
    execute_job(job["id"])
    result = admin.get("/api/v1/admin/source-deletions/current").json()["job"]
    assert result["id"] == job["id"] and result["status"] == "completed"
    return {"succeeded": [item["id"] for item in result["items"] if item["status"] == "deleted"],
            "failed": [item for item in result["items"] if item["status"] in ("skipped", "failed")]}


@pytest.fixture(autouse=True)
def cleanup_collection_records(api_sandbox):
    yield
    with transaction() as session:
        for row in session.scalars(select(Resource).where(Resource.kind.in_(("snapshot", "source_fetch")))):
            if row.data.get("source_id") in api_sandbox.resources:
                api_sandbox.resource(row.id)


def create_source(sandbox, admin, name, **changes):
    body = dict(name=name, kind="rss", sourceId="", url="https://fixture.invalid/feed", interval=600)
    response = admin.post(BASE, json={**body, **changes})
    assert response.status_code == 201, response.text
    source = response.json()
    sandbox.resource(source["id"])
    return source


def test_name_search_covers_all_sources_and_pages_by_ten(api_sandbox):
    admin = api_sandbox.admin()
    name = api_sandbox.prefix + " 科技"
    sources = [create_source(api_sandbox, admin, f"{name} {i}") for i in range(25)]
    create_source(api_sandbox, admin, "Unrelated", sourceId=name, url="https://fixture.invalid/" + name)
    pages = [admin.get(BASE, params={"q": name, "page": n}).json() for n in (1, 2, 3)]
    assert [len(page["items"]) for page in pages] == [10, 10, 5]
    assert pages[0]["total"] == 25 and pages[0]["pageSize"] == 10
    assert pages[2]["page"] == 3 and pages[2]["totalPages"] == 3
    assert {item["id"] for page in pages for item in page["items"]} == {s["id"] for s in sources}
    assert admin.get(BASE, params={"q": name, "kind": "newsnow"}).json()["total"] == 0
    assert admin.get(BASE, params={"page": 0}).status_code == 400


def test_invalid_source_stops_automatic_collection_and_recovers_manually(api_sandbox, tmp_path, monkeypatch):
    from zhigenews.settings import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    admin = api_sandbox.admin()
    source = create_source(api_sandbox, admin, api_sandbox.prefix)
    clock = utcnow()
    monkeypatch.setattr(workers, "utcnow", lambda: clock)

    def failing(source, storage, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
            return fetch_source(
                source, storage, client=client, now=clock.replace(tzinfo=UTC), jitter_ratio=0, **kwargs
            )

    for minutes in (0, 10, 20):
        clock += timedelta(minutes=minutes)
        workers.collect_source(source["id"], collector=failing)
    result = admin.get(BASE + "/" + source["id"]).json()
    assert result["health"] == "invalid" and result["nextFetch"] == ""
    clock += timedelta(days=1)
    assert workers.schedule_due(source_ids=[source["id"]], user_ids=[], now=clock)["sources"] == []
    assert workers.collect_source(source["id"], collector=failing)["status"] == "invalid"
    disabled = admin.put(BASE + "/" + source["id"] + "/enabled", json={"enabled": False}).json()
    assert disabled["health"] == "invalid" and disabled["enabled"] is False
    assert (
        admin.post(
            BASE + "/" + source["id"] + "/fetch", headers={"Idempotency-Key": "manual-restore"}
        ).status_code
        == 202
    )
    from test_workers import collector

    assert workers.collect_source(source["id"], collector=collector)["status"] == "disabled"
    restored = admin.get(BASE + "/" + source["id"]).json()
    assert restored["health"] == "healthy" and restored["enabled"] is False


def test_legacy_queued_invalid_source_can_recover_manually(api_sandbox, tmp_path, monkeypatch):
    from test_workers import collector

    from zhigenews.settings import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    admin = api_sandbox.admin()
    source = create_source(api_sandbox, admin, api_sandbox.prefix)
    with transaction() as session:
        row = session.get(Resource, source["id"])
        row.data = {
            key: value
            for key, value in row.data.items()
            if key not in ("health", "enabled", "collectionStatus")
        }
        row.data = {**row.data, "status": "syncing"}
        row.private = {"state": {"failure_count": 3, "status": "failed"}}
    assert workers.collect_source(source["id"], collector=collector)["status"] == "invalid"
    state = admin.get(BASE + "/" + source["id"]).json()
    assert state["health"] == "invalid" and state["collectionStatus"] == "idle"
    queued = admin.post(
        BASE + "/" + source["id"] + "/fetch", headers={"Idempotency-Key": "legacy-manual-restore"}
    )
    assert queued.status_code == 202, queued.text
    assert workers.collect_source(source["id"], collector=collector)["status"] == "healthy"


def test_stop_must_finish_before_batch_delete_and_queued_work_cannot_recreate(
    api_sandbox, tmp_path, monkeypatch
):
    from test_workers import collector

    from zhigenews.settings import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    admin = api_sandbox.admin()
    source = create_source(api_sandbox, admin, api_sandbox.prefix)
    entered, release = Event(), Event()

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(15)
        return collector(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(workers.collect_source, source["id"], collector=blocked)
        assert entered.wait(5)
        try:
            with transaction() as session:
                row = session.get(Resource, source["id"])
                row.lease_until = utcnow() - timedelta(minutes=1)
            stopped = admin.post(BASE + "/" + source["id"] + "/stop")
            assert stopped.status_code == 200, stopped.text
            assert stopped.json()["collectionStatus"] == "stopping"
            denied = complete_deletion(admin, [source["id"]])
            assert denied["succeeded"] == []
            assert denied["failed"][0]["code"] == "SOURCE_BUSY"
        finally:
            release.set()
        assert task.result(timeout=10)["status"] == "stopped"
    state = admin.get(BASE + "/" + source["id"]).json()
    assert state["collectionStatus"] == "stopped" and state["enabled"] is False
    assert state["failureCount"] == 0
    assert complete_deletion(admin, [source["id"]])["succeeded"] == [source["id"]]
    assert admin.get(BASE + "/" + source["id"]).status_code == 404
    assert workers.collect_source(source["id"], collector=collector)["status"] == "missing"
    assert not (tmp_path / "rss" / source["id"]).exists()


def test_global_invalid_delete_includes_disabled_and_cleans_history(api_sandbox, tmp_path, monkeypatch):
    import os

    from zhigenews.db import engine

    if (
        not os.environ.get("ZHIGENEWS_DISPOSABLE_SOURCE_DB")
        or engine().url.database != os.environ["ZHIGENEWS_DISPOSABLE_SOURCE_DB"]
    ):
        pytest.skip("Global deletion requires the explicitly disposable database test runner")
    from test_workers import collector, pending_brief

    from zhigenews.db import Brief
    from zhigenews.settings import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    admin = api_sandbox.admin()
    bad = create_source(api_sandbox, admin, api_sandbox.prefix + " outside search")
    disabled = create_source(api_sandbox, admin, api_sandbox.prefix + " disabled")
    healthy = create_source(api_sandbox, admin, api_sandbox.prefix + " healthy")
    result = workers.collect_source(bad["id"], collector=collector)
    snapshot = result["snapshot_id"]
    # Another historical configuration must be cleaned too, even after a kind change.
    historical = tmp_path / "newsnow" / bad["id"] / "configs" / "old"
    historical.mkdir(parents=True)
    (historical / "old.json").write_text("{}")
    _, _, brief_id, _ = pending_brief(api_sandbox, published=True)
    # Legacy disabled records have no separate health field; only persisted failure count.
    with transaction() as session:
        for source, status in [(bad, "failed"), (disabled, "disabled")]:
            row = session.get(Resource, source["id"])
            row.data = {**row.data, "status": status}
            row.data.pop("health", None)
            row.data.pop("enabled", None)
            row.private = {**row.private, "state": {**row.private.get("state", {}), "failure_count": 3}}
    listing = admin.get(BASE, params={"q": healthy["name"]}).json()
    assert listing["total"] == 1 and listing["invalidTotal"] == 2
    result = complete_deletion(admin)
    assert set(result["succeeded"]) == {bad["id"], disabled["id"]}
    assert result["failed"] == []
    assert admin.get(BASE + "/" + healthy["id"]).status_code == 200
    assert admin.get(BASE + "/" + bad["id"]).status_code == 404
    assert not (tmp_path / "rss" / bad["id"]).exists()
    assert not (tmp_path / "newsnow" / bad["id"]).exists()
    with transaction() as session:
        assert session.get(Resource, snapshot) is None
        assert session.get(Brief, brief_id) is not None


def test_batch_disable_and_cleanup_failure_can_be_retried(api_sandbox, tmp_path, monkeypatch):
    import shutil

    from zhigenews.settings import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    admin = api_sandbox.admin()
    sources = [create_source(api_sandbox, admin, api_sandbox.prefix + str(i)) for i in range(3)]
    ids = [sources[0]["id"], sources[2]["id"]]
    assert set(
        admin.post(BASE + "/batch", json={"action": "disable", "ids": ids}).json()["succeeded"]
    ) == set(ids)
    assert admin.get(BASE + "/" + sources[1]["id"]).json()["enabled"] is True
    assert admin.get(BASE + "/" + ids[0]).json()["enabled"] is False
    directory = tmp_path / "rss" / ids[0]
    directory.mkdir(parents=True)
    (directory / "fixture.json").write_text("{}")
    with monkeypatch.context() as patch:

        def denied(*args, **kwargs):
            raise PermissionError("Synthetic filesystem refusal")

        patch.setattr(shutil, "rmtree", denied)
        result = complete_deletion(admin, ids)
        assert result["succeeded"] == [ids[1]]
        assert result["failed"][0]["code"] == "CLEANUP_FAILED"
    assert admin.get(BASE + "/" + ids[0]).json()["enabled"] is False
    assert complete_deletion(admin, [ids[0]])["succeeded"] == [ids[0]]
    assert not directory.exists()
