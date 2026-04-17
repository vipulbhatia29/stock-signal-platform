"""DirectTarget — writes events directly through event_writer.write_batch.

Monolith default. At extraction time, swap with ExternalHTTPTarget in bootstrap — no
application code changes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable

from backend.observability.schema.v1 import ObsEventBase
from backend.observability.service.event_writer import write_batch as default_writer
from backend.observability.targets.base import BatchResult, TargetHealth

WriterFn = Callable[[list[ObsEventBase]], Awaitable[None]]


class DirectTarget:
    """Target that writes directly to the database via event_writer."""

    def __init__(self, event_writer: WriterFn | None = None) -> None:
        self._writer = event_writer or default_writer
        self._last_success_ts: str | None = None
        self._last_error: str | None = None

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult:
        """Delegate to the event writer; classify failures."""
        try:
            await self._writer(events)
        except Exception as exc:  # noqa: BLE001 — writer exceptions classified below
            self._last_error = type(exc).__name__
            return BatchResult(sent=0, failed=len(events), error=self._last_error)
        self._last_success_ts = datetime.now(timezone.utc).isoformat()
        self._last_error = None
        return BatchResult(sent=len(events), failed=0)

    async def health(self) -> TargetHealth:
        """Report health based on last send result."""
        return TargetHealth(
            healthy=self._last_error is None,
            last_success_ts=self._last_success_ts,
            last_error=self._last_error,
        )
