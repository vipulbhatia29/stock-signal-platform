"""Persist RATE_LIMITER_EVENT events to observability.rate_limiter_event."""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.models.rate_limiter_event import (
    RateLimiterEvent as RateLimiterEventModel,
)
from backend.observability.schema.v1 import ObsEventBase

logger = logging.getLogger(__name__)


def _event_to_row(event: ObsEventBase) -> RateLimiterEventModel:
    """Map a RateLimiterEventPayload onto the RateLimiterEvent model.

    UUID fields are coerced to str because the model uses UUID(as_uuid=False).
    trace_id and span_id are nullable on this model.

    Args:
        event: An ObsEventBase instance with rate-limiter payload fields.

    Returns:
        A detached RateLimiterEvent ORM instance ready for session.add().
    """
    trace_id = str(event.trace_id) if event.trace_id is not None else None
    span_id = str(event.span_id) if event.span_id is not None else None

    return RateLimiterEventModel(
        ts=event.ts,
        trace_id=trace_id,
        span_id=span_id,
        limiter_name=getattr(event, "limiter_name", "unknown"),
        action=getattr(event, "action", "unknown"),
        wait_time_ms=getattr(event, "wait_time_ms", None),
        tokens_remaining=getattr(event, "tokens_remaining", None),
        reason_if_fallback=getattr(event, "reason_if_fallback", None),
        env=event.env,
        git_sha=event.git_sha,
    )


async def persist_rate_limiter_events(events: list[ObsEventBase]) -> None:
    """Insert a batch of RATE_LIMITER_EVENT events in a single DB transaction.

    Uses ``session.add_all()`` + single commit for efficiency. Never raises —
    errors are logged and swallowed so a DB hiccup cannot interrupt the caller
    or the event-writer flush loop.

    Args:
        events: List of ObsEventBase instances (RateLimiterEventPayload payloads).
    """
    try:
        rows = [_event_to_row(e) for e in events]
        async with async_session_factory() as db:
            db.add_all(rows)
            await db.commit()
    except Exception:
        logger.exception("obs.writer.rate_limiter_event.failed")


# Backward-compatible alias for single-event callers (tests).
async def persist_rate_limiter_event(event: ObsEventBase) -> None:
    """Insert one RATE_LIMITER_EVENT. Delegates to batch writer."""
    await persist_rate_limiter_events([event])
