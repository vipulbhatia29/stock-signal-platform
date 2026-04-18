"""Routes events by event_type to the right repository.

PR2a ships a no-op DEBUG logger — validates SDK end-to-end. PR4 adds external_api_call_log +
rate_limiter_event writers; PR5 adds writers for refactored legacy emitters.
"""

from __future__ import annotations

import logging

from backend.observability.schema.v1 import EventType, ObsEventBase

logger = logging.getLogger(__name__)


async def write_batch(events: list[ObsEventBase]) -> None:
    """Write a batch of events to their respective stores.

    Routes each event by event_type to its dedicated writer. Writers are imported
    lazily inside each branch to avoid circular imports and keep startup fast.
    Unrecognised event types are logged at DEBUG level — PR5 will add the
    remaining writers (LLM_CALL, TOOL_EXECUTION, etc.).

    Args:
        events: Batch of events to persist. Typically drained from the in-memory
            buffer by the flush loop in ObservabilityClient.
    """
    for event in events:
        if event.event_type == EventType.EXTERNAL_API_CALL:
            from backend.observability.service.external_api_writer import (
                persist_external_api_call,
            )

            await persist_external_api_call(event)
        elif event.event_type == EventType.RATE_LIMITER_EVENT:
            from backend.observability.service.rate_limiter_writer import (
                persist_rate_limiter_event,
            )

            await persist_rate_limiter_event(event)
        else:
            # PR5 will add writers for LLM_CALL, TOOL_EXECUTION, etc.
            logger.debug("obs.event.unhandled", extra={"event_type": event.event_type.value})
