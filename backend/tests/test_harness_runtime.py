"""Synthetic models test protocol/runtime behavior, not live model quality."""

import asyncio
import json
import os
import time
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
from zhigenews.harness.middleware import NewsSummarizationMiddleware, SummaryContextMiddleware, token_count
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
    if name == "BriefOutput":
        args = {"summary": "Synthetic reader overview.", **args}
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
        usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
    )


def test_initial_request_is_independent_of_news_volume(tmp_path):
    prompts = []
    for count in (1, 1000):
        model = ScriptedModel(responses=[ai_call("BriefOutput", {
            "title": "Synthetic no-match brief", "items": [],
        }, "final")])
        request = HarnessRequest(
            "u", "r", "t", {"topics": ["AI"]}, {"tools": ["read_file"]},
            tmp_path / "rss", tmp_path / str(count), model,
            evidence=[{"id": str(i), "title": "Private synthetic headline"} for i in range(count)],
            fixed_at="2026-09-19T08:00:00+08:00",
        )
        HarnessRunner(checkpointer=InMemorySaver()).run(request)
        prompts.append([message.content for message in model.received[0]])
    assert prompts[0] == prompts[1]
    assert "Private synthetic headline" not in str(prompts)
    initial = json.loads(prompts[0][-1].split("\n", 1)[1])
    assert initial["windowStart"] == "2026-09-18T08:00:00+08:00"
    assert initial["windowEnd"] == "2026-09-19T08:00:00+08:00"
    assert initial["currentDate"] == "2026-09-19" and initial["timezone"] == "+08:00"
    assert initial["windowHours"] == 24 and initial["preferences"] == {"topics": ["AI"]}
    assert "evidence_index" not in initial


def test_agent_reads_source_files_and_resolves_only_selected_evidence(tmp_path):
    source = tmp_path / "news-source"
    source.mkdir()
    record = {
        "id": "article", "evidence_id": "snapshot:article", "title": "Synthetic AI release",
        "source": "Synthetic RSS", "source_id": "source", "source_type": "rss",
        "url": "https://example.test/article", "published_at": "2026-09-18T23:00:00Z",
        "fetched_at": "2026-09-19T00:00:00Z", "snapshot_id": "snapshot",
    }
    (source / "records.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (source / "index.json").write_text(json.dumps({"items": [{
        "evidence_id": "snapshot:article", "title": record["title"],
        "file": "records.jsonl", "line": 1,
    }]}), encoding="utf-8")
    resolved = []

    def resolve(ident):
        resolved.append(ident)
        return record if ident == "snapshot:article" else None

    model = ScriptedModel(responses=[
        ai_call("read_file", {"path": "/news/source/index.json"}, "index"),
        ai_call("read_file", {"path": "/news/source/records.jsonl", "start_line": 1, "end_line": 1}, "record"),
        ai_call("BriefOutput", {"title": "Synthetic brief", "items": [{
            "evidence_id": "snapshot:article", "summary": "AI release", "reason": "Matches AI", "topic": "AI",
        }]}, "final"),
    ])
    request = HarnessRequest(
        "u", "r", "t", {"topics": ["AI"]}, {"tools": ["read_file"]},
        tmp_path / "rss", tmp_path / "run", model,
        fixed_at="2026-09-19T00:00:00Z", news_roots={"source": source}, resolve_evidence=resolve,
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request)
    assert resolved == ["snapshot:article"]
    assert [item["id"] for item in result.items] == ["snapshot:article"]
    tool_results = [message for message in result.state["messages"] if isinstance(message, ToolMessage)]
    assert "Synthetic AI release" in tool_results[0].content
    assert "2026-09-18T23:00:00Z" in tool_results[1].content
    initial = json.loads(model.received[0][-1].content.split("\n", 1)[1])
    assert "/news" in initial["directories"] and "/rss" not in initial["directories"]
    assert "Synthetic AI release" not in str(model.received[0])


@pytest.mark.parametrize(("published", "accepted"), [
    (None, False), ("invalid", False), ("2026-09-18T23:00:00", False),
    ("2026-09-19T00:00:01Z", False), ("2026-09-17T23:59:59Z", False),
    ("2026-09-18T00:00:00Z", True), ("2026-09-19T00:00:00Z", True),
    ("2026-09-19T07:00:00+08:00", True),
])
def test_brief_only_publishes_explicit_times_in_fixed_window(tmp_path, published, accepted):
    model = ScriptedModel(responses=[ai_call("BriefOutput", {
        "title": "Synthetic dated brief", "items": [{
            "evidence_id": "n1", "summary": "AI summary", "reason": "Matches AI", "topic": "AI",
        }],
    }, "final")])
    request = HarnessRequest(
        "u", "r", "t", {"topics": ["AI"]}, {"tools": ["read_file"], "windowHours": 72},
        tmp_path / "rss", tmp_path / "run", model,
        evidence=[{
            "id": "n1", "title": "Synthetic AI release", "url": "https://example.test/article",
            "source": "Synthetic", "published_at": published,
            "fetched_at": "2026-09-19T00:00:00Z", "snapshot_id": "s1",
        }], fixed_at="2026-09-19T00:00:00Z",
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request)
    assert bool(result.items) is accepted
    if not accepted:
        assert result.limitations


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


