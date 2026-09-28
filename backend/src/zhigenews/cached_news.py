"""Read the current source news indexes and their immutable cached evidence."""

from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

from .db import iso
from .errors import AppError
from .ingestion import read_source_index, resolve_source_evidence

PAGE_SIZE = 20


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif not self.hidden and tag in ("p", "div", "br", "li", "h1", "h2", "h3", "blockquote"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in ("p", "div", "li", "h1", "h2", "h3", "blockquote"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value):
    parser = _PlainText()
    parser.feed(value or "")
    parser.close()
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def _entries(source, storage, now):
    try:
        index = read_source_index(source, storage)
    except FileNotFoundError:
        # Source deletion may remove its files after the source row was read.
        return []
    except (OSError, ValueError) as exc:
        raise AppError("DEPENDENCY_UNAVAILABLE", "新闻缓存读取失败，请稍后重试", 503) from exc
    if index is None:
        return []
    if index.get("source_id") != source["id"]:
        raise AppError("DEPENDENCY_UNAVAILABLE", "新闻缓存与来源不匹配，请稍后重试", 503)
    cutoff = now - timedelta(hours=24)
    entries = []
    for item in index["items"]:
        published = datetime.fromisoformat(item["published_at"]) if item.get("published_at") else None
        if published is not None and published.tzinfo and cutoff <= published <= now:
            entries.append(item)
    return entries


def _item_view(item, source):
    return dict(
        id=item["id"], evidenceId=item["evidence_id"], sourceId=source["id"],
        sourceName=source["name"], title=item["title"], url=item["url"],
        publishedAt=item["published_at"],
    )


def list_cached_news(sources: list[dict], storage: Path, params: dict, now: datetime):
    now = now.replace(tzinfo=UTC)
    selected = params.get("sourceId")
    if selected and not any(source["id"] == selected for source in sources):
        raise AppError("NOT_FOUND", "新闻来源不存在", 404)
    items, choices = [], []
    query = params.get("q", "").strip().casefold()
    for source in sources:
        entries = _entries(source, storage, now)
        choices.append(dict(id=source["id"], name=source["name"], count=len(entries)))
        if selected and source["id"] != selected:
            continue
        items.extend(_item_view(item, source) for item in entries if query in item["title"].casefold())
    items.sort(key=lambda item: (item["publishedAt"], item["sourceId"], item["id"]), reverse=True)
    total = len(items)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = min(int(params.get("page", 1)), max(1, total_pages))
    return dict(
        items=items[(page - 1) * PAGE_SIZE:page * PAGE_SIZE], total=total,
        page=page, pageSize=PAGE_SIZE, totalPages=total_pages,
        windowStart=iso(now - timedelta(hours=24)), windowEnd=iso(now),
        sources=sorted(choices, key=lambda choice: (choice["name"].casefold(), choice["id"])),
    )


def get_cached_news(source: dict, storage: Path, item_id: str, now: datetime):
    entry = next((item for item in _entries(source, storage, now.replace(tzinfo=UTC))
                  if item["id"] == item_id), None)
    if entry is None:
        raise AppError("NOT_FOUND", "新闻不存在或已退出最近 24 小时索引", 404)
    try:
        evidence = resolve_source_evidence(source, storage, entry["evidence_id"])
    except FileNotFoundError:
        evidence = None
    except (OSError, ValueError) as exc:
        raise AppError("DEPENDENCY_UNAVAILABLE", "新闻缓存读取失败，请稍后重试", 503) from exc
    if evidence is None:
        raise AppError("NOT_FOUND", "新闻缓存已不可用，请刷新列表", 404)
    return {
        **_item_view(evidence, source), "sourceUrl": source["url"],
        "snapshotId": evidence["snapshot_id"], "fetchedAt": evidence["fetched_at"],
        "firstSeenAt": evidence["first_seen_at"],
        "summary": plain_text(evidence["summary"]), "content": plain_text(evidence["content"]),
    }
