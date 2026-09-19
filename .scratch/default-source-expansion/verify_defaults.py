from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch

from zhigenews import cli
from zhigenews.ingestion.catalog import default_sources, newsnow_catalog

sources = default_sources("https://fixture.invalid/")
assert len(sources) == len({s["id"] for s in sources}) == 388
assert len({(s["kind"], s["url"]) for s in sources}) == 388
assert all(s["name"] and len(s["name"]) <= 120 for s in sources)
assert all(s["enabled"] and s["status"] == "unverified" for s in sources)
newsnow = [s for s in sources if s["kind"] == "newsnow"]
assert len(newsnow) == 47
assert {s["source_id"] for s in newsnow} == {
    key for key, value in newsnow_catalog().items()
    if not value.get("redirect") and not value.get("disable")
}
assert all(s["url"] == "https://fixture.invalid/api/s?id=" + s["source_id"] for s in newsnow)
assert all(s["effective_interval_seconds"] == s["upstream_interval_seconds"] for s in newsnow)
assert {"newsnow-hackernews", "newsnow-solidot", "rss-chinanews"} <= {s["id"] for s in sources}

records = {}
session = SimpleNamespace(
    scalar=lambda _: object(),
    get=lambda _, key: records.get(key),
    add=lambda record: records.setdefault(record.id, record),
)
settings = SimpleNamespace(
    secret_encryption_key="synthetic", ip_hash_key="synthetic", admin_password="synthetic-password",
    admin_email="admin@example.invalid", newsnow_base_url="https://fixture.invalid", database_url="synthetic",
)
with (
    patch.object(cli, "get_settings", return_value=settings),
    patch.object(cli, "transaction", return_value=nullcontext(session)),
    patch.object(cli, "mysql_persistence", return_value=nullcontext()),
):
    cli.initialize()
    assert len(records) == 388
    edited = records["rss-chinanews"]
    edited.data.update(url="https://fixture.invalid/edited.xml", interval=86400, status="disabled")
    cli.initialize()
    assert len(records) == 388
    assert records["rss-chinanews"] is edited
    assert edited.data["url"] == "https://fixture.invalid/edited.xml"
    assert edited.data["interval"] == 86400 and edited.data["status"] == "disabled"
print("Verified 388 unique defaults, 47 canonical NewsNow IDs, custom base URL, and additive initialization.")
