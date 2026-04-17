"""Celery signals that propagate trace_id + span_id across worker boundaries.

- before_task_publish: read ContextVar → write to task headers
- task_prerun: read headers → set ContextVars; store reset Tokens per task_id
- task_postrun: reset ContextVars via Tokens so a prerun exception can't leak
"""

from __future__ import annotations

import logging
from contextvars import Token
from uuid import UUID

from celery.signals import before_task_publish, task_postrun, task_prerun
from uuid_utils import uuid7

from backend.observability.context import (
    parent_span_id_var,
    span_id_var,
    trace_id_var,
)

logger = logging.getLogger(__name__)

_HEADER_TRACE_ID = "obs_trace_id"
_HEADER_SPAN_ID = "obs_parent_span_id"

# Per-task reset tokens — keyed by Celery task_id so overlapping tasks in the same
# worker thread (eventlet/gevent pools) don't step on each other's Tokens.
# Note: entries are removed in task_postrun. If postrun never fires (SIGKILL, OOM),
# entries leak — acceptable since worker restarts clear the dict. If this becomes an
# issue, add bounded eviction in a follow-up PR.
_TOKENS: dict[str, tuple[Token, Token, Token]] = {}


@before_task_publish.connect
def _inject_trace_headers(sender=None, headers=None, **_):
    """Inject ambient trace_id + span_id into outgoing task headers.

    Args:
        sender: The task name (unused).
        headers: Mutable dict of Celery task headers to augment.
        **_: Additional signal kwargs (ignored).
    """
    if headers is None:
        return
    trace_id = trace_id_var.get()
    span_id = span_id_var.get()
    if trace_id is not None:
        headers[_HEADER_TRACE_ID] = str(trace_id)
    if span_id is not None:
        headers[_HEADER_SPAN_ID] = str(span_id)


@task_prerun.connect
def _adopt_trace_headers(task_id=None, task=None, **kwargs):
    """Read trace headers from incoming task and set ContextVars.

    Args:
        task_id: Celery task ID string used as token key.
        task: The Celery Task instance whose request headers are read.
        **kwargs: Additional signal kwargs (ignored).
    """
    req = getattr(task, "request", None)
    if req is None:
        return
    headers = getattr(req, "headers", {}) or {}
    trace_raw = headers.get(_HEADER_TRACE_ID)
    parent_raw = headers.get(_HEADER_SPAN_ID)
    trace_id = _parse(trace_raw)
    if trace_id is None:
        # Beat-triggered or publisher without trace → new root.
        trace_id = UUID(bytes=uuid7().bytes)

    # Set via tokens so postrun can reset even if a later handler raises.
    trace_tok = trace_id_var.set(trace_id)
    span_tok = span_id_var.set(UUID(bytes=uuid7().bytes))
    parent_tok = parent_span_id_var.set(_parse(parent_raw))
    if task_id is not None:
        _TOKENS[task_id] = (trace_tok, span_tok, parent_tok)


@task_postrun.connect
def _clear_trace(task_id=None, **_):
    """Reset ContextVars via stored Tokens, preventing cross-task leaks.

    Args:
        task_id: Celery task ID whose tokens should be popped and reset.
        **_: Additional signal kwargs (ignored).
    """
    tokens = _TOKENS.pop(task_id, None) if task_id is not None else None
    if tokens is None:
        # Fallback: set to None unconditionally. Handles the "prerun raised before
        # we stored tokens" case so the NEXT task on this context isn't polluted.
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)
        return
    trace_tok, span_tok, parent_tok = tokens
    try:
        trace_id_var.reset(trace_tok)
        span_id_var.reset(span_tok)
        parent_span_id_var.reset(parent_tok)
    except ValueError:
        # Token was created in a different Context (e.g., eventlet switch).
        logger.warning("obs.trace.token_reset_failed", extra={"task_id": task_id})
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)


def _parse(raw: str | None) -> UUID | None:
    """Parse a string as UUID, returning None on failure.

    Args:
        raw: A UUID string to parse, or None.

    Returns:
        Parsed UUID instance, or None if raw is falsy or invalid.
    """
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None
