"""Repair only settled model inputs; never invent successful tool outcomes."""

from __future__ import annotations

from collections import defaultdict

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, RemoveMessage, ToolMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from .errors import HarnessError


def repair_messages(
    messages: list[BaseMessage], *, active_calls: set[str] | None = None
) -> tuple[list[BaseMessage], list[dict]]:
    calls, results, audit = {}, defaultdict(list), []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in [*message.tool_calls, *message.invalid_tool_calls]:
                call_id = call.get("id")
                if not call_id or call_id in calls:
                    raise HarnessError("AMBIGUOUS_TOOL_CALL", "工具调用标识缺失或被多次使用，不能自动配对。")
                calls[call_id] = call
        elif isinstance(message, ToolMessage):
            results[message.tool_call_id].append(message)
    for call_id in results.keys() - calls.keys():
        audit.append({"kind": "orphan_result", "toolCallId": call_id, "count": len(results[call_id])})
    rebuilt = []
    for message in messages:
        if isinstance(message, ToolMessage):
            continue
        rebuilt.append(message)
        if not isinstance(message, AIMessage):
            continue
        for call in [*message.tool_calls, *message.invalid_tool_calls]:
            call_id = call["id"]
            matches = results[call_id]
            if not matches:
                if call_id in (active_calls or set()):
                    raise HarnessError("TOOL_STILL_RUNNING", "工具尚未终止，不得补写中断结果。")
                result = ToolMessage(
                    content="工具结果未记录；该调用可能已中断或已执行但回执丢失。不得假定成功或盲目重做副作用。",
                    tool_call_id=call_id,
                    name=call.get("name"),
                    status="error",
                    id="repair-" + call_id,
                )
                audit.append({"kind": "missing_result", "toolCallId": call_id})
            else:
                # Latest recorded terminal result wins; original journal remains unchanged.
                result = matches[-1]
                if len(matches) > 1:
                    audit.append({"kind": "duplicate_result", "toolCallId": call_id, "count": len(matches)})
            rebuilt.append(result)
    if [x.id for x in rebuilt] != [x.id for x in messages] and not audit:
        audit.append({"kind": "reordered_results"})
    return rebuilt, audit


class MessageRepairMiddleware(AgentMiddleware):
    def before_model(self, state, runtime):
        repaired, audit = repair_messages(state["messages"])
        for event in audit:
            runtime.context.emit("message_repaired", **event)
        if audit:
            return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *repaired]}
        return None

    async def abefore_model(self, state, runtime):
        return self.before_model(state, runtime)
