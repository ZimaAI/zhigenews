"""Deterministic synthetic HTTP responses; live checks are recorded separately."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from zhigenews.ingestion import catalog_source, default_sources, fetch_source, load_snapshot_items

NOW = datetime(2026, 9, 18, 16, 0, tzinfo=UTC)
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Synthetic feed</title>
<link>https://example.test/</link><description>Test only</description><ttl>60</ttl>
<item><guid>one</guid><title>Synthetic item</title><link>https://example.test/article</link>
<description>Source summary</description><pubDate>Fri, 18 Sep 2026 12:00:00 GMT</pubDate></item>
<item><guid>two</guid><title>Unknown date</title><link>https://example.test/unknown</link></item>
</channel></rss>"""


def rss_source():
    return {
        "id": "source-rss",
        "kind": "rss",
        "name": "Synthetic",
        "url": "https://example.test/feed.xml",
        "configured_interval_seconds": 600,
    }


def test_two_failed_backoff_retries_invalidate_source_and_success_recovers(tmp_path):
    source = rss_source()
    for offset, expected in [(0, "failed"), (600, "failed"), (1800, "invalid")]:
        result = call(source, tmp_path, httpx.Response(503), now=NOW + timedelta(seconds=offset))
        source = result["source"]
        assert source["status"] == expected
    assert source["next_fetch_at"] == ""
    recovered = call(source, tmp_path, httpx.Response(200, content=RSS), now=NOW + timedelta(hours=2))
    assert recovered["source"]["status"] == "healthy"
    assert recovered["source"]["failure_count"] == 0


def call(source, tmp_path, response, **kwargs):
    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
        return fetch_source(
            source, tmp_path, client=client, now=kwargs.pop("now", NOW), jitter_ratio=0, **kwargs
        )


def test_pinned_catalog_units_redirects_and_distinct_intervals():
    assert catalog_source("weibo")["upstream_interval_seconds"] == 120
    assert catalog_source("github")["source_id"] == "github-trending-today"
    assert [s["upstream_interval_seconds"] for s in default_sources()[:2]] == [600, 3600]
    with pytest.raises(ValueError):
        catalog_source("invented-source")


def test_rss_snapshot_raw_metadata_dates_and_ttl(tmp_path):
    result = call(
        rss_source(),
        tmp_path,
        httpx.Response(
            200, content=RSS, headers={"etag": '"v1"', "last-modified": "Fri, 18 Sep 2026 12:00:00 GMT"}
        ),
    )
    source, manifest = result["source"], result["snapshot"]
    assert source["status"] == "healthy"
    assert source["effective_interval_seconds"] == 3600
    assert source["next_fetch_at"] == "2026-09-18T17:00:00Z"
    assert (tmp_path / manifest["raw_path"]).read_bytes() == RSS
    assert "/raw/2026/09/18/" in manifest["raw_path"]
    assert manifest["etag"] == '"v1"'
    assert result["items"][0]["published_at"] == "2026-09-18T12:00:00Z"
    assert result["items"][1]["published_at"] is None
    assert load_snapshot_items(manifest, tmp_path) == result["items"]
    assert all(item["snapshot_id"] == manifest["snapshot_id"] for item in result["items"])


