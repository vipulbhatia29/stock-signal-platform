"""Async fire-and-forget DB writer for observability events.

Writes LLMCallLog and ToolExecutionLog rows. Reads session_id and
query_id from ContextVars. Never raises — all errors are logged and
swallowed to avoid blocking user requests.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.request_context import (
    current_agent_instance_id,
    current_agent_type,
    current_query_id,
    current_session_id,
)
from backend.utils.sanitize import sanitize_summary

logger = logging.getLogger(__name__)


async def write_event(event_type: str, data: dict) -> None:
    """Write an observability event to the database.

    Args:
        event_type: "llm_call" or "tool_execution"
        data: Event data dict (keys match model columns).
    """
    try:
        session_id = current_session_id.get()
        query_id = current_query_id.get()
        agent_type = current_agent_type.get(None)
        agent_instance_id = current_agent_instance_id.get(None)

        async with async_session_factory() as db:
            if event_type == "llm_call":
                row = LLMCallLog(
                    session_id=session_id,
                    query_id=query_id,
                    provider=data["provider"],
                    model=data["model"],
                    tier=data.get("tier"),
                    latency_ms=data.get("latency_ms"),
                    prompt_tokens=data.get("prompt_tokens"),
                    completion_tokens=data.get("completion_tokens"),
                    cost_usd=data.get("cost_usd"),
                    error=data.get("error"),
                    agent_type=agent_type,
                    agent_instance_id=agent_instance_id,
                    loop_step=data.get("loop_step"),
                    status=data.get("status", "completed"),
                    langfuse_trace_id=data.get("langfuse_trace_id"),
                )
            elif event_type == "tool_execution":
                row = ToolExecutionLog(
                    session_id=session_id,
                    query_id=query_id,
                    tool_name=data["tool_name"],
                    latency_ms=data.get("latency_ms"),
                    status=data["status"],
                    result_size_bytes=data.get("result_size_bytes"),
                    params=data.get("params"),
                    error=data.get("error"),
                    cache_hit=data.get("cache_hit", False),
                    agent_type=agent_type,
                    agent_instance_id=agent_instance_id,
                    loop_step=data.get("loop_step"),
                    input_summary=sanitize_summary(data.get("params", {})),
                    output_summary=sanitize_summary(data.get("result", "")),
                )
            else:
                logger.warning("Unknown event type: %s", event_type)
                return

            db.add(row)
            await db.commit()
    except Exception:
        logger.warning("Failed to write %s event to DB", event_type, exc_info=True)
