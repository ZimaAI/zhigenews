"""Explicit, bounded live dependency probe. Never substitutes fixtures for providers."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from zhigenews.harness.search import TavilySearch
from zhigenews.models import build_model
from zhigenews.settings import get_settings
from zhigenews.tracing import get_tracing_client, tracing_scope


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    settings = get_settings()
    checks = []
    if not settings.openai_api_key or not settings.openai_model:
        checks.append({"id": "live-model", "status": "blocked", "reason": "OPENAI_MODEL/OPENAI_API_KEY missing"})
    else:
        try:
            model = build_model(
                {"modelId": settings.openai_model, "endpoint": settings.openai_base_url,
                 "thinkingEnabled": False},
                api_key=settings.openai_api_key, timeout=30, max_tokens=100,
            )
            tool = {"type": "function", "function": {"name": "verify_connection", "description": "Check tool calling",
                    "parameters": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}}}
            with tracing_scope(tags=["live-probe"]):
                result = model.bind_tools([tool], tool_choice="verify_connection").invoke(
                    "Call verify_connection with ok=true.", config={"run_name": "zhigenews.live_model_probe"}
                )
            passed = any(t["name"] == "verify_connection" and t["args"].get("ok") is True for t in result.tool_calls)
            checks.append({"id": "live-model", "status": "passed" if passed else "failed", "model": settings.openai_model,
                           "toolCalling": passed, "usage": result.usage_metadata})
        except Exception as exc:
            checks.append({"id": "live-model", "status": "failed", "errorType": type(exc).__name__})
    if not settings.tavily_api_key:
        checks.append({"id": "live-tavily", "status": "blocked", "reason": "TAVILY_API_KEY missing"})
    else:
        try:
            result = TavilySearch(settings.tavily_api_key, max_calls=1).search("artificial intelligence news", max_results=1)
            checks.append({"id": "live-tavily", "status": "passed", "resultCount": len(result.get("results", []))})
        except Exception as exc:
            checks.append({"id": "live-tavily", "status": "failed", "errorType": type(exc).__name__})
    report = {"synthetic": False, "executedAt": datetime.now(UTC).isoformat(), "checks": checks}
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    client = get_tracing_client()
    if client is not None:
        client.flush()
    return 0 if all(c["status"] == "passed" for c in checks) else 2


if __name__ == "__main__":
    raise SystemExit(main())
