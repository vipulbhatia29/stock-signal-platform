"""Contract tests for strangler-fig dual-write — record_request + record_cascade."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.observability.schema.legacy_events import LLMCallEvent


@pytest.fixture
def mock_obs_client() -> MagicMock:
    """Mock ObservabilityClient with async emit."""
    client = MagicMock()
    client.emit = AsyncMock()
    return client


@pytest.fixture
def collector() -> "ObservabilityCollector":  # noqa: F821
    """Fresh ObservabilityCollector with mocked _safe_db_write."""
    from backend.observability.collector import ObservabilityCollector

    c = ObservabilityCollector()
    # Mock _safe_db_write directly so create_task can resolve without a real DB
    c._safe_db_write = AsyncMock()
    # Set a truthy _db_writer so the legacy guard passes when flag=True
    c._db_writer = AsyncMock()
    return c


class TestRecordRequestStranglerFig:
    @pytest.mark.asyncio
    async def test_dual_write_when_flag_true(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both legacy DB write AND SDK emit happen when flag is True."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", True
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_request(
            model="gpt-4o",
            provider="openai",
            tier="primary",
            latency_ms=123,
            prompt_tokens=50,
            completion_tokens=10,
        )
        # Let the fire-and-forget task run
        await asyncio.sleep(0)

        # Legacy path ran (_safe_db_write was called)
        collector._safe_db_write.assert_awaited_once()
        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, LLMCallEvent)
        assert event.model == "gpt-4o"
        assert event.wrote_via_legacy is True

    @pytest.mark.asyncio
    async def test_sdk_only_when_flag_false(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only SDK emit happens when flag is False."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_request(
            model="gpt-4o",
            provider="openai",
            tier="primary",
            latency_ms=100,
            prompt_tokens=5,
            completion_tokens=5,
        )
        await asyncio.sleep(0)

        # Legacy path skipped — _safe_db_write never called
        collector._safe_db_write.assert_not_awaited()
        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert event.wrote_via_legacy is False

    @pytest.mark.asyncio
    async def test_no_emit_when_no_obs_client(
        self, collector: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When obs client not available, only legacy runs (no crash)."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", True
        )
        monkeypatch.setattr("backend.observability.collector._maybe_get_obs_client", lambda: None)

        # Must not raise
        await collector.record_request(
            model="gpt-4o",
            provider="openai",
            tier="primary",
            latency_ms=100,
            prompt_tokens=5,
            completion_tokens=5,
        )
        await asyncio.sleep(0)

        # Legacy still ran
        collector._safe_db_write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_request_event_fields(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SDK event carries all request fields correctly."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_request(
            model="claude-3-haiku",
            provider="anthropic",
            tier="fast",
            latency_ms=42,
            prompt_tokens=100,
            completion_tokens=20,
            cost_usd=0.001,
            loop_step=3,
            status="completed",
        )

        event = mock_obs_client.emit.call_args[0][0]
        assert event.provider == "anthropic"
        assert event.tier == "fast"
        assert event.latency_ms == 42
        assert event.prompt_tokens == 100
        assert event.completion_tokens == 20
        assert event.cost_usd == 0.001
        assert event.loop_step == 3
        assert event.status == "completed"


class TestRecordCascadeStranglerFig:
    @pytest.mark.asyncio
    async def test_dual_write_when_flag_true(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both legacy DB write AND SDK emit happen when flag is True."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", True
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_cascade(
            from_model="gpt-4o",
            reason="rate_limit",
            provider="openai",
            tier="primary",
        )
        await asyncio.sleep(0)

        # Legacy ran
        collector._safe_db_write.assert_awaited_once()
        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, LLMCallEvent)
        assert event.status == "error"
        assert event.error == "rate_limit"
        assert event.wrote_via_legacy is True

    @pytest.mark.asyncio
    async def test_sdk_only_when_flag_false(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only SDK emit happens when flag is False."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_cascade(
            from_model="gpt-4o",
            reason="rate_limit",
            provider="openai",
            tier="primary",
        )
        await asyncio.sleep(0)

        # Legacy skipped
        collector._safe_db_write.assert_not_awaited()
        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert event.wrote_via_legacy is False

    @pytest.mark.asyncio
    async def test_cascade_appends_to_log_regardless_of_flag(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """In-memory cascade log is always appended, regardless of write flag."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr("backend.observability.collector._maybe_get_obs_client", lambda: None)

        await collector.record_cascade(
            from_model="gpt-4o",
            reason="timeout",
            provider="openai",
            tier="primary",
        )

        assert len(collector._cascade_log) == 1
        entry = collector._cascade_log[0]
        assert entry["model"] == "gpt-4o"
        assert entry["reason"] == "timeout"

    @pytest.mark.asyncio
    async def test_cascade_event_fields(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SDK cascade event has correct None fields for tokens/latency."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_cascade(
            from_model="gpt-4o-mini",
            reason="context_length",
            provider="openai",
            tier="balanced",
        )

        event = mock_obs_client.emit.call_args[0][0]
        assert event.model == "gpt-4o-mini"
        assert event.latency_ms is None
        assert event.prompt_tokens is None
        assert event.completion_tokens is None
        assert event.error == "context_length"
        assert event.status == "error"
