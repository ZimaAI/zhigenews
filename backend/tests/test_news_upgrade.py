"""Upgrade fixtures contain the real pre-index on-disk layout, without networking."""

import json
from datetime import timedelta

import httpx
import pytest
from test_ingestion import NOW, RSS, call, rss_source

from zhigenews.execution import source_access
from zhigenews.harness.files import FileService
from zhigenews.ingestion import service
from zhigenews.ingestion.upgrade import migrate_source_news


def legacy_news(tmp_path, monkeypatch, source=None):
    source = source or rss_source()
    with monkeypatch.context() as patch:
        patch.setattr(service, "_source_dir", lambda s, storage: storage / s["kind"] / s["id"])
        patch.setattr(service, "_maintain_source_index", lambda *args: None)
        result = call(source, tmp_path, httpx.Response(200, content=RSS, headers={"etag": '"v1"'}))
    return result


def test_upgraded_news_is_discoverable_before_next_collection(tmp_path, monkeypatch):
    result = legacy_news(tmp_path, monkeypatch)
    migrate_source_news(result["source"], tmp_path, now=NOW)
    roots, resolve = source_access([result["source"]], tmp_path)
    (tmp_path / "workspace").mkdir()
    files = FileService(tmp_path / "rss", tmp_path / "workspace", news_roots=roots)
    assert files.list_dir("/news")["entries"], "升级后 /news 新闻目录为空，旧新闻记录不可见"
    index = service.read_source_index(result["source"], tmp_path)
    assert index and len(index["items"]) == 1
    item = index["items"][0]
    assert resolve(item["evidence_id"]) == result["items"][0]


def test_upgraded_collection_keeps_previous_evidence_on_upstream_failure(tmp_path, monkeypatch):
    first = legacy_news(tmp_path, monkeypatch)
    failed = call(first["source"], tmp_path, httpx.Response(503), now=NOW + timedelta(hours=1))
    assert failed["snapshot"] is not None, "升级后的首次采集失败丢失了旧证据"
    assert failed["items"] == first["items"]
    assert service.read_source_index(first["source"], tmp_path)["items"]


def test_upgrade_preserves_files_and_is_idempotent(tmp_path, monkeypatch):
    first = legacy_news(tmp_path, monkeypatch)
    old = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert migrate_source_news(first["source"], tmp_path, now=NOW)
    after = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert all(p.read_bytes() == content for p, content in old.items())
    assert not migrate_source_news(first["source"], tmp_path, now=NOW + timedelta(hours=1))
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == after
    index = service.read_source_index(first["source"], tmp_path)
    root = service.source_news_directory(first["source"], tmp_path)
    record = json.loads((root / index["items"][0]["file"]).read_text("utf-8").splitlines()[0])
    assert record == first["items"][0]
    latest = service.read_latest_snapshot(first["source"], tmp_path)
    assert (tmp_path / latest["raw_path"]).read_bytes() == RSS


def test_upgrade_reuses_conditional_snapshot(tmp_path, monkeypatch):
    first = legacy_news(tmp_path, monkeypatch)

    def respond(request):
        assert request.headers["If-None-Match"] == '"v1"'
        return httpx.Response(304)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        second = service.fetch_source(first["source"], tmp_path, client=client, now=NOW)
    assert second["attempt"]["outcome"] == "not_modified"
    assert second["snapshot"]["snapshot_id"] == first["snapshot"]["snapshot_id"]


def test_upgrade_does_not_authorize_old_url(tmp_path, monkeypatch):
    first = legacy_news(tmp_path, monkeypatch)
    changed = {**first["source"], "url": "https://example.test/replaced.xml"}
    assert not migrate_source_news(changed, tmp_path, now=NOW)
    assert service.read_source_index(changed, tmp_path) is None
    assert service.resolve_source_evidence(changed, tmp_path, first["items"][0]["evidence_id"]) is None


def test_upgrade_keeps_newer_snapshot_and_rotated_news(tmp_path, monkeypatch):
    first = legacy_news(tmp_path, monkeypatch)
    # Simulate an upgraded collector that has already obtained a fresh feed.
    with monkeypatch.context() as patch:
        patch.setattr("zhigenews.ingestion.upgrade.migrate_source_news", lambda *a, **kw: False)
        newer = call(
            first["source"],
            tmp_path,
            httpx.Response(200, content=RSS.replace(b"Synthetic item", b"Updated item")),
            now=NOW + timedelta(minutes=1),
        )
        newest = call(
            newer["source"],
            tmp_path,
            httpx.Response(
                200, content=RSS.replace(b"one", b"three").replace(b"Synthetic item", b"Rotated item")
            ),
            now=NOW + timedelta(minutes=2),
        )
    index = service.read_source_index(first["source"], tmp_path)
    migrate_source_news(first["source"], tmp_path, now=NOW + timedelta(minutes=3))
    assert service.read_latest_snapshot(first["source"], tmp_path) == newest["snapshot"]
    assert service.read_source_index(first["source"], tmp_path)["items"] == index["items"]
    assert (
        service.resolve_source_evidence(first["source"], tmp_path, first["items"][0]["evidence_id"])
        == first["items"][0]
    )


def test_upgrade_can_retry_interrupted_publication(tmp_path, monkeypatch):
    first = legacy_news(tmp_path, monkeypatch)
    checks = 0

    def lose_lease():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise service.IngestionError("LEASE_LOST", "Synthetic interrupted migration")

    with pytest.raises(service.IngestionError, match="interrupted"):
        migrate_source_news(first["source"], tmp_path, now=NOW, before_publish=lose_lease)
    assert not (service.source_news_directory(first["source"], tmp_path) / "legacy-migrated.json").exists()
    assert migrate_source_news(first["source"], tmp_path, now=NOW)
    assert service.read_source_index(first["source"], tmp_path)["items"]
