"""Stream event types for NDJSON chat streaming + LangGraph bridge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal


@dataclass
class StreamEvent:
    """A single event in the NDJSON response stream."""

    type: Literal[
        "thinking",
        "tool_start",
        "tool_result",
        "token",
        "done",
        "provider_fallback",
        "context_truncated",
    ]
    content: str | None = None
    tool: str | None = None
    params: dict[str, Any] | None = None
    status: str | None = None
    data: Any = None
    usage: dict[str, Any] | None = None
    error: str | None = None

    def to_ndjson(self) -> str:
        """Serialize to a single JSON line (no trailing newline)."""
        d: dict[str, Any] = {"type": self.type}
        for key in ("content", "tool", "params", "status", "data", "usage", "error"):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        return json.dumps(d)


async def stream_graph_events(
    graph: Any,
    input_state: dict[str, Any],
    config: dict[str, Any],
) -> AsyncIterator[StreamEvent]:
    """Bridge LangGraph astream_events to our NDJSON StreamEvent format."""
    yield StreamEvent(type="thinking", content="Analyzing your question...")

    async for event in graph.astream_events(input_state, config, version="v2"):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            if hasattr(chunk, "content") and chunk.content:
                yield StreamEvent(type="token", content=chunk.content)
        elif kind == "on_tool_start":
            yield StreamEvent(
                type="tool_start",
                tool=event["name"],
                params=event["data"].get("input"),
            )
        elif kind == "on_tool_end":
            yield StreamEvent(
                type="tool_result",
                tool=event["name"],
                status="ok",
                data=event["data"].get("output"),
            )

    yield StreamEvent(type="done", usage={})
