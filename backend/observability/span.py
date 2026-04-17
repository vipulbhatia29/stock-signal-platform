"""`span()` async contextmanager — builds causality trees.

Each nested span inherits the ambient trace_id and sets its own UUIDv7 span_id;
parent_span_id = the span_id that was current on entry. On exit, ContextVars are
restored so siblings see the parent span_id, not the just-closed one.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator
from uuid import UUID

from uuid_utils import uuid7

from backend.observability.context import (
    parent_span_id_var,
    span_id_var,
    trace_id_var,
)


@dataclass(frozen=True)
class Span:
    """Immutable record of a span's identity within a trace."""

    name: str
    trace_id: UUID | None
    span_id: UUID
    parent_span_id: UUID | None


@asynccontextmanager
async def span(name: str) -> AsyncIterator[Span]:
    """Create a child span under the current trace context.

    Sets span_id to a new UUIDv7 and parent_span_id to the previous span_id.
    Restores ContextVars on exit so sibling spans see the correct parent.
    """
    prev_span = span_id_var.get()
    prev_parent = parent_span_id_var.get()
    new_span = UUID(bytes=uuid7().bytes)
    span_tok = span_id_var.set(new_span)
    parent_tok = parent_span_id_var.set(prev_span)  # previous becomes parent
    try:
        yield Span(
            name=name,
            trace_id=trace_id_var.get(),
            span_id=new_span,
            parent_span_id=prev_span,
        )
    finally:
        span_id_var.reset(span_tok)
        parent_span_id_var.reset(parent_tok)
