"""Translate live LangChain execution events into AI SDK UI message SSE."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Any, Literal, TypedDict
from uuid import uuid4

from langchain_core.messages import ToolMessage

from rag_library.agent.context import AgentContext

logger = logging.getLogger(__name__)


class Start(TypedDict):
    type: Literal["start"]
    messageId: str


class TextBoundary(TypedDict):
    type: Literal["text-start", "text-end"]
    id: str


class TextDelta(TypedDict):
    type: Literal["text-delta"]
    id: str
    delta: str


class ToolInput(TypedDict):
    type: Literal["tool-input-available"]
    toolCallId: str
    toolName: str
    input: dict[str, Any]
    dynamic: bool


class ToolOutput(TypedDict):
    type: Literal["tool-output-available"]
    toolCallId: str
    output: dict[str, Any]


class Source(TypedDict):
    type: Literal["data-source"]
    id: str
    data: dict[str, Any]


class Finish(TypedDict):
    type: Literal["finish"]


class Error(TypedDict):
    type: Literal["error"]
    errorText: str


ChatEvent = (
    Start | TextBoundary | TextDelta | ToolInput | ToolOutput | Source | Finish | Error
)


def encode_event(event: ChatEvent) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def stream_chat(
    agent: Any, message: str, context: AgentContext
) -> AsyncIterator[str]:
    """Yield immediately; never accumulate the answer or wait for graph completion."""
    yield encode_event({"type": "start", "messageId": str(uuid4())})
    tool_runs: set[str] = set()
    text_runs: set[str] = set()
    try:
        events = agent.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            context=context,
            version="v2",
        )
        async with aclosing(events):
            async for event in events:
                kind, run_id, data = event["event"], event["run_id"], event["data"]
                if kind == "on_tool_start":
                    tool_runs.add(run_id)
                    yield encode_event(
                        {
                            "type": "tool-input-available",
                            "toolCallId": run_id,
                            "toolName": event["name"],
                            "input": data["input"],
                            "dynamic": True,
                        }
                    )
                elif kind == "on_tool_end":
                    output = data["output"]
                    if isinstance(output, ToolMessage):
                        if output.status == "error":
                            raise ValueError("Agent tool execution failed")
                        output = json.loads(output.content)
                    yield encode_event(
                        {
                            "type": "tool-output-available",
                            "toolCallId": run_id,
                            "output": output,
                        }
                    )
                    if event["name"] == "answer_book_question":
                        for index, source in enumerate(output["sources"]):
                            yield encode_event(
                                {
                                    "type": "data-source",
                                    "id": f"{run_id}-{index}",
                                    "data": {"toolCallId": run_id, **source},
                                }
                            )
                elif (
                    kind == "on_chat_model_stream"
                    and event.get("metadata", {}).get("langgraph_node") == "model"
                    and not tool_runs.intersection(event.get("parent_ids", []))
                ):
                    text = data["chunk"].text
                    if text:
                        if run_id not in text_runs:
                            text_runs.add(run_id)
                            yield encode_event({"type": "text-start", "id": run_id})
                        yield encode_event(
                            {
                                "type": "text-delta",
                                "id": run_id,
                                "delta": text,
                            }
                        )
                elif kind == "on_chat_model_end" and run_id in text_runs:
                    text_runs.remove(run_id)
                    yield encode_event({"type": "text-end", "id": run_id})
        yield encode_event({"type": "finish"})
    except Exception:
        logger.exception("Chat agent execution failed")
        for run_id in text_runs:
            yield encode_event({"type": "text-end", "id": run_id})
        yield encode_event({"type": "error", "errorText": "Agent service unavailable"})
    yield "data: [DONE]\n\n"
