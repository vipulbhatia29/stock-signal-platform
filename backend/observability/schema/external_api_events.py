"""Pydantic event model for EXTERNAL_API_CALL events.

Every outbound HTTP call made via ObservedHttpClient emits one of these events.
The event is written to the ``observability.external_api_call_log`` hypertable by
the event_writer (PR8).

Spec reference: §5.3 — External API observability payload.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.observability.schema.v1 import EventType, ObsEventBase


class ExternalApiCallEvent(ObsEventBase):
    """Event emitted for every outbound HTTP call to an external API.

    Carries the full HTTP envelope (provider, endpoint, method, status) plus
    latency, byte counts, retry count, and parsed rate-limit header fields.

    Attributes:
        event_type: Always EXTERNAL_API_CALL — discriminator for the event router.
        provider: Canonical provider name (ExternalProvider.value).
        endpoint: URL path without query string (e.g. ``/v1/chat/completions``).
        method: HTTP verb in uppercase (GET, POST, …).
        status_code: HTTP response status code, or None when a transport error occurred.
        error_reason: ErrorReason.value when the call failed, else None.
        latency_ms: Wall-clock call duration in milliseconds (monotonic).
        request_bytes: Content-Length of the request body, or None if not known.
        response_bytes: Content-Length of the response body, or None if not known.
        retry_count: Number of retries before this attempt (0 = first attempt).
        rate_limit_remaining: Parsed ``X-RateLimit-Remaining`` header value.
        rate_limit_reset_ts: Parsed ``X-RateLimit-Reset`` as a tz-aware UTC datetime.
        rate_limit_headers: Raw rate-limit headers keyed by normalised header name.
    """

    event_type: Literal[EventType.EXTERNAL_API_CALL] = EventType.EXTERNAL_API_CALL

    # --- Provider / call identity ---
    provider: str
    endpoint: str
    method: str

    # --- Response classification ---
    status_code: int | None = Field(default=None)
    error_reason: str | None = Field(default=None)

    # --- Perf / size ---
    latency_ms: int
    request_bytes: int | None = Field(default=None)
    response_bytes: int | None = Field(default=None)

    # --- Retry ---
    retry_count: int = Field(default=0)

    # --- Rate-limit metadata ---
    rate_limit_remaining: int | None = Field(default=None)
    rate_limit_reset_ts: datetime | None = Field(default=None)
    rate_limit_headers: dict[str, str] | None = Field(default=None)
