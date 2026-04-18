"""Persist EXTERNAL_API_CALL events to observability.external_api_call_log."""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.models.external_api_call import ExternalApiCallLog
from backend.observability.schema.v1 import ObsEventBase

logger = logging.getLogger(__name__)


def _event_to_row(event: ObsEventBase) -> ExternalApiCallLog:
    """Map an ExternalApiCallEvent onto an ExternalApiCallLog model instance.

    UUID fields are coerced to str because the model uses UUID(as_uuid=False).

    Args:
        event: An ObsEventBase instance with external-API-call payload fields.

    Returns:
        A detached ExternalApiCallLog ORM instance ready for session.add().
    """
    trace_id = str(event.trace_id) if event.trace_id is not None else None
    span_id = str(event.span_id) if event.span_id is not None else None
    parent_span_id = str(event.parent_span_id) if event.parent_span_id is not None else None
    user_id = str(event.user_id) if event.user_id is not None else None

    return ExternalApiCallLog(
        ts=event.ts,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        user_id=user_id,
        provider=getattr(event, "provider", "unknown"),
        endpoint=getattr(event, "endpoint", ""),
        method=getattr(event, "method", "GET"),
        status_code=getattr(event, "status_code", None),
        error_reason=getattr(event, "error_reason", None),
        latency_ms=getattr(event, "latency_ms", 0),
        request_bytes=getattr(event, "request_bytes", None),
        response_bytes=getattr(event, "response_bytes", None),
        retry_count=getattr(event, "retry_count", 0),
        cost_usd=getattr(event, "cost_usd", None),
        rate_limit_remaining=getattr(event, "rate_limit_remaining", None),
        rate_limit_reset_ts=getattr(event, "rate_limit_reset_ts", None),
        rate_limit_headers=getattr(event, "rate_limit_headers", None),
        stack_signature=getattr(event, "stack_signature", None),
        stack_hash=getattr(event, "stack_hash", None),
        env=event.env,
        git_sha=event.git_sha,
    )


async def persist_external_api_calls(events: list[ObsEventBase]) -> None:
    """Insert a batch of EXTERNAL_API_CALL events in a single DB transaction.

    Uses ``session.add_all()`` + single commit for efficiency. Never raises —
    errors are logged and swallowed so a DB hiccup cannot interrupt the caller
    or the event-writer flush loop.

    Args:
        events: List of ObsEventBase instances (ExternalApiCallEvent payloads).
    """
    try:
        rows = [_event_to_row(e) for e in events]
        async with async_session_factory() as db:
            db.add_all(rows)
            await db.commit()
    except Exception:
        logger.exception("obs.writer.external_api_call.failed")


# Backward-compatible alias for single-event callers (tests).
async def persist_external_api_call(event: ObsEventBase) -> None:
    """Insert one EXTERNAL_API_CALL event. Delegates to batch writer."""
    await persist_external_api_calls([event])
