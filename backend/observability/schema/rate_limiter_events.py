"""Pydantic event model for RATE_LIMITER_EVENT events.

Emitted on rate-limiter permissive fallback, timeout, or (optionally) normal acquisition.
Currently only fallback + timeout paths emit — normal acquisition is too high-volume.

Spec reference: §5.4 — Rate-limiter observability payload.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.observability.schema.v1 import EventType, ObsEventBase


class RateLimiterEventPayload(ObsEventBase):
    """Event emitted on rate-limiter fallback, timeout, or acquisition.

    Attributes:
        event_type: Always RATE_LIMITER_EVENT — discriminator for the event router.
        limiter_name: Unique name of the TokenBucketLimiter instance (e.g. ``yfinance``).
        action: What happened — ``fallback_permissive`` when Redis errors cause allow-all,
            ``timeout`` when the caller waited too long, ``acquired`` on normal success.
        wait_time_ms: How long the caller waited before the event was emitted, in ms.
            None for fallback paths that return immediately without waiting.
        tokens_remaining: Tokens left after acquisition. None when not applicable (fallback /
            timeout).
        reason_if_fallback: Populated only when ``action == "fallback_permissive"`` — describes
            the Redis failure category.
    """

    event_type: Literal[EventType.RATE_LIMITER_EVENT] = EventType.RATE_LIMITER_EVENT

    limiter_name: str
    action: Literal["acquired", "timeout", "fallback_permissive", "rejected"]
    wait_time_ms: int | None = Field(default=None)
    tokens_remaining: int | None = Field(default=None)
    reason_if_fallback: (
        Literal["redis_down", "script_load_failed", "redis_error", "unknown"] | None
    ) = Field(default=None)
