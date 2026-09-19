"""Run real public-source probes and save a metadata-only report."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from .catalog import DEFAULT_NEWSNOW_URL, default_sources
from .service import fetch_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--newsnow-base-url", default=DEFAULT_NEWSNOW_URL)
    args = parser.parse_args()
    results = []
    for source in default_sources(args.newsnow_base_url):
        result = fetch_source(source, args.storage, jitter_ratio=0)
        results.append(
            {
                "source": result["source"],
                "attempt": result["attempt"],
                "snapshot": {
                    key: value
                    for key, value in (result["snapshot"] or {}).items()
                    if key not in ("raw_path", "parsed_path")
                },
                "publication_times_known": sum(item["published_at"] is not None for item in result["items"]),
            }
        )
        print(
            source["id"],
            result["attempt"]["http_status"],
            result["source"]["status"],
            result["attempt"]["item_count"],
        )
    passed = all(result["source"]["status"] == "healthy" for result in results)
    report = {
        "checked_at": datetime.now(UTC).isoformat(),
        "synthetic": False,
        "storage": str(args.storage.resolve()),
        "results": results,
        "passed": passed,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
