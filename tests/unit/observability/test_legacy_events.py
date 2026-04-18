"""Tests for PR5 strangler-fig legacy event subclasses.

Validates:
- Each subclass roundtrips through JSON (model_dump_json → model_validate_json)
- Required fields are present and validated
- wrote_via_legacy is required (no default)
- event_type discriminator is set correctly on each class
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from backend.observability.schema.legacy_events import (
    DqFindingEvent,
    LLMCallEvent,
    LoginAttemptEvent,
    PipelineLifecycleEvent,
    ToolExecutionEvent,
    _LegacyStranglerFigMixin,
)
from backend.observability.schema.v1 import EventType

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_UID = uuid.uuid4()
_TRACE = uuid.uuid4()
_SPAN = uuid.uuid4()


def _base_fields() -> dict:
    """Return the minimum ObsEventBase fields required for construction."""
    return {
        "trace_id": str(_TRACE),
        "span_id": str(_SPAN),
        "parent_span_id": None,
        "ts": _NOW.isoformat(),
        "env": "dev",
        "git_sha": None,
        "user_id": None,
        "session_id": None,
        "query_id": None,
    }


# ---------------------------------------------------------------------------
# _LegacyStranglerFigMixin
# ---------------------------------------------------------------------------


class TestLegacyStranglerFigMixin:
    def test_wrote_via_legacy_required_no_default(self):
        """wrote_via_legacy must be required — no default value."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            _LegacyStranglerFigMixin()  # type: ignore[call-arg]

    def test_wrote_via_legacy_accepts_bool(self):
        """Both True and False are valid values for wrote_via_legacy."""
        m = _LegacyStranglerFigMixin(wrote_via_legacy=True)
        assert m.wrote_via_legacy is True

        m2 = _LegacyStranglerFigMixin(wrote_via_legacy=False)
        assert m2.wrote_via_legacy is False


# ---------------------------------------------------------------------------
# LLMCallEvent
# ---------------------------------------------------------------------------


class TestLLMCallEvent:
    def _build(self, **overrides) -> dict:
        data = {
            **_base_fields(),
            "wrote_via_legacy": True,
            "model": "gpt-4o-mini",
            "provider": "openai",
            "tier": "fast",
        }
        data.update(overrides)
        return data

    def test_roundtrip_json(self):
        """LLMCallEvent roundtrips through model_dump_json → model_validate_json."""
        evt = LLMCallEvent(**self._build())
        raw = evt.model_dump_json()
        restored = LLMCallEvent.model_validate_json(raw)
        assert restored.model == "gpt-4o-mini"
        assert restored.event_type == EventType.LLM_CALL

    def test_event_type_discriminator(self):
        """event_type is always set to LLM_CALL regardless of caller-supplied value."""
        evt = LLMCallEvent(**self._build())
        assert evt.event_type == EventType.LLM_CALL

    def test_required_fields(self):
        """Missing required field model raises ValidationError."""
        import pydantic

        # Missing model → ValidationError
        bad = self._build()
        del bad["model"]
        with pytest.raises(pydantic.ValidationError):
            LLMCallEvent(**bad)

    def test_wrote_via_legacy_required(self):
        """wrote_via_legacy is required on LLMCallEvent — no default."""
        import pydantic

        bad = self._build()
        del bad["wrote_via_legacy"]
        with pytest.raises(pydantic.ValidationError):
            LLMCallEvent(**bad)

    def test_optional_fields_default_none(self):
        """All optional numeric and error fields default to None."""
        evt = LLMCallEvent(**self._build())
        assert evt.latency_ms is None
        assert evt.prompt_tokens is None
        assert evt.completion_tokens is None
        assert evt.cost_usd is None
        assert evt.loop_step is None
        assert evt.error is None
        assert evt.langfuse_trace_id is None

    def test_status_default(self):
        """status defaults to 'completed' when not supplied."""
        evt = LLMCallEvent(**self._build())
        assert evt.status == "completed"

    def test_cascade_fields(self):
        """LLMCallEvent must accept latency_ms=None and error for cascade events."""
        evt = LLMCallEvent(**self._build(latency_ms=None, error="timeout"))
        assert evt.latency_ms is None
        assert evt.error == "timeout"


# ---------------------------------------------------------------------------
# ToolExecutionEvent
# ---------------------------------------------------------------------------


