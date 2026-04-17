"""Generate-or-adopt a canonical trace_id on every HTTP request.

- Generates UUIDv7 if no valid X-Trace-Id header
- Adopts incoming X-Trace-Id if parseable as UUID (not strictly v7 — forward-compat)
- Sets ContextVars so downstream code + logs see it
- Injects X-Trace-Id into response headers
- MUST be registered OUTSIDE ErrorHandlerMiddleware so errors carry trace_id
"""
from __future__ import annotations

from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from uuid_utils import uuid7

from backend.observability.context import parent_span_id_var, span_id_var, trace_id_var


class TraceIdMiddleware(BaseHTTPMiddleware):
    """Assign a trace_id to every HTTP request."""

    async def dispatch(self, request: Request, call_next):
        """Generate or adopt trace_id, set ContextVars, inject response header."""
        incoming = request.headers.get("X-Trace-Id")
        trace_id: UUID | None = None
        if incoming:
            try:
                trace_id = UUID(incoming)
            except ValueError:
                trace_id = None
        if trace_id is None:
            trace_id = UUID(bytes=uuid7().bytes)

        trace_tok = trace_id_var.set(trace_id)
        span_tok = span_id_var.set(None)
        parent_tok = parent_span_id_var.set(None)
        try:
            response: Response = await call_next(request)
        finally:
            trace_id_var.reset(trace_tok)
            span_id_var.reset(span_tok)
            parent_span_id_var.reset(parent_tok)
        response.headers["X-Trace-Id"] = str(trace_id)
        return response
