"""Synthetic provider, real evaluation worker/create_agent/MySQL integration.

These tests certify fixed-input execution and persistence, not a live model's
quality or a real judge's relevance/faithfulness scores. No outbox is created.
"""

import json
import shutil
from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from test_harness_runtime import ScriptedModel, ai_call

from zhigenews import execution
from zhigenews.contract import schema, validate
from zhigenews.db import Brief, Delivery, MessageJournal, Outbox, Resource, Run, iso, transaction, utcnow
from zhigenews.evaluation import freeze_dataset
from zhigenews.harness import mysql_persistence
from zhigenews.security import encrypt
from zhigenews.settings import get_settings

pytestmark = pytest.mark.mysql
FIXED_AT = "2026-01-02T01:00:00Z"


def final_response():
    return ai_call(
        "BriefOutput",
        {
            "title": "Synthetic evaluation result",
            "items": [
                {
                    "evidence_id": "synthetic-evidence-1",
                    "summary": "Synthetic source-backed Agent summary",
                    "reason": "Matches the fixed Agent preference",
                    "topic": "Agent",
                }
            ],
        },
        "synthetic-evaluation-final",
    )


@pytest.fixture
def evaluation_case():
    suffix = uuid4().hex[:20]
    evaluation_id, case_id, snapshot_id = (
        prefix + suffix for prefix in ("exec_eval_", "exec_case_", "exec_snap_")
    )
    user_namespace = "evaluation-" + evaluation_id
    case_run_id = evaluation_id + "-" + case_id
    preferences = dict(version=1, role="Synthetic evaluation reader", topics=["Agent"], keywords=[])
    config = dict(
        id="synthetic-eval-config",
        name="Synthetic evaluation configuration",
        version="synthetic-eval-v1",
        status="published",
        modelId="synthetic-eval-model",
        summaryModelId="synthetic-eval-model",
        maxSteps=13,
        maxSeconds=60,
        summaryRatio=0.9,
        subagentConcurrency=0,
        tools=["list_dir", "read_file", "search_content", "web_search", "delegate_research"],
        systemPrompt="Synthetic evaluation: use only the supplied fixed Agent evidence.",
    )
    evidence = [
        {
            "id": "synthetic-evidence-1",
            "title": "Synthetic fixed Agent source",
            "summary": "Synthetic frozen evidence",
            "source": "Synthetic RSS",
            "source_type": "rss",
            "url": "https://example.com/synthetic-fixed-agent",
            "published_at": "2026-01-02T00:05:00Z",
            "fetched_at": "2026-01-02T00:10:00Z",
            "snapshot_id": snapshot_id,
        }
    ]
    case = dict(
        id=case_id,
        revision=1,
        name="Synthetic frozen case",
        preference="Follow Agent engineering",
        expected="Cite only the fixed Agent evidence",
        preferenceSnapshot=preferences,
        fixedAt=FIXED_AT,
        sourceSnapshotIds=[snapshot_id],
    )
    snapshots = {snapshot_id: evidence}
    frozen = freeze_dataset([case], snapshots)
    model = {
        "data": dict(
            id="synthetic-eval-model",
            name="Synthetic provider",
            modelId="synthetic",
            endpoint="https://fixture.invalid/v1",
            contextWindow=32000,
        ),
        "encryptedSecret": encrypt("synthetic-evaluation-key"),
    }
    data = dict(
        id=evaluation_id,
        name="Synthetic integration experiment",
        configVersion=config["version"],
        status="queued",
        relevance=None,
        faithfulness=None,
        citations=None,
        cost=None,
        latency=None,
        cases=1,
        createdAt=iso(utcnow()),
        datasetVersion=frozen.version,
        scorerVersion="rules-v1",
        modelId=config["modelId"],
        results=[],
    )
    private = dict(
        snapshot=dict(cases=[deepcopy(case)], sources=deepcopy(snapshots)),
        config=config,
        models={"modelId": model, "summaryModelId": model},
        judge=None,
    )
    with transaction() as session:
        session.add(Resource(id=case_id, kind="case", data=case))
        session.add(
            Resource(
                id=snapshot_id,
                kind="snapshot",
                data={"snapshot_id": snapshot_id},
                private={"items": evidence},
            )
        )
        session.add(Resource(id=evaluation_id, kind="evaluation", data=data, private=private))
    settings = get_settings()
    with mysql_persistence(settings.database_url, setup=True):
        pass
    authorized_root = (settings.data_dir.resolve() / "evaluations").resolve()
    target = (authorized_root / evaluation_id).resolve()
    fixture = SimpleNamespace(
        id=evaluation_id,
        case_id=case_id,
        snapshot_id=snapshot_id,
        run_id=case_run_id,
        namespace=user_namespace,
        thread_key=user_namespace + ":" + case_run_id,
        workspace=target / case_id / "workspace",
        frozen=deepcopy(private["snapshot"]),
        dataset_version=frozen.version,
        preferences=preferences,
    )
    try:
        yield fixture
    finally:
        with mysql_persistence(settings.database_url) as saver:
            saver.delete_thread(fixture.thread_key)
        with transaction() as session:
            session.execute(delete(Outbox).where(Outbox.target_id == evaluation_id))
            session.execute(delete(MessageJournal).where(MessageJournal.thread_id == case_run_id))
            session.execute(delete(Resource).where(Resource.id.in_([evaluation_id, case_id, snapshot_id])))
        # Only remove the exact server-generated directory created by this fixture.
        assert target.is_relative_to(authorized_root) and target.name == evaluation_id
        assert evaluation_id.startswith("exec_eval_")
        if target.exists():
            shutil.rmtree(target)


