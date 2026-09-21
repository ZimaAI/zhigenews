"""Fetch a source, publish immutable evidence, and return state for a DB transaction.

The caller owns the source lease. No database lock should be held during HTTP.
All returned timestamps are UTC ISO strings. Raw/parsed paths are relative to
``storage`` and must never be returned through a public DTO.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import os
import random
import re
import tempfile
import time
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser
import httpx

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; ZhigeNews/1.0; news feed reader)"
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class IngestionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, (int, float)):
            result = datetime.fromtimestamp(value / 1000 if value > 100_000_000_000 else value, UTC)
        else:
            try:
                result = datetime.fromisoformat(str(value))
            except ValueError:
                result = parsedate_to_datetime(str(value))
        # Unqualified dates cannot supply an invented publication timezone.
        return result.astimezone(UTC) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _path(storage: Path, relative: str) -> Path:
    root = storage.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise IngestionError("INVALID_SNAPSHOT_PATH", "Snapshot path is outside source storage")
    return path


def _source_dir(source: dict, storage: Path) -> Path:
    if not SAFE_ID.fullmatch(str(source.get("id", ""))):
        raise IngestionError("INVALID_SOURCE_ID", "Source ID must be a system-generated safe identifier")
    if source.get("kind") != "rss":
        raise IngestionError("INVALID_SOURCE_KIND", "Source kind must be rss")
    normalized = _normalize_source(source)
    identity = _hash(
        _json_bytes(
            {
                "kind": normalized["kind"],
                "url": normalized["url"],
                "source_id": normalized.get("source_id", ""),
            }
        )
    )
    return _path(storage, f"{source['kind']}/{source['id']}/configs/{identity}")


def _atomic_write(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".ingest-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            # These files contain public news; the read-only sandbox runs as
            # a different UID from the collecting worker. mkstemp starts 0600.
            if hasattr(os, "fchmod"):
                os.fchmod(handle.fileno(), 0o644)
            else:
                os.chmod(temporary, 0o644)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_latest_snapshot(source: dict, storage: Path) -> dict | None:
    latest = _source_dir(source, storage) / "latest.json"
    if not latest.exists():
        return None
    snapshot = json.loads(latest.read_text(encoding="utf-8"))
    if source.get("url") and snapshot.get("request_url") != source["url"]:
        return None
    return snapshot


def load_snapshot_items(snapshot: dict | None, storage: Path) -> list[dict]:
    if snapshot is None:
        return []
    return [
        json.loads(line)
        for line in _path(storage, snapshot["parsed_path"]).read_text(encoding="utf-8").splitlines()
        if line
    ]


def source_news_directory(source: dict, storage: Path) -> Path:
    """Return the source's authorized news directory without reading news."""
    return _source_dir(_normalize_source(source), Path(storage))


def read_source_index(source: dict, storage: Path) -> dict | None:
    """Read the ingestion-maintained discovery index; never build it here."""
    path = source_news_directory(source, storage) / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def resolve_source_evidence(source: dict, storage: Path, evidence_id: str) -> dict | None:
    """Resolve a selected immutable citation without loading the discovery index."""
    if not re.fullmatch(r"[0-9a-f]{32}:[0-9a-f]{32}", evidence_id):
        return None
    snapshot_id, item_id = evidence_id.split(":")
    normalized = _normalize_source(source)
    root = _source_dir(normalized, Path(storage))
    manifest_path = root / "manifests" / f"{snapshot_id}.json"
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("request_url") != normalized["url"] or manifest.get("source_id") != source["id"]:
        return None
    parsed = _path(storage, manifest["parsed_path"])
    if not parsed.is_relative_to(root):
        return None
    with parsed.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            if (item.get("id"), item.get("evidence_id"), item.get("source_id")) == (
                item_id,
                evidence_id,
                source["id"],
            ):
                return item
    return None


