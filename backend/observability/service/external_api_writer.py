"""Persist EXTERNAL_API_CALL events to observability.external_api_call_log."""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.models.external_api_call import ExternalApiCallLog
from backend.observability.schema.v1 import ObsEventBase

logger = logging.getLogger(__name__)


async def persist_external_api_call(event: ObsEventBase) -> None:
    """Insert one EXTERNAL_API_CALL event into the database.

    Maps fields from ExternalApiCallEvent onto ExternalApiCallLog and commits.
    UUID fields are coerced to str because the model uses UUID(as_uuid=False).

    Never raises — errors are logged and swallowed so a DB hiccup cannot
    interrupt the caller or the event-writer flush loop.

    Args:
        event: An ObsEventBase instance, expected to be an ExternalApiCallEvent
            (with provider, endpoint, method, latency_ms, etc.).
    """
    try:
        trace_id = str(event.trace_id) if event.trace_id is not None else None
        span_id = str(event.span_id) if event.span_id is not None else None
        parent_span_id = str(event.parent_span_id) if event.parent_span_id is not None else None
        user_id = str(event.user_id) if event.user_id is not None else None

        row = ExternalApiCallLog(
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
        async with async_session_factory() as db:
            db.add(row)
            await db.commit()
    except Exception:
        logger.exception("obs.writer.external_api_call.failed")
