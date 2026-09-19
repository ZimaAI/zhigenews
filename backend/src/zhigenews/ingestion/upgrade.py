"""Additively migrate pre-index news before workers accept generation tasks."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import service


def migrate_source_news(source: dict, storage: Path, *, now=None, before_publish=None) -> bool:
    """Caller holds the source's collection lock. Preserve old files and citation IDs."""
    storage = Path(storage)
    source = service._normalize_source(source)
    root = service.source_news_directory(source, storage)
    marker = root / "legacy-migrated.json"
    legacy = root.parent.parent
    if marker.exists() or not (legacy / "latest.json").is_file():
        return False
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(hours=24)
    latest = service.read_latest_snapshot(source, storage)
    current_index = service.read_source_index(source, storage)
    old_latest = json.loads((legacy / "latest.json").read_text("utf-8"))
    manifests = [
        json.loads(path.read_text("utf-8")) for path in sorted((legacy / "manifests").glob("*.json"))
    ]
    migrated = 0
    for manifest in sorted(manifests, key=lambda item: item["fetched_at"]):
        if (manifest.get("source_id"), manifest.get("kind"), manifest.get("request_url")) != (
            source["id"],
            source["kind"],
            source["url"],
        ):
            continue
        items = service.load_snapshot_items(manifest, storage)
        if manifest["snapshot_id"] != old_latest["snapshot_id"] and not any(
            (published := service._datetime(item.get("published_at"))) is not None
            and cutoff <= published <= now
            for item in items
        ):
            continue
        if before_publish is not None:
            before_publish()
        migrated_manifest = dict(manifest)
        for field in ("raw_path", "parsed_path", "manifest_path"):
            original = service._path(storage, manifest[field])
            relative = original.relative_to(legacy)
            target = root / relative
            migrated_manifest[field] = target.relative_to(storage.resolve()).as_posix()
            if field != "manifest_path":
                service._atomic_write(target, original.read_bytes())
        service._atomic_write(
            service._path(storage, migrated_manifest["manifest_path"]), service._json_bytes(migrated_manifest)
        )
        service._maintain_source_index(source, storage, now, migrated_manifest)
        if latest is None or manifest["fetched_at"] > latest["fetched_at"]:
            latest = migrated_manifest
        migrated += 1
    if before_publish is not None:
        before_publish()
    if latest is not None:
        # Merge the current snapshot last so old duplicate IDs cannot replace newer citations.
        service._maintain_source_index(source, storage, now, latest)
        service._atomic_write(root / "latest.json", service._json_bytes(latest))
    if current_index is not None and migrated:
        index = service.read_source_index(source, storage)
        entries = {item["id"]: item for item in index["items"]}
        entries.update(
            {
                item["id"]: item
                for item in current_index["items"]
                if (published := service._datetime(item.get("published_at"))) is not None
                and cutoff <= published <= now
            }
        )
        index["items"] = sorted(
            entries.values(), key=lambda item: (item["published_at"], item["id"]), reverse=True
        )
        service._atomic_write(
            root / "index.json", json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8")
        )
    service._atomic_write(marker, service._json_bytes({"migrated_snapshots": migrated}))
    return bool(migrated)
