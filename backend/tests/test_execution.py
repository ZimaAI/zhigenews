"""Synthetic model, real create_agent/MySQL/files/publication integration.

Only the external model factory is replaced. These checks do not certify a live
provider, Tavily, news quality, or real-model evaluation scores.
"""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import Client, MockTransport, Request, Response
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai.chat_models.base import OpenAITimeoutError
from openai import APITimeoutError
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
from zhigenews.harness import mysql_persistence
from zhigenews.ingestion import fetch_source
from zhigenews.models import tool_model_options
from zhigenews.security import encrypt
from zhigenews.settings import get_settings
from zhigenews.workers import publish_delivery

pytestmark = pytest.mark.mysql
FIXED_AT = "2026-01-02T01:00:00Z"


def final_response(*, empty=False, evidence_id="synthetic-evidence-1", limitations=None):
    return ai_call(
        "BriefOutput",
        {
            "title": "Synthetic no-match brief" if empty else "Synthetic execution brief",
            "summary": "暂无相关新闻。" if empty else "新工具让新闻整理更方便。",
            "limitations": limitations or [],
            "items": []
            if empty
            else [
                {
                    "evidence_id": evidence_id,
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
        maxSteps=13,
        maxSeconds=60,
        summaryRatio=0.9,
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
        with mysql_persistence(settings.database_url) as saver:
            saver.delete_thread(user_id + ":" + run_id)
        with transaction() as session:
            delivery_ids = list(session.scalars(select(Delivery.id).where(Delivery.user_id == user_id)))
            session.execute(delete(Outbox).where(Outbox.target_id.in_([run_id, *delivery_ids])))
            session.execute(delete(Delivery).where(Delivery.user_id == user_id))
            session.execute(delete(Brief).where(Brief.user_id == user_id))
            session.execute(delete(RunEvent).where(RunEvent.run_id == run_id))
            session.execute(delete(MessageJournal).where(MessageJournal.thread_id == run_id))
            session.execute(delete(Run).where(Run.user_id == user_id))
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
                ai_call("list_dir", {"path": "/news/fixed"}, "synthetic-list"),
                ai_call("read_file", {"path": "/news/fixed/records.jsonl"}, "synthetic-read"),
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


@pytest.mark.parametrize("legacy_layout", [False, True])
def test_new_run_discovers_collected_news_without_preloading_and_uses_actual_start(
    execution_case, monkeypatch, tmp_path, legacy_layout,
):
    case = execution_case
    started = datetime.now(UTC).replace(microsecond=0)
    published = started - timedelta(hours=1)
    source = dict(
        id="exsrc_" + case.run_id[-10:], name="Synthetic discovery RSS",
        kind="rss", source_id="", url="https://fixture.invalid/feed", configured_interval_seconds=300,
    )
    body = (
        '<rss version="2.0"><channel><title>Synthetic feed</title><item>'
        '<guid>agent-discovery</guid><title>Agent source discovery</title>'
        '<link>https://example.com/agent-discovery</link>'
        '<description>Source text only available through news files</description>'
        f'<pubDate>{published.strftime("%a, %d %b %Y %H:%M:%S +0000")}</pubDate>'
        '</item></channel></rss>'
    ).encode()
    with monkeypatch.context() as patch:
        if legacy_layout:
            patch.setattr("zhigenews.ingestion.service._source_dir", lambda s, storage: storage / s["kind"] / s["id"])
            patch.setattr("zhigenews.ingestion.service._maintain_source_index", lambda *args: None)
        with Client(transport=MockTransport(lambda request: Response(200, content=body))) as client:
            collected = fetch_source(source, tmp_path, client=client, now=started)
            disabled = {**source, "id": source["id"] + "_disabled", "name": "Synthetic disabled RSS"}
            fetch_source(disabled, tmp_path, client=client, now=started)
    item = collected["items"][0]
    with transaction() as session:
        session.add(Resource(
            id=source["id"], owner_id=case.user_id, kind="source",
            data={"id": source["id"], "name": source["name"], "kind": "rss", "sourceId": "",
                  "url": source["url"], "status": "healthy", "interval": 300, "snapshotId": item["snapshot_id"]},
        ))
        session.add(Resource(
            id=item["snapshot_id"], owner_id=case.user_id, kind="snapshot",
            data=collected["snapshot"], private={"items": collected["items"]},
        ))
        session.add(Resource(
            id=disabled["id"], owner_id=case.user_id, kind="source",
            data={"id": disabled["id"], "name": disabled["name"], "kind": "rss", "sourceId": "",
                  "url": disabled["url"], "status": "disabled", "interval": 300},
        ))
        run = session.get(Run, case.run_id)
        run.private = {"models": run.private["models"]}
        run.created_at = (started - timedelta(days=3)).replace(tzinfo=None)
    settings = get_settings().model_copy(update={"data_dir": tmp_path})
    monkeypatch.setattr(execution, "get_settings", lambda: settings)
    monkeypatch.setattr(execution, "utcnow", lambda: started.replace(tzinfo=None))
    if legacy_layout:
        from zhigenews import workers

        monkeypatch.setattr(workers, "get_settings", lambda: settings)
        assert source["id"] in workers.migrate_news_indexes()["migratedSources"]
    before = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()}
    model = patch_model(monkeypatch, ScriptedModel(responses=[
        ai_call("list_dir", {"path": "/news"}, "discover-sources"),
        ai_call("read_file", {"path": f"/news/{source['id']}/index.json"}, "discover-source"),
        final_response(evidence_id=item["evidence_id"]),
    ]))
    execution.execute_run(case.run_id)
    state = rows(case)
    assert state.briefs and len(state.briefs[0].data["items"]) == 1, [e.data for e in state.events]
    assert state.briefs[0].data["items"][0]["url"] == item["url"]
    initial = next(m for m in model.received[0] if isinstance(m, HumanMessage))
    payload = json.loads(initial.content.split("\n", 1)[1])
    assert payload["fixedAt"] == started.isoformat()
    assert "evidence_index" not in payload and item["title"] not in initial.content
    assert "evidence" not in state.run.private
    listing = next(m for m in model.received[1] if isinstance(m, ToolMessage))
    assert source["id"] in listing.content and disabled["id"] not in listing.content
    assert any(isinstance(m, ToolMessage) and item["title"] in m.content for m in model.received[2])
    after = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file() and "runs" not in p.parts}
    assert after == before
    workspace = tmp_path / "runs" / case.user_id / case.run_id / "workspace"
    assert not (workspace / "inputs" / "evidence.jsonl").exists()


@pytest.mark.parametrize("has_previous", [False, True])
@pytest.mark.parametrize("filtered", [False, True])
def test_no_match_remains_empty_instead_of_fabricating_news(execution_case, monkeypatch, has_previous, filtered):
    case = execution_case
    with transaction() as session:
        run = session.get(Run, case.run_id)
        if filtered:
            evidence = [{**item, "published_at": "2025-01-01T00:00:00Z"} for item in run.private["evidence"]]
            run.private = {**run.private, "evidence": evidence}
        else:
            run.private = {**run.private, "evidence": [], "snapshotIds": []}
        if has_previous:
            session.add(Run(id=case.run_id + "old", user_id=case.user_id, business_key=case.run_id + "old",
                            status="completed", preferences=run.preferences, config=run.config, private={}))
            session.flush()
            session.add(Brief(id=case.run_id + "old", user_id=case.user_id, run_id=case.run_id + "old",
                              date="2026-01-01", version=1, published=True,
                              data={"title": "Previous brief", "items": [{"id": "old-news"}]}))
    patch_model(monkeypatch, ScriptedModel(responses=[final_response(empty=not filtered)]))
    execution.execute_run(case.run_id)
    snapshot = rows(case)
    assert snapshot.run.status == ("partial" if filtered else "completed"), [event.data for event in snapshot.events]
    assert snapshot.run.percent == 100 and snapshot.run.lease_token is None
    assert not snapshot.briefs and not snapshot.deliveries
    assert progress(snapshot.run)["emptyResult"] and progress(snapshot.run)["briefId"] is None
    execution.execute_run(case.run_id)  # Replay must not create an empty edition either.
    with transaction() as session:
        previous = list(session.scalars(select(Brief).where(Brief.user_id == case.user_id)))
        assert len(previous) == int(has_previous)
        if has_previous:
            assert previous[0].published and previous[0].data == {"title": "Previous brief", "items": [{"id": "old-news"}]}
        assert not list(session.scalars(select(Outbox).where(Outbox.target_id == case.run_id)))


def test_partial_brief_keeps_reader_overview_separate_from_diagnostics(execution_case, monkeypatch):
    case = execution_case
    limitation = "UTC window; missing source; internal diagnostic"
    patch_model(monkeypatch, ScriptedModel(responses=[final_response(limitations=[limitation])]))
    execution.execute_run(case.run_id)
    snapshot = rows(case)
    assert progress(snapshot.run)["phase"] == "publishing"
    assert snapshot.briefs[0].data["summary"] == "新工具让新闻整理更方便。"
    assert limitation in snapshot.briefs[0].data["missingSources"]
    markdown = (case.workspace / "output" / "brief.md").read_text("utf-8")
    assert "新工具让新闻整理更方便。" in markdown and limitation not in markdown
    publish_delivery(snapshot.deliveries[0].id)
    finished = progress(rows(case).run)
    assert finished["status"] == "partial" and finished["phase"] is None
    assert not finished["emptyResult"] and finished["error"] == ""


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
        run.config = {**run.config, "maxSteps": 1}
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


class TimeoutScriptedModel(ScriptedModel):
    timeout_type: type[Exception] = APITimeoutError

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise self.timeout_type(request=Request("POST", "https://fixture.invalid/v1"))


@pytest.mark.parametrize("timeout_type", [APITimeoutError, OpenAITimeoutError])
def test_model_timeout_with_empty_provider_code_reports_failure(execution_case, monkeypatch, timeout_type):
    patch_model(monkeypatch, TimeoutScriptedModel(responses=[final_response()], timeout_type=timeout_type))
    execution.execute_run(execution_case.run_id)
    snapshot = rows(execution_case)
    assert snapshot.run.status == "failed" and snapshot.run.remaining_seconds is None
    assert "超时" in snapshot.run.error
    assert snapshot.events[-1].data["detail"] == timeout_type.__name__
    assert not snapshot.briefs and not snapshot.deliveries


@pytest.mark.parametrize(("context_window", "expected_output"), [(32000, 8000), (131072, 32768), (258000, 64500)])
def test_model_uses_run_timeout_and_reasoning_output_budget(context_window, expected_output):
    model = execution.model_from({
        "data": {"modelId": "synthetic-model", "endpoint": "https://fixture.invalid/v1", "contextWindow": context_window},
        "encryptedSecret": encrypt("synthetic-secret"),
    }, max_seconds=180)
    assert model.request_timeout == 180
    assert model.max_retries == 0
    assert model.max_tokens == expected_output


def test_deepseek_v4_tool_calls_disable_incompatible_thinking_mode():
    options = tool_model_options("deepseek-v4-flash")
    assert options == {"extra_body": {"thinking": {"type": "disabled"}}}
    model = execution.model_from({
        "data": {"modelId": "deepseek-v4-flash", "endpoint": "https://fixture.invalid/v1", "contextWindow": 131072},
        "encryptedSecret": encrypt("synthetic-secret"),
    })
    assert model.extra_body == options["extra_body"]
    assert tool_model_options("other-reasoning-model") == {}


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


def test_cancel_api_finishes_before_blocked_model_returns_and_fences_its_result(
    execution_case, api_sandbox, monkeypatch,
):
    case = execution_case
    admin = api_sandbox.admin()
    entered, release = Event(), Event()
    original_generate = ScriptedModel._generate

    def blocking_generate(self, messages, stop=None, run_manager=None, **kwargs):
        entered.set()
        assert release.wait(20), "test did not release the synthetic model response"
        return original_generate(self, messages, stop=stop, run_manager=run_manager, **kwargs)

    monkeypatch.setattr(ScriptedModel, "_generate", blocking_generate)
    model = patch_model(monkeypatch, ScriptedModel(responses=[final_response()]))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(execution.execute_run, case.run_id)
        try:
            assert entered.wait(10), "worker did not enter the synthetic model request"
            before = rows(case)
            assert before.run.status == "running" and before.run.lease_token
            response = admin.post(f"/api/v1/admin/runs/{case.run_id}/cancel")
            assert response.status_code == 202, response.text
            assert response.json()["status"] == "cancelled"
            assert not pending.done(), "upstream response should still be blocked"
            cancelled = rows(case)
            assert cancelled.run.status == "cancelled" and cancelled.run.cancel_requested
            assert cancelled.run.lease_token is None and cancelled.run.lease_until is None
            assert not cancelled.briefs and not cancelled.deliveries
        finally:
            release.set()
        pending.result(timeout=10)

    after = rows(case)
    assert model.position == 1
    assert after.run.status == "cancelled" and after.run.brief_id is None
    assert not after.briefs and not after.deliveries
    assert [event.data for event in after.events] == [event.data for event in before.events]


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
        "phase",
        "phaseStartedAt",
        "emptyResult",
    }
