from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.observability.schema.v1 import (
    AttributionLayer,
    EventType,
    ObsEventBase,
    Severity,
)


def test_event_type_covers_1a_scope():
    assert {
        "LLM_CALL",
        "TOOL_EXECUTION",
        "LOGIN_ATTEMPT",
        "DQ_FINDING",
        "PIPELINE_LIFECYCLE",
        "EXTERNAL_API_CALL",
        "RATE_LIMITER_EVENT",
    }.issubset({e.name for e in EventType})


def test_attribution_layer_enum():
    assert {layer.value for layer in AttributionLayer} == {
        "http",
        "auth",
        "db",
        "cache",
        "external_api",
        "llm",
        "agent",
        "celery",
        "frontend",
        "anomaly_engine",
    }


def test_severity_enum():
    assert {s.value for s in Severity} == {"info", "warning", "error", "critical"}


def _valid_payload(**overrides):
    base = dict(
        event_type=EventType.LLM_CALL,
        trace_id=UUID("01234567-89ab-7def-8123-456789abcdef"),
        span_id=UUID("01234567-89ab-7def-8123-456789abcde0"),
        parent_span_id=None,
        ts=datetime(2026, 4, 16, 12, tzinfo=timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
    )
    base.update(overrides)
    return base


def test_round_trip():
    event = ObsEventBase(**_valid_payload())
    assert ObsEventBase.model_validate_json(event.model_dump_json()) == event


def test_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        ObsEventBase(**_valid_payload(ts=datetime(2026, 4, 16, 12)))  # naive


def test_rejects_invalid_env():
    with pytest.raises(ValidationError):
        ObsEventBase(**_valid_payload(env="production"))  # must be dev/staging/prod