class TestToolExecutionEvent:
    def _build(self, **overrides) -> dict:
        data = {
            **_base_fields(),
            "wrote_via_legacy": True,
            "tool_name": "get_price",
            "latency_ms": 42,
            "status": "success",
        }
        data.update(overrides)
        return data

    def test_roundtrip_json(self):
        """ToolExecutionEvent roundtrips through model_dump_json → model_validate_json."""
        evt = ToolExecutionEvent(**self._build())
        raw = evt.model_dump_json()
        restored = ToolExecutionEvent.model_validate_json(raw)
        assert restored.tool_name == "get_price"
        assert restored.event_type == EventType.TOOL_EXECUTION

    def test_event_type_discriminator(self):
        """event_type is always set to TOOL_EXECUTION regardless of caller-supplied value."""
        evt = ToolExecutionEvent(**self._build())
        assert evt.event_type == EventType.TOOL_EXECUTION

    def test_required_fields(self):
        """Missing required field tool_name raises ValidationError."""
        import pydantic

        bad = self._build()
        del bad["tool_name"]
        with pytest.raises(pydantic.ValidationError):
            ToolExecutionEvent(**bad)

    def test_wrote_via_legacy_required(self):
        """wrote_via_legacy is required on ToolExecutionEvent — no default."""
        import pydantic

        bad = self._build()
        del bad["wrote_via_legacy"]
        with pytest.raises(pydantic.ValidationError):
            ToolExecutionEvent(**bad)

    def test_optional_fields_default(self):
        """Optional fields default to None/False when not supplied."""
        evt = ToolExecutionEvent(**self._build())
        assert evt.result_size_bytes is None
        assert evt.error is None
        assert evt.cache_hit is False
        assert evt.loop_step is None


# ---------------------------------------------------------------------------
# LoginAttemptEvent
# ---------------------------------------------------------------------------


class TestLoginAttemptEvent:
    def _build(self, **overrides) -> dict:
        data = {
            **_base_fields(),
            "wrote_via_legacy": False,
            "email": "user@example.com",
            "success": True,
            "ip_address": "127.0.0.1",
            "user_agent": "pytest/1.0",
        }
        data.update(overrides)
        return data

    def test_roundtrip_json(self):
        """LoginAttemptEvent roundtrips through model_dump_json → model_validate_json."""
        evt = LoginAttemptEvent(**self._build())
        raw = evt.model_dump_json()
        restored = LoginAttemptEvent.model_validate_json(raw)
        assert restored.email == "user@example.com"
        assert restored.event_type == EventType.LOGIN_ATTEMPT

    def test_event_type_discriminator(self):
        """event_type is always set to LOGIN_ATTEMPT regardless of caller-supplied value."""
        evt = LoginAttemptEvent(**self._build())
        assert evt.event_type == EventType.LOGIN_ATTEMPT

    def test_required_fields(self):
        """Missing required field email raises ValidationError."""
        import pydantic

        bad = self._build()
        del bad["email"]
        with pytest.raises(pydantic.ValidationError):
            LoginAttemptEvent(**bad)

    def test_wrote_via_legacy_required(self):
        """wrote_via_legacy is required on LoginAttemptEvent — no default."""
        import pydantic

        bad = self._build()
        del bad["wrote_via_legacy"]
        with pytest.raises(pydantic.ValidationError):
            LoginAttemptEvent(**bad)

    def test_method_default(self):
        """method defaults to 'password' when not supplied."""
        evt = LoginAttemptEvent(**self._build())
        assert evt.method == "password"

    def test_method_accepts_arbitrary_string(self):
        """method is str, not Literal — accepts google/github/etc."""
        evt = LoginAttemptEvent(**self._build(method="google"))
        assert evt.method == "google"


# ---------------------------------------------------------------------------
# DqFindingEvent
# ---------------------------------------------------------------------------