def test_large_recent_parallel_news_reads_are_compacted_before_context_limit(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "index.json").write_text(
        "\n".join(f'{i}: 新闻目录索引证据来源发布时间' * 3 for i in range(200)), encoding="utf-8"
    )
    model = ScriptedModel(responses=[
        AIMessage(content="", tool_calls=[
            {"id": f"index-{i}", "name": "read_file", "args": {"path": "/news/source/index.json"}}
            for i in range(3)
        ]),
        ai_call("read_file", {"path": "/news/source/index.json", "start_line": 50}, "more-news"),
        ai_call("BriefOutput", {"title": "Synthetic compacted brief", "items": [{
            "evidence_id": "n1", "summary": "Synthetic news summary", "reason": "Matches AI", "topic": "AI",
        }]}, "final"),
    ])
    summary = ScriptedModel(responses=[AIMessage(content="Synthetic index inspected; evidence_id=n1 matches AI.")])
    events = []
    request = HarnessRequest(
        "u", "r", "t", {"topics": ["AI"]},
        {"tools": ["read_file"], "contextWindow": 32768, "outputReserve": 8192,
         "summaryContextWindow": 32768, "summaryOutputReserve": 8192},
        tmp_path / "rss", tmp_path / "run", model, summary_model=summary,
        news_roots={"source": source}, fixed_at="2026-09-19T00:00:00Z",
        evidence=[{"id": "n1", "title": "Synthetic AI news", "source": "Synthetic",
                   "url": "https://example.test/news", "published_at": "2026-09-18T23:00:00Z",
                   "fetched_at": "2026-09-19T00:00:00Z", "snapshot_id": "synthetic"}],
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request, event_sink=events.append)
    assert result.title == "Synthetic compacted brief"
    assert result.items[0]["id"] == "n1"
    assert summary.position > 0
    journal_ids = {event["messageId"] for event in events if event["type"] == "message_recorded"}
    assert set(result.state["summary_covered_ids"]) <= journal_ids
    original = next(m for m in model.received[0] if isinstance(m, HumanMessage))
    assert all(any(m.content == original.content for m in messages) for messages in model.received)
    for messages in model.received:
        repaired, audit = repair_messages(messages)
        assert not audit and repaired == messages


def test_token_pressure_compacts_complete_groups_and_keeps_small_recent_result():
    middleware = NewsSummarizationMiddleware(
        ScriptedModel(responses=[]), context_window=2200,
    )
    user = HumanMessage(content="Exact user preference", id="user")
    large = ai_call("read_file", {}, "large")
    recent = ai_call("list_dir", {}, "recent")
    state = {"messages": [user, large, ToolMessage(content="news " * 3000, tool_call_id="large"),
                          recent, ToolMessage(content="small directory listing", tool_call_id="recent")]}
    runtime = SimpleNamespace(context=SimpleNamespace(config={}))
    old, keep, groups = middleware._plan(state, runtime)
    assert old == state["messages"][1:3]
    assert keep == [user, *state["messages"][3:]]
    assert groups == [old]


def test_oversized_user_prompt_is_not_summarized_or_silently_truncated():
    from langchain.agents.middleware.types import ModelRequest

    from zhigenews.harness.middleware import RuntimeMiddleware

    model = ScriptedModel(responses=[])
    middleware = NewsSummarizationMiddleware(model, context_window=1000)
    user = HumanMessage(content="Exact user preference " * 1000, id="user")
    state = {"messages": [user]}
    context = SimpleNamespace(config={"contextWindow": 1000, "outputReserve": 256})
    runtime = SimpleNamespace(context=context)
    assert middleware._plan(state, runtime) is None
    request = ModelRequest(model=model, messages=[user], tools=[], state=state, runtime=runtime)
    with pytest.raises(HarnessError) as exc:
        RuntimeMiddleware()._before(request)
    assert exc.value.code == "CONTEXT_BUDGET"
    assert state["messages"] == [user] and model.position == 0


