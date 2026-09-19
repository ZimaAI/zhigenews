"""Fixed-input evaluation, deliberately independent of publishing and HTTP state."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urldefrag

SCORER_VERSION = "rules-v1"
RULE_METRICS = ("freshness", "deduplication", "sourceCoverage", "citationAccuracy")


class EvaluationInputError(ValueError):
    """A fixed dataset cannot be constructed from the supplied records."""


@dataclass(frozen=True)
class FrozenDataset:
    version: str
    cases: tuple[dict[str, Any], ...]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise EvaluationInputError("Fixed evaluation times must include a timezone")
    return parsed.astimezone(timezone.utc)


def freeze_dataset(
    cases: Sequence[Mapping[str, Any]],
    snapshots: Mapping[str, Sequence[Mapping[str, Any]]],
) -> FrozenDataset:
    """Copy the exact cases and evidence; never refresh a missing or empty snapshot."""
    if not cases:
        raise EvaluationInputError("EMPTY_DATASET")
    frozen: list[dict[str, Any]] = []
    for original in sorted(cases, key=lambda row: str(row["id"])):
        row = copy.deepcopy(dict(original))
        _instant(row["fixedAt"])
        if not isinstance(row["revision"], int) or row["revision"] < 1:
            raise EvaluationInputError("INVALID_CASE_REVISION")
        evidence: list[dict[str, Any]] = []
        for snapshot_id in row["sourceSnapshotIds"]:
            if snapshot_id not in snapshots:
                raise EvaluationInputError(f"MISSING_SNAPSHOT:{snapshot_id}")
            evidence.extend(copy.deepcopy(list(snapshots[snapshot_id])))
        row["evidence"] = evidence
        frozen.append(row)
    digest = hashlib.sha256(_canonical(frozen).encode()).hexdigest()
    return FrozenDataset(f"dataset-{digest}", tuple(frozen))


def _score(
    metric: str,
    method: str,
    value: float | None,
    maximum: float | None = 100,
    passed: bool | None = None,
    error: str = "",
) -> dict[str, Any]:
    return dict(metric=metric, method=method, value=value, maximum=maximum, passed=passed, error=error)


def _url(value: Any) -> str:
    return urldefrag(str(value or "").strip())[0]


def rule_scores(
    case: Mapping[str, Any], generated_items: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Measure observable properties; rules never claim semantic faithfulness."""
    if not generated_items:
        return [_score(metric, "rule", None) for metric in RULE_METRICS]
    evidence = case["evidence"]
    evidence_by_url = {_url(item.get("url")): item for item in evidence if _url(item.get("url"))}
    evidence_urls = set(evidence_by_url)
    available_sources = {str(item.get("source", "")) for item in evidence} - {""}
    fixed_at = _instant(case["fixedAt"])
    earliest = fixed_at - timedelta(hours=24)
    fresh = 0
    valid_citations = 0
    unique_items = 0
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    covered_sources: set[str] = set()
    for item in generated_items:
        published = item.get("publishedAt")
        if published:
            try:
                fresh += earliest <= _instant(str(published)) <= fixed_at
            except (ValueError, TypeError):
                pass
        url = _url(item.get("url"))
        title = " ".join(str(item.get("title", "")).casefold().split())
        if (not url or url not in seen_urls) and (not title or title not in seen_titles):
            unique_items += 1
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        citations = item.get("citations") or []
        citation_urls = [_url(citation.get("url")) for citation in citations]
        supported = url in evidence_urls and bool(citation_urls) and all(
            citation_url in evidence_urls for citation_url in citation_urls
        )
        valid_citations += supported
        if supported:
            source = str(evidence_by_url[url].get("source", ""))
            if source in available_sources:
                covered_sources.add(source)
    count = len(generated_items)
    return [
        _score("freshness", "rule", fresh / count * 100, passed=fresh == count),
        _score("deduplication", "rule", unique_items / count * 100, passed=unique_items == count),
        _score("sourceCoverage", "rule", len(covered_sources) / len(available_sources) * 100 if available_sources else None),
        _score("citationAccuracy", "rule", valid_citations / count * 100, passed=valid_citations == count),
    ]


