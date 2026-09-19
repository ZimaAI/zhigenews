"""File-backed model settings and code-owned Agent policy, frozen for each run."""

from .errors import AppError
from .security import canonical, digest, encrypt
from .settings import Settings, get_settings

MAX_MODEL_CALLS = 20
MAX_TOOL_CALLS = 40
MAX_SECONDS = 180
SUMMARY_TOKENS = 12000
SUMMARY_MESSAGES = 30
SUMMARY_RATIO = 0.7
SUBAGENT_CONCURRENCY = 2
TOOLS = (
    "list_dir",
    "read_file",
    "search_content",
    "write_file",
    "bash",
    "web_search",
    "delegate_research",
)
SYSTEM_PROMPT = (
    "你是知更新闻编辑。按用户话题、背景与关键词检索可信新闻，核对引用，生成简洁中文摘要和推荐理由。"
    "证据不足时明确说明，不编造新闻。"
)


def agent_config() -> dict:
    """Return a fresh policy snapshot; its version follows changes to the constants."""
    config = dict(
        id="code-agent",
        name="每日新闻",
        modelId="file-main",
        summaryModelId="file-summary",
        maxModelCalls=MAX_MODEL_CALLS,
        maxToolCalls=MAX_TOOL_CALLS,
        maxSeconds=MAX_SECONDS,
        summaryTokens=SUMMARY_TOKENS,
        summaryMessages=SUMMARY_MESSAGES,
        summaryRatio=SUMMARY_RATIO,
        subagentConcurrency=SUBAGENT_CONCURRENCY,
        tools=list(TOOLS),
        systemPrompt=SYSTEM_PROMPT,
    )
    config["version"] = "code-" + digest(canonical(config))[:24]
    return config


def _model_snapshot(settings: Settings, role: str) -> dict:
    prefix = {"main": "", "summary": "summary_", "evaluation": "evaluation_"}[role]

    def value(field):
        primary = getattr(settings, "openai_" + field)
        if isinstance(primary, str):
            primary = primary.strip()
        if not prefix:
            return primary
        override = getattr(settings, prefix + "openai_" + field)
        if isinstance(override, str):
            override = override.strip() or None
        return override if override is not None else primary

    model, endpoint, key = value("model"), value("base_url"), value("api_key")
    missing = [
        prefix.upper() + "OPENAI_" + field
        for field, configured in (("MODEL", model), ("BASE_URL", endpoint), ("API_KEY", key))
        if not configured or not configured.strip()
    ]
    if missing:
        raise AppError(
            "CONFIGURATION_REQUIRED",
            "服务器模型配置不完整，请在配置文件中设置 " + "、".join(missing),
            503,
        )
    return {
        "data": dict(
            id="file-" + role,
            name=model,
            provider="OpenAI-compatible",
            modelId=model,
            endpoint=endpoint,
            contextWindow=value("context_window"),
            thinkingEnabled=value("thinking_enabled"),
        ),
        "encryptedSecret": encrypt(key),
    }


def runtime_models(settings: Settings | None = None) -> dict:
    """Freeze model settings and encrypted credentials without consulting database resources."""
    settings = settings or get_settings()
    return {
        "modelId": _model_snapshot(settings, "main"),
        "summaryModelId": _model_snapshot(settings, "summary"),
    }


def evaluation_judge(settings: Settings | None = None) -> dict | None:
    """An omitted judge model keeps evaluation on its rule-based scorers."""
    settings = settings or get_settings()
    if not settings.evaluation_openai_model.strip():
        return None
    return _model_snapshot(settings, "evaluation")