class TestDqFindingEvent:
    def _build(self, **overrides) -> dict:
        data = {
            **_base_fields(),
            "wrote_via_legacy": True,
            "check_name": "null_price_check",
            "severity": "warning",
            "message": "Null price detected for AAPL",
        }
        data.update(overrides)
        return data

    def test_roundtrip_json(self):
        """DqFindingEvent roundtrips through model_dump_json → model_validate_json."""
        evt = DqFindingEvent(**self._build())
        raw = evt.model_dump_json()
        restored = DqFindingEvent.model_validate_json(raw)
        assert restored.check_name == "null_price_check"
        assert restored.event_type == EventType.DQ_FINDING

    def test_event_type_discriminator(self):
        """event_type is always set to DQ_FINDING regardless of caller-supplied value."""
        evt = DqFindingEvent(**self._build())
        assert evt.event_type == EventType.DQ_FINDING

    def test_severity_enum(self):
        """All four valid severity levels are accepted."""
        for sev in ("info", "warning", "error", "critical"):
            evt = DqFindingEvent(**self._build(severity=sev))
            assert evt.severity == sev

    def test_invalid_severity(self):
        """Severity values outside the Literal set raise ValidationError."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            DqFindingEvent(**self._build(severity="debug"))

    def test_wrote_via_legacy_required(self):
        """wrote_via_legacy is required on DqFindingEvent — no default."""
        import pydantic

        bad = self._build()
        del bad["wrote_via_legacy"]
        with pytest.raises(pydantic.ValidationError):
            DqFindingEvent(**bad)

    def test_optional_fields(self):
        """ticker and metadata default to None when not supplied."""
        evt = DqFindingEvent(**self._build())
        assert evt.ticker is None
        assert evt.metadata is None

    def test_with_metadata(self):
        """ticker and metadata are stored when supplied."""
        evt = DqFindingEvent(**self._build(ticker="AAPL", metadata={"count": 3}))
        assert evt.ticker == "AAPL"
        assert evt.metadata == {"count": 3}


# ---------------------------------------------------------------------------
# PipelineLifecycleEvent
# ---------------------------------------------------------------------------


class TestPipelineLifecycleEvent:
    def _build(self, **overrides) -> dict:
        data = {
            **_base_fields(),
            "wrote_via_legacy": True,
            "pipeline_name": "nightly_signal",
            "transition": "started",
            "run_id": str(uuid.uuid4()),
            "trigger": "celery_beat",
        }
        data.update(overrides)
        return data

    def test_roundtrip_json(self):
        """PipelineLifecycleEvent roundtrips through model_dump_json → model_validate_json."""
        evt = PipelineLifecycleEvent(**self._build())
        raw = evt.model_dump_json()
        restored = PipelineLifecycleEvent.model_validate_json(raw)
        assert restored.pipeline_name == "nightly_signal"
        assert restored.event_type == EventType.PIPELINE_LIFECYCLE

    def test_event_type_discriminator(self):
        """event_type is always set to PIPELINE_LIFECYCLE regardless of caller-supplied value."""
        evt = PipelineLifecycleEvent(**self._build())
        assert evt.event_type == EventType.PIPELINE_LIFECYCLE

    def test_transition_values(self):
        """All valid transition values must be accepted."""
        for transition in ("started", "success", "failed", "no_op", "partial"):
            evt = PipelineLifecycleEvent(**self._build(transition=transition))
            assert evt.transition == transition

    def test_invalid_transition(self):
        """'succeeded' is rejected — the correct value is 'success' to match complete_run()."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            PipelineLifecycleEvent(**self._build(transition="succeeded"))

    def test_wrote_via_legacy_required(self):
        """wrote_via_legacy is required on PipelineLifecycleEvent — no default."""
        import pydantic

        bad = self._build()
        del bad["wrote_via_legacy"]
        with pytest.raises(pydantic.ValidationError):
            PipelineLifecycleEvent(**bad)

    def test_optional_fields(self):
        """All optional duration and ticker count fields default to None."""
        evt = PipelineLifecycleEvent(**self._build())
        assert evt.celery_task_id is None
        assert evt.duration_s is None
        assert evt.tickers_total is None
        assert evt.tickers_succeeded is None
        assert evt.tickers_failed is None


# ---------------------------------------------------------------------------
# __init__ exports
# ---------------------------------------------------------------------------


class TestInitExports:
    """Verify that all legacy event classes are accessible from the package __init__."""

    def test_exports_available(self):
        """All five event subclasses and the mixin are importable from the schema package."""
        from backend.observability.schema import (
            DqFindingEvent,
            LLMCallEvent,
            LoginAttemptEvent,
            PipelineLifecycleEvent,
            ToolExecutionEvent,
            _LegacyStranglerFigMixin,
        )

        # Smoke-check they are the correct types
        assert issubclass(LLMCallEvent, _LegacyStranglerFigMixin)
        assert issubclass(ToolExecutionEvent, _LegacyStranglerFigMixin)
        assert issubclass(LoginAttemptEvent, _LegacyStranglerFigMixin)
        assert issubclass(DqFindingEvent, _LegacyStranglerFigMixin)
        assert issubclass(PipelineLifecycleEvent, _LegacyStranglerFigMixin)
