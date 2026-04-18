"""Batch writer for api_error_log events."""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.models.api_error_log import ApiErrorLog
from backend.observability.schema.http_events import ApiErrorLogEvent

logger = logging.getLogger(__name__)


async def persist_api_error_logs(events: list[ApiErrorLogEvent]) -> None:
    """Persist API error events to observability.api_error_log.

    Args:
        events: List of ApiErrorLogEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                ApiErrorLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    user_id=str(event.user_id) if event.user_id else None,
                    status_code=event.status_code,
                    error_type=(
                        event.error_type.value
                        if hasattr(event.error_type, "value")
                        else event.error_type
                    ),
                    error_reason=event.error_reason,
                    error_message=event.error_message,
                    stack_signature=event.stack_signature,
                    stack_hash=event.stack_hash,
                    stack_trace=event.stack_trace[:5120] if event.stack_trace else None,
                    exception_class=event.exception_class,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        await session.commit()
    logger.debug("Persisted %d api_error_log rows", len(events))
