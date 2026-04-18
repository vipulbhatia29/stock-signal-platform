"""Contract tests for strangler-fig dual-write — record_request + record_cascade."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.observability.schema.legacy_events import (
    DqFindingEvent,
    LLMCallEvent,
    LoginAttemptEvent,
    PipelineLifecycleEvent,
    ToolExecutionEvent,
)


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


class TestRecordToolExecutionStranglerFig:
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

        await collector.record_tool_execution(
            tool_name="get_stock_price",
            latency_ms=50,
            status="success",
        )
        # Let the fire-and-forget task run
        await asyncio.sleep(0)

        # Legacy path ran (_safe_db_write was called)
        collector._safe_db_write.assert_awaited_once()
        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, ToolExecutionEvent)
        assert event.tool_name == "get_stock_price"
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

        await collector.record_tool_execution(
            tool_name="get_stock_price",
            latency_ms=50,
            status="success",
        )
        await asyncio.sleep(0)

        # Legacy path skipped — _safe_db_write never called
        collector._safe_db_write.assert_not_awaited()
        # SDK emit happened with wrote_via_legacy=False
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
        await collector.record_tool_execution(
            tool_name="get_stock_price",
            latency_ms=50,
            status="success",
        )
        await asyncio.sleep(0)

        # Legacy still ran
        collector._safe_db_write.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_tool_execution_event_fields(
        self, collector: MagicMock, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SDK event carries all tool execution fields correctly."""
        monkeypatch.setattr(
            "backend.observability.collector.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.observability.collector._maybe_get_obs_client", lambda: mock_obs_client
        )

        await collector.record_tool_execution(
            tool_name="get_portfolio_holdings",
            latency_ms=120,
            status="error",
            result_size_bytes=None,
            error="timeout",
            cache_hit=False,
            loop_step=2,
        )

        event = mock_obs_client.emit.call_args[0][0]
        assert event.tool_name == "get_portfolio_holdings"
        assert event.latency_ms == 120
        assert event.status == "error"
        assert event.result_size_bytes is None
        assert event.error == "timeout"
        assert event.cache_hit is False
        assert event.loop_step == 2


