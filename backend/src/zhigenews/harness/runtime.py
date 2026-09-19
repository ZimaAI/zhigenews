from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain.agents import AgentState
from typing_extensions import NotRequired

from .errors import HarnessError, RunCancelled


class NewsAgentState(AgentState):
    summary: NotRequired[str]
    summary_revision: NotRequired[int]
    summary_covered_ids: NotRequired[list[str]]
    budget: NotRequired[dict]
    file_versions: NotRequired[dict]
    journal_ids: NotRequired[list[str]]
    next_message_seq: NotRequired[int]
    subtasks: NotRequired[list[dict]]


@dataclass
class Budget:
    max_model_calls: int = 20
    max_tool_calls: int = 40
    max_seconds: int = 180
    model_calls: int = 0
    tool_calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_complete: bool = True
    started: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    persist: Callable[[dict], None] = field(default=lambda state: None, repr=False)

    def check(self, cancelled: Callable[[], bool]) -> None:
        if cancelled():
            raise RunCancelled()
        if time.time() - self.started > self.max_seconds:
            raise HarnessError("TIME_BUDGET", "运行时间预算已耗尽。")

    def reserve(self, kind: str, cancelled: Callable[[], bool]) -> None:
        with self.lock:
            self.check(cancelled)
            field_name = kind + "_calls"
            if getattr(self, field_name) >= getattr(self, "max_" + field_name):
                raise HarnessError("BUDGET_EXHAUSTED", "模型或工具调用预算已耗尽。")
            setattr(self, field_name, getattr(self, field_name) + 1)
            self.persist(self.snapshot())

    def record_usage(self, usage: dict | None) -> None:
        with self.lock:
            if not usage or "input_tokens" not in usage or "output_tokens" not in usage:
                self.usage_complete = False
            else:
                self.input_tokens = (self.input_tokens or 0) + usage["input_tokens"]
                self.output_tokens = (self.output_tokens or 0) + usage["output_tokens"]
            self.persist(self.snapshot())

    def snapshot(self) -> dict:
        return {
            "modelCalls": self.model_calls,
            "toolCalls": self.tool_calls,
            "inputTokens": self.input_tokens if self.usage_complete else None,
            "outputTokens": self.output_tokens if self.usage_complete else None,
            "knownInputTokens": self.input_tokens,
            "knownOutputTokens": self.output_tokens,
            "usageComplete": self.usage_complete,
            "elapsedSeconds": round(time.time() - self.started, 3),
            "started": self.started,
            "cost": None,
        }


@dataclass
class RunContext:
    user_id: str
    run_id: str
    thread_id: str
    config: dict
    preferences: dict
    budget: Budget
    files: Any
    event_sink: Callable[[dict], None]
    cancelled: Callable[[], bool]
    evidence: dict
    depth: int = 0
    child_semaphore: Any = None
    subtasks: list[dict] = field(default_factory=list)

    def emit(self, kind: str, **payload) -> None:
        from datetime import datetime, timezone

        self.event_sink(
            {
                "type": kind,
                "runId": self.run_id,
                "threadId": self.thread_id,
                "time": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
        )