def test_rss_conditional_304_and_same_body_preserve_snapshot_age(tmp_path):
    first = call(
        rss_source(),
        tmp_path,
        httpx.Response(
            200, content=RSS, headers={"etag": '"v1"', "last-modified": "Fri, 18 Sep 2026 12:00:00 GMT"}
        ),
    )

    def unchanged(request):
        assert request.headers["If-None-Match"] == '"v1"'
        assert request.headers["If-Modified-Since"] == "Fri, 18 Sep 2026 12:00:00 GMT"
        return httpx.Response(304)

    with httpx.Client(transport=httpx.MockTransport(unchanged)) as client:
        second = fetch_source(
            first["source"], tmp_path, client=client, now=NOW + timedelta(hours=1), jitter_ratio=0
        )
    assert second["attempt"]["outcome"] == "not_modified"
    assert second["snapshot"] == first["snapshot"]
    assert second["source"]["snapshot_fetched_at"] == first["source"]["snapshot_fetched_at"]
    assert second["source"]["cache_age_seconds"] == 3600
    assert second["source"]["last_success_at"] == first["source"]["last_success_at"]
    third = call(second["source"], tmp_path, httpx.Response(200, content=RSS), now=NOW + timedelta(hours=2))
    assert third["attempt"]["outcome"] == "unchanged"
    assert third["snapshot"] == first["snapshot"]
    assert len(list(tmp_path.rglob("*.xml"))) == 1


@pytest.mark.parametrize("raw", [b"<html><body>Access denied</body></html>", b"<rss><channel><item>"])
def test_bad_response_keeps_valid_snapshot(tmp_path, raw):
    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS, headers={"etag": '"good"'}))
    failed = call(
        first["source"],
        tmp_path,
        httpx.Response(200, content=raw, headers={"etag": '"bad"'}),
        now=NOW + timedelta(hours=1),
    )
    assert failed["source"]["status"] == "failed"
    assert failed["source"]["etag"] == '"good"'
    assert failed["snapshot"] == first["snapshot"]
    assert failed["items"] == first["items"]
    assert failed["source"]["last_success_at"] == first["source"]["last_success_at"]
    assert failed["source"]["stale"] is True


def test_no_snapshot_304_is_not_success(tmp_path):
    result = call(rss_source(), tmp_path, httpx.Response(304))
    assert result["attempt"]["error_type"] == "ORPHAN_304"
    assert result["snapshot"] is None
    assert result["source"]["cache_age_seconds"] is None


def test_recover_published_snapshot_after_worker_state_commit_interruption(tmp_path):
    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS, headers={"etag": '"v1"'}))
    recovered = call(rss_source(), tmp_path, httpx.Response(304), now=NOW + timedelta(hours=1))
    assert recovered["snapshot"] == first["snapshot"]
    assert recovered["source"]["last_success_at"] == first["source"]["last_success_at"]
    assert recovered["source"]["etag"] == '"v1"'
    assert recovered["source"]["effective_interval_seconds"] == 3600
    assert recovered["source"]["cache_age_seconds"] == 3600


def test_timeout_exponential_backoff_and_retry_after(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        first = fetch_source(rss_source(), tmp_path, client=client, now=NOW, jitter_ratio=0)
        second = fetch_source(first["source"], tmp_path, client=client, now=NOW, jitter_ratio=0)
    assert first["attempt"]["error_type"] == "TIMEOUT"
    assert first["source"]["next_fetch_at"] == "2026-09-18T16:10:00Z"
    assert second["source"]["next_fetch_at"] == "2026-09-18T16:20:00Z"
    limited = call(first["source"], tmp_path, httpx.Response(429, headers={"retry-after": "7200"}))
    assert limited["source"]["next_fetch_at"] == "2026-09-18T18:00:00Z"
    assert limited["attempt"]["http_status"] == 429
    dated = call(
        rss_source(), tmp_path, httpx.Response(503, headers={"retry-after": "Fri, 18 Sep 2026 19:00:00 GMT"})
    )
    assert dated["source"]["next_fetch_at"] == "2026-09-18T19:00:00Z"


def test_newsnow_upstream_interval_and_updated_time_is_not_news_time(tmp_path):
    from zhigenews.ingestion import read_source_index, source_news_directory

    source = {**default_sources()[1], "configured_interval_seconds": 1}
    payload = {
        "id": "solidot",
        "status": "cache",
        "updatedTime": 1789743600000,
        "items": [{"id": "one", "title": "Synthetic story", "url": "https://example.test/item"}],
    }
    first = call(source, tmp_path, httpx.Response(200, json=payload))
    assert first["source"]["effective_interval_seconds"] == 3600
    assert first["items"][0]["published_at"] is None
    assert read_source_index(source, tmp_path)["items"] == []
    assert source_news_directory({**source, "url": ""}, tmp_path) == source_news_directory(source, tmp_path)
    assert first["attempt"]["upstream_status"] == "cache"
    payload.update({"status": "success", "updatedTime": 1789747200000})
    second = call(first["source"], tmp_path, httpx.Response(200, json=payload), now=NOW + timedelta(hours=1))
    assert second["attempt"]["outcome"] == "unchanged"
    assert second["snapshot"] == first["snapshot"]
    assert second["source"]["cache_age_seconds"] == 3600


def test_snapshot_publication_failure_does_not_replace_latest(tmp_path, monkeypatch):
    from zhigenews.ingestion import read_latest_snapshot, service

    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS))
    original = service._atomic_write

    def fail_parsed(path, raw):
        if path.suffix == ".jsonl":
            raise OSError("synthetic disk failure")
        return original(path, raw)

    monkeypatch.setattr(service, "_atomic_write", fail_parsed)
    with pytest.raises(OSError, match="synthetic disk failure"):
        call(
            first["source"],
            tmp_path,
            httpx.Response(200, content=RSS.replace(b"Synthetic item", b"Changed item")),
        )
    latest = read_latest_snapshot(rss_source(), tmp_path)
    assert latest == first["snapshot"]


