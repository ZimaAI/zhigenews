"""Synthetic models test protocol/runtime behavior, not live model quality."""

import os
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from pydantic import Field

from zhigenews.harness import HarnessRequest, HarnessRunner
from zhigenews.harness.errors import HarnessError
from zhigenews.harness.messages import repair_messages
from zhigenews.harness.middleware import NewsSummarizationMiddleware, SummaryContextMiddleware
from zhigenews.harness.runtime import Budget


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]
    position: int = 0
    received: list[Any] = Field(default_factory=list)

    @property
    def _llm_type(self):
        return "synthetic-test-model"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.received.append(messages)
        result = self.responses[min(self.position, len(self.responses) - 1)]
        self.position += 1
        return ChatResult(generations=[ChatGeneration(message=result.model_copy(deep=True))])


def ai_call(name, args, call_id):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
    )


def test_repair_order_missing_orphans_duplicates_and_idempotency():
    user = HumanMessage(content="preserve", id="user")
    ai = AIMessage(
        content="",
        id="ai",
        tool_calls=[{"id": "a", "name": "read", "args": {}}, {"id": "b", "name": "read", "args": {}}],
    )
    later = HumanMessage(content="later", id="later")
    messages = [
        user,
        ai,
        later,
        ToolMessage(content="old", tool_call_id="a", id="old"),
        ToolMessage(content="latest", tool_call_id="a", id="new"),
        ToolMessage(content="orphan", tool_call_id="x", id="orphan"),
    ]
    repaired, audit = repair_messages(messages)
    assert [m.id for m in repaired] == ["user", "ai", "new", "repair-b", "later"]
    assert {e["kind"] for e in audit} == {"duplicate_result", "missing_result", "orphan_result"}
    again, audit = repair_messages(repaired)
    assert again == repaired and not audit
    assert repaired[3].status == "error"
    with pytest.raises(HarnessError):
        repair_messages([user, ai], active_calls={"b"})
    with pytest.raises(HarnessError):
        repair_messages([ai, ai.model_copy(update={"id": "another"})])


def test_summary_keeps_user_merges_old_and_renders_separately():
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="merged old and new",
                usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            )
        ]
    )
    middleware = NewsSummarizationMiddleware(model, messages=4, keep=2)
    original = HumanMessage(content="Latest exact user prompt", id="latest")
    messages = [HumanMessage(content="old", id="old"), AIMessage(content="answer", id="a1"), original]
    messages += [AIMessage(content=str(i), id=f"a{i + 2}") for i in range(6)]
    events = []
    context = SimpleNamespace(
        memory=[],
        config={},
        budget=Budget(),
        cancelled=lambda: False,
        emit=lambda kind, **data: events.append({"type": kind, **data}),
    )
    state = {"messages": messages, "summary": "OLDER SUMMARY", "summary_revision": 3}
    update = middleware.before_model(state, SimpleNamespace(context=context))
    assert "OLDER SUMMARY" in str(model.received)
    after = add_messages(messages, update["messages"])
    assert after[0] is original
    assert update["summary_revision"] == 4 and update["summary"] == "merged old and new"
    assert all(m.additional_kwargs.get("lc_source") != "summarization" for m in after)
    from langchain.agents.middleware.types import ModelRequest

    request = ModelRequest(
        model=model,
        messages=after,
        tools=[],
        state={**state, **update},
        runtime=SimpleNamespace(context=context),
    )
    rendered = SummaryContextMiddleware()._render(request)
    assert "merged old and new" in str(rendered.messages[0])
    assert len(request.messages) == len(after)


@pytest.mark.parametrize("kind", ["tokens", "ratio"])
def test_summary_all_trigger_modes(kind):
    model = ScriptedModel(responses=[AIMessage(content="summary")])
    middleware = NewsSummarizationMiddleware(
        model,
        messages=1000,
        tokens=1 if kind == "tokens" else 999999,
        ratio=0.01 if kind == "ratio" else 1,
        context_window=500,
        keep=1,
    )
    context = SimpleNamespace(
        memory=[], config={}, budget=Budget(), cancelled=lambda: False, emit=lambda *a, **k: None
    )
    update = middleware.before_model(
        {
            "messages": [
                HumanMessage(content="hello", id="u"),
                AIMessage(content="long old message", id="a"),
                AIMessage(content="latest", id="b"),
            ]
        },
        SimpleNamespace(context=context),
    )
    assert update and update["summary"] == "summary"


