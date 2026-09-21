# Source ingestion

`fetch_source(source, storage)` performs one HTTP request and returns `source`,
`attempt`, the last valid `snapshot`, and normalized `items`. The caller must
hold a per-source lease and persist the returned source state and attempt after
the call. The adapter does not access a database or schedule work itself.

Only RSS / Atom subscriptions are supported. Dependencies are `httpx` and `feedparser`.

`configured_interval_seconds` is an administrator setting. The effective
interval is the maximum of it and RSS `ttl`. HTTP cache hints and bounded exponential failure backoff may postpone
`next_fetch_at` further. `Retry-After` is respected. Positive jitter never
causes earlier polling.

## Default sources

`default_sources()` provides 341 enabled, unverified RSS sources:

- 341 RSS sources in `default-rss-sources.json`: the existing China News
  immediate feed plus all 340 feed URLs in the table at
  <https://juejin.cn/post/7459966392429101067>, captured on 2026-09-19.
  These use a 30-minute configured interval. Original URLs are preserved,
  including HTTP/HTTPS, host and trailing-slash variants; different URLs
  with the same name remain separate. Three unnamed rows use their URL as
  the display name. The article's preview links are not feed URLs.

RSS source IDs are unchanged. The additional RSS IDs were generated from
the hostname and the first 12 SHA-256 hex characters of the original URL, then
saved in the JSON file; keep these IDs stable when editing entries. This is a
source inventory, not a claim that all endpoints currently return valid feeds.

For new or existing installations, run from the repository root:

```sh
uv run --project backend python -m zhigenews.cli init
```

Initialization adds missing source IDs only. Re-running it preserves existing
URLs, intervals and disabled states. Editing defaults does not update rows
already in the database; use the admin Sources page for those changes.

## Storage and evidence

Each source configuration has a separate root at
`{kind}/{source_db_id}/configs/{identity_hash}/`. The identity uses the
normalized source kind, URL and optional source identifier. `source_news_directory`
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

Existing installations migrate matching legacy snapshots locally with
`python -m zhigenews.cli migrate-news`. The Compose worker runs this preflight
before consuming tasks; standalone workers must run it against their data
directory before startup. Collection also migrates its source before using
conditional HTTP validators. Migration preserves original files and evidence
IDs, copies the latest snapshot and snapshots containing recent news into the
configuration directory, and builds the 24-hour index without external HTTP.
It uses the collection lock, keeps newer indexes/snapshots, and can be rerun.
Only matching source IDs, kinds and normalized request URLs are imported.
If no matching snapshot exists, stored validators are cleared to obtain a
complete feed. Agent startup never builds a news index.

Normalized evidence includes `id`, `evidence_id`, `external_id`, `source_id`,
`source`, `source_type`, `title`, `url`, `summary`, `content`, `published_at`,
`fetched_at`, `first_seen_at`, and `snapshot_id`. Unknown publication time is
null. Feed update times, collection times and first-seen times cannot establish
a story's publication time. RSS/Atom summaries and content remain untrusted source material.

State fields use snake_case. Map `snapshot_id`, `snapshot_fetched_at`,
`last_fetched_at`, `cache_age_seconds`, and `stale` to the
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

From the repository root, probe all default RSS subscriptions and save metadata
without news text in the report:

```powershell
uv run --project backend python -m zhigenews.ingestion.smoke --storage backend/data/ingestion-smoke --report .project-flow/versions/v1.0.0/evidence/ingestion-live.json
```

This exits with a failure code if any source is unavailable. The storage
directory contains the actual raw/parsed evidence and is excluded from Git.