def test_new_snapshot_preserves_first_seen_and_previous_snapshot(tmp_path):
    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS))
    second = call(
        first["source"],
        tmp_path,
        httpx.Response(200, content=RSS.replace(b"Source summary", b"Updated summary")),
        now=NOW + timedelta(hours=2),
    )
    assert first["snapshot"]["snapshot_id"] != second["snapshot"]["snapshot_id"]
    assert first["items"][0]["first_seen_at"] == second["items"][0]["first_seen_at"]
    assert load_snapshot_items(first["snapshot"], tmp_path) == first["items"]


def test_response_size_limit_and_cache_header_delay(tmp_path):
    too_large = call(rss_source(), tmp_path, httpx.Response(200, content=RSS), max_response_bytes=10)
    assert too_large["attempt"]["error_type"] == "RESPONSE_TOO_LARGE"
    assert too_large["snapshot"] is None
    cached = call(
        rss_source(),
        tmp_path,
        httpx.Response(200, content=RSS, headers={"cache-control": "public, max-age=10800", "age": "60"}),
    )
    assert cached["source"]["next_fetch_at"] == "2026-09-18T18:59:00Z"


def test_source_ids_and_snapshot_paths_cannot_escape_storage(tmp_path):
    source = {**rss_source(), "id": "../escape"}
    with pytest.raises(ValueError, match="safe identifier"):
        call(source, tmp_path, httpx.Response(200, content=RSS))
    with pytest.raises(ValueError, match="outside source storage"):
        load_snapshot_items({"parsed_path": "../outside.jsonl"}, tmp_path)


def test_recoverable_xml_warning_keeps_parseable_items(tmp_path):
    malformed = RSS.replace(b"Synthetic item", b"Synthetic & item")
    result = call(rss_source(), tmp_path, httpx.Response(200, content=malformed))
    assert result["source"]["status"] == "healthy"
    assert result["attempt"]["parse_warning"] is not None
    assert len(result["items"]) == 2