def persisted(case):
    with transaction() as session:
        row = session.get(Resource, case.id)
        return SimpleNamespace(
            data=deepcopy(row.data), private=deepcopy(row.private), lease_until=row.lease_until
        )


def assert_no_publication(case):
    with transaction() as session:
        assert session.scalar(select(func.count()).select_from(Brief).where(Brief.run_id == case.run_id)) == 0
        assert (
            session.scalar(
                select(func.count()).select_from(Delivery).where(Delivery.user_id == case.namespace)
            )
            == 0
        )
        assert session.get(Run, case.run_id) is None
        assert (
            session.scalar(
                select(func.count()).select_from(Outbox).where(Outbox.target_id.in_([case.id, case.run_id]))
            )
            == 0
        )


def test_evaluation_executes_frozen_case_with_real_agent_and_persists_unknown_judge_metrics(
    evaluation_case, monkeypatch
):
    case = evaluation_case
    # The editable case changes after enqueue; the evaluation's private copy
    # must retain its original preference, revision, source and fixed clock.
    with transaction() as session:
        editable = session.get(Resource, case.case_id)
        editable.data = {
            **editable.data,
            "revision": 2,
            "preference": "UNRELATED-LIVE-CASE",
            "sourceSnapshotIds": [],
            "fixedAt": "2026-09-19T00:00:00Z",
            "preferenceSnapshot": dict(version=2, role="", topics=["UNRELATED-LIVE-CASE"], keywords=[]),
        }
    model = ScriptedModel(
        responses=[
            ai_call("read_file", {"path": "/news/fixed/records.jsonl"}, "synthetic-evaluation-read"),
            final_response(),
        ]
    )
    monkeypatch.setattr(execution, "model_from", lambda *args, **kwargs: model)
    execution.execute_evaluation(case.id)
    result = persisted(case)
    validate(schema("Evaluation"), result.data, output=True)
    assert result.data["status"] == "completed" and model.position == 2
    assert result.data["datasetVersion"] == case.dataset_version
    assert result.data["configVersion"] == "synthetic-eval-v1"
    assert result.data["results"][0]["caseRevision"] == 1
    assert result.private["snapshot"] == case.frozen
    assert result.lease_until is None
    assert result.data["citations"] == 100
    assert result.data["relevance"] is None and result.data["faithfulness"] is None
    assert result.data["cost"] is None
    scores = {score["metric"]: score for score in result.data["results"][0]["scores"]}
    assert scores["freshness"]["value"] == 100  # January source is fresh relative to the fixed January clock.
    for metric in ("relevance", "faithfulness"):
        assert scores[metric]["method"] == "llm"
        assert scores[metric]["value"] is None and scores[metric]["passed"] is None
        assert scores[metric]["error"] == "JUDGE_NOT_CONFIGURED"
    assert "2026-01-02T01:00:00+00:00" in str(model.received)
    assert "UNRELATED-LIVE-CASE" not in str(model.received)
    assert json.loads((case.workspace / "inputs" / "preferences.json").read_text("utf-8")) == case.preferences
    actual_evidence = [
        json.loads(line)
        for line in (case.workspace.parent / "news" / "records.jsonl").read_text("utf-8").splitlines()
    ]
    assert actual_evidence == case.frozen["sources"][case.snapshot_id]
    assert not (case.workspace / "inputs" / "evidence.jsonl").exists()
    assert "evidence_index" not in str(model.received[0])
    artifact = json.loads((case.workspace / "output" / "brief.json").read_text("utf-8"))
    assert artifact["items"][0]["snapshotId"] == case.snapshot_id
    with mysql_persistence(get_settings().database_url) as saver:
        checkpoint = saver.get_tuple({"configurable": {"thread_id": case.thread_key}})
        assert checkpoint is not None
        assert checkpoint.checkpoint["channel_values"]["messages"]
    assert_no_publication(case)
    before = deepcopy(result.data)
    execution.execute_evaluation(case.id)
    assert model.position == 2 and persisted(case).data == before


class FailingEvaluationModel(ScriptedModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.position += 1
        raise RuntimeError("Synthetic provider failure sk-synthetic-evaluation-secret")


def test_evaluation_provider_failure_persists_failed_case_and_null_scores_without_publication(
    evaluation_case, monkeypatch
):
    case = evaluation_case
    model = FailingEvaluationModel(responses=[final_response()])
    monkeypatch.setattr(execution, "model_from", lambda *args, **kwargs: model)
    execution.execute_evaluation(case.id)
    result = persisted(case)
    validate(schema("Evaluation"), result.data, output=True)
    assert model.position == 1 and result.data["status"] == "failed"
    assert result.data["results"][0]["status"] == "failed"
    assert result.lease_until is None
    assert all(result.data[metric] is None for metric in ("relevance", "faithfulness", "citations", "cost"))
    for score in result.data["results"][0]["scores"]:
        if score["metric"] != "latency":
            assert score["value"] is None and score["passed"] is None
            assert score["error"] == "GENERATION_FAILED"
    assert "synthetic-evaluation-secret" not in json.dumps(result.data)
    assert_no_publication(case)
    execution.execute_evaluation(case.id)
    assert model.position == 1
