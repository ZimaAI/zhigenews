"""LangGraph/LangChain tracing configured from the same settings as the backend."""

import logging
import re
from functools import lru_cache

from langsmith import Client, tracing_context

from .settings import get_settings

logger = logging.getLogger(__name__)

# Provider reasoning is retained locally for protocol replay, never for export.
PRIVATE_FIELDS = {"reasoning_content", "reasoning_details", "reasoning", "thinking", "signature"}
SECRET_FIELDS = {
    "api_key", "apikey", "openai_api_key", "tavily_api_key", "langsmith_api_key",
    "authorization", "password", "encryptedsecret", "secret_encryption_key", "ip_hash_key",
}
PRIVATE_BLOCKS = {"reasoning", "thinking", "redacted_thinking", "reasoning.text"}


def sanitize_trace(value):
    """Copy the SDK's JSON payload, keeping visible content and usage intact."""
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in SECRET_FIELDS else sanitize_trace(item)
            for key, item in value.items()
            if key.lower() not in PRIVATE_FIELDS
        }
    if isinstance(value, list):
        return [
            sanitize_trace(item) for item in value
            if not (
                isinstance(item, dict) and isinstance(item.get("type"), str)
                and item["type"] in PRIVATE_BLOCKS
            )
        ]
    if isinstance(value, str):
        value = re.sub(r"(?i)(bearer\s+|api[_-]?key[\"'\s:=]+)[\w\-\.]+", r"\1[redacted]", value)
        return re.sub(r"\b(?:sk-|lsv2_(?:pt|sk)_)[\w-]+", "[redacted]", value)
    return value


@lru_cache(maxsize=1)
def get_tracing_client() -> Client | None:
    settings = get_settings()
    if not settings.langsmith_tracing:
        return None
    if not settings.langsmith_api_key.get_secret_value():
        logger.warning("LangSmith tracing is enabled but LANGSMITH_API_KEY is missing; tracing is inactive.")
        return None
    try:
        return Client(
            api_key=settings.langsmith_api_key.get_secret_value(),
            api_url=settings.langsmith_endpoint,
            workspace_id=settings.langsmith_workspace_id or None,
            anonymizer=sanitize_trace,
        )
    except Exception as exc:
        # Observability configuration must not prevent brief generation.
        logger.warning("LangSmith client initialization failed (%s); tracing is inactive.", type(exc).__name__)
        return None


def tracing_scope(*, metadata=None, tags=None):
    client = get_tracing_client()
    return tracing_context(
        enabled=client is not None,
        client=client,
        project_name=get_settings().langsmith_project,
        tags=["zhigenews", *(tags or [])],
        metadata=metadata,
    )
