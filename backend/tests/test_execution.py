"""Synthetic model, real create_agent/MySQL/files/publication integration.

Only the external model factory is replaced. These checks do not certify a live
provider, Tavily, news quality, or real-model evaluation scores.
"""

import json
import shutil
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from test_harness_runtime import ScriptedModel, ai_call

from zhigenews import execution
from zhigenews.application import progress, public_brief
from zhigenews.contract import schema, validate
from zhigenews.db import (
    Brief,
    Delivery,
    MessageJournal,
    Outbox,
    Resource,
    Run,
    RunEvent,
    User,
    transaction,
    utcnow,
)
from zhigenews.harness import UserMemory, mysql_persistence
from zhigenews.security import encrypt
from zhigenews.settings import get_settings
from zhigenews.workers import publish_delivery

pytestmark = pytest.mark.mysql
FIXED_AT = "2026-01-02T01:00:00Z"


def final_response(*, empty=False):
    return ai_call(
        "BriefOutput",
        {
            "title": "Synthetic no-match brief" if empty else "Synthetic execution brief",
            "items": []
            if empty
            else [
                {
                    "evidence_id": "synthetic-evidence-1",
                    "summary": "Synthetic source-backed summary",
                    "reason": "Matches the explicit Agent topic",
                    "topic": "Agent",
                }
            ],
        },
        "synthetic-final",
    )