def test_source_news_index_contains_only_published_news_in_24_hour_window(tmp_path):
    from zhigenews.ingestion import read_source_index, source_news_directory

    dates = {
        "recent": "Fri, 18 Sep 2026 12:00:00 GMT",
        "boundary": "Thu, 17 Sep 2026 16:00:00 GMT",
        "old": "Thu, 17 Sep 2026 15:59:59 GMT",
        "future": "Fri, 18 Sep 2026 16:00:01 GMT",
        "timezone": "Sat, 19 Sep 2026 00:00:00 +0800",
        "missing": None,
        "invalid": "not a publication time",
        "unqualified": "Fri, 18 Sep 2026 12:00:00",
    }
    items = "".join(
        f"<item><guid>{name}</guid><title>{name}</title><link>https://example.test/{name}</link>"
        + (f"<pubDate>{date}</pubDate>" if date else "") + "</item>"
        for name, date in dates.items()
    )
    feed = f'<rss version="2.0"><channel><title>Synthetic</title>{items}</channel></rss>'.encode()
    result = call(rss_source(), tmp_path, httpx.Response(200, content=feed))
    index = read_source_index(rss_source(), tmp_path)
    assert {entry["title"] for entry in index["items"]} == {"recent", "boundary", "timezone"}
    assert index["maintained_at"] == "2026-09-18T16:00:00Z"
    root = source_news_directory(rss_source(), tmp_path)
    for entry in index["items"]:
        lines = (root / entry["file"]).read_text(encoding="utf-8").splitlines()
        evidence = json.loads(lines[entry["line"] - 1])
        assert evidence["evidence_id"] == entry["evidence_id"]
        assert evidence["title"] == entry["title"]
    assert len(load_snapshot_items(result["snapshot"], tmp_path)) == 8


def test_source_index_retains_rotated_news_and_resolves_immutable_evidence(tmp_path):
    from zhigenews.ingestion import read_source_index, resolve_source_evidence

    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS))
    original = read_source_index(rss_source(), tmp_path)["items"][0]
    rotated = RSS.replace(b"<guid>one</guid>", b"<guid>next</guid>").replace(
        b"https://example.test/article", b"https://example.test/next"
    ).replace(b"Synthetic item", b"New story")
    second = call(first["source"], tmp_path, httpx.Response(200, content=rotated), now=NOW + timedelta(hours=1))
    entries = read_source_index(rss_source(), tmp_path)["items"]
    assert {entry["title"] for entry in entries} == {"Synthetic item", "New story"}
    assert resolve_source_evidence(rss_source(), tmp_path, original["evidence_id"]) == first["items"][0]
    third = call(second["source"], tmp_path, httpx.Response(200, content=RSS), now=NOW + timedelta(hours=2))
    entries = read_source_index(rss_source(), tmp_path)["items"]
    assert len(entries) == 2
    current = next(entry for entry in entries if entry["title"] == "Synthetic item")
    assert resolve_source_evidence(rss_source(), tmp_path, current["evidence_id"]) == third["items"][0]
    assert resolve_source_evidence(rss_source(), tmp_path, "invented") is None
    assert resolve_source_evidence(rss_source(), tmp_path, "../outside:missing") is None
    # Older references remain usable even after the live index advances.
    assert resolve_source_evidence(rss_source(), tmp_path, original["evidence_id"]) == first["items"][0]


def test_source_configuration_change_has_an_isolated_news_directory(tmp_path):
    from zhigenews.ingestion import read_source_index, resolve_source_evidence, source_news_directory

    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS, headers={"etag": '"first"'}))
    changed = {**first["source"], "url": "https://example.test/another-feed.xml"}
    assert source_news_directory(changed, tmp_path) != source_news_directory(rss_source(), tmp_path)
    assert read_source_index(changed, tmp_path) is None
    assert resolve_source_evidence(changed, tmp_path, first["items"][0]["evidence_id"]) is None

    def replacement(request):
        assert "If-None-Match" not in request.headers
        return httpx.Response(200, content=RSS.replace(b"Synthetic item", b"Replacement source"))

    with httpx.Client(transport=httpx.MockTransport(replacement)) as client:
        fetch_source(changed, tmp_path, client=client, now=NOW, jitter_ratio=0)
    assert [entry["title"] for entry in read_source_index(changed, tmp_path)["items"]] == ["Replacement source"]
    assert [entry["title"] for entry in read_source_index(rss_source(), tmp_path)["items"]] == ["Synthetic item"]


