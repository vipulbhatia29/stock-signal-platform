"""Event contract v1 — baseline fields present on every event.

Per spec §4.1-4.4:
- Every event carries trace_id + span_id + parent_span_id (causality tree)
- ts MUST be tz-aware UTC (never datetime.utcnow)
- env enum-constrained (dev|staging|prod)
- EventType forward-declared with every type used in 1a PR1-PR5

Additive evolution only — bumping to v2 = new `observability.schema_versions` row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class EventType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_EXECUTION = "tool_execution"
    LOGIN_ATTEMPT = "login_attempt"
    DQ_FINDING = "dq_finding"
    PIPELINE_LIFECYCLE = "pipeline_lifecycle"
    EXTERNAL_API_CALL = "external_api_call"
    RATE_LIMITER_EVENT = "rate_limiter_event"


class AttributionLayer(str, Enum):
    HTTP = "http"
    AUTH = "auth"
    DB = "db"
    CACHE = "cache"
    EXTERNAL_API = "external_api"
    LLM = "llm"
    AGENT = "agent"
    CELERY = "celery"
    FRONTEND = "frontend"
    ANOMALY_ENGINE = "anomaly_engine"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ObsEventBase(BaseModel):
    """Envelope on every event. Subclasses add payload-specific fields."""

    model_config = ConfigDict(extra="allow", frozen=False, str_strip_whitespace=True)

    event_type: EventType
    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None
    ts: datetime
    env: Literal["dev", "staging", "prod"]
    git_sha: str | None
    user_id: UUID | None
    session_id: UUID | None
    query_id: UUID | None

    @field_validator("ts")
    @classmethod
    def _ts_tz_aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must be tz-aware UTC (spec §4.3)")
        return v.astimezone(timezone.utc)
