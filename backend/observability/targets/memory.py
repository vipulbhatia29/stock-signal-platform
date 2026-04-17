"""In-process target for tests."""

from __future__ import annotations

from backend.observability.schema.v1 import ObsEventBase
from backend.observability.targets.base import BatchResult, TargetHealth


class MemoryTarget:
    """Stores events in-memory — use in unit tests to assert emission correctness."""

    def __init__(self, fail_next: int = 0) -> None:
        self.events: list[ObsEventBase] = []
        self._fail_next = fail_next

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult:
        """Accept or reject a batch based on fail_next counter."""
        if self._fail_next > 0:
            self._fail_next -= 1
            return BatchResult(sent=0, failed=len(events), error="memory_target_simulated_failure")
        self.events.extend(events)
        return BatchResult(sent=len(events), failed=0)

    async def health(self) -> TargetHealth:
        """Always healthy unless fail_next is active."""
        return TargetHealth(healthy=True)
