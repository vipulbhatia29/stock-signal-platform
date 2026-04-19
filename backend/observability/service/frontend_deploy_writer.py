"""Batch writer for frontend error events.

Deploy events are written directly by the deploy endpoint (not via SDK),
so only the frontend error writer is needed here.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.instrumentation.db import _in_obs_write
from backend.observability.models.frontend_error_log import FrontendErrorLog
from backend.observability.schema.frontend_deploy_events import FrontendErrorEvent

logger = logging.getLogger(__name__)


async def persist_frontend_errors(events: list[FrontendErrorEvent]) -> None:
    """Persist frontend error rows to observability.frontend_error_log.

    Args:
        events: List of FrontendErrorEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    token = _in_obs_write.set(True)
    try:
        async with async_session_factory() as session:
            for event in events:
                session.add(
                    FrontendErrorLog(
                        ts=event.ts,
                        trace_id=str(event.trace_id) if event.trace_id else None,
                        user_id=str(event.user_id) if event.user_id else None,
                        error_type=event.error_type.value,
                        error_message=event.error_message,
                        error_stack=event.error_stack,
                        page_route=event.page_route,
                        component_name=event.component_name,
                        user_agent=event.user_agent,
                        url=event.url,
                        frontend_metadata=event.frontend_metadata,
                        env=event.env,
                        git_sha=event.git_sha,
                    )
                )
            await session.commit()
    finally:
        _in_obs_write.reset(token)
    logger.debug("Persisted %d frontend_error_log rows", len(events))
