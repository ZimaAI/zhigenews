"""Source collection independent of the Gateway, database and task queue."""

from .catalog import CATALOG_REVISION, catalog_source, default_sources, newsnow_catalog
from .service import fetch_source, load_snapshot_items, read_latest_snapshot

__all__ = [
    "CATALOG_REVISION",
    "catalog_source",
    "default_sources",
    "fetch_source",
    "load_snapshot_items",
    "newsnow_catalog",
    "read_latest_snapshot",
]
