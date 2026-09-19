# Source ingestion

`fetch_source(source, storage)` performs one HTTP request and returns `source`,
`attempt`, the last valid `snapshot`, and normalized `items`. The caller must
hold a per-source lease and persist the returned source state and attempt after
the call. The adapter does not access a database or schedule work itself.

Dependencies are `httpx` and `feedparser`. The bundled NewsNow catalog is fixed
at `0f95b2c998dffbfd2ddbc51b47b5809887dc6b97`, imported from the upstream
`shared/sources.json`; its MIT license is in `NEWSNOW-LICENSE`. Redirect aliases
are resolved before fetching. Catalog changes must be explicitly reviewed and
imported rather than silently taking newer metadata on startup.

`configured_interval_seconds` is an administrator setting. The effective
interval is the maximum of it, the pinned NewsNow source interval, and RSS
`ttl`. HTTP cache hints and bounded exponential failure backoff may postpone
`next_fetch_at` further. `Retry-After` is respected. Positive jitter never
causes earlier polling. `default_sources()` provides two NewsNow sources with
different intervals and the China News immediate feed as unverified sources.

Each source configuration has a separate root at
`{kind}/{source_db_id}/configs/{identity_hash}/`. The identity uses the
normalized source kind, URL and NewsNow source ID. `source_news_directory`
computes that root without reading articles, so a run can authorize only
enabled configurations. Changing a source URL cannot expose earlier
configuration files through the new root.

Snapshot files live beneath this root in `raw/YYYY/MM/DD/{uuid}` and
`parsed/YYYY/MM/DD/{uuid}.jsonl`; `manifests/{uuid}.json` describes them.
The pretty-printed `index.json` is atomically replaced only after all evidence
files are complete, followed by the `latest.json` pointer. Readers never see
partial index JSON or an index referring to an unfinished evidence file.
`read_latest_snapshot` and `load_snapshot_items` read immutable snapshots.
Failure, RSS 304 and identical content retain the old snapshot and its
original timestamp; the attempt records the new check time.

Every actual collection attempt maintains `index.json`, including HTTP
failure, RSS 304 and unchanged content. Only news with an explicit publication
time within the inclusive preceding 24-hour window is indexed; unknown,
invalid and future publication times are excluded. The index accumulates
news by stable item ID, retaining stories that rotate out of the upstream
feed until expiry. Pruning the index never deletes historical evidence.
Lease loss prevents index publication as well as snapshot publication.

`index.json` records `source_id`, `request_url`, `maintained_at`, `window_start`,
`window_end` and `items`. Each item contains `id`, `evidence_id`, `source_id`,
`title`, `url`, `published_at`, a `file` path relative to the authorized root,
and its one-based `line`. Bodies remain in the immutable parsed JSONL files.
`read_source_index` reads this file and does not build it. Agent runs discover
news through the live index, apply their fixed run window, and validate only
selected citations using `resolve_source_evidence(source, storage, evidence_id)`.
That resolver reads the identified immutable manifest and article, so a
citation remains resolvable when its index entry expires or is superseded.

Existing installations acquire the new configuration directory and index on
their next collection attempt. If this directory lacks a valid snapshot,
stored conditional HTTP validators are cleared to obtain a complete feed.
Agent startup never creates an index or presents old storage as ready.

Normalized evidence includes `id`, `evidence_id`, `external_id`, `source_id`,
`source`, `source_type`, `title`, `url`, `summary`, `content`, `published_at`,
`fetched_at`, `first_seen_at`, and `snapshot_id`. Unknown publication time is
null. The NewsNow `updatedTime` is separately recorded as upstream metadata;
it cannot establish a story's publication time or a content change. RSS/Atom
summaries and content remain untrusted source material.

State fields use snake_case. Map `snapshot_id`, `snapshot_fetched_at`,
`last_fetched_at`, `cache_age_seconds`, `stale`, and `upstream_revision` to the
corresponding camelCase Source DTO fields. Calculate cache age again when
serving a later query; the returned value describes this collection attempt.
`last_success_at` and `last_changed_at` advance only with a new valid snapshot;
`last_checked_at` records the latest successful check. `stale` means no valid
snapshot, failed latest check, or latest successful check over its effective
interval. A successful 304 extends validity without resetting cache age.

`pytest backend/tests/test_ingestion.py` uses explicitly synthetic HTTP
responses for conditional requests, bad XML/HTML, timeouts, rate limits,
publication failure, byte limits and snapshot stability. Live evidence is
recorded separately and must never be inferred from those tests.

From the repository root, run the three actual HTTP probes and save metadata
without news text in the report:

```powershell
uv run --project backend python -m zhigenews.ingestion.smoke --storage backend/data/ingestion-smoke --report .project-flow/versions/v1.0.0/evidence/ingestion-live.json
```

This exits with a failure code if any source is unavailable. The storage
directory contains the actual raw/parsed evidence and is excluded from Git.
