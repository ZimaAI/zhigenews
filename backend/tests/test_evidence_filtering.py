"""Synthetic final responses exercise the real Harness evidence boundary."""

import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_harness_runtime import ScriptedModel, ai_call

from zhigenews.harness import HarnessRequest, HarnessRunner


def evidence(ident, **changes):
    return {
        "id": ident, "title": "保留的新闻标题", "source": "Synthetic RSS",
        "url": "https://example.test/" + ident,
        "published_at": "2026-09-18T23:00:00Z",
        "fetched_at": "2026-09-19T00:00:00Z", "snapshot_id": "snapshot",
        **changes,
    }


def response(ids):
    return ai_call("BriefOutput", {
        "title": "应被删除的原标题", "summary": "应被删除的原导语",
        "items": [
            {"evidence_id": ident, "summary": "保留的新闻摘要" if ident == "good" else "待过滤摘要",
             "reason": "Matches", "topic": "AI"}
            for ident in ids
        ],
    }, "final")


def run_brief(tmp_path, ids, records, *, resolve=None):
    model = ScriptedModel(responses=[response(ids)])
    events = []
    request = HarnessRequest(
        "u", "r", "t", {}, {"tools": ["read_file"]},
        tmp_path / "rss", tmp_path / "workspace", model,
        evidence=records, fixed_at="2026-09-19T00:00:00Z", resolve_evidence=resolve,
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request, event_sink=events.append)
    assert model.position == 1  # Filtering never asks the model to replenish the brief.
    return result, events


@pytest.mark.parametrize(("bad_record", "reason"), [
    (None, "EVIDENCE_NOT_FOUND"),
    (evidence("bad", url="not-a-url"), "INVALID_URL"),
    (evidence("bad", url="https://[broken"), "INVALID_URL"),
    (evidence("bad", url=None), "INVALID_URL"),
    (evidence("bad", url="https://example.test:bad/"), "INVALID_URL"),
    (evidence("bad", url="https://example.test/a b"), "INVALID_URL"),
    (evidence("bad", fetched_at=None), "MISSING_PROVENANCE"),
    (evidence("bad", fetched_at="not-a-time"), "MISSING_PROVENANCE"),
    (evidence("bad", snapshot_id=""), "MISSING_PROVENANCE"),
    (evidence("bad", published_at="bad-date"), "INVALID_PUBLISHED_AT"),
    (evidence("bad", published_at="2026-09-17T00:00:00Z"), "OUTSIDE_WINDOW"),
])
def test_invalid_evidence_keeps_single_valid_item_and_consistent_artifacts(tmp_path, bad_record, reason):
    result, events = run_brief(tmp_path, ["bad", "good"],
                               [evidence("good"), *([bad_record] if bad_record else [])])
    assert [item["id"] for item in result.items] == ["good"]
    assert result.title == "保留的新闻标题" and result.summary == "保留的新闻摘要"
    assert result.limitations
    report = next(event for event in events if event["type"] == "evidence_validated")
    assert json.loads(report["resultSummary"]) == {
        "submitted": 2, "retained": 1, "rejected": 1,
        "rejections": [{"evidence_id": "bad", "reason": reason}],
    }
    artifact = json.loads((tmp_path / "workspace/output/brief.json").read_text("utf-8"))
    completed = json.loads((tmp_path / ".workspace.harness/result.json").read_text("utf-8"))
    assert artifact == completed
    assert artifact["title"] == result.title and artifact["summary"] == result.summary
    assert artifact["items"] == result.items
    markdown = (tmp_path / "workspace/output/brief.md").read_text("utf-8")
    assert markdown == result.markdown
    assert "应被删除" not in markdown and "待过滤摘要" not in markdown
    assert "INVALID" not in markdown and "证据" not in markdown


def test_all_invalid_evidence_returns_empty_result_with_diagnostics(tmp_path):
    result, events = run_brief(tmp_path, ["missing", "bad"], [evidence("bad", url="ftp://example.test/a")])
    assert result.items == [] and result.limitations
    assert result.title == "暂无可用新闻" and result.summary == "本次暂无可发布的新闻。"
    assert "应被删除" not in result.markdown
    report = json.loads(next(e["resultSummary"] for e in events if e["type"] == "evidence_validated"))
    assert (report["submitted"], report["retained"], report["rejected"]) == (2, 0, 2)


def test_duplicate_filters_without_hiding_later_valid_provenance(tmp_path):
    result, events = run_brief(tmp_path, ["bad", "good", "duplicate"], [
        evidence("bad", url="https://example.test/good", snapshot_id=None), evidence("good"),
        evidence("duplicate", url="https://example.test/good#section"),
    ])
    assert [item["id"] for item in result.items] == ["good"]
    report = json.loads(next(e["resultSummary"] for e in events if e["type"] == "evidence_validated"))
    assert [r["reason"] for r in report["rejections"]] == ["MISSING_PROVENANCE", "DUPLICATE_URL"]


def test_resolver_infrastructure_error_is_not_treated_as_bad_evidence(tmp_path):
    def resolve(ident):
        raise OSError("Synthetic storage unavailable")

    with pytest.raises(OSError, match="Synthetic storage unavailable"):
        run_brief(tmp_path, ["bad", "good"], [evidence("good")], resolve=resolve)


@pytest.mark.parametrize("ids", [[], ["good"]])
def test_unfiltered_output_preserves_editorial_copy(tmp_path, ids):
    result, _ = run_brief(tmp_path, ids, [evidence("good")])
    assert result.title == "应被删除的原标题" and result.summary == "应被删除的原导语"
    assert result.limitations == []
