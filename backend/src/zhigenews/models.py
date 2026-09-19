"""Model construction and private thinking-protocol support shared by all callers."""

import re
from copy import deepcopy

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from pydantic import Field

DEEPSEEK_THINKING_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-flash"}
PRIVATE_REASONING_FIELDS = ("reasoning_content", "reasoning_details")


class ModelConfigurationError(ValueError):
    code = "THINKING_UNSUPPORTED"


def tool_model_options(model_id: str, thinking_enabled: bool = False) -> dict:
    if model_id.lower() in DEEPSEEK_THINKING_MODELS:
        return {"extra_body": {"thinking": {"type": "enabled" if thinking_enabled else "disabled"}}}
    if model_id.lower() == "minimax-m3":
        # MiniMax's Chat API documents adaptive as thinking on. Split reasoning
        # from visible text so it stays private while being replayed intact.
        # https://platform.minimax.io/docs/api-reference/text-openai-api
        return {"extra_body": {
            "thinking": {"type": "adaptive" if thinking_enabled else "disabled"},
            "reasoning_split": True,
        }}
    if re.fullmatch(r"gpt-5\.(1|2|4|5)(?:-\d{4}-\d{2}-\d{2})?", model_id.lower()):
        return {"reasoning_effort": "medium" if thinking_enabled else "none"}
    if thinking_enabled:
        raise ModelConfigurationError("当前模型尚未适配深度思考开关，请关闭开关或使用已支持的模型")
    return {}


class ThinkingChatOpenAI(ChatOpenAI):
    """Retain provider reasoning only in private messages and the provider protocol.

    ChatOpenAI intentionally drops provider-specific reasoning fields. DeepSeek
    requires those fields to be replayed on every assistant turn when using tools.
    https://api-docs.deepseek.com/guides/thinking_mode/
    """

    thinking_enabled: bool = Field(default=False, exclude=True)
    provider_family: str = Field(default="deepseek", exclude=True)

    def _create_chat_result(self, response, generation_info=None):
        result = super()._create_chat_result(response, generation_info)
        if self.thinking_enabled:
            raw = response if isinstance(response, dict) else response.model_dump()
            for generation, choice in zip(result.generations, raw.get("choices", []), strict=False):
                message = choice.get("message", {})
                for field in PRIVATE_REASONING_FIELDS:
                    if message.get(field) is not None:
                        generation.message.additional_kwargs[field] = deepcopy(message[field])
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs):
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        if self.provider_family == "deepseek" and "max_completion_tokens" in payload:
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        if self.thinking_enabled and payload.get("tools"):
            # Required/named choices are incompatible with DeepSeek thinking.
            payload["tool_choice"] = "auto"
            for message, wire in zip(messages, payload["messages"], strict=True):
                if isinstance(message, AIMessage):
                    for field in PRIVATE_REASONING_FIELDS:
                        if field in message.additional_kwargs:
                            wire[field] = deepcopy(message.additional_kwargs[field])
                    wire["content"] = wire.get("content") or ""
        return payload


def build_model(data, *, api_key, timeout, max_tokens):
    model_id = data["modelId"]
    thinking_enabled = data.get("thinkingEnabled", False)
    options = tool_model_options(model_id, thinking_enabled)
    model_class = ChatOpenAI
    if model_id.lower() in DEEPSEEK_THINKING_MODELS or model_id.lower() == "minimax-m3":
        model_class = ThinkingChatOpenAI
        # Both invoke and ainvoke use the result conversion above; reasoning is
        # never emitted through a streaming callback or public progress channel.
        options.update(
            thinking_enabled=thinking_enabled,
            provider_family="minimax" if model_id.lower() == "minimax-m3" else "deepseek",
            disable_streaming=True,
            use_responses_api=False,
        )
    return model_class(
        model=model_id,
        base_url=data["endpoint"],
        api_key=api_key,
        timeout=timeout,
        max_retries=0,
        max_tokens=max_tokens,
        **options,
    )
