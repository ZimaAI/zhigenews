"""Source collection independent of the Gateway, database and task queue."""

from .catalog import default_sources
from .service import (
    fetch_source,
    load_snapshot_items,
    read_latest_snapshot,
    read_source_index,
    resolve_source_evidence,
    source_news_directory,
)

__all__ = [
    "default_sources",
    "fetch_source",
    "load_snapshot_items",
    "read_latest_snapshot",
    "read_source_index",
    "resolve_source_evidence",
    "source_news_directory",
]
