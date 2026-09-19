"""Pinned NewsNow source metadata; upgrades are explicit administrative changes."""

import json
from importlib.resources import files
from urllib.parse import urlencode

CATALOG_REVISION = "0f95b2c998dffbfd2ddbc51b47b5809887dc6b97"
DEFAULT_NEWSNOW_URL = "https://newsnow.busiyi.world"

# All 47 sources offered by the public site's More menu on 2026-09-19.
# Use canonical IDs, excluding redirect aliases and sources unavailable there.
DEFAULT_NEWSNOW_SOURCE_IDS = (
    "hackernews",
    "solidot",
    "v2ex-share",
    "coolapk",
    "aihot",
    "ithome",
    "pcbeta-windows11",
    "producthunt",
    "github-trending-today",
    "sspai",
    "juejin",
    "hupu",
    "dongqiudi",
    "zhihu",
    "weibo",
    "douyin",
    "tieba",
    "toutiao",
    "thepaper",
    "bilibili-hot-search",
    "baidu",
    "nowcoder",
    "ifeng",
    "chongbuluo-latest",
    "chongbuluo-hot",
    "douban",
    "tencent-hot",
    "freebuf",
    "qqvideo-tv-hotsearch",
    "iqiyi-hot-ranklist",
    "zaobao",
    "sputniknewscn",
    "cankaoxiaoxi",
    "kaopu",
    "steam",
    "mktnews-flash",
    "wallstreetcn-quick",
    "wallstreetcn-news",
    "wallstreetcn-hot",
    "cls-telegraph",
    "cls-depth",
    "cls-hot",
    "xueqiu-hotstock",
    "gelonghui",
    "fastbull-express",
    "fastbull-news",
    "jin10",
)


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
    for source_id in DEFAULT_NEWSNOW_SOURCE_IDS:
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
    rss_catalog = json.loads(files(__package__).joinpath("default-rss-sources.json").read_text(encoding="utf-8"))
    for entry in rss_catalog["sources"]:
        sources.append(
            {
                **entry,
                "kind": "rss",
                "source_id": "",
                "configured_interval_seconds": rss_catalog["configured_interval_seconds"],
                "upstream_interval_seconds": 0,
                "effective_interval_seconds": rss_catalog["configured_interval_seconds"],
                "status": "unverified",
                "enabled": True,
            }
        )
    return sources