def _maintain_source_index(source: dict, storage: Path, now: datetime, snapshot: dict | None) -> None:
    root = _source_dir(source, storage)
    cutoff = now - timedelta(hours=24)
    prior = read_source_index(source, storage)
    entries = {
        item["id"]: item
        for item in (prior or {}).get("items", [])
        if (published := _datetime(item.get("published_at"))) is not None and cutoff <= published <= now
    }
    for line, item in enumerate(load_snapshot_items(snapshot, storage), 1):
        published = _datetime(item.get("published_at"))
        if published is None or not cutoff <= published <= now:
            continue
        entries[item["id"]] = {
            key: item[key] for key in ("id", "evidence_id", "source_id", "title", "url", "published_at")
        } | {
            "file": _path(storage, snapshot["parsed_path"]).relative_to(root).as_posix(),
            "line": line,
        }
    index = {
        "source_id": source["id"],
        "request_url": source["url"],
        "maintained_at": _iso(now),
        "window_start": _iso(cutoff),
        "window_end": _iso(now),
        "items": sorted(entries.values(), key=lambda item: (item["published_at"], item["id"]), reverse=True),
    }
    _atomic_write(root / "index.json", json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"))


def _http_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError
        _ = parts.port
    except ValueError:
        raise IngestionError(
            "INVALID_URL", "Source and article URLs must be HTTP(S) without embedded credentials"
        ) from None
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def _normalize_source(source: dict) -> dict:
    result = dict(source)
    configured = source.get("configured_interval_seconds", source.get("interval", 1800))
    result["configured_interval_seconds"] = max(1, int(configured))
    result["url"] = _http_url(source["url"])
    result["effective_interval_seconds"] = max(
        result["configured_interval_seconds"],
        int(result.get("feed_ttl_seconds", 0)),
    )
    return result


def _item(
    source: dict,
    external_id: str,
    title: str,
    url: str,
    published: datetime | None,
    summary: str,
    content: str = "",
) -> dict:
    canonical = _http_url(url)
    identity = _hash(f"{source['id']}:{external_id or canonical}".encode())[:32]
    return {
        "id": identity,
        "external_id": external_id or canonical,
        "source_id": source["id"],
        "source": source.get("name", source["id"]),
        "source_type": source["kind"],
        "title": title.strip(),
        "url": canonical,
        "published_at": _iso(published) if published else None,
        "summary": summary,
        "content": content,
    }


def _parse_rss(raw: bytes, source: dict, headers: dict) -> tuple[list[dict], dict]:
    parsed = feedparser.parse(raw, response_headers=headers)
    if not parsed.get("version"):
        raise IngestionError("INVALID_FEED", "Response is not an RSS or Atom feed")
    if parsed.get("bozo") and not parsed.entries:
        raise IngestionError("INVALID_FEED", "Feed XML could not be parsed")
    items, dropped, seen = [], 0, set()
    for entry in parsed.entries:
        title, url = entry.get("title", ""), entry.get("link", "")
        if not title or not url:
            dropped += 1
            continue
        published = None
        if entry.get("published_parsed"):
            published = datetime.fromtimestamp(calendar.timegm(entry.published_parsed), UTC)
        content = "\n".join(part.get("value", "") for part in entry.get("content", []))
        try:
            item = _item(
                source, str(entry.get("id", "")), title, url, published, entry.get("summary", ""), content
            )
        except IngestionError:
            dropped += 1
            continue
        if item["id"] not in seen:
            items.append(item)
            seen.add(item["id"])
    if parsed.entries and not items:
        raise IngestionError("INVALID_FEED_ITEMS", "Feed contains no usable article links")
    try:
        ttl = max(0, int(parsed.feed.get("ttl", 0))) * 60
    except (TypeError, ValueError):
        ttl = 0
    return items, {
        "feed_format": parsed.version,
        "feed_ttl_seconds": ttl,
        "parse_warning": type(parsed.get("bozo_exception")).__name__ if parsed.get("bozo") else None,
        "dropped_items": dropped,
        "content_hash": _hash(raw),
    }


def _publish(
    source: dict,
    storage: Path,
    now: datetime,
    raw: bytes,
    items: list[dict],
    metadata: dict,
    prior_items: list[dict],
    before_publish=None,
    fixed_now: datetime | None = None,
) -> dict:
    snapshot_id = uuid.uuid4().hex
    base = _source_dir(source, storage).relative_to(storage.resolve()).as_posix()
    date = now.strftime("%Y/%m/%d")
    extension = "xml"
    prior = {item["id"]: item for item in prior_items}
    for item in items:
        item.update(
            {
                "snapshot_id": snapshot_id,
                "fetched_at": _iso(now),
                "first_seen_at": prior.get(item["id"], {}).get("first_seen_at", _iso(now)),
                "evidence_id": f"{snapshot_id}:{item['id']}",
            }
        )
    manifest = {
        **metadata,
        "snapshot_id": snapshot_id,
        "source_id": source["id"],
        "kind": source["kind"],
        "fetched_at": _iso(now),
        "raw_hash": _hash(raw),
        "raw_bytes": len(raw),
        "item_count": len(items),
        "raw_path": f"{base}/raw/{date}/{snapshot_id}.{extension}",
        "parsed_path": f"{base}/parsed/{date}/{snapshot_id}.jsonl",
        "manifest_path": f"{base}/manifests/{snapshot_id}.json",
    }
    _atomic_write(_path(storage, manifest["raw_path"]), raw)
    _atomic_write(
        _path(storage, manifest["parsed_path"]), b"".join(_json_bytes(item) + b"\n" for item in items)
    )
    _atomic_write(_path(storage, manifest["manifest_path"]), _json_bytes(manifest))
    # Publish discovery only after its immutable evidence files are complete.
    if before_publish is not None:
        before_publish()
    _maintain_source_index(source, storage, fixed_now or datetime.now(UTC), manifest)
    # Do not advance the latest pointer when index publication was interrupted.
    _atomic_write(_source_dir(source, storage) / "latest.json", _json_bytes(manifest))
    return manifest


def _retry_after(value: str | None, now: datetime) -> int:
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        date = _datetime(value)
        return max(0, int((date - now).total_seconds())) if date else 0


def _cache_delay(headers: dict, now: datetime) -> int:
    match = re.search(
        r"(?:^|,)\s*(?:s-maxage|max-age)\s*=\s*\"?(\d+)", headers.get("cache-control", ""), re.IGNORECASE
    )
    if match:
        try:
            age = max(0, int(headers.get("age", 0)))
        except ValueError:
            age = 0
        return max(0, int(match[1]) - age)
    expires = _datetime(headers.get("expires"))
    return max(0, int((expires - now).total_seconds())) if expires else 0


def fetch_source(
    source: dict,
    storage: Path,
    *,
    client: httpx.Client | None = None,
    now: datetime | None = None,
    timeout_seconds: float = 20,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
    jitter_ratio: float = 0.05,
    before_publish=None,
) -> dict:
    """Perform one bounded request, returning state, attempt, snapshot and items.

    Expected source keys: id, kind (rss), url, and
    configured_interval_seconds. The returned source preserves original keys
    and contains conditional request state for the caller to persist.
    ``client`` and ``now`` permit deterministic HTTP failure/clock fixtures.
    A failure returns the previous valid snapshot without replacing it.
    """
    storage = Path(storage)
    fixed_now = now
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    started = time.monotonic()
    state = _normalize_source(source)
    from .upgrade import migrate_source_news

    migrate_source_news(state, storage, now=now, before_publish=before_publish)
    previous = read_latest_snapshot(state, storage)
    if previous is None:
        # A new configuration (or pre-index installation) must obtain a full
        # response; validators from a different storage identity are unusable.
        state.pop("etag", None)
        state.pop("last_modified", None)
    items = load_snapshot_items(previous, storage)
    snapshot = previous
    if previous:
        # Recover a successfully published snapshot if the worker stopped
        # before committing its returned state to the database.
        if state.get("snapshot_id") != previous["snapshot_id"]:
            state["last_success_at"] = previous["fetched_at"]
            state["last_changed_at"] = previous["fetched_at"]
        for field in ("etag", "last_modified"):
            if not state.get(field) and previous.get(field):
                state[field] = previous[field]
        state.setdefault("last_checked_at", previous["fetched_at"])
        if "feed_ttl_seconds" in previous:
            state["feed_ttl_seconds"] = previous["feed_ttl_seconds"]
            state["effective_interval_seconds"] = max(
                state["configured_interval_seconds"],
                state["feed_ttl_seconds"],
            )
    attempt = {
        "id": uuid.uuid4().hex,
        "source_id": state["id"],
        "started_at": _iso(now),
        "request_url": state["url"],
        "final_url": None,
        "http_status": None,
        "bytes": 0,
        "item_count": 0,
        "changed": False,
        "snapshot_id": None,
        "outcome": "failed",
        "error_type": None,
        "error": None,
    }
    if state.get("enabled") is False or state.get("status") == "disabled":
        state["status"] = "disabled"
        attempt["outcome"] = "disabled"
        return {"source": state, "attempt": attempt, "snapshot": snapshot, "items": items}
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml",
    }
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    response_headers: dict = {}
    owned_client = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        if before_publish is not None:
            before_publish()
        with client.stream(
            "GET", state["url"], headers=headers, timeout=timeout_seconds, follow_redirects=True
        ) as response:
            attempt.update({"http_status": response.status_code, "final_url": str(response.url)})
            response_headers = dict(response.headers)
            if response.status_code == 304:
                if snapshot is None:
                    raise IngestionError(
                        "ORPHAN_304", "Source returned 304 without a previously valid snapshot"
                    )
                attempt["outcome"] = "not_modified"
            elif response.status_code != 200:
                raise IngestionError(
                    f"HTTP_{response.status_code}", f"Source returned HTTP {response.status_code}"
                )
            else:
                chunks: list[bytes] = []
                for chunk in response.iter_bytes():
                    if before_publish is not None:
                        before_publish()
                    attempt["bytes"] += len(chunk)
                    if attempt["bytes"] > max_response_bytes:
                        raise IngestionError(
                            "RESPONSE_TOO_LARGE", "Source response exceeds the configured byte limit"
                        )
                    chunks.append(chunk)
                raw = b"".join(chunks)
                parsed_items, metadata = _parse_rss(raw, state, response_headers)
                attempt.update(metadata)
                state["feed_ttl_seconds"] = metadata.get("feed_ttl_seconds", 0)
                state["effective_interval_seconds"] = max(
                    state["configured_interval_seconds"],
                    state["feed_ttl_seconds"],
                )
                if previous is None or metadata["content_hash"] != previous["content_hash"]:
                    if before_publish is not None:
                        before_publish()
                    metadata.update(
                        {
                            "request_url": state["url"],
                            "final_url": str(response.url),
                            "http_status": 200,
                            "etag": response_headers.get("etag"),
                            "last_modified": response_headers.get("last-modified"),
                        }
                    )
                    snapshot = _publish(
                        state, storage, now, raw, parsed_items, metadata, items, before_publish, fixed_now
                    )
                    items = parsed_items
                    state["last_success_at"] = _iso(now)
                    state["last_changed_at"] = _iso(now)
                    attempt.update({"changed": True, "outcome": "published"})
                else:
                    attempt["outcome"] = "unchanged"
        # Only successful/validated responses replace conditional metadata.
        for header, field in (("etag", "etag"), ("last-modified", "last_modified")):
            if header in response_headers:
                state[field] = response_headers[header]
        state.update({"status": "healthy", "failure_count": 0, "error": "", "last_checked_at": _iso(now)})
        delay = max(state["effective_interval_seconds"], _cache_delay(response_headers, now))
    except (httpx.HTTPError, IngestionError) as exc:
        if isinstance(exc, IngestionError) and exc.code == "SOURCE_STOPPED":
            raise
        failures = int(state.get("failure_count", 0)) + 1
        error_type = (
            exc.code
            if isinstance(exc, IngestionError)
            else ("TIMEOUT" if isinstance(exc, httpx.TimeoutException) else "NETWORK_ERROR")
        )
        # Do not echo remote response bodies or arbitrary request exceptions.
        message = (
            str(exc)
            if isinstance(exc, IngestionError)
            else ("Source request timed out" if error_type == "TIMEOUT" else "Source network request failed")
        )
        attempt.update({"error_type": error_type, "error": message})
        state.update(
            {"status": "invalid" if failures >= 3 else "failed", "failure_count": failures, "error": message}
        )
        base = state["effective_interval_seconds"]
        delay = max(
            base,
            min(86400, base * 2 ** min(failures - 1, 12)),
            _retry_after(response_headers.get("retry-after"), now),
        )
    finally:
        if owned_client:
            client.close()
    if attempt["outcome"] != "published" and attempt["error_type"] != "LEASE_LOST":
        try:
            if before_publish is not None:
                before_publish()
            _maintain_source_index(state, storage, fixed_now or datetime.now(UTC), snapshot)
        except IngestionError as exc:
            if exc.code != "LEASE_LOST":
                raise
            attempt.update({"outcome": "failed", "error_type": exc.code, "error": str(exc)})
            state.update({"status": "failed", "error": str(exc)})
    delay += random.uniform(0, max(0, jitter_ratio)) * delay
    state.update(
        {
            "last_fetched_at": _iso(now),
            "next_fetch_at": "" if state["status"] == "invalid" else _iso(now + timedelta(seconds=delay)),
            "snapshot_id": snapshot["snapshot_id"] if snapshot else None,
            "snapshot_fetched_at": snapshot["fetched_at"] if snapshot else None,
            "items": len(items),
        }
    )
    fetched = _datetime(state["snapshot_fetched_at"])
    age = max(0, int((now - fetched).total_seconds())) if fetched else None
    state["cache_age_seconds"] = age
    checked = _datetime(state.get("last_checked_at"))
    validity_age = max(0, int((now - checked).total_seconds())) if checked else age
    state["stale"] = (
        snapshot is None
        or state["status"] in ("failed", "invalid")
        or validity_age > state["effective_interval_seconds"]
    )
    attempt.update(
        {
            "finished_at": _iso(now + timedelta(seconds=time.monotonic() - started)),
            "duration_ms": round((time.monotonic() - started) * 1000),
            "item_count": len(items),
            "snapshot_id": state["snapshot_id"],
            "etag": response_headers.get("etag"),
            "last_modified": response_headers.get("last-modified"),
            "next_fetch_at": state["next_fetch_at"],
        }
    )
    return {"source": state, "attempt": attempt, "snapshot": snapshot, "items": items}
