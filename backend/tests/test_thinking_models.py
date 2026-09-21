"""Protocol fixtures exercise real SDK/LangChain turns, never a live provider."""

import asyncio
import json

import httpx
import pytest
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from zhigenews.harness import HarnessRequest, HarnessRunner
from zhigenews.harness.errors import HarnessError
from zhigenews.harness.files import FileService
from zhigenews.harness.middleware import NewsSummarizationMiddleware, RuntimeMiddleware
from zhigenews.harness.runner import BriefOutput
from zhigenews.harness.runtime import Budget, NewsAgentState, RunContext
from zhigenews.models import ModelConfigurationError, ThinkingChatOpenAI, build_model, tool_model_options

PRIVATE_REASONING = "Synthetic private protocol reasoning must not enter public events"


def provider_response(*, name=None, args=None, content="", finish_reason=None):
    message = {
        "role": "assistant", "content": content, "reasoning_content": PRIVATE_REASONING,
        "reasoning_details": [{"type": "reasoning.text", "text": PRIVATE_REASONING,
                               "signature": "synthetic-private-signature"}],
    }
    if name:
        message["tool_calls"] = [{
            "id": "call-" + name, "type": "function",
            "function": {"name": name, "arguments": json.dumps(args or {})},
        }]
    return httpx.Response(200, json={
        "id": "synthetic-reply", "object": "chat.completion", "created": 1,
        "model": "deepseek-v4-flash",
        "choices": [{"index": 0, "message": message,
                     "finish_reason": finish_reason or ("tool_calls" if name else "stop")}],
        "usage": {"prompt_tokens": 30, "completion_tokens": 20, "total_tokens": 50,
                  "completion_tokens_details": {"reasoning_tokens": 10}},
    })


