"""Tests for Agent layer observability — schemas + emission helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from backend.observability.schema.agent_events import (
    AgentIntentEvent,
    AgentReasoningEvent,
    ProviderHealthSnapshotEvent,
    ReasoningType,
    TerminationReason,
)
from backend.observability.schema.v1 import EventType


def _base_fields() -> dict:
    """Return a valid base event payload."""
    return {
        "trace_id": uuid.uuid4(),
        "span_id": uuid.uuid4(),
        "parent_span_id": None,
        "ts": datetime.now(timezone.utc),
        "env": "dev",
        "git_sha": "abc123",
        "user_id": None,
        "session_id": None,
        "query_id": None,
    }


class TestAgentIntentEvent:
    """Tests for AgentIntentEvent schema."""

    def test_valid_event(self):
        """AgentIntentEvent should parse with required fields."""
        e = AgentIntentEvent(
            **_base_fields(),
            intent="stock",
            confidence=0.95,
            out_of_scope=False,
            query_text_hash="abc123def456",
        )
        assert e.event_type == EventType.AGENT_INTENT
        assert e.intent == "stock"
        assert e.confidence == 0.95
        assert e.decline_reason is None

    def test_out_of_scope_with_reason(self):
        """AgentIntentEvent should accept decline_reason for OOS queries."""
        e = AgentIntentEvent(
            **_base_fields(),
            intent="out_of_scope",
            confidence=1.0,
            out_of_scope=True,
            decline_reason="injection detected",
            query_text_hash="xyz789",
        )
        assert e.out_of_scope is True
        assert e.decline_reason == "injection detected"

    def test_missing_required(self):
        """AgentIntentEvent should reject missing query_text_hash."""
        with pytest.raises(ValidationError):
            AgentIntentEvent(
                **_base_fields(),
                intent="stock",
                confidence=0.9,
                out_of_scope=False,
            )


class TestAgentReasoningEvent:
    """Tests for AgentReasoningEvent schema."""

    def test_valid_iteration_event(self):
        """AgentReasoningEvent should parse a mid-loop iteration."""
        e = AgentReasoningEvent(
            **_base_fields(),
            loop_step=0,
            reasoning_type=ReasoningType.PLAN,
            content_summary="Analyzing AAPL stock data...",
            tool_calls_proposed={"tools": ["get_signals", "get_price"]},
        )
        assert e.event_type == EventType.AGENT_REASONING
        assert e.loop_step == 0
        assert e.termination_reason is None

    def test_termination_event(self):
        """AgentReasoningEvent should accept termination_reason on final step."""
        e = AgentReasoningEvent(
            **_base_fields(),
            loop_step=5,
            reasoning_type=ReasoningType.SYNTHESIZE,
            content_summary="Final summary of analysis...",
            termination_reason=TerminationReason.ZERO_TOOL_CALLS,
        )
        assert e.termination_reason == TerminationReason.ZERO_TOOL_CALLS

    def test_all_reasoning_types(self):
        """All ReasoningType values should be valid."""
        for rt in ReasoningType:
            e = AgentReasoningEvent(
                **_base_fields(),
                loop_step=0,
                reasoning_type=rt,
                content_summary="test",
            )
            assert e.reasoning_type == rt

    def test_all_termination_reasons(self):
        """All TerminationReason values should be valid."""
        for tr in TerminationReason:
            e = AgentReasoningEvent(
                **_base_fields(),
                loop_step=0,
                reasoning_type=ReasoningType.SYNTHESIZE,
                content_summary="test",
                termination_reason=tr,
            )
            assert e.termination_reason == tr

    def test_content_summary_not_truncated_by_schema(self):
        """Schema should accept long content (truncation is caller's job)."""
        long_content = "x" * 600
        e = AgentReasoningEvent(
            **_base_fields(),
            loop_step=0,
            reasoning_type=ReasoningType.PLAN,
            content_summary=long_content,
        )
        assert len(e.content_summary) == 600


class TestProviderHealthSnapshotEvent:
    """Tests for ProviderHealthSnapshotEvent schema."""

    def test_valid_healthy_provider(self):
        """ProviderHealthSnapshotEvent should parse a healthy provider."""
        e = ProviderHealthSnapshotEvent(
            **_base_fields(),
            provider="openai",
            model="gpt-4o",
            is_exhausted=False,
            consecutive_failures=0,
        )
        assert e.event_type == EventType.PROVIDER_HEALTH_SNAPSHOT
        assert e.provider == "openai"
        assert e.is_exhausted is False

    def test_exhausted_provider(self):
        """ProviderHealthSnapshotEvent should record exhausted state."""
        now = datetime.now(timezone.utc)
        e = ProviderHealthSnapshotEvent(
            **_base_fields(),
            provider="anthropic",
            is_exhausted=True,
            exhausted_until=now,
            consecutive_failures=3,
            last_failure_at=now,
        )
        assert e.is_exhausted is True
        assert e.consecutive_failures == 3


class TestEmitHelpers:
    """Tests for emission helper functions."""

    @patch("backend.observability.bootstrap._maybe_get_obs_client", return_value=None)
    def test_emit_intent_noop_without_client(self, mock_client):
        """emit_intent_log should no-op when client is unavailable."""
        from backend.observability.instrumentation.agent import emit_intent_log

        # Should not raise
        emit_intent_log(
            intent="stock",
            confidence=0.9,
            out_of_scope=False,
            query_text_hash="abc",
        )

    @patch("backend.observability.bootstrap._maybe_get_obs_client")
    def test_emit_intent_calls_emit_sync(self, mock_get_client):
        """emit_intent_log should call emit_sync with correct event."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        from backend.observability.instrumentation.agent import emit_intent_log

        emit_intent_log(
            intent="portfolio",
            confidence=0.85,
            out_of_scope=False,
            query_text_hash="hash123",
        )

        mock_client.emit_sync.assert_called_once()
        event = mock_client.emit_sync.call_args[0][0]
        assert event.intent == "portfolio"
        assert event.confidence == 0.85

    @patch("backend.observability.bootstrap._maybe_get_obs_client", return_value=None)
    def test_emit_reasoning_noop_without_client(self, mock_client):
        """emit_reasoning_log should no-op when client is unavailable."""
        from backend.observability.instrumentation.agent import emit_reasoning_log

        emit_reasoning_log(
            loop_step=0,
            reasoning_type="plan",
            content_summary="test",
        )

    def test_hash_query_text(self):
        """hash_query_text should produce consistent SHA256 hashes."""
        from backend.observability.instrumentation.agent import hash_query_text

        h1 = hash_query_text("What is AAPL price?")
        h2 = hash_query_text("What is AAPL price?")
        h3 = hash_query_text("Different query")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 64  # SHA256 hex digest length
