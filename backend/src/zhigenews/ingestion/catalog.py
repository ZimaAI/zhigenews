"""Pinned NewsNow source metadata; upgrades are explicit administrative changes."""

import json
from importlib.resources import files
from urllib.parse import urlencode

CATALOG_REVISION = "0f95b2c998dffbfd2ddbc51b47b5809887dc6b97"
DEFAULT_NEWSNOW_URL = "https://newsnow.busiyi.world"


def newsnow_catalog() -> dict:
    return json.loads(files(__package__).joinpath("newsnow-sources.json").read_text(encoding="utf-8"))


def catalog_source(source_id: str) -> dict:
    catalog = newsnow_catalog()
    entry = catalog.get(source_id)
    if entry is None:
        raise ValueError(f"Unknown NewsNow source: {source_id}")
    resolved = entry.get("redirect", source_id)
    entry = catalog[resolved]
    if entry.get("disable") is True:
        raise ValueError(f"Disabled NewsNow source: {source_id}")
    return {
        "source_id": resolved,
        "name": entry["name"] + (" · " + entry["title"] if entry.get("title") else ""),
        "upstream_interval_seconds": int(entry["interval"]) // 1000,
        "upstream_revision": CATALOG_REVISION,
        "catalog_revision": CATALOG_REVISION,
        "deployment_restriction": entry.get("disable"),
    }


def default_sources(base_url: str = DEFAULT_NEWSNOW_URL) -> list[dict]:
    sources = []
    for source_id in ("hackernews", "solidot"):
        entry = catalog_source(source_id)
        sources.append(
            {
                **entry,
                "id": "newsnow-" + source_id,
                "kind": "newsnow",
                "url": base_url.rstrip("/") + "/api/s?" + urlencode({"id": entry["source_id"]}),
                "configured_interval_seconds": entry["upstream_interval_seconds"],
                "effective_interval_seconds": entry["upstream_interval_seconds"],
                "status": "unverified",
                "enabled": True,
            }
        )
    sources.append(
        {
            "id": "rss-chinanews",
            "name": "中国新闻网 · 即时新闻",
            "kind": "rss",
            "source_id": "",
            "url": "https://www.chinanews.com.cn/rss/scroll-news.xml",
            "configured_interval_seconds": 1800,
            "upstream_interval_seconds": 0,
            "effective_interval_seconds": 1800,
            "status": "unverified",
            "enabled": True,
        }
    )
    return sources
