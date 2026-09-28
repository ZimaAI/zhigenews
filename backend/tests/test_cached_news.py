"""Administrator browsing uses actual ingestion files without collecting new news."""

from datetime import UTC, timedelta
from html import escape

import httpx
import pytest
from sqlalchemy import func, select

from zhigenews import application
from zhigenews.db import Outbox, Resource, iso, transaction, utcnow
from zhigenews.ingestion import fetch_source, source_news_directory
from zhigenews.settings import get_settings

pytestmark = pytest.mark.mysql
BASE = "/api/v1/admin/news"


@pytest.fixture
def cache(api_sandbox, tmp_path_factory, monkeypatch):
    # Keep deeply nested ingestion paths below Windows' default path limit.
    storage = tmp_path_factory.mktemp("news")
    monkeypatch.setattr(get_settings(), "data_dir", storage)
    now = utcnow().replace(microsecond=0)
    monkeypatch.setattr(application, "utcnow", lambda: now)
    return api_sandbox.admin(), storage, now


def source(sandbox, admin, suffix):
    response = admin.post("/api/v1/admin/sources", json={
        "name": sandbox.prefix + " " + suffix, "kind": "rss", "sourceId": "",
        "url": "https://fixture.invalid/" + suffix, "interval": 600,
    })
    assert response.status_code == 201, response.text
    data = response.json()
    sandbox.resource(data["id"])
    return data


def collect(source, storage, now, entries):
    items = []
    for entry in entries:
        published = entry.get("published", now - timedelta(hours=1))
        date = f"<pubDate>{iso(published)}</pubDate>" if published else ""
        items.append(
            f"<item><guid>{entry['id']}</guid><title>{escape(entry['title'])}</title>"
            f"<link>https://fixture.invalid/articles/{entry['id']}</link>{date}"
            f"<description>{escape(entry.get('summary', ''))}</description>"
            f"<content:encoded>{escape(entry.get('content', ''))}</content:encoded></item>"
        )
    raw = ('<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
           '<channel><title>Synthetic news</title>' + "".join(items) + '</channel></rss>')
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, text=raw))) as client:
        result = fetch_source(source, storage, client=client, now=now.replace(tzinfo=UTC), jitter_ratio=0)
    assert result["source"]["status"] == "healthy"
    return result


def detail_path(source, item):
    return f"/api/v1/admin/sources/{source['id']}/news/{item['id']}"


def test_news_browsing_requires_administrator_session(api_sandbox):
    for client, expected in [(api_sandbox.client(), 401), (api_sandbox.anonymous(), 403)]:
        for path in [BASE, "/api/v1/admin/sources/missing/news/missing"]:
            assert client.get(path).status_code == expected


def test_news_pagination_title_search_source_filter_and_disabled_cache(api_sandbox, cache):
    admin, storage, now = cache
    first = source(api_sandbox, admin, "first")
    second = source(api_sandbox, admin, "second")
    empty = source(api_sandbox, admin, "empty")
    collect(first, storage, now, [
        {"id": f"item-{n}", "title": f"Synthetic Report {n}", "published": now - timedelta(minutes=n)}
        for n in range(24)
    ] + [{"id": "unknown", "title": "Unknown date", "published": None}])
    collect(second, storage, now, [{"id": "other", "title": "Other news"}])
    assert admin.put(f"/api/v1/admin/sources/{first['id']}/enabled", json={"enabled": False}).status_code == 200
    pages = [admin.get(BASE, params={"page": n}).json() for n in (1, 2)]
    assert [len(page["items"]) for page in pages] == [20, 5]
    assert pages[0]["total"] == 25 and pages[0]["pageSize"] == 20 and pages[0]["totalPages"] == 2
    all_items = [item for page in pages for item in page["items"]]
    assert len({(item["sourceId"], item["id"]) for item in all_items}) == 25
    assert [item["publishedAt"] for item in all_items] == sorted(
        [item["publishedAt"] for item in all_items], reverse=True
    )
    choices = {choice["id"]: choice for choice in pages[0]["sources"]}
    assert [choices[entry["id"]]["count"] for entry in (first, second, empty)] == [24, 1, 0]
    assert pages[0]["windowStart"] == iso(now - timedelta(hours=24))
    assert pages[0]["windowEnd"] == iso(now)
    selected = admin.get(BASE, params={"sourceId": first["id"], "q": " report 2 ", "page": 8}).json()
    assert selected["page"] == 1 and selected["total"] == 5
    assert {item["sourceId"] for item in selected["items"]} == {first["id"]}
    assert selected["sources"] == pages[0]["sources"]
    assert admin.get(BASE, params={"page": 100}).json()["page"] == 2
    assert admin.get(BASE, params={"sourceId": "missing"}).status_code == 404