def _judge_scores(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    scores = []
    for metric in ("relevance", "faithfulness"):
        value = raw.get(metric)
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        valid = valid and math.isfinite(value) and 0 <= value <= 5
        scores.append(_score(metric, "llm", float(value) if valid else None, maximum=5, error="" if valid else "INVALID_JUDGE_SCORE"))
    return scores


def evaluate_dataset(
    dataset: FrozenDataset,
    *,
    evaluation_id: str,
    name: str,
    config_version: str,
    model_id: str,
    generate: Callable[[dict[str, Any]], Mapping[str, Any]],
    judge: Callable[[dict[str, Any], Sequence[Mapping[str, Any]]], Mapping[str, Any]] | None = None,
    scorer_version: str = SCORER_VERSION,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Run only supplied callbacks against copied inputs; no publication capability.

    ``generate`` returns items plus optional true cost. It must use the supplied
    evidence and fixedAt; worker assembly disables network search for this run.
    The worker persists this returned DTO and the dataset before executing it.
    """
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    costs: list[float | None] = []
    for original in dataset.cases:
        case = copy.deepcopy(original)
        scores: list[dict[str, Any]] = []
        case_started = time.monotonic()
        status = "completed"
        case_cost: float | None = None
        try:
            generated = generate(copy.deepcopy(case))
            items = generated["items"]
            if not isinstance(items, (list, tuple)):
                raise ValueError("Invalid generated items")
            scores.extend(rule_scores(case, items))
            cost = generated.get("cost")
            if not isinstance(cost, (int, float)) or isinstance(cost, bool) or not math.isfinite(cost) or cost < 0:
                cost = None
            case_cost = cost
            if judge is None:
                scores.extend(_score(metric, "llm", None, maximum=5, error="JUDGE_NOT_CONFIGURED") for metric in ("relevance", "faithfulness"))
            else:
                try:
                    judged = judge(copy.deepcopy(case), copy.deepcopy(items))
                    scores.extend(_judge_scores(judged))
                    judge_cost = judged.get("cost")
                    valid_cost = isinstance(judge_cost, (int, float)) and not isinstance(judge_cost, bool)
                    valid_cost = valid_cost and math.isfinite(judge_cost) and judge_cost >= 0
                    case_cost = case_cost + judge_cost if case_cost is not None and valid_cost else None
                except Exception:
                    case_cost = None
                    scores.extend(_score(metric, "llm", None, maximum=5, error="JUDGE_UNAVAILABLE") for metric in ("relevance", "faithfulness"))
            scores.append(_score("cost", "rule", case_cost, maximum=None))
        except Exception:
            status = "failed"
            case_cost = None
            scores = [_score(metric, "rule", None, error="GENERATION_FAILED") for metric in RULE_METRICS]
            scores.extend(_score(metric, "llm", None, maximum=5, error="GENERATION_FAILED") for metric in ("relevance", "faithfulness"))
        scores.append(_score("latency", "rule", time.monotonic() - case_started, maximum=None))
        costs.append(case_cost)
        results.append(dict(caseId=case["id"], caseRevision=case["revision"], status=status, scores=scores))

    def average(metric: str, method: str) -> float | None:
        values = [score["value"] for row in results for score in row["scores"] if score["metric"] == metric and score["method"] == method and score["value"] is not None]
        return sum(values) / len(values) if values else None

    return dict(
        id=evaluation_id,
        name=name,
        configVersion=config_version,
        status="completed" if all(row["status"] == "completed" for row in results) else "failed",
        relevance=average("relevance", "llm"),
        faithfulness=average("faithfulness", "llm"),
        citations=average("citationAccuracy", "rule"),
        cost=sum(costs) if costs and all(cost is not None for cost in costs) else None,
        latency=time.monotonic() - started,
        cases=len(dataset.cases),
        createdAt=created_at or datetime.now(timezone.utc).isoformat(),
        datasetVersion=dataset.version,
        scorerVersion=scorer_version,
        modelId=model_id,
        results=results,
    )


def evaluate_record(
    evaluation: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    generate: Callable[[dict[str, Any]], Mapping[str, Any]],
    judge: Callable[[dict[str, Any], Sequence[Mapping[str, Any]]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Worker adapter for an already-persisted evaluation snapshot.

    The private ``snapshot`` object contains ``cases`` and ``sources``; sources
    maps each immutable snapshot ID to normalized evidence records. Neither is
    copied into the public DTO. Config must be the creation-time config snapshot.
    """
    snapshot = evaluation["snapshot"]
    dataset = freeze_dataset(snapshot["cases"], snapshot["sources"])
    expected_version = evaluation.get("datasetVersion")
    if expected_version is not None and expected_version != dataset.version:
        raise EvaluationInputError("DATASET_CHANGED")
    return evaluate_dataset(
        dataset,
        evaluation_id=evaluation["id"],
        name=evaluation["name"],
        config_version=evaluation["configVersion"],
        model_id=config["modelId"],
        generate=generate,
        judge=judge,
        scorer_version=evaluation.get("scorerVersion", SCORER_VERSION),
        created_at=evaluation.get("createdAt"),
    )
