"""Tests for Langfuse service wrapper."""

import uuid
from unittest.mock import MagicMock, patch

from backend.observability.langfuse import LangfuseService


class TestLangfuseService:
    def test_disabled_when_no_secret(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        assert svc.enabled is False

    def test_enabled_when_secret_set(self):
        with patch("langfuse.Langfuse") as mock_cls:
            mock_cls.return_value = MagicMock()
            svc = LangfuseService(
                secret_key="sk-test", public_key="pk-test", base_url="http://localhost:3001"
            )
            assert svc.enabled is True
            mock_cls.assert_called_once()

    def test_create_trace_returns_none_when_disabled(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        result = svc.create_trace(
            trace_id=uuid.uuid4(), session_id=uuid.uuid4(), user_id=uuid.uuid4()
        )
        assert result is None

    def test_create_trace_returns_trace_when_enabled(self):
        with patch("langfuse.Langfuse") as mock_cls:
            mock_client = MagicMock()
            mock_trace = MagicMock()
            mock_client.trace.return_value = mock_trace
            mock_cls.return_value = mock_client

            svc = LangfuseService(
                secret_key="sk-test", public_key="pk-test", base_url="http://localhost:3001"
            )
            result = svc.create_trace(
                trace_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                metadata={"agent_type": "react_v2"},
            )
            assert result is mock_trace
            mock_client.trace.assert_called_once()

    def test_flush_noop_when_disabled(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        svc.flush()  # should not raise

    def test_record_generation_noop_when_no_trace(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        svc.record_generation(
            trace=None,
            name="llm.groq.llama",
            model="llama-3.3-70b",
            input_messages=[],
            output="test",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.001,
        )

    def test_create_span_returns_none_when_disabled(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        result = svc.create_span(trace=None, name="tool.fetch_prices")
        assert result is None

    def test_create_span_returns_span_when_enabled(self):
        with patch("langfuse.Langfuse") as mock_cls:
            mock_client = MagicMock()
            mock_trace = MagicMock()
            mock_span = MagicMock()
            mock_trace.span.return_value = mock_span
            mock_cls.return_value = mock_client

            svc = LangfuseService(
                secret_key="sk-test", public_key="pk-test", base_url="http://localhost:3001"
            )
            result = svc.create_span(trace=mock_trace, name="tool.fetch_prices")
            assert result is mock_span

    def test_end_span_noop_when_none(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        svc.end_span(span=None)  # should not raise

    def test_shutdown_noop_when_disabled(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        svc.shutdown()  # should not raise

    def test_shutdown_flushes_and_closes_when_enabled(self):
        with patch("langfuse.Langfuse") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client

            svc = LangfuseService(
                secret_key="sk-test", public_key="pk-test", base_url="http://localhost:3001"
            )
            svc.shutdown()
            mock_client.flush.assert_called_once()
            mock_client.shutdown.assert_called_once()