def test_create_agent_repeated_tool_loop_and_budget(tmp_path):
    model = ScriptedModel(
        responses=[
            ai_call("list_dir", {"path": "/workspace"}, "c1"),
            ai_call("read_file", {"path": "/workspace/inputs/news.json"}, "c2"),
            ai_call(
                "BriefOutput",
                {
                    "title": "synthetic test brief",
                    "items": [
                        {
                            "evidence_id": "n1",
                            "summary": "Evidence summary",
                            "reason": "Matches AI preference",
                            "topic": "AI",
                        }
                    ],
                },
                "done",
            ),
        ]
    )
    workspace = tmp_path / "run"
    (workspace / "inputs").mkdir(parents=True)
    (workspace / "inputs" / "news.json").write_text('{"id":"n1","title":"AI update"}', "utf-8")
    events = []
    req = HarnessRequest(
        "u",
        "r",
        "t",
        {"topics": ["AI"]},
        {"maxModelCalls": 5, "maxToolCalls": 5, "tools": ["list_dir", "read_file"]},
        tmp_path / "rss",
        workspace,
        model,
        evidence=[
            {
                "id": "n1",
                "title": "AI update",
                "source": "Fixture",
                "source_type": "rss",
                "url": "https://example.com/news",
                "published_at": None,
                "fetched_at": "2026-09-19T00:00:00Z",
                "snapshot_id": "s1",
            }
        ],
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(req, events.append)
    assert model.position == 3 and result.usage["modelCalls"] == 3 and result.usage["toolCalls"] == 2
    assert result.items[0]["publishedAt"] is None
    assert (workspace / "output" / "brief.json").exists()
    assert len([event for event in events if event["type"] == "tool_completed"]) == 2
    req.model = ScriptedModel(responses=[ai_call("list_dir", {}, "repeat")])
    req.config["maxModelCalls"] = 1
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(checkpointer=InMemorySaver()).run(req)
    assert exc.value.code == "BUDGET_EXHAUSTED"


def test_shared_budget_and_cancel():
    budget = Budget(max_model_calls=2)
    budget.reserve("model", lambda: False)
    budget.reserve("model", lambda: False)
    with pytest.raises(HarnessError):
        budget.reserve("model", lambda: False)
    with pytest.raises(HarnessError) as exc:
        Budget().reserve("tool", lambda: True)
    assert exc.value.code == "CANCELLED"


@pytest.mark.skipif(not os.environ.get("HARNESS_TEST_MYSQL_URL"), reason="requires actual MySQL")
def test_create_agent_mysql_cancel_resume_without_repeating_completed_model(tmp_path):
    import uuid

    from zhigenews.harness import mysql_persistence

    url = os.environ["HARNESS_TEST_MYSQL_URL"]
    thread = "cancel-test-" + uuid.uuid4().hex
    first = ScriptedModel(responses=[ai_call("list_dir", {"path": "/workspace"}, "list-1")])
    request = HarnessRequest(
        "test-user",
        thread,
        thread,
        {"topics": ["AI"]},
        {"maxModelCalls": 5, "maxToolCalls": 5, "tools": ["list_dir"]},
        tmp_path / "rss",
        tmp_path / "run",
        first,
    )
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(url).run(request, cancelled=lambda: first.position >= 1)
    assert exc.value.code == "CANCELLED"
    resumed = ScriptedModel(
        responses=[
            ai_call(
                "BriefOutput",
                {"title": "no matching news", "items": [], "limitations": ["synthetic no-match case"]},
                "final",
            )
        ]
    )
    request.model = resumed
    result = HarnessRunner(url).run(request, resume=True)
    assert result.usage["modelCalls"] == 2 and result.usage["toolCalls"] == 1
    assert resumed.position == 1
    assert (
        len(
            [m for m in result.state["messages"] if isinstance(m, ToolMessage) and m.tool_call_id == "list-1"]
        )
        == 1
    )
    with mysql_persistence(url) as (saver, _):
        saver.delete_thread("test-user:" + thread)


def test_subagent_real_loop_shares_total_budget_and_thread(tmp_path):
    model = ScriptedModel(
        responses=[
            ai_call("delegate_research", {"task": "Find news about AI"}, "delegate-1"),
            ai_call("BriefOutput", {"title": "child no match", "items": []}, "child-done"),
            ai_call("BriefOutput", {"title": "parent no match", "items": []}, "parent-done"),
        ]
    )
    request = HarnessRequest(
        "u",
        "parent",
        "parent",
        {"topics": ["AI"]},
        {"tools": ["delegate_research"], "maxModelCalls": 4, "subagentConcurrency": 1},
        tmp_path / "rss",
        tmp_path / "run",
        model,
    )
    events = []
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request, events.append)
    assert result.usage["modelCalls"] == 3 and result.usage["toolCalls"] == 1
    child = next(e for e in events if e["type"] == "subagent_started")
    assert child["childRunId"] != "parent"
    assert any(e["type"] == "harness_completed" and e["runId"] == child["childRunId"] for e in events)


