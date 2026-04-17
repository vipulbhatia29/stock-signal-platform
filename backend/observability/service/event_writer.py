"""Routes events by event_type to the right repository.

PR2a ships a no-op DEBUG logger — validates SDK end-to-end. PR4 adds external_api_call_log +
rate_limiter_event writers; PR5 adds writers for refactored legacy emitters.
"""

from __future__ import annotations

import logging

from backend.observability.schema.v1 import ObsEventBase

logger = logging.getLogger(__name__)


async def write_batch(events: list[ObsEventBase]) -> None:
    """Write a batch of events to their respective stores.

    Stub implementation — logs at DEBUG level only. Real persistence lands in PR4/PR5.
    """
    for event in events:
        logger.debug("obs.event.write", extra={"event_type": event.event_type.value})
