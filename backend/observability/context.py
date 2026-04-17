"""Request-scoped context variables for tool execution.

Tools called by LangGraph's ToolNode don't receive the FastAPI request
or user object. This module provides contextvars that the chat router
sets before streaming, and tools read during execution.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# Set by chat_stream before invoking the LangGraph graph.
# Read by tools that need user context (portfolio_exposure, etc.).
current_user_id: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)

# Set by chat_stream to propagate session/query tracing context to the
# observability writer without changing any function signatures.
current_session_id: ContextVar[uuid.UUID | None] = ContextVar("current_session_id", default=None)
current_query_id: ContextVar[uuid.UUID | None] = ContextVar("current_query_id", default=None)

# Agent attribution — set by chat_stream, read by observability writer.
# agent_type: "stock" | "general" etc.; agent_instance_id: unique per-query UUID.
current_agent_type: ContextVar[str | None] = ContextVar("current_agent_type", default=None)
current_agent_instance_id: ContextVar[str | None] = ContextVar(
    "current_agent_instance_id", default=None
)

# --- Trace propagation ContextVars (PR3) ---
trace_id_var: ContextVar[uuid.UUID | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[uuid.UUID | None] = ContextVar("span_id", default=None)
parent_span_id_var: ContextVar[uuid.UUID | None] = ContextVar("parent_span_id", default=None)


def current_trace_id() -> uuid.UUID | None:
    """Return the ambient trace_id or None."""
    return trace_id_var.get()


def current_span_id() -> uuid.UUID | None:
    """Return the ambient span_id or None."""
    return span_id_var.get()


def current_parent_span_id() -> uuid.UUID | None:
    """Return the ambient parent_span_id or None."""
    return parent_span_id_var.get()