def protocol_model(handler, *, thinking=True, provider="deepseek"):
    transport = httpx.MockTransport(handler)
    model_id = "MiniMax-M3" if provider == "minimax" else "deepseek-v4-flash"
    return ThinkingChatOpenAI(
        model=model_id, base_url="https://fixture.invalid/v1", api_key="synthetic-key",
        provider_family=provider,
        thinking_enabled=thinking, disable_streaming=True, use_responses_api=False,
        max_tokens=8192, max_retries=0,
        http_client=httpx.Client(transport=transport),
        http_async_client=httpx.AsyncClient(transport=transport),
        **tool_model_options(model_id, thinking),
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_factory_uses_saved_thinking_toggle_and_deepseek_token_field(enabled):
    model = build_model({
        "modelId": "deepseek-v4-flash", "endpoint": "https://fixture.invalid/v1",
        "thinkingEnabled": enabled,
    }, api_key="synthetic-key", timeout=180, max_tokens=16384)
    payload = model._get_request_payload([HumanMessage(content="Probe")])
    assert payload["extra_body"]["thinking"]["type"] == ("enabled" if enabled else "disabled")
    assert payload["max_tokens"] == 16384 and "max_completion_tokens" not in payload
    assert model.request_timeout == 180 and model.thinking_enabled == enabled


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("provider", ["deepseek", "minimax"])
@pytest.mark.parametrize("json_final", [False, True])
def test_thinking_real_agent_preserves_reasoning_and_finishes_with_auto_tools(
    tmp_path, asynchronous, provider, json_final
):
    requests, events = [], []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["thinking"] == {"type": "adaptive" if provider == "minimax" else "enabled"}
        assert payload["tool_choice"] == "auto"
        if provider == "minimax":
            assert payload["max_completion_tokens"] == 8192 and payload["reasoning_split"]
        else:
            assert payload["max_tokens"] == 8192 and "max_completion_tokens" not in payload
        if len(requests) == 1:
            return provider_response(name="research", content=None)
        assistant = next(message for message in payload["messages"] if message["role"] == "assistant")
        assert assistant["reasoning_content"] == PRIVATE_REASONING and assistant["content"] == ""
        assert assistant["reasoning_details"][0]["signature"] == "synthetic-private-signature"
        assert [entry["function"]["name"] for entry in payload["tools"]] == ["BriefOutput"]
        final = {
            "title": "Synthetic provider final", "items": [], "limitations": ["No supplied news"],
            "summary": "No matching news.",
        }
        return provider_response(content=json.dumps(final)) if json_final else provider_response(
            name="BriefOutput", args=final
        )

    @tool
    def research() -> str:
        """Return a synthetic research result."""
        return "No matching news in synthetic fixture."

    workspace, rss = tmp_path / "workspace", tmp_path / "rss"
    workspace.mkdir()
    rss.mkdir()
    context = RunContext(
        "u", "r", "t", {}, {}, Budget(max_steps=4), FileService(rss, workspace),
        events.append, lambda: False, {},
    )
    graph = create_agent(
        protocol_model(handler, provider=provider), tools=[research], middleware=[RuntimeMiddleware()],
        response_format=ToolStrategy(BriefOutput), state_schema=NewsAgentState,
        context_schema=RunContext, checkpointer=InMemorySaver(),
    )
    arguments = ({"messages": [HumanMessage(content="Generate a synthetic brief", id="request")]},
                 {"configurable": {"thread_id": "thinking-test"}})
    state = (asyncio.run(graph.ainvoke(*arguments, context=context)) if asynchronous
             else graph.invoke(*arguments, context=context))
    assert state["structured_response"].title == "Synthetic provider final"
    assert len(requests) == 2 and context.budget.model_calls == 2
    assert PRIVATE_REASONING not in json.dumps(events)
    assert any(message.additional_kwargs.get("reasoning_content") == PRIVATE_REASONING
               for message in state["messages"])


def test_disabled_thinking_keeps_required_tool_choice_and_drops_reasoning():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return provider_response(name="connection_probe", args={"value": "ok"})

    tool = {"type": "function", "function": {
        "name": "connection_probe", "parameters": {"type": "object", "properties": {}},
    }}
    answer = protocol_model(handler, thinking=False).bind_tools(
        [tool], tool_choice="connection_probe"
    ).invoke("Call connection_probe")
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["tool_choice"]["function"]["name"] == "connection_probe"
    assert "reasoning_content" not in answer.additional_kwargs


@pytest.mark.parametrize(("content", "finish_reason", "expected_error"), [
    ('{"title":"Actual JSON fixture","summary":"No matching news.","items":[]}', "stop", None),
    ('{"title":"Missing reader overview","items":[]}', "stop", "STRUCTURED_OUTPUT_MISSING"),
    ('{"title":"Incomplete fixture"', "length", "MODEL_OUTPUT_INCOMPLETE"),
    ('{"title":"Incomplete fixture"', "stop", "STRUCTURED_OUTPUT_MISSING"),
    ("Ordinary prose has no validated brief", "stop", "STRUCTURED_OUTPUT_MISSING"),
])
def test_thinking_final_text_requires_complete_valid_actual_json(
    tmp_path, content, finish_reason, expected_error
):
    model = protocol_model(lambda request: provider_response(content=content, finish_reason=finish_reason))
    request = HarnessRequest(
        "u", "r", "t", {}, {"tools": ["list_dir"]},
        tmp_path / "rss", tmp_path / "workspace", model,
    )
    runner = HarnessRunner(checkpointer=InMemorySaver())
    if expected_error:
        with pytest.raises(HarnessError) as exc:
            runner.run(request)
        assert exc.value.code == expected_error
        assert not (request.workspace_root / "output" / "brief.json").exists()
    else:
        result = runner.run(request)
        assert result.title == "Actual JSON fixture" and result.items == []


def test_thinking_json_still_requires_existing_evidence(tmp_path):
    content = json.dumps({"title": "Synthetic invalid evidence", "summary": "Synthetic overview.", "items": [{
        "evidence_id": "invented", "summary": "Synthetic", "reason": "Synthetic", "topic": "AI",
    }]})
    request = HarnessRequest(
        "u", "r", "t", {}, {"tools": ["list_dir"]}, tmp_path / "rss", tmp_path / "workspace",
        protocol_model(lambda request: provider_response(content=content)),
    )
    with pytest.raises(HarnessError) as exc:
        HarnessRunner(checkpointer=InMemorySaver()).run(request)
    assert exc.value.code == "INVALID_EVIDENCE"


@pytest.mark.parametrize("enabled", [False, True])
def test_minimax_and_known_openai_toggle_options(enabled):
    options = tool_model_options("MiniMax-M3", enabled)
    assert options["extra_body"] == {
        "thinking": {"type": "adaptive" if enabled else "disabled"}, "reasoning_split": True,
    }
    for name in ("gpt-5.1", "gpt-5.2", "gpt-5.4", "gpt-5.5", "gpt-5.2-2025-12-11"):
        assert tool_model_options(name, enabled) == {"reasoning_effort": "medium" if enabled else "none"}
    model = build_model({"modelId": "MiniMax-M3", "endpoint": "https://fixture.invalid/v1",
                         "thinkingEnabled": enabled},
                        api_key="synthetic", timeout=180, max_tokens=8192)
    assert model.provider_family == "minimax" and model.thinking_enabled == enabled


def test_unknown_model_does_not_pretend_to_enable_thinking():
    assert tool_model_options("custom-model") == {}
    with pytest.raises(ModelConfigurationError, match="尚未适配深度思考"):
        build_model({"modelId": "custom-model", "endpoint": "https://fixture.invalid/v1",
                     "thinkingEnabled": True}, api_key="synthetic", timeout=180, max_tokens=8192)
    for unsupported in ("o3", "gpt-5", "gpt-5.2-pro", "gpt-5.2-chat-latest"):
        with pytest.raises(ModelConfigurationError):
            tool_model_options(unsupported, True)


def test_summary_excludes_private_reasoning_without_mutating_replay_messages():
    original = AIMessage(content="Visible provider answer", additional_kwargs={
        "reasoning_content": PRIVATE_REASONING,
        "reasoning_details": [{"text": PRIVATE_REASONING, "signature": "synthetic-private-signature"}],
        "other": "Keep this metadata",
    })
    middleware = NewsSummarizationMiddleware(protocol_model(lambda request: provider_response()))
    messages = middleware._input("Prior summary", [[original]])
    serialized = json.dumps([message.model_dump() for message in messages])
    assert PRIVATE_REASONING not in serialized and "synthetic-private-signature" not in serialized
    assert "Visible provider answer" in serialized and "Keep this metadata" in serialized
    assert original.additional_kwargs["reasoning_content"] == PRIVATE_REASONING
