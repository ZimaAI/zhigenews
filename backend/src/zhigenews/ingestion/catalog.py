"""Default RSS subscriptions; initialization preserves existing source settings."""

import json
from importlib.resources import files


def default_sources() -> list[dict]:
    sources = []
    rss_catalog = json.loads(files(__package__).joinpath("default-rss-sources.json").read_text(encoding="utf-8"))
    for entry in rss_catalog["sources"]:
        sources.append(
            {
                **entry,
                "kind": "rss",
                "source_id": "",
                "configured_interval_seconds": rss_catalog["configured_interval_seconds"],
                "effective_interval_seconds": rss_catalog["configured_interval_seconds"],
                "status": "unverified",
                "enabled": True,
            }
        )
    return sources
