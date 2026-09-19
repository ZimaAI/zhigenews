"""Bounded Tavily searches; only the trusted worker has the credential."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import httpx

from .errors import HarnessError


class TavilySearch:
    def __init__(
        self,
        api_key: str | None,
        *,
        max_calls: int = 5,
        timeout: float = 15,
        client: httpx.Client | None = None,
        evidence: dict | None = None,
        persist=None,
    ):
        self.api_key, self.max_calls, self.timeout = api_key, max_calls, timeout
        self.client = client
        self.evidence = evidence if evidence is not None else {}
        self.calls, self.lock = 0, threading.Lock()
        self.persist = persist or (lambda evidence, calls: None)

    def search(
        self, query: str, max_results: int = 5, days: int = 1, include_domains: list[str] | None = None
    ) -> dict:
        if not self.api_key:
            raise HarnessError("SEARCH_NOT_CONFIGURED", "尚未配置 Tavily 凭据。")
        if not query.strip() or len(query) > 1000:
            raise HarnessError("INVALID_QUERY", "查询词长度无效。")
        if include_domains and (
            len(include_domains) > 10 or any("/" in d or len(d) > 253 for d in include_domains)
        ):
            raise HarnessError("INVALID_QUERY", "来源域名列表无效。")
        with self.lock:
            if self.calls >= self.max_calls:
                raise HarnessError("SEARCH_BUDGET", "搜索次数预算已耗尽。")
            self.calls += 1
            self.persist(self.evidence, self.calls)
        payload = {
            "query": query,
            "topic": "news",
            "search_depth": "basic",
            "max_results": min(max(max_results, 1), 10),
            "days": min(max(days, 1), 30),
            "include_raw_content": False,
            "include_answer": False,
            "include_domains": include_domains or [],
        }
        client = self.client or httpx.Client(timeout=self.timeout)
        try:
            with client.stream(
                "POST",
                "https://api.tavily.com/search",
                headers={"Authorization": "Bearer " + self.api_key},
                json=payload,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1048576:
                        raise HarnessError("OUTPUT_LIMIT", "搜索响应超过允许大小。")
                result = json.loads(body)
        except httpx.TimeoutException:
            raise HarnessError("TIMEOUT", "Tavily 搜索超时。") from None
        except (httpx.HTTPError, ValueError):
            raise HarnessError("SEARCH_FAILED", "Tavily 搜索失败。") from None
        finally:
            if self.client is None:
                client.close()
        fetched = datetime.now(timezone.utc).isoformat()
        results, used, truncated = [], 1024, False
        for entry in result.get("results", [])[: payload["max_results"]]:
            url = entry.get("url", "")
            if urlparse(url).scheme not in ("http", "https"):
                continue
            evidence_id = "search-" + hashlib.sha256((query + "\0" + url).encode()).hexdigest()[:24]
            published = None
            if entry.get("published_date"):
                try:
                    parsed = datetime.fromisoformat(entry["published_date"].replace("Z", "+00:00"))
                    published = parsed.astimezone(timezone.utc).isoformat() if parsed.tzinfo else None
                except ValueError:
                    try:
                        published = (
                            parsedate_to_datetime(entry["published_date"])
                            .astimezone(timezone.utc)
                            .isoformat()
                        )
                    except (ValueError, TypeError):
                        pass
            item = {
                "id": evidence_id,
                "evidence_id": evidence_id,
                "title": str(entry.get("title", ""))[:500],
                "url": url[:4096],
                "summary": str(entry.get("content", ""))[:2200],
                "source": urlparse(url).hostname or "Tavily",
                "source_type": "search",
                "published_at": published,
                "fetched_at": fetched,
                "snapshot_id": evidence_id,
                "query": query,
            }
            used += len(json.dumps(item, ensure_ascii=False).encode())
            if used > 24576:
                truncated = True
                break
            results.append(item)
            with self.lock:
                self.evidence[evidence_id] = item
                self.persist(self.evidence, self.calls)
        return {"ok": True, "query": query, "results": results, "truncated": truncated, "calls": self.calls}