def test_detail_resolves_retained_evidence_as_plain_text_without_writes(api_sandbox, cache):
    admin, storage, now = cache
    feed = source(api_sandbox, admin, "detail")
    first = collect(feed, storage, now - timedelta(minutes=10), [{
        "id": "old", "title": "Retained report", "summary": "<p>Source &amp; facts</p>",
        "content": "<p>First paragraph.</p><p>Second <strong>paragraph</strong>.</p>",
    }])
    old = first["items"][0]
    collect(first["source"], storage, now, [{"id": "new", "title": "Latest report"}])
    before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in storage.rglob("*") if path.is_file()}
    response = admin.get(detail_path(feed, old))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "Retained report" and data["sourceName"] == feed["name"]
    assert data["summary"] == "Source & facts"
    assert data["content"] == "First paragraph.\nSecond paragraph."
    assert data["sourceUrl"] == feed["url"] and data["url"] == old["url"]
    assert data["evidenceId"] == old["evidence_id"] and data["snapshotId"] == old["snapshot_id"]
    assert data["fetchedAt"] == old["fetched_at"] and data["firstSeenAt"] == old["first_seen_at"]
    assert not {"file", "line", "raw_path", "parsed_path", "manifest_path"}.intersection(data)
    assert admin.get(BASE, params={"sourceId": feed["id"]}).json()["total"] == 2
    assert before == {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in storage.rglob("*") if path.is_file()}
    with transaction() as session:
        assert session.scalar(select(func.count()).select_from(Outbox).where(Outbox.target_id == feed["id"])) == 0
        assert session.get(Resource, feed["id"]).data["snapshotId"] is None


def test_stale_indexes_expire_on_read_and_empty_sources_remain_available(api_sandbox, cache, monkeypatch):
    admin, storage, now = cache
    feed = source(api_sandbox, admin, "expiration")
    result = collect(feed, storage, now, [{"id": "expires", "title": "Expiring report"}])
    monkeypatch.setattr(application, "utcnow", lambda: now + timedelta(hours=24))
    response = admin.get(BASE, params={"sourceId": feed["id"], "page": 3})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["items"] == [] and data["total"] == 0 and data["totalPages"] == 0 and data["page"] == 1
    assert next(choice for choice in data["sources"] if choice["id"] == feed["id"])["count"] == 0
    assert admin.get(detail_path(feed, result["items"][0])).status_code == 404


def test_missing_cache_and_evidence_and_corrupt_index_have_distinct_results(api_sandbox, cache):
    admin, storage, now = cache
    feed = source(api_sandbox, admin, "missing")
    assert admin.get(BASE, params={"sourceId": feed["id"]}).json()["items"] == []
    assert admin.get(detail_path(feed, {"id": "missing"})).status_code == 404
    result = collect(feed, storage, now, [{"id": "one", "title": "Synthetic report"}])
    item = result["items"][0]
    other = source(api_sandbox, admin, "other")
    assert admin.get(detail_path(other, item)).status_code == 404
    (storage / result["snapshot"]["parsed_path"]).unlink()
    assert admin.get(detail_path(feed, item)).status_code == 404
    (source_news_directory(feed, storage) / "index.json").write_text("{invalid json", encoding="utf-8")
    response = admin.get(BASE)
    assert response.status_code == 503 and response.json()["code"] == "DEPENDENCY_UNAVAILABLE"
    assert admin.get(detail_path(feed, item)).status_code == 503


@pytest.mark.parametrize("params", [{"page": 0}, {"page": "no"}, {"q": "a" * 201}])
def test_news_parameters_are_validated(cache, params):
    admin, _, _ = cache
    response = admin.get(BASE, params=params)
    assert response.status_code == 400 and response.json()["code"] == "VALIDATION_ERROR"