def test_summary_keeps_user_merges_old_and_renders_separately():
    model = ScriptedModel(
        responses=[
            AIMessage(
                content="merged old and new",
                usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
            )
        ]
    )
    middleware = NewsSummarizationMiddleware(model, ratio=0.001, keep=2)
    original = HumanMessage(content="Latest exact user prompt", id="latest")
    messages = [HumanMessage(content="old", id="old"), AIMessage(content="answer", id="a1"), original]
    messages += [AIMessage(content=str(i), id=f"a{i + 2}") for i in range(6)]
    events = []
    context = SimpleNamespace(
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
    assert json.loads(rendered.messages[0].content.split("\n", 1)[1]) == {
        "summary": "merged old and new"
    }
    assert len(request.messages) == len(after)
    without_summary = request.override(state={**state, "summary": ""})
    assert SummaryContextMiddleware()._render(without_summary) is without_summary


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_summary_triggers_at_ninety_percent(offset):
    model = ScriptedModel(responses=[AIMessage(content="summary")])
    state = {
        "messages": [
            HumanMessage(content="hello", id="u"),
            AIMessage(content="long old message", id="a"),
            AIMessage(content="latest", id="b"),
        ],
        "summary": "previous summary",
    }
    context = SimpleNamespace(
        config={"systemPrompt": "Synthetic system prompt"},
        budget=Budget(), cancelled=lambda: False, emit=lambda *a, **k: None,
    )
    counted = (
        token_count(state["messages"])
        + token_count(state["summary"])
        + token_count(context.config["systemPrompt"])
    )
    middleware = NewsSummarizationMiddleware(
        model,
        fixed_overhead=232200 + offset - counted,
        keep=1,
    )
    update = middleware.before_model(state, SimpleNamespace(context=context))
    if offset < 0:
        assert update is None and model.position == 0
    else:
        assert update and update["summary"] == "summary"
        assert model.position == 1


def test_summary_does_not_trigger_at_old_token_or_message_thresholds():
    model = ScriptedModel(responses=[])
    messages = [HumanMessage(content="Keep my request verbatim", id="u")]
    messages += [AIMessage(content="news " * 400, id=f"a{i}") for i in range(40)]
    assert len(messages) > 30
    assert 12000 < token_count(messages) < 232200
    middleware = NewsSummarizationMiddleware(model)
    runtime = SimpleNamespace(context=SimpleNamespace(config={}))
    assert middleware.before_model({"messages": messages}, runtime) is None
    assert model.position == 0


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
        {"maxSteps": 11, "tools": ["list_dir", "read_file"]},
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
                "published_at": "2026-09-18T23:00:00Z",
                "fetched_at": "2026-09-19T00:00:00Z",
                "snapshot_id": "s1",
            }
        ],
        fixed_at="2026-09-19T00:00:00Z",
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(req, events.append)
    assert model.position == 3 and result.usage["modelCalls"] == 3 and result.usage["toolCalls"] == 2
    assert result.items[0]["publishedAt"] == "2026-09-18T23:00:00Z"
    assert (workspace / "output" / "brief.json").exists()
    assert len([event for event in events if event["type"] == "tool_completed"]) == 2
    req.model = ScriptedModel(responses=[ai_call("list_dir", {}, "repeat")])
    req.config["maxSteps"] = 1
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(checkpointer=InMemorySaver()).run(req)
    assert exc.value.code == "BUDGET_EXHAUSTED"


@pytest.mark.parametrize(
    ("api_key", "enabled", "search_available"),
    [(None, ["read_file", "web_search"], False),
     ("synthetic-key", ["read_file", "web_search"], True),
     ("synthetic-key", ["read_file"], False)],
)
def test_private_evidence_stays_out_of_prompt_and_search_matches_credentials(
    tmp_path, api_key, enabled, search_available
):
    class RecordingModel(ScriptedModel):
        bound_tools: list[str] = Field(default_factory=list)

        def bind_tools(self, tools, **kwargs):
            from langchain_core.utils.function_calling import convert_to_openai_tool

            self.bound_tools = [convert_to_openai_tool(tool)["function"]["name"] for tool in tools]
            return self

    item = {
        "id": "n1",
        "title": "AI update",
        "summary": "Source-provided summary",
        "source": "Fixture RSS",
        "source_type": "rss",
        "url": "https://example.com/news",
        "published_at": "2026-09-18T23:00:00Z",
        "fetched_at": "2026-09-19T00:00:00Z",
        "snapshot_id": "snapshot-1",
        "content": "",
    }
    workspace = tmp_path / "run"
    (workspace / "inputs").mkdir(parents=True)
    # A duplicate ID's selected record must point to its actual last file line.
    records = [{**item, "summary": "Earlier record"}, item]
    (workspace / "inputs" / "evidence.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records), encoding="utf-8"
    )
    model = RecordingModel(responses=[ai_call("BriefOutput", {
        "title": "Synthetic direct brief",
        "items": [{"evidence_id": "n1", "summary": item["summary"],
                   "reason": "Matches AI preference", "topic": "AI"}],
    }, "final")])
    request = HarnessRequest(
        "u", "r", "t", {"topics": ["AI"]}, {"tools": enabled},
        tmp_path / "rss", workspace, model, evidence=records, tavily_api_key=api_key,
        fixed_at="2026-09-19T00:00:00Z",
    )
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request)
    assert result.usage["modelCalls"] == 1 and result.usage["toolCalls"] == 0
    assert ("web_search" in model.bound_tools) == search_available
    initial = next(message for message in model.received[0] if isinstance(message, HumanMessage))
    payload = json.loads(initial.content.split("\n", 1)[1])
    assert "evidence_index" not in payload
    assert item["title"] not in initial.content and item["summary"] not in initial.content
    assert result.items[0]["publishedAt"] == "2026-09-18T23:00:00Z"
    assert request.config["tools"] == enabled


