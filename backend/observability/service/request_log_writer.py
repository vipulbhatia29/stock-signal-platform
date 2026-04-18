"""Batch writer for request_log events."""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.models.request_log import RequestLog
from backend.observability.schema.http_events import RequestLogEvent

logger = logging.getLogger(__name__)


async def persist_request_logs(events: list[RequestLogEvent]) -> None:
    """Persist request log events to observability.request_log.

    Args:
        events: List of RequestLogEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                RequestLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id),
                    span_id=str(event.span_id),
                    user_id=str(event.user_id) if event.user_id else None,
                    session_id=str(event.session_id) if event.session_id else None,
                    method=event.method,
                    path=event.path,
                    raw_path=event.raw_path,
                    status_code=event.status_code,
                    latency_ms=event.latency_ms,
                    request_bytes=event.request_bytes,
                    response_bytes=event.response_bytes,
                    ip_address=event.ip_address,
                    user_agent=event.user_agent,
                    referer=event.referer,
                    environment_snapshot=event.environment_snapshot,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        await session.commit()
    logger.debug("Persisted %d request_log rows", len(events))