class TestWriteLoginAttemptStranglerFig:
    @pytest.mark.asyncio
    async def test_dual_write_when_flag_true(
        self, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both legacy DB write AND SDK emit happen when OBS_LEGACY_DIRECT_WRITES=True."""
        monkeypatch.setattr("backend.routers.auth._helpers.settings.OBS_LEGACY_DIRECT_WRITES", True)
        monkeypatch.setattr(
            "backend.routers.auth._helpers._maybe_get_obs_client", lambda: mock_obs_client
        )

        # Patch async_session_factory at its canonical location so the lazy import picks it up
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.database.async_session_factory", lambda: mock_ctx)

        from backend.routers.auth._helpers import _write_login_attempt

        await _write_login_attempt(
            email="test@example.com",
            success=True,
            user_id=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

        # Legacy path ran: session.commit was called
        mock_session.commit.assert_awaited_once()
        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, LoginAttemptEvent)
        assert event.wrote_via_legacy is True

    @pytest.mark.asyncio
    async def test_sdk_only_when_flag_false(
        self, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only SDK emit happens when OBS_LEGACY_DIRECT_WRITES=False; no DB call."""
        monkeypatch.setattr(
            "backend.routers.auth._helpers.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.routers.auth._helpers._maybe_get_obs_client", lambda: mock_obs_client
        )

        from backend.routers.auth._helpers import _write_login_attempt

        await _write_login_attempt(
            email="test@example.com",
            success=True,
            user_id=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

        # SDK emit happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, LoginAttemptEvent)
        assert event.email == "test@example.com"
        assert event.success is True
        assert event.wrote_via_legacy is False

    @pytest.mark.asyncio
    async def test_no_emit_when_no_obs_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When obs client not available, legacy runs if flag=True and no crash occurs."""
        monkeypatch.setattr("backend.routers.auth._helpers.settings.OBS_LEGACY_DIRECT_WRITES", True)
        monkeypatch.setattr("backend.routers.auth._helpers._maybe_get_obs_client", lambda: None)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.database.async_session_factory", lambda: mock_ctx)

        from backend.routers.auth._helpers import _write_login_attempt

        # Must not raise
        await _write_login_attempt(
            email="test@example.com",
            success=False,
            user_id=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
            failure_reason="bad_password",
        )

        # Legacy path ran
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_login_attempt_event_fields(
        self, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """SDK event carries all login-attempt fields correctly."""
        monkeypatch.setattr(
            "backend.routers.auth._helpers.settings.OBS_LEGACY_DIRECT_WRITES", False
        )
        monkeypatch.setattr(
            "backend.routers.auth._helpers._maybe_get_obs_client", lambda: mock_obs_client
        )

        import uuid

        user_id = uuid.uuid4()

        from backend.routers.auth._helpers import _write_login_attempt

        await _write_login_attempt(
            email="user@example.com",
            success=False,
            user_id=user_id,
            ip_address="10.0.0.1",
            user_agent="Mozilla/5.0",
            failure_reason="invalid_password",
            method="password",
        )

        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, LoginAttemptEvent)
        assert event.email == "user@example.com"
        assert event.success is False
        assert event.ip_address == "10.0.0.1"
        assert event.user_agent == "Mozilla/5.0"
        assert event.failure_reason == "invalid_password"
        assert event.method == "password"
        assert event.user_id == user_id
        assert event.wrote_via_legacy is False


class TestDqScanStranglerFig:
    @pytest.mark.asyncio
    async def test_sdk_emit_per_finding(
        self, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each DQ finding produces exactly one DqFindingEvent emitted via SDK."""
        monkeypatch.setattr("backend.tasks.dq_scan.settings.OBS_LEGACY_DIRECT_WRITES", False)
        monkeypatch.setattr("backend.tasks.dq_scan._maybe_get_obs_client", lambda: mock_obs_client)

        # Mock all 10 check functions to return empty lists by default
        for check_name in [
            "_check_negative_prices",
            "_check_rsi_out_of_range",
            "_check_composite_score_out_of_range",
            "_check_null_sectors",
            "_check_forecast_extreme_ratios",
            "_check_orphan_positions",
            "_check_duplicate_signals",
            "_check_stale_universe_coverage",
            "_check_negative_volume",
            "_check_bollinger_violations",
        ]:
            monkeypatch.setattr(f"backend.tasks.dq_scan.{check_name}", AsyncMock(return_value=[]))

        # One check returns a single finding
        monkeypatch.setattr(
            "backend.tasks.dq_scan._check_negative_prices",
            AsyncMock(
                return_value=[
                    {
                        "check": "negative_prices",
                        "severity": "warning",
                        "ticker": "AAPL",
                        "message": "Negative price",
                    }
                ]
            ),
        )

        # Mock DB session (no real DB needed)
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.tasks.dq_scan.async_session_factory", lambda: mock_cm)

        from backend.observability.schema.legacy_events import DqFindingEvent
        from backend.tasks.dq_scan import _dq_scan_async

        result = await _dq_scan_async()

        assert result["findings"] == 1
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, DqFindingEvent)
        assert event.check_name == "negative_prices"
        assert event.ticker == "AAPL"
        assert event.wrote_via_legacy is False

    @pytest.mark.asyncio
    async def test_legacy_persist_when_flag_true(
        self, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flag=True: db.add called for each finding AND SDK emit happens."""
        monkeypatch.setattr("backend.tasks.dq_scan.settings.OBS_LEGACY_DIRECT_WRITES", True)
        monkeypatch.setattr("backend.tasks.dq_scan._maybe_get_obs_client", lambda: mock_obs_client)

        # Mock all checks to return empty, except one with a finding
        for check_name in [
            "_check_negative_prices",
            "_check_rsi_out_of_range",
            "_check_composite_score_out_of_range",
            "_check_null_sectors",
            "_check_forecast_extreme_ratios",
            "_check_orphan_positions",
            "_check_duplicate_signals",
            "_check_stale_universe_coverage",
            "_check_negative_volume",
            "_check_bollinger_violations",
        ]:
            monkeypatch.setattr(f"backend.tasks.dq_scan.{check_name}", AsyncMock(return_value=[]))

        monkeypatch.setattr(
            "backend.tasks.dq_scan._check_rsi_out_of_range",
            AsyncMock(
                return_value=[
                    {
                        "check": "rsi_out_of_range",
                        "severity": "high",
                        "ticker": "TSLA",
                        "message": "RSI 105.0 for TSLA",
                    }
                ]
            ),
        )

        # Mock DB session to capture db.add calls
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.tasks.dq_scan.async_session_factory", lambda: mock_cm)

        from backend.observability.schema.legacy_events import DqFindingEvent
        from backend.tasks.dq_scan import _dq_scan_async

        result = await _dq_scan_async()

        assert result["findings"] == 1
        # Legacy path: db.add was called once for the finding
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        # SDK emit also happened
        mock_obs_client.emit.assert_awaited_once()
        event = mock_obs_client.emit.call_args[0][0]
        assert isinstance(event, DqFindingEvent)
        assert event.check_name == "rsi_out_of_range"
        assert event.ticker == "TSLA"
        assert event.wrote_via_legacy is True

    @pytest.mark.asyncio
    async def test_no_sdk_emit_when_no_obs_client(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When obs client unavailable, legacy persist still runs and no crash occurs."""
        monkeypatch.setattr("backend.tasks.dq_scan.settings.OBS_LEGACY_DIRECT_WRITES", True)
        monkeypatch.setattr("backend.tasks.dq_scan._maybe_get_obs_client", lambda: None)

        for check_name in [
            "_check_negative_prices",
            "_check_rsi_out_of_range",
            "_check_composite_score_out_of_range",
            "_check_null_sectors",
            "_check_forecast_extreme_ratios",
            "_check_orphan_positions",
            "_check_duplicate_signals",
            "_check_stale_universe_coverage",
            "_check_negative_volume",
            "_check_bollinger_violations",
        ]:
            monkeypatch.setattr(f"backend.tasks.dq_scan.{check_name}", AsyncMock(return_value=[]))

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.tasks.dq_scan.async_session_factory", lambda: mock_cm)

        from backend.tasks.dq_scan import _dq_scan_async

        # Must not raise
        result = await _dq_scan_async()
        assert result["status"] == "ok"
        assert result["findings"] == 0

    @pytest.mark.asyncio
    async def test_multiple_findings_emit_multiple_events(
        self, mock_obs_client: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Multiple findings each get their own DqFindingEvent (non-critical, no alerts branch)."""
        monkeypatch.setattr("backend.tasks.dq_scan.settings.OBS_LEGACY_DIRECT_WRITES", False)
        monkeypatch.setattr("backend.tasks.dq_scan._maybe_get_obs_client", lambda: mock_obs_client)

        two_findings = [
            {
                "check": "rsi_out_of_range",
                "severity": "high",
                "ticker": "AAPL",
                "message": "RSI 105 for AAPL",
            },
            {
                "check": "rsi_out_of_range",
                "severity": "high",
                "ticker": "MSFT",
                "message": "RSI 105 for MSFT",
            },
        ]

        for check_name in [
            "_check_negative_prices",
            "_check_rsi_out_of_range",
            "_check_composite_score_out_of_range",
            "_check_null_sectors",
            "_check_forecast_extreme_ratios",
            "_check_orphan_positions",
            "_check_duplicate_signals",
            "_check_stale_universe_coverage",
            "_check_negative_volume",
            "_check_bollinger_violations",
        ]:
            monkeypatch.setattr(f"backend.tasks.dq_scan.{check_name}", AsyncMock(return_value=[]))

        monkeypatch.setattr(
            "backend.tasks.dq_scan._check_rsi_out_of_range",
            AsyncMock(return_value=two_findings),
        )

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.tasks.dq_scan.async_session_factory", lambda: mock_cm)

        from backend.tasks.dq_scan import _dq_scan_async

        result = await _dq_scan_async()

        assert result["findings"] == 2
        assert result["critical"] == 0
        assert mock_obs_client.emit.await_count == 2


# ---------------------------------------------------------------------------
# TestLegacyEmittersWriter — dedup invariant tests for each persist_* function
# ---------------------------------------------------------------------------


def _make_llm_call_event(**overrides) -> LLMCallEvent:
    """Build a minimal valid LLMCallEvent for writer tests.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use LLMCallEvent instance.
    """
    defaults = dict(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        wrote_via_legacy=False,
        model="gpt-4o",
        provider="openai",
        tier="primary",
        latency_ms=100,
        prompt_tokens=50,
        completion_tokens=10,
    )
    defaults.update(overrides)
    return LLMCallEvent(**defaults)


def _make_tool_execution_event(**overrides) -> ToolExecutionEvent:
    """Build a minimal valid ToolExecutionEvent for writer tests.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use ToolExecutionEvent instance.
    """
    defaults = dict(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        wrote_via_legacy=False,
        tool_name="get_stock_price",
        latency_ms=50,
        status="success",
    )
    defaults.update(overrides)
    return ToolExecutionEvent(**defaults)


def _make_login_attempt_event(**overrides) -> LoginAttemptEvent:
    """Build a minimal valid LoginAttemptEvent for writer tests.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use LoginAttemptEvent instance.
    """
    defaults = dict(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        wrote_via_legacy=False,
        email="user@example.com",
        success=True,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )
    defaults.update(overrides)
    return LoginAttemptEvent(**defaults)


def _make_dq_finding_event(**overrides) -> DqFindingEvent:
    """Build a minimal valid DqFindingEvent for writer tests.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use DqFindingEvent instance.
    """
    defaults = dict(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        wrote_via_legacy=False,
        check_name="null_price_check",
        severity="warning",
        ticker="AAPL",
        message="Negative price detected",
    )
    defaults.update(overrides)
    return DqFindingEvent(**defaults)


def _make_pipeline_lifecycle_event(**overrides) -> PipelineLifecycleEvent:
    """Build a minimal valid PipelineLifecycleEvent for writer tests.

    Args:
        **overrides: Field overrides applied on top of sensible defaults.

    Returns:
        A ready-to-use PipelineLifecycleEvent instance.
    """
    defaults = dict(
        trace_id=uuid4(),
        span_id=uuid4(),
        parent_span_id=None,
        ts=datetime.now(timezone.utc),
        env="dev",
        git_sha=None,
        user_id=None,
        session_id=None,
        query_id=None,
        wrote_via_legacy=False,
        pipeline_name="nightly_signal",
        transition="started",
        run_id=uuid4(),
        trigger="celery_beat",
    )
    defaults.update(overrides)
    return PipelineLifecycleEvent(**defaults)


def _make_session_cm():
    """Build an (async_session_factory mock, mock_session) pair.

    Returns:
        Tuple of (context_manager_mock, mock_session) where mock_session
        records calls to add() and commit().
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm, mock_session


class TestLegacyEmittersWriter:
    """Tests for legacy_emitters_writer dedup invariant (wrote_via_legacy flag)."""

    @pytest.mark.asyncio
    async def test_persist_llm_calls_skips_when_wrote_via_legacy(self) -> None:
        """When wrote_via_legacy=True, writer skips DB (row already exists from legacy path)."""
        from backend.observability.service.legacy_emitters_writer import persist_llm_calls

        event = _make_llm_call_event(wrote_via_legacy=True)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory"
        ) as mock_sf:
            await persist_llm_calls([event])
            mock_sf.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_llm_calls_writes_when_sdk_only(self) -> None:
        """When wrote_via_legacy=False, writer inserts the LLMCallLog row."""
        from backend.observability.service.legacy_emitters_writer import persist_llm_calls

        event = _make_llm_call_event(wrote_via_legacy=False)
        mock_cm, mock_session = _make_session_cm()

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_llm_calls([event])
            mock_session.add.assert_called_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_llm_calls_row_fields(self) -> None:
        """LLMCallLog row receives correct field values from the event."""
        from backend.models.logs import LLMCallLog
        from backend.observability.service.legacy_emitters_writer import persist_llm_calls

        event = _make_llm_call_event(
            wrote_via_legacy=False,
            model="claude-3-haiku",
            provider="anthropic",
            tier="fast",
            latency_ms=42,
            prompt_tokens=100,
            completion_tokens=20,
            status="completed",
            error=None,
        )
        added_rows: list = []
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda r: added_rows.append(r))
        mock_session.commit = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_llm_calls([event])

        assert len(added_rows) == 1
        row = added_rows[0]
        assert isinstance(row, LLMCallLog)
        assert row.model == "claude-3-haiku"
        assert row.provider == "anthropic"
        assert row.tier == "fast"
        assert row.latency_ms == 42
        assert row.prompt_tokens == 100
        assert row.completion_tokens == 20

    @pytest.mark.asyncio
    async def test_persist_tool_executions_skips_when_wrote_via_legacy(self) -> None:
        """When wrote_via_legacy=True, writer skips DB (row already exists from legacy path)."""
        from backend.observability.service.legacy_emitters_writer import persist_tool_executions

        event = _make_tool_execution_event(wrote_via_legacy=True)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory"
        ) as mock_sf:
            await persist_tool_executions([event])
            mock_sf.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_tool_executions_writes_when_sdk_only(self) -> None:
        """When wrote_via_legacy=False, writer inserts the ToolExecutionLog row."""
        from backend.observability.service.legacy_emitters_writer import persist_tool_executions

        event = _make_tool_execution_event(wrote_via_legacy=False)
        mock_cm, mock_session = _make_session_cm()

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_tool_executions([event])
            mock_session.add.assert_called_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_login_attempts_skips_when_wrote_via_legacy(self) -> None:
        """When wrote_via_legacy=True, writer skips DB (row already exists from legacy path)."""
        from backend.observability.service.legacy_emitters_writer import persist_login_attempts

        event = _make_login_attempt_event(wrote_via_legacy=True)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory"
        ) as mock_sf:
            await persist_login_attempts([event])
            mock_sf.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_login_attempts_writes_when_sdk_only(self) -> None:
        """When wrote_via_legacy=False, writer inserts the LoginAttempt row."""
        from backend.observability.service.legacy_emitters_writer import persist_login_attempts

        event = _make_login_attempt_event(wrote_via_legacy=False)
        mock_cm, mock_session = _make_session_cm()

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_login_attempts([event])
            mock_session.add.assert_called_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_login_attempts_timestamp_maps_from_ts(self) -> None:
        """LoginAttempt.timestamp is populated from event.ts (not event.timestamp)."""
        from backend.models.login_attempt import LoginAttempt
        from backend.observability.service.legacy_emitters_writer import persist_login_attempts

        ts = datetime.now(timezone.utc)
        event = _make_login_attempt_event(wrote_via_legacy=False, ts=ts)
        added_rows: list = []
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda r: added_rows.append(r))
        mock_session.commit = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_login_attempts([event])

        assert len(added_rows) == 1
        row = added_rows[0]
        assert isinstance(row, LoginAttempt)
        assert row.timestamp == ts

    @pytest.mark.asyncio
    async def test_persist_dq_findings_skips_when_wrote_via_legacy(self) -> None:
        """When wrote_via_legacy=True, writer skips DB (row already exists from legacy path)."""
        from backend.observability.service.legacy_emitters_writer import persist_dq_findings

        event = _make_dq_finding_event(wrote_via_legacy=True)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory"
        ) as mock_sf:
            await persist_dq_findings([event])
            mock_sf.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_dq_findings_writes_when_sdk_only(self) -> None:
        """When wrote_via_legacy=False, writer inserts the DqCheckHistory row."""
        from backend.observability.service.legacy_emitters_writer import persist_dq_findings

        event = _make_dq_finding_event(wrote_via_legacy=False)
        mock_cm, mock_session = _make_session_cm()

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_dq_findings([event])
            mock_session.add.assert_called_once()
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persist_dq_findings_metadata_field(self) -> None:
        """DqCheckHistory.metadata_ is populated from event.metadata."""
        from backend.models.dq_check_history import DqCheckHistory
        from backend.observability.service.legacy_emitters_writer import persist_dq_findings

        meta = {"rows_affected": 5}
        event = _make_dq_finding_event(wrote_via_legacy=False, metadata=meta)
        added_rows: list = []
        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=lambda r: added_rows.append(r))
        mock_session.commit = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            await persist_dq_findings([event])

        assert len(added_rows) == 1
        row = added_rows[0]
        assert isinstance(row, DqCheckHistory)
        assert row.metadata_ == meta

    @pytest.mark.asyncio
    async def test_persist_pipeline_lifecycle_no_db_write(self) -> None:
        """Pipeline lifecycle events are informational only — no DB write occurs."""
        from backend.observability.service.legacy_emitters_writer import (
            persist_pipeline_lifecycle,
        )

        event = _make_pipeline_lifecycle_event(wrote_via_legacy=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory"
        ) as mock_sf:
            await persist_pipeline_lifecycle([event])
            mock_sf.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_pipeline_lifecycle_logs_debug(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Pipeline lifecycle events are logged at DEBUG level."""
        import logging

        from backend.observability.service.legacy_emitters_writer import (
            persist_pipeline_lifecycle,
        )

        event = _make_pipeline_lifecycle_event(
            wrote_via_legacy=False,
            pipeline_name="nightly_signal",
            transition="success",
        )

        with caplog.at_level(
            logging.DEBUG,
            logger="backend.observability.service.legacy_emitters_writer",
        ):
            await persist_pipeline_lifecycle([event])

        assert any("obs.pipeline_lifecycle" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_persist_llm_calls_swallows_db_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DB errors in persist_llm_calls are swallowed and logged, not re-raised."""
        import logging

        from backend.observability.service.legacy_emitters_writer import persist_llm_calls

        event = _make_llm_call_event(wrote_via_legacy=False)
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=RuntimeError("DB exploded"))
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.async_session_factory",
            return_value=mock_cm,
        ):
            with caplog.at_level(
                logging.WARNING,
                logger="backend.observability.service.legacy_emitters_writer",
            ):
                await persist_llm_calls([event])  # must not raise

        assert any("obs.writer.llm_call.failed" in r.message for r in caplog.records)