@pytest.mark.parametrize(
    ("content", "finish_reason", "code"),
    [("", "length", "MODEL_OUTPUT_INCOMPLETE"),
     ('{"title":"Unstructured JSON","items":[]}', "stop", "STRUCTURED_OUTPUT_MISSING")],
)
def test_missing_structured_output_has_actionable_error_and_no_brief(
    tmp_path, content, finish_reason, code
):
    model = ScriptedModel(responses=[AIMessage(
        content=content, response_metadata={"finish_reason": finish_reason},
        usage_metadata={"input_tokens": 20, "output_tokens": 10, "total_tokens": 30},
    )])
    workspace = tmp_path / "run"
    request = HarnessRequest(
        "u", "r", "t", {"topics": ["AI"]}, {"tools": ["read_file"]},
        tmp_path / "rss", workspace, model,
    )
    events = []
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(checkpointer=InMemorySaver()).run(request, events.append)
    assert exc.value.code == code and model.position == 1
    assert not (workspace / "output" / "brief.json").exists()
    assert not any(event["type"] == "harness_completed" for event in events)


@pytest.mark.parametrize("trigger", ["time", "calls", "normal"])
def test_create_agent_reserves_final_call_without_research_tools(tmp_path, monkeypatch, trigger):
    from zhigenews.harness import middleware

    class RecordingModel(ScriptedModel):
        bindings: list[list[str]] = Field(default_factory=list)

        def bind_tools(self, tools, **kwargs):
            from langchain_core.utils.function_calling import convert_to_openai_tool

            self.bindings.append([convert_to_openai_tool(tool)["function"]["name"] for tool in tools])
            return self

    started, elapsed = time.time(), [0]
    monkeypatch.setattr(middleware, "time", SimpleNamespace(
        time=lambda: started + elapsed[0], monotonic=time.monotonic,
    ))
    model = RecordingModel(responses=[
        ai_call("list_dir", {"path": "/workspace"}, "research"),
        ai_call("BriefOutput", {
            "title": "Synthetic no-match brief", "items": [], "limitations": ["No supplied evidence"],
        }, "final"),
    ])
    request = HarnessRequest(
        "u", "r", "t", {"topics": ["AI"]},
        {"tools": ["list_dir"], "maxSeconds": 100, "maxSteps": 4 if trigger == "calls" else 6,
         "systemPrompt": "Preserve these original instructions."},
        tmp_path / "rss", tmp_path / "run", model,
    )

    def event_sink(event):
        if trigger == "time" and event["type"] == "tool_completed":
            elapsed[0] = 60

    result = HarnessRunner(checkpointer=InMemorySaver()).run(request, event_sink)
    assert set(model.bindings[0]) == {"list_dir", "BriefOutput"}
    if trigger == "normal":
        assert set(model.bindings[1]) == {"list_dir", "BriefOutput"}
    else:
        assert model.bindings[1] == ["BriefOutput"]
        assert "本次运行已进入最终整理阶段" in model.received[1][0].text
    assert "Preserve these original instructions." in model.received[1][0].text
    assert result.usage["modelCalls"] == 2 and result.usage["toolCalls"] == 1
    assert request.config["tools"] == ["list_dir"]


