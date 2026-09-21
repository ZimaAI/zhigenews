"""File-backed model settings and code-owned Agent policy, frozen for each run."""

from .errors import AppError
from .security import canonical, digest, encrypt
from .settings import Settings, get_settings

MAX_STEPS = 1000
MAX_SECONDS = 600
MAX_SEARCH_CALLS = 20
SUMMARY_RATIO = 0.9
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
    "你是知更新闻编辑。按用户话题、背景与关键词检索可信新闻，核对引用，为普通读者编写简报。"
    "简报标题像报纸标题，用一句话概括本期主要新闻，不堆砌话题、简报前缀或运行日期。"
    "导语 summary 用1–2句概括本期重点；每条新闻 summary 用2–3句大白话讲清发生了什么、"
    "为什么值得关注，没有证据支持就不补意义。短句、少术语，避免罗列大量人名、品牌和数字。"
    "保留事实所需的来源归属和限定，例如‘据某方称’‘尚未公布’，不编造新闻或结论。"
    "标题、导语和新闻摘要都是给读者看的，不得出现检索窗口、UTC、索引数量、工具、预算、"
    "执行过程或后台配置。检索限制、来源缺失和资料不足只写入内部 limitations；"
    "reason 单独说明推荐理由，不把内部诊断写进读者正文。"
)


def agent_config() -> dict:
    """Return a fresh policy snapshot; its version follows changes to the constants."""
    config = dict(
        id="code-agent",
        name="每日新闻",
        modelId="file-main",
        summaryModelId="file-summary",
        maxSteps=MAX_STEPS,
        maxSearchCalls=MAX_SEARCH_CALLS,
        maxSeconds=MAX_SECONDS,
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