class TestEventWriterLegacyRouting:
    """Tests for write_batch routing of PR5 legacy emitter event types."""

    @pytest.mark.asyncio
    async def test_routes_llm_call_events(self) -> None:
        """LLM_CALL events are routed to persist_llm_calls."""
        from backend.observability.service.event_writer import write_batch

        event = _make_llm_call_event(wrote_via_legacy=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.persist_llm_calls",
            new_callable=AsyncMock,
        ) as mock_persist:
            await write_batch([event])
            mock_persist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_tool_execution_events(self) -> None:
        """TOOL_EXECUTION events are routed to persist_tool_executions."""
        from backend.observability.service.event_writer import write_batch

        event = _make_tool_execution_event(wrote_via_legacy=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.persist_tool_executions",
            new_callable=AsyncMock,
        ) as mock_persist:
            await write_batch([event])
            mock_persist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_login_attempt_events(self) -> None:
        """LOGIN_ATTEMPT events are routed to persist_login_attempts."""
        from backend.observability.service.event_writer import write_batch

        event = _make_login_attempt_event(wrote_via_legacy=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.persist_login_attempts",
            new_callable=AsyncMock,
        ) as mock_persist:
            await write_batch([event])
            mock_persist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_dq_finding_events(self) -> None:
        """DQ_FINDING events are routed to persist_dq_findings."""
        from backend.observability.service.event_writer import write_batch

        event = _make_dq_finding_event(wrote_via_legacy=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.persist_dq_findings",
            new_callable=AsyncMock,
        ) as mock_persist:
            await write_batch([event])
            mock_persist.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_routes_pipeline_lifecycle_events(self) -> None:
        """PIPELINE_LIFECYCLE events are routed to persist_pipeline_lifecycle."""
        from backend.observability.service.event_writer import write_batch

        event = _make_pipeline_lifecycle_event(wrote_via_legacy=False)

        with patch(
            "backend.observability.service.legacy_emitters_writer.persist_pipeline_lifecycle",
            new_callable=AsyncMock,
        ) as mock_persist:
            await write_batch([event])
            mock_persist.assert_awaited_once()
