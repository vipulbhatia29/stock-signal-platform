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
