"""Stream event types for NDJSON chat streaming + LangGraph bridge."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """A single event in the NDJSON response stream."""

    type: Literal[
        "thinking",
        "tool_start",
        "tool_result",
        "tool_error",
        "token",
        "done",
        "error",
        "provider_fallback",
        "context_truncated",
        "plan",
        "evidence",
        "decline",
    ]
    content: str | None = None
    tool: str | None = None
    params: dict[str, Any] | None = None
    status: str | None = None
    data: dict[str, Any] | list | str | None = None
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


async def stream_graph_v2_events(
    graph: Any,
    input_state: dict[str, Any],
) -> AsyncIterator[StreamEvent]:
    """Stream events from the V2 Plan→Execute→Synthesize graph.

    Unlike V1 which bridges LangGraph astream_events, V2 runs the graph
    to completion and yields structured events from the result state.
    """
    yield StreamEvent(type="thinking", content="Planning research approach...")

    try:
        result = await graph.ainvoke(input_state)

        plan = result.get("plan", {})
        intent = plan.get("intent", "")

        # Out-of-scope → decline event
        if intent == "out_of_scope":
            decline_msg = result.get("decline_message") or plan.get(
                "decline_message", "I can only help with financial analysis."
            )
            yield StreamEvent(type="decline", content=decline_msg)
            yield StreamEvent(type="done", usage={})
            return

        # Emit plan event
        steps = plan.get("steps", [])
        if steps:
            yield StreamEvent(
                type="plan",
                content=plan.get("reasoning", ""),
                data={"steps": [s.get("tool") for s in steps]},
            )

        # Emit tool results
        for tr in result.get("tool_results", []):
            if tr.get("status") in ("unavailable", "error"):
                yield StreamEvent(
                    type="tool_error",
                    tool=tr.get("tool"),
                    error=tr.get("reason", "Tool failed"),
                )
            else:
                yield StreamEvent(
                    type="tool_result",
                    tool=tr.get("tool"),
                    status=tr.get("status", "ok"),
                    data=tr.get("data"),
                )

        # Emit synthesis / simple response
        synthesis = result.get("synthesis")
        response_text = result.get("response_text", "")

        if synthesis and synthesis.get("evidence"):
            yield StreamEvent(
                type="evidence",
                data=synthesis["evidence"],
            )

        # Stream the response text as tokens (for consistent frontend handling)
        if response_text:
            yield StreamEvent(type="token", content=response_text)

    except Exception:
        logger.exception("stream_graph_v2_events error")
        yield StreamEvent(type="error", error="An internal error occurred. Please try again.")

    yield StreamEvent(type="done", usage={})