@pytest.mark.parametrize("response", [httpx.Response(304), httpx.Response(200, content=RSS), httpx.Response(503)])
def test_source_index_maintenance_requires_current_collection_lease(tmp_path, response):
    from zhigenews.ingestion import read_source_index
    from zhigenews.ingestion.service import IngestionError

    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS))
    index = read_source_index(rss_source(), tmp_path)

    def lease_lost():
        raise IngestionError("LEASE_LOST", "Synthetic lease replacement")

    result = call(
        first["source"], tmp_path, response,
        now=NOW + timedelta(hours=22), before_publish=lease_lost,
    )
    assert result["attempt"]["error_type"] == "LEASE_LOST"
    assert read_source_index(rss_source(), tmp_path) == index
    # The current owner still prunes expired entries on every attempt outcome.
    call(first["source"], tmp_path, response, now=NOW + timedelta(hours=22))
    maintained = read_source_index(rss_source(), tmp_path)
    assert maintained["items"] == []
    assert maintained["maintained_at"] == "2026-09-19T14:00:00Z"
    assert load_snapshot_items(first["snapshot"], tmp_path) == first["items"]


def test_index_publication_failure_keeps_previous_discovery_and_latest_snapshot(tmp_path, monkeypatch):
    import os
    from pathlib import Path

    from zhigenews.ingestion import read_latest_snapshot, read_source_index, resolve_source_evidence

    first = call(rss_source(), tmp_path, httpx.Response(200, content=RSS))
    index = read_source_index(rss_source(), tmp_path)
    replace = os.replace

    def unavailable_index(source, target):
        if Path(target).name == "index.json":
            raise OSError("Synthetic interrupted index publication")
        return replace(source, target)

    with monkeypatch.context() as patch:
        patch.setattr(os, "replace", unavailable_index)
        with pytest.raises(OSError, match="interrupted index publication"):
            call(
                first["source"], tmp_path,
                httpx.Response(200, content=RSS.replace(b"Synthetic item", b"Revised story")),
            )
    assert read_source_index(rss_source(), tmp_path) == index
    assert read_latest_snapshot(rss_source(), tmp_path) == first["snapshot"]
    assert resolve_source_evidence(rss_source(), tmp_path, index["items"][0]["evidence_id"]) == first["items"][0]
    recovered = call(
        first["source"], tmp_path,
        httpx.Response(200, content=RSS.replace(b"Synthetic item", b"Revised story")),
    )
    assert read_source_index(rss_source(), tmp_path)["items"][0]["title"] == "Revised story"
    assert read_latest_snapshot(rss_source(), tmp_path) == recovered["snapshot"]


@pytest.mark.parametrize("status", [200, 304, 503])
def test_source_index_window_uses_collection_completion_time(tmp_path, monkeypatch, status):
    from zhigenews.ingestion import read_source_index, service

    feed = RSS.replace(b"Fri, 18 Sep 2026 12:00:00 GMT", b"Thu, 17 Sep 2026 16:00:01 GMT")
    first = call(rss_source(), tmp_path, httpx.Response(200, content=feed))

    class Clock(datetime):
        current = NOW

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz)

    def slow_response(request):
        Clock.current = NOW + timedelta(seconds=2)
        return httpx.Response(status, content=feed.replace(b"Synthetic item", b"Changed item"))

    monkeypatch.setattr(service, "datetime", Clock)
    with httpx.Client(transport=httpx.MockTransport(slow_response)) as client:
        fetch_source(first["source"], tmp_path, client=client, jitter_ratio=0)
    index = read_source_index(rss_source(), tmp_path)
    assert index["maintained_at"] == "2026-09-18T16:00:02Z"
    assert index["items"] == []