@pytest.fixture
def execution_case():
    suffix = uuid4().hex[:20]
    user_id, run_id = "exec_user_" + suffix, "exec_run_" + suffix
    preferences = dict(version=1, role="Synthetic integration reader", topics=["Agent"], keywords=[])
    config = dict(
        id="synthetic-config",
        name="Synthetic integration config",
        version="synthetic-v1",
        status="published",
        modelId="synthetic-model",
        summaryModelId="synthetic-model",
        maxModelCalls=6,
        maxToolCalls=6,
        maxSeconds=60,
        summaryTokens=12000,
        summaryMessages=30,
        summaryRatio=0.7,
        subagentConcurrency=0,
        tools=["list_dir", "read_file", "search_content"],
        systemPrompt="Synthetic integration test: use the fixed supplied Agent evidence.",
    )
    evidence = [
        {
            "id": "synthetic-evidence-1",
            "title": "Synthetic Agent source",
            "summary": "Synthetic evidence",
            "source": "Synthetic RSS",
            "source_type": "rss",
            "url": "https://example.com/synthetic-agent",
            "published_at": "2026-01-02T00:05:00Z",
            "fetched_at": "2026-01-02T00:10:00Z",
            "snapshot_id": "synthetic-snapshot",
        }
    ]
    model = {
        "data": dict(
            id="synthetic-model",
            name="Synthetic model",
            modelId="synthetic",
            endpoint="https://fixture.invalid/v1",
            contextWindow=32000,
        ),
        "encryptedSecret": encrypt("synthetic-model-key"),
    }
    future_slot = (utcnow() + timedelta(days=1)).replace(microsecond=0)
    with transaction() as session:
        session.add(
            User(
                id=user_id,
                name="Synthetic execution reader",
                role="anonymous",
                onboarding=True,
                preference=preferences,
                next_run_at=future_slot,
            )
        )
        session.flush()
        session.add(
            Run(
                id=run_id,
                user_id=user_id,
                business_key="synthetic:" + suffix,
                status="queued",
                preferences=preferences,
                config=config,
                private={
                    "models": {"modelId": model, "summaryModelId": model},
                    "evidence": evidence,
                    "snapshotIds": ["synthetic-snapshot"],
                    "missingSources": [],
                    "fixedAt": FIXED_AT,
                },
            )
        )
    settings = get_settings()
    with mysql_persistence(settings.database_url, setup=True):
        pass
    run_root = settings.data_dir.resolve() / "runs" / user_id / run_id
    case = SimpleNamespace(
        user_id=user_id,
        run_id=run_id,
        root=run_root,
        workspace=run_root / "workspace",
        future_slot=future_slot,
    )
    try:
        yield case
    finally:
        with mysql_persistence(settings.database_url) as (saver, store):
            saver.delete_thread(user_id + ":" + run_id)
            for item in UserMemory(store, user_id).list():
                UserMemory(store, user_id).delete(item["id"])
        with transaction() as session:
            delivery_ids = list(session.scalars(select(Delivery.id).where(Delivery.user_id == user_id)))
            session.execute(delete(Outbox).where(Outbox.target_id.in_([run_id, *delivery_ids])))
            session.execute(delete(Delivery).where(Delivery.user_id == user_id))
            session.execute(delete(Brief).where(Brief.user_id == user_id))
            session.execute(delete(RunEvent).where(RunEvent.run_id == run_id))
            session.execute(delete(MessageJournal).where(MessageJournal.thread_id == run_id))
            session.execute(delete(Run).where(Run.id == run_id))
            session.execute(delete(Resource).where(Resource.owner_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
        # Remove only this fixture's server-generated directory under the configured run root.
        authorized_root = (settings.data_dir.resolve() / "runs").resolve()
        target = (authorized_root / user_id).resolve()
        assert target.is_relative_to(authorized_root) and target.name == user_id
        assert user_id.startswith("exec_user_")
        if target.exists():
            shutil.rmtree(target)


def patch_model(monkeypatch, model):
    monkeypatch.setattr(execution, "model_from", lambda *args, **kwargs: model)
    return model


def rows(case):
    with transaction() as session:
        run = session.get(Run, case.run_id)
        briefs = list(session.scalars(select(Brief).where(Brief.run_id == case.run_id)))
        deliveries = list(session.scalars(select(Delivery).where(Delivery.user_id == case.user_id)))
        events = list(
            session.scalars(select(RunEvent).where(RunEvent.run_id == case.run_id).order_by(RunEvent.seq))
        )
        journal = list(
            session.scalars(
                select(MessageJournal)
                .where(MessageJournal.thread_id == case.run_id)
                .order_by(MessageJournal.message_seq)
            )
        )
        return SimpleNamespace(run=run, briefs=briefs, deliveries=deliveries, events=events, journal=journal)


def test_real_harness_saves_artifacts_then_publication_confirms_completion(execution_case, monkeypatch):
    case = execution_case
    model = patch_model(
        monkeypatch,
        ScriptedModel(
            responses=[
                ai_call("list_dir", {"path": "/workspace/inputs"}, "synthetic-list"),
                ai_call("read_file", {"path": "/workspace/inputs/evidence.jsonl"}, "synthetic-read"),
                final_response(),
            ]
        ),
    )
    execution.execute_run(case.run_id)
    snapshot = rows(case)
    assert snapshot.run.status == "running", [event.data for event in snapshot.events]
    assert snapshot.run.percent == 95 and snapshot.run.brief_id is None
    validate(schema("GenerationProgress"), progress(snapshot.run), output=True)
    assert len(snapshot.briefs) == len(snapshot.deliveries) == 1
    brief, delivery = snapshot.briefs[0], snapshot.deliveries[0]
    assert not brief.published and delivery.status == "pending"
    assert brief.data["items"][0]["publishedAt"] == "2026-01-02T00:05:00Z"
    assert model.position == 3 and "2026-01-02T01:00:00+00:00" in str(model.received)
    artifact = json.loads((case.workspace / "output" / "brief.json").read_text("utf-8"))
    assert artifact["items"] == brief.data["items"]
    assert (case.workspace / "output" / "brief.md").is_file()
    published = publish_delivery(delivery.id)
    assert published["status"] == "submitted"
    final = rows(case)
    assert final.run.status == "completed" and final.run.percent == 100
    assert final.run.brief_id == brief.id and final.run.remaining_seconds == 0
    assert final.briefs[0].published and final.deliveries[0].attempts == 1
    validate(schema("Brief"), public_brief(final.briefs[0]), output=True)
    publish_delivery(delivery.id)
    assert rows(case).deliveries[0].attempts == 1


def test_no_match_remains_empty_instead_of_fabricating_news(execution_case, monkeypatch):
    case = execution_case
    with transaction() as session:
        run = session.get(Run, case.run_id)
        run.private = {**run.private, "evidence": [], "snapshotIds": []}
    patch_model(monkeypatch, ScriptedModel(responses=[final_response(empty=True)]))
    execution.execute_run(case.run_id)
    snapshot = rows(case)
    assert snapshot.run.percent == 95, [event.data for event in snapshot.events]
    assert snapshot.briefs[0].data["items"] == []
    publish_delivery(snapshot.deliveries[0].id)
    final = rows(case)
    assert final.run.percent == 100 and final.briefs[0].data["items"] == []


def test_tool_error_can_be_handled_by_real_model_tool_loop(execution_case, monkeypatch):
    model = patch_model(
        monkeypatch,
        ScriptedModel(
            responses=[
                ai_call("read_file", {"path": "/workspace/inputs/missing.json"}, "synthetic-missing"),
                final_response(),
            ]
        ),
    )
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert model.position == 2
    assert snapshot.run.status == "running" and snapshot.run.percent == 95
    assert any(
        event.data["status"] == "failed" and event.data.get("tool") == "read_file"
        for event in snapshot.events
    )
    assert any(
        row.data.get("toolCallId") == "synthetic-missing" and "FILE_NOT_FOUND" in row.data["content"]
        for row in snapshot.journal
    )
    assert not snapshot.briefs[0].published


def test_tool_loop_budget_failure_never_publishes_a_completed_brief(execution_case, monkeypatch):
    with transaction() as session:
        run = session.get(Run, execution_case.run_id)
        run.config = {**run.config, "maxModelCalls": 1}
    patch_model(
        monkeypatch,
        ScriptedModel(
            responses=[
                ai_call("read_file", {"path": "/workspace/inputs/missing.json"}, "synthetic-missing"),
            ]
        ),
    )
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert snapshot.run.status == "failed" and snapshot.run.percent != 100
    assert not snapshot.briefs and not snapshot.deliveries
    assert any("BUDGET_EXHAUSTED" in event.data["detail"] for event in snapshot.events)


class FailingScriptedModel(ScriptedModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.position += 1
        raise RuntimeError("Synthetic provider failure sk-synthetic-provider-secret")


def test_model_failure_keeps_unknown_usage_and_redacts_public_failure(execution_case, monkeypatch):
    patch_model(monkeypatch, FailingScriptedModel(responses=[final_response()]))
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert snapshot.run.status == "failed" and snapshot.run.brief_id is None
    assert snapshot.run.input_tokens is None and snapshot.run.cost is None
    assert not snapshot.briefs and not snapshot.deliveries
    assert "synthetic-provider-secret" not in str(progress(snapshot.run))
    assert "synthetic-provider-secret" not in str([event.data for event in snapshot.events])


def test_queued_cancellation_requires_no_model_and_preserves_daily_slot(execution_case, monkeypatch):
    model = patch_model(monkeypatch, ScriptedModel(responses=[final_response()]))
    with transaction() as session:
        run = session.get(Run, execution_case.run_id)
        run.cancel_requested, run.status = True, "cancelling"
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert snapshot.run.status == "cancelled" and model.position == 0
    assert not snapshot.briefs and not snapshot.deliveries
    with transaction() as session:
        assert session.get(User, execution_case.user_id).next_run_at == execution_case.future_slot


class CancellingScriptedModel(ScriptedModel):
    target_run: str

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        if self.position == 1:
            with transaction() as session:
                run = session.get(Run, self.target_run)
                run.cancel_requested, run.status = True, "cancelling"
        return result


def test_cancellation_during_model_call_stops_before_publication(execution_case, monkeypatch):
    model = patch_model(
        monkeypatch,
        CancellingScriptedModel(
            target_run=execution_case.run_id,
            responses=[
                ai_call("list_dir", {"path": "/workspace/inputs"}, "synthetic-before-cancel"),
                final_response(),
            ],
        ),
    )
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert snapshot.run.status == "cancelled" and snapshot.run.percent != 100
    assert model.position == 1 and not snapshot.briefs and not snapshot.deliveries


def test_existing_brief_replay_has_no_new_generation_and_preserves_journal(execution_case, monkeypatch):
    case = execution_case
    first = patch_model(
        monkeypatch,
        ScriptedModel(
            responses=[
                ai_call("list_dir", {"path": "/workspace/inputs"}, "synthetic-replay-list"),
                final_response(),
            ]
        ),
    )
    execution.execute_run(case.run_id)
    before = rows(case)
    assert before.briefs and first.position == 2
    before_journal = [(row.message_seq, row.message_id, row.data) for row in before.journal]
    assert len(before_journal) >= 4
    assert len({row[0] for row in before_journal}) == len(before_journal)
    assert len({row[1] for row in before_journal}) == len(before_journal)
    assert [row[0] for row in before_journal] == sorted(row[0] for row in before_journal)
    assert before.journal[0].data["role"] == "human"
    with transaction() as session:
        run = session.get(Run, case.run_id)
        run.lease_until = utcnow() - timedelta(seconds=1)
    replay = patch_model(monkeypatch, FailingScriptedModel(responses=[final_response()]))
    execution.execute_run(case.run_id)
    after = rows(case)
    assert replay.position == 0
    assert len(after.briefs) == len(after.deliveries) == 1 and after.briefs[0].id == before.briefs[0].id
    assert [(row.message_seq, row.message_id, row.data) for row in after.journal] == before_journal
    assert after.run.percent == 95 and not after.briefs[0].published
    with transaction() as session:
        jobs = list(
            session.scalars(
                select(Outbox).where(Outbox.kind == "delivery", Outbox.target_id == after.deliveries[0].id)
            )
        )
        assert len(jobs) == 1


def test_actual_tool_event_payloads_are_bounded_and_redacted(execution_case, monkeypatch):
    secret = "synthetic-sensitive-token"
    patch_model(
        monkeypatch,
        ScriptedModel(
            responses=[
                ai_call(
                    "search_content",
                    {
                        "query": "api_key=" + secret + " Bearer synthetic-bearer sk-synthetic-key",
                        "path": "/workspace/inputs",
                    },
                    "synthetic-redact",
                ),
                final_response(),
            ]
        ),
    )
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert snapshot.run.percent == 95
    public_events = [event.data for event in snapshot.events]
    assert any(event.get("tool") == "search_content" and "params" in event for event in public_events)
    serialized = json.dumps(public_events)
    assert all(value not in serialized for value in (secret, "synthetic-bearer", "sk-synthetic-key"))
    assert "[redacted]" in serialized
    for event in public_events:
        validate(schema("RunEvent"), event, output=True)
        assert len(event.get("params", "")) <= 4000 and len(event.get("output", "")) <= 4000
    assert set(progress(snapshot.run)) == {
        "id",
        "status",
        "percent",
        "remainingSeconds",
        "updatedAt",
        "briefId",
        "error",
    }
