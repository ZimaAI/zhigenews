"""Exercise real LangSmith serialization without sending traces over the network."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import requests
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import Client
from pydantic import SecretStr
from test_harness_runtime import ScriptedModel, ai_call

from zhigenews import tracing
from zhigenews.harness import HarnessRequest, HarnessRunner
from zhigenews.settings import Settings

PRIVATE_REASONING = "Synthetic private reasoning retained only for provider replay"
PRIVATE_SIGNATURE = "synthetic-private-reasoning-signature"
PROVIDER_KEY = "sk-synthetic-provider-key"
TOOL_TOKEN = "synthetic-tool-bearer-token"
ORIGINAL_GET_TRACING_CLIENT = tracing.get_tracing_client


class TracedScriptedModel(ScriptedModel):
    def to_json(self):
        # This fixture holds predetermined replies in its attributes. Production
        # ChatOpenAI serializes model configuration, never preloaded reply history.
        return {"lc": 1, "type": "constructor", "id": ["tests", "ScriptedModel"], "kwargs": {}}


class RecordingSession(requests.Session):
    def __init__(self, *, fail=False):
        super().__init__()
        self.payloads = []
        self.fail = fail

    def request(self, method, url, **kwargs):
        # A real Client serializes and sanitizes these bodies before this boundary.
        assert "/runs" in url, f"Unexpected tracing request: {method} {url}"
        payload = json.loads(kwargs["data"])
        if method.upper() == "PATCH":
            payload["id"] = url.rsplit("/", 1)[-1]
        self.payloads.append((method.upper(), payload))
        response = requests.Response()
        response.status_code = 403 if self.fail else 200
        response._content = b'{"detail":"Synthetic exporter failure"}' if self.fail else b"{}"
        response.url = url
        response.request = requests.Request(method, url).prepare()
        return response


@pytest.fixture
def recording_tracing(monkeypatch):
    clients = []
    monkeypatch.setenv("LANGCHAIN_CALLBACKS_BACKGROUND", "false")

    def configure(*, fail=False):
        session = RecordingSession(fail=fail)
        client = Client(
            api_url="https://tracing.example.test",
            api_key="synthetic-langsmith-key",
            session=session,
            auto_batch_tracing=False,
            info={"version": "test"},
            anonymizer=tracing.sanitize_trace,
        )
        clients.append(client)
        monkeypatch.setattr(tracing, "get_tracing_client", lambda: client)
        monkeypatch.setattr(
            tracing, "get_settings", lambda: SimpleNamespace(langsmith_project="my-first-agent")
        )
        return session

    yield configure
    for client in clients:
        client.close()


def harness_request(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "inputs").mkdir(parents=True)
    (workspace / "inputs" / "fixture.json").write_text(
        json.dumps({"authorization": "Bearer " + TOOL_TOKEN, "news": "No matching news"}),
        encoding="utf-8",
    )
    first = ai_call("read_file", {"path": "/workspace/inputs/fixture.json"}, "read")
    first.additional_kwargs = {
        "reasoning_content": PRIVATE_REASONING,
        "reasoning_details": [{"text": PRIVATE_REASONING, "signature": PRIVATE_SIGNATURE}],
    }
    model = TracedScriptedModel(responses=[
        first,
        ai_call("BriefOutput", {"title": "Synthetic traced brief", "items": [],
                                "limitations": ["No supplied news"]}, "final"),
    ])
    return HarnessRequest(
        user_id="synthetic-user",
        run_id="synthetic-run",
        thread_id="synthetic-thread",
        preferences={"topics": ["AI"]},
        config={"tools": ["read_file"], "maxSteps": 4},
        rss_root=tmp_path / "rss",
        workspace_root=workspace,
        model=model,
        instruction="Generate a synthetic brief. api_key=" + PROVIDER_KEY,
    )


@pytest.mark.parametrize("asynchronous", [False, True])
def test_harness_exports_agent_model_tool_tree_without_private_fields(
    tmp_path, recording_tracing, asynchronous
):
    session = recording_tracing()
    request = harness_request(tmp_path)
    runner = HarnessRunner(checkpointer=InMemorySaver())
    result = asyncio.run(runner.arun(request)) if asynchronous else runner.run(request)

    assert result.title == "Synthetic traced brief"
    runs = {payload["id"]: payload for method, payload in session.payloads if method == "POST"}
    root = next(run for run in runs.values() if run["name"] == "zhigenews.agent")
    assert root["session_name"] == "my-first-agent"
    assert root.get("parent_run_id") is None
    assert "zhigenews" in root["tags"]
    metadata = root["extra"]["metadata"]
    assert metadata["run_id"] == request.run_id
    assert metadata["agent_thread_id"] == request.thread_id
    assert metadata["resumed"] is False
    assert metadata["agent_depth"] == 0
    model_runs = [run for run in runs.values() if run["run_type"] == "llm"]
    tool_runs = [run for run in runs.values() if run["run_type"] == "tool"]
    assert len(model_runs) == 2
    assert [run["name"] for run in tool_runs] == ["read_file"]
    for child in model_runs + tool_runs:
        assert child["trace_id"] == root["id"]
        cursor = child
        while cursor.get("parent_run_id"):
            cursor = runs[cursor["parent_run_id"]]
        assert cursor["id"] == root["id"]

    exported = json.dumps(session.payloads)
    for secret in (PRIVATE_REASONING, PRIVATE_SIGNATURE, PROVIDER_KEY, TOOL_TOKEN):
        assert secret not in exported
    assert "Synthetic traced brief" in exported
    original = request.model.responses[0]
    assert original.additional_kwargs["reasoning_content"] == PRIVATE_REASONING
    replay = next(message for message in request.model.received[1]
                  if message.additional_kwargs.get("reasoning_content"))
    assert replay.additional_kwargs["reasoning_content"] == PRIVATE_REASONING


def test_disabled_scope_overrides_ambient_tracing(tmp_path, recording_tracing, monkeypatch):
    session = recording_tracing()
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setattr(tracing, "get_tracing_client", lambda: None)
    result = HarnessRunner(checkpointer=InMemorySaver()).run(harness_request(tmp_path))
    assert result.title == "Synthetic traced brief"
    assert session.payloads == []


def test_export_failure_does_not_fail_generation(tmp_path, recording_tracing):
    session = recording_tracing(fail=True)
    result = HarnessRunner(checkpointer=InMemorySaver()).run(harness_request(tmp_path))
    assert session.payloads
    assert result.title == "Synthetic traced brief"
    assert result.usage["modelCalls"] == 2
    assert (tmp_path / "workspace" / "output" / "brief.json").exists()


def test_subagent_remains_in_parent_trace(tmp_path, recording_tracing):
    session = recording_tracing()
    request = harness_request(tmp_path)
    request.config.update(tools=["read_file", "delegate_research"], maxSteps=7)
    request.model.responses = [
        ai_call("delegate_research", {"task": "Check the supplied fixture"}, "delegate"),
        *request.model.responses,
        ai_call("BriefOutput", {"title": "Parent brief", "items": []}, "parent-final"),
    ]
    result = HarnessRunner(checkpointer=InMemorySaver()).run(request)
    assert result.title == "Parent brief"
    runs = {payload["id"]: payload for method, payload in session.payloads if method == "POST"}
    parent = next(run for run in runs.values() if run["name"] == "zhigenews.agent")
    child = next(run for run in runs.values() if run["name"] == "zhigenews.subagent")
    assert child["trace_id"] == parent["id"]
    assert child["extra"]["metadata"]["agent_depth"] == 1
    assert child["extra"]["metadata"]["run_id"].startswith(request.run_id + ":")
    cursor = child
    ancestor_names = []
    while cursor.get("parent_run_id"):
        cursor = runs[cursor["parent_run_id"]]
        ancestor_names.append(cursor["name"])
    assert "delegate_research" in ancestor_names
    assert cursor["id"] == parent["id"]


def test_sanitizer_preserves_original_and_cleans_nested_metadata():
    original = {
        "metadata": {"api_key": "synthetic-config-key", "Authorization": "Bearer " + TOOL_TOKEN},
        "messages": [{"additional_kwargs": {
            "reasoning_content": PRIVATE_REASONING,
            "reasoning_details": [{"signature": PRIVATE_SIGNATURE}],
        }, "content": "A visible answer"}],
    }
    before = deepcopy(original)
    sanitized = tracing.sanitize_trace(original)
    serialized = json.dumps(sanitized)
    assert "A visible answer" in serialized
    for secret in ("synthetic-config-key", TOOL_TOKEN, PRIVATE_REASONING, PRIVATE_SIGNATURE):
        assert secret not in serialized
    assert original == before


@pytest.mark.parametrize(("enabled", "key"), [(False, "synthetic-key"), (True, "")])
def test_client_requires_both_opt_in_and_credentials(monkeypatch, enabled, key):
    monkeypatch.setattr(tracing, "get_tracing_client", ORIGINAL_GET_TRACING_CLIENT)
    tracing.get_tracing_client.cache_clear()
    monkeypatch.setattr(tracing, "get_settings", lambda: SimpleNamespace(
        langsmith_tracing=enabled, langsmith_api_key=SecretStr(key)
    ))
    try:
        assert tracing.get_tracing_client() is None
    finally:
        tracing.get_tracing_client.cache_clear()


def test_client_uses_settings_credentials_endpoint_workspace_and_sanitizer(monkeypatch):
    monkeypatch.setattr(tracing, "get_tracing_client", ORIGINAL_GET_TRACING_CLIENT)
    tracing.get_tracing_client.cache_clear()
    monkeypatch.setattr(tracing, "get_settings", lambda: SimpleNamespace(
        langsmith_tracing=True, langsmith_api_key=SecretStr("synthetic-client-key"),
        langsmith_endpoint="https://tracing.example.test", langsmith_workspace_id="synthetic-workspace",
    ))
    created = []
    client = object()

    def create_client(**kwargs):
        created.append(kwargs)
        return client

    monkeypatch.setattr(tracing, "Client", create_client)
    try:
        assert tracing.get_tracing_client() is client
        assert tracing.get_tracing_client() is client
        assert created == [{"api_key": "synthetic-client-key", "api_url": "https://tracing.example.test",
                            "workspace_id": "synthetic-workspace", "anonymizer": tracing.sanitize_trace}]
    finally:
        tracing.get_tracing_client.cache_clear()


def test_settings_load_langsmith_from_dotenv(tmp_path, monkeypatch):
    for name in ("LANGSMITH_TRACING", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    config = tmp_path / ".env"
    config.write_text(
        "LANGSMITH_TRACING=true\nLANGSMITH_API_KEY=synthetic-dotenv-key\n"
        "LANGSMITH_PROJECT=my-first-agent\nLANGSMITH_ENDPOINT=https://tracing.example.test\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=config)
    assert settings.langsmith_tracing is True
    assert settings.langsmith_project == "my-first-agent"
    assert settings.langsmith_api_key.get_secret_value() == "synthetic-dotenv-key"
    assert "synthetic-dotenv-key" not in repr(settings)
