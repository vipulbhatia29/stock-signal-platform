"""ObservabilityTarget Protocol — the extraction seam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from backend.observability.schema.v1 import ObsEventBase


@dataclass(frozen=True)
class BatchResult:
    """Result of sending a batch of events to a target."""

    sent: int
    failed: int
    error: str | None = None


@dataclass(frozen=True)
class TargetHealth:
    """Health status of an observability target."""

    healthy: bool
    last_success_ts: str | None = None
    last_error: str | None = None


@runtime_checkable
class ObservabilityTarget(Protocol):
    """Protocol for event delivery targets.

    Implementations: DirectTarget (monolith DB), MemoryTarget (tests),
    InternalHTTPTarget (PR2b), ExternalHTTPTarget (extraction).
    """

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult: ...

    async def health(self) -> TargetHealth: ...