def test_async_runtime_reserves_completion_on_final_model_call():
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    from zhigenews.harness.middleware import RuntimeMiddleware

    context = SimpleNamespace(
        budget=Budget(max_steps=2), config={}, cancelled=lambda: False,
        emit=lambda *args, **kwargs: None,
    )
    request = ModelRequest(
        model=ScriptedModel(responses=[]), messages=[HumanMessage(content="Make a brief")],
        tools=[{"type": "function", "function": {"name": "research", "parameters": {"type": "object"}}}],
        runtime=SimpleNamespace(context=context),
    )
    received = []

    async def handler(current):
        received.append(current)
        return ModelResponse(result=[AIMessage(content="Synthetic response")])

    asyncio.run(RuntimeMiddleware().awrap_model_call(request, handler))
    assert received[0].tools == [] and "BriefOutput" in received[0].system_message.text
    assert request.tools and context.budget.model_calls == 1


def test_shared_budget_and_cancel():
    budget = Budget(max_steps=2)
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
        {"maxSteps": 11, "tools": ["list_dir"]},
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
    with mysql_persistence(url) as saver:
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
        {"tools": ["delegate_research"], "maxSteps": 5, "subagentConcurrency": 1},
        tmp_path / "rss",
        tmp_path / "run",
        model,
        evidence=[{"id": "private-record", "title": "Private child headline"}],
        news_roots={},
        fixed_at="2026-09-19T00:00:00Z",
    )
    events = []
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request, events.append)
    assert result.usage["modelCalls"] == 3 and result.usage["toolCalls"] == 1
    child = next(e for e in events if e["type"] == "subagent_started")
    assert child["childRunId"] != "parent"
    assert any(e["type"] == "harness_completed" and e["runId"] == child["childRunId"] for e in events)
    for call in model.received:
        initial = next(message for message in call if isinstance(message, HumanMessage))
        payload = json.loads(initial.content.split("\n", 1)[1])
        assert payload["windowEnd"] == "2026-09-19T00:00:00+00:00"
        assert "/news" in payload["directories"] and "/rss" not in payload["directories"]
        assert "Private child headline" not in initial.content and "evidence_index" not in payload


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
        {"tools": ["delegate_research", "write_file"], "maxSteps": 17},
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
        summary="Synthetic reader overview.",
        items=[
            {"evidence_id": ident, "summary": "Summary", "reason": "Match", "topic": "AI"}
            for ident in evidence
        ],
    )
    items = validate_items(
        output, evidence, fixed_at=datetime(2026, 9, 19, tzinfo=timezone.utc)
    )
    assert [item["id"] for item in items] == ["fresh"]


@pytest.mark.parametrize("last_kind", ["model", "tool"])
def test_default_step_budget_counts_both_kinds_and_stops_at_1000(last_kind):
    budget = Budget()
    for index in range(999):
        budget.reserve("model" if index % 2 else "tool", lambda: False)
    budget.reserve(last_kind, lambda: False)
    assert budget.snapshot()["steps"] == 1000
    for kind in ("model", "tool"):
        with pytest.raises(HarnessError) as exc:
            budget.reserve(kind, lambda: False)
        assert exc.value.code == "BUDGET_EXHAUSTED"
    with pytest.raises(HarnessError):
        budget.check(lambda: False)
    assert budget.steps == 1000


@pytest.mark.parametrize("max_steps", [1, 2, 3])
def test_agent_stops_at_step_limit_without_publishing(tmp_path, max_steps):
    model = ScriptedModel(responses=[
        ai_call("list_dir", {"path": "/workspace"}, "read"),
        ai_call("BriefOutput", {"title": "Synthetic", "items": []}, "done"),
    ])
    request = HarnessRequest(
        "u", "r", "t", {}, {"maxSteps": max_steps, "tools": ["list_dir"]},
        tmp_path / "rss", tmp_path / "run", model,
    )
    events = []
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(checkpointer=InMemorySaver()).run(request, events.append)
    assert exc.value.code == "BUDGET_EXHAUSTED"
    persisted = json.loads((tmp_path / ".run.harness" / "budget.json").read_text())
    assert persisted["steps"] == max_steps
    assert not any(event["type"] == "harness_completed" for event in events)


def test_resume_restores_combined_step_budget(tmp_path):
    metadata = tmp_path / ".run.harness"
    metadata.mkdir()
    # Existing snapshots only stored the separate counters.
    (metadata / "budget.json").write_text(json.dumps({"modelCalls": 600, "toolCalls": 400}))
    model = ScriptedModel(responses=[])
    request = HarnessRequest("u", "r", "t", {}, {}, tmp_path / "rss", tmp_path / "run", model)
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(checkpointer=InMemorySaver()).run(request, resume=True)
    assert exc.value.code == "BUDGET_EXHAUSTED"
    assert model.position == 0
