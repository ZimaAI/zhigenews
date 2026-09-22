"""Synthetic file configuration and frozen snapshots; no database or provider calls."""

import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from zhigenews import cli, runtime_config, security
from zhigenews.errors import AppError
from zhigenews.settings import Settings


@pytest.fixture
def model_settings(monkeypatch):
    for name in Settings.model_fields:
        if "openai" in name:
            monkeypatch.delenv(name.upper(), raising=False)
    settings = Settings(
        _env_file=None,
        openai_model="synthetic-main",
        openai_base_url="https://fixture.invalid/v1",
        openai_api_key="synthetic-main-key",
        openai_context_window=65536,
        openai_thinking_enabled=True,
        secret_encryption_key=Fernet.generate_key().decode(),
    )
    monkeypatch.setattr(runtime_config, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    return settings


def test_model_settings_load_from_env_file(tmp_path, model_settings):
    path = tmp_path / "models.env"
    path.write_text(
        "OPENAI_MODEL=synthetic-file-main\n"
        "OPENAI_BASE_URL=https://file.invalid/v1\n"
        "OPENAI_API_KEY=synthetic-file-key\n"
        "OPENAI_CONTEXT_WINDOW=131072\n"
        "OPENAI_THINKING_ENABLED=true\n"
        "SUMMARY_OPENAI_MODEL=synthetic-file-summary\n"
        "SUMMARY_OPENAI_THINKING_ENABLED=false\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=path)
    snapshots = runtime_config.runtime_models(settings)
    assert snapshots["modelId"]["data"]["modelId"] == "synthetic-file-main"
    assert snapshots["modelId"]["data"]["endpoint"] == "https://file.invalid/v1"
    assert snapshots["modelId"]["data"]["contextWindow"] == 131072
    assert snapshots["modelId"]["data"]["thinkingEnabled"] is True
    assert snapshots["summaryModelId"]["data"]["modelId"] == "synthetic-file-summary"
    assert snapshots["summaryModelId"]["data"]["thinkingEnabled"] is False
    assert security.decrypt(snapshots["modelId"]["encryptedSecret"]) == "synthetic-file-key"


def test_default_context_window_is_inherited_by_summary(model_settings):
    settings = Settings(
        _env_file=None,
        openai_model="synthetic-main",
        openai_api_key="synthetic-key",
    )
    snapshots = runtime_config.runtime_models(settings)
    assert snapshots["modelId"]["data"]["contextWindow"] == 258000
    assert snapshots["summaryModelId"]["data"]["contextWindow"] == 258000
    config = runtime_config.agent_config()
    assert config["summaryRatio"] == 0.9
    assert "summaryTokens" not in config and "summaryMessages" not in config


def test_summary_inherits_main_and_snapshots_encrypt_credentials(model_settings):
    model_settings.openai_model = " synthetic-main "
    model_settings.openai_base_url = " https://fixture.invalid/v1 "
    model_settings.openai_api_key = " synthetic-main-key "
    snapshots = runtime_config.runtime_models()
    main, summary = snapshots["modelId"], snapshots["summaryModelId"]
    assert main["data"]["id"] == "file-main"
    assert main["data"]["modelId"] == "synthetic-main"
    assert main["data"]["endpoint"] == "https://fixture.invalid/v1"
    assert summary["data"]["id"] == "file-summary"
    for field in ("modelId", "endpoint", "contextWindow", "thinkingEnabled"):
        assert summary["data"][field] == main["data"][field]
    assert "synthetic-main-key" not in json.dumps(snapshots)
    assert security.decrypt(main["encryptedSecret"]) == "synthetic-main-key"
    assert security.decrypt(summary["encryptedSecret"]) == "synthetic-main-key"
    model_settings.openai_model = "synthetic-next"
    model_settings.openai_api_key = "synthetic-next-key"
    assert main["data"]["modelId"] == "synthetic-main"
    assert security.decrypt(main["encryptedSecret"]) == "synthetic-main-key"
    assert runtime_config.runtime_models()["modelId"]["data"]["modelId"] == "synthetic-next"


def test_summary_accepts_independent_model_and_explicit_false(model_settings):
    model_settings.summary_openai_model = "synthetic-summary"
    model_settings.summary_openai_base_url = "https://summary.invalid/v1"
    model_settings.summary_openai_api_key = "synthetic-summary-key"
    model_settings.summary_openai_context_window = 16384
    model_settings.summary_openai_thinking_enabled = False
    snapshot = runtime_config.runtime_models()["summaryModelId"]
    assert snapshot["data"]["modelId"] == "synthetic-summary"
    assert snapshot["data"]["endpoint"] == "https://summary.invalid/v1"
    assert snapshot["data"]["contextWindow"] == 16384
    assert snapshot["data"]["thinkingEnabled"] is False
    assert security.decrypt(snapshot["encryptedSecret"]) == "synthetic-summary-key"


@pytest.mark.parametrize("field", ["model", "base_url", "api_key"])
def test_missing_main_model_setting_has_clear_service_unavailable_error(model_settings, field):
    setattr(model_settings, "openai_" + field, " ")
    with pytest.raises(AppError) as error:
        runtime_config.runtime_models()
    assert error.value.status == 503
    assert "OPENAI_" + field.upper() in error.value.message
    assert "synthetic-main-key" not in error.value.message


@pytest.mark.parametrize("prefix", ["", "summary_"])
def test_context_window_rejects_invalid_configuration(model_settings, prefix):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{prefix + "openai_context_window": 0})


def test_agent_constants_produce_independent_versioned_snapshots(monkeypatch):
    first = runtime_config.agent_config()
    second = runtime_config.agent_config()
    assert first == second
    first["tools"].clear()
    assert second["tools"]
    monkeypatch.setattr(runtime_config, "SYSTEM_PROMPT", "Synthetic changed Agent policy")
    changed = runtime_config.agent_config()
    assert changed["version"] != second["version"]
    assert changed["systemPrompt"] == "Synthetic changed Agent policy"
    assert second["systemPrompt"] != changed["systemPrompt"]


def test_initialization_does_not_create_model_or_agent_resources(monkeypatch, model_settings, capsys):
    model_settings.admin_password = "Synthetic-admin-password"
    model_settings.ip_hash_key = "synthetic-ip-key"
    added = []
    session = SimpleNamespace(scalar=lambda _: object(), get=lambda *_: None, add=added.append)
    monkeypatch.setattr(cli, "get_settings", lambda: model_settings)
    monkeypatch.setattr(cli, "transaction", lambda: nullcontext(session))
    monkeypatch.setattr(cli, "mysql_persistence", lambda *_, **__: nullcontext())
    cli.initialize()
    assert added
    assert {record.kind for record in added} == {"source"}
    assert "No administrator verification or configuration publishing is required" in capsys.readouterr().out


def test_agent_execution_budget_defaults():
    from zhigenews.harness.runtime import Budget
    from zhigenews.harness.search import TavilySearch

    config = runtime_config.agent_config()
    assert config["maxSteps"] == Budget().max_steps == 1000
    assert config["maxSeconds"] == Budget().max_seconds == 600
    assert config["maxSearchCalls"] == TavilySearch(None).max_calls == 20
    assert "maxModelCalls" not in config and "maxToolCalls" not in config
