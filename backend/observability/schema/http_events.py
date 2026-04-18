"""Pydantic event schemas for HTTP layer observability."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from backend.observability.schema.v1 import EventType, ObsEventBase


class ErrorType(str, Enum):
    """Classification of HTTP errors."""

    VALIDATION = "validation"
    AUTH = "auth"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    RATE_LIMIT = "rate_limit"
    DOMAIN = "domain"
    INTERNAL_SERVER = "internal_server"


class RequestLogEvent(ObsEventBase):
    """Event emitted for every HTTP request."""

    event_type: EventType = Field(default=EventType.REQUEST_LOG, frozen=True)

    method: str
    path: str  # normalized (UUIDs → {id}, tickers → {param})
    raw_path: str  # original for debugging
    status_code: int
    latency_ms: int = Field(ge=0)
    request_bytes: int | None = None
    response_bytes: int | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    referer: str | None = None
    environment_snapshot: dict[str, Any] | None = None


class ApiErrorLogEvent(ObsEventBase):
    """Event emitted for 4xx and 5xx HTTP errors."""

    event_type: EventType = Field(default=EventType.API_ERROR_LOG, frozen=True)

    status_code: int
    error_type: ErrorType
    error_reason: str | None = None
    error_message: str | None = None
    stack_signature: str | None = None
    stack_hash: str | None = None
    stack_trace: str | None = None  # only for 5xx; truncated to 5KB
    exception_class: str | None = None
    request_log_id: str | None = None  # UUID as string, filled by writer if available