def test_interrupted_child_resumes_its_pending_write(tmp_path):
    import hashlib

    model = ScriptedModel(
        responses=[
            ai_call("delegate_research", {"task": "Write a research artifact"}, "delegate-recover"),
            ai_call(
                "write_file",
                {
                    "path": "/workspace/output/research.txt",
                    "content": "original pending write",
                    "create_new": True,
                },
                "write-recover",
            ),
        ]
    )
    request = HarnessRequest(
        "u",
        "recover",
        "recover",
        {"topics": ["AI"]},
        {"tools": ["delegate_research", "write_file"], "maxModelCalls": 8, "maxToolCalls": 8},
        tmp_path / "rss",
        tmp_path / "run",
        model,
    )
    saver = InMemorySaver()
    runner = HarnessRunner(checkpointer=saver)
    with pytest.raises(HarnessError) as exc:
        runner.run(request, cancelled=lambda: model.position >= 2)
    assert exc.value.code == "CANCELLED"
    request.model = ScriptedModel(
        responses=[
            ai_call("BriefOutput", {"title": "child complete", "items": []}, "child-final"),
            ai_call("BriefOutput", {"title": "parent complete", "items": []}, "parent-final"),
        ]
    )
    result = runner.run(request, resume=True)
    child_id = hashlib.sha256(b"delegate-recover").hexdigest()[:24]
    artifact = tmp_path / ("run-child-" + child_id) / "output" / "research.txt"
    assert artifact.read_text() == "original pending write"
    assert result.usage["modelCalls"] == 4
    assert request.model.position == 2


def test_stale_duplicate_cannot_hide_fresh_evidence():
    from datetime import datetime, timezone

    from zhigenews.harness.runner import BriefOutput, validate_items

    evidence = {
        ident: {
            "id": ident,
            "title": "AI release",
            "source": "Fixture",
            "url": "https://example.com/release",
            "published_at": published,
            "fetched_at": "2026-09-19T00:00:00Z",
            "snapshot_id": ident,
        }
        for ident, published in [("old", "2026-09-01T00:00:00Z"), ("fresh", "2026-09-18T22:00:00Z")]
    }
    output = BriefOutput(
        title="test",
        items=[
            {"evidence_id": ident, "summary": "Summary", "reason": "Match", "topic": "AI"}
            for ident in evidence
        ],
    )
    items = validate_items(
        output, evidence, {"topics": ["AI"]}, fixed_at=datetime(2026, 9, 19, tzinfo=timezone.utc)
    )
    assert [item["id"] for item in items] == ["fresh"]
