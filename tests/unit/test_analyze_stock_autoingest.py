"""Tests for AnalyzeStockTool canonical ingest behaviour (KAN-450).

PR2 of Spec C rewrites AnalyzeStockTool to use ingest_ticker (canonical pipeline)
then reload signals from DB via get_latest_signals. These tests verify the new path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.analyze_stock import AnalyzeStockTool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_cm(session: AsyncMock) -> AsyncMock:
    """Return an async context-manager mock that yields *session*."""
    cm = AsyncMock()
    cm.__aenter__.return_value = session
    cm.__aexit__.return_value = None
    return cm


def _fake_snapshot() -> MagicMock:
    """Return a MagicMock that looks like a SignalSnapshot ORM row."""
    snap = MagicMock()
    snap.composite_score = 7.5
    snap.rsi_value = 45.0
    snap.rsi_signal = "neutral"
    snap.macd_signal_label = "bullish"
    snap.sma_signal = "above_sma50"
    snap.bb_position = "mid"
    snap.annual_return = 0.18
    snap.volatility = 0.22
    snap.sharpe_ratio = 1.1
    snap.computed_at = None
    return snap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyzeStockCanonicalIngest:
    """Tests for the canonical ingest path in AnalyzeStockTool._run (KAN-450)."""

    @pytest.mark.asyncio
    async def test_analyze_stock_calls_ingest_ticker(self) -> None:
        """ingest_ticker is called when lock is acquired."""
        tool = AnalyzeStockTool()
        session = AsyncMock()
        snapshot = _fake_snapshot()

        acquire_mock = AsyncMock(return_value=True)
        release_mock = AsyncMock()
        ingest_mock = AsyncMock()
        signals_mock = AsyncMock(return_value=snapshot)

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch("backend.services.ingest_lock.acquire_ingest_lock", acquire_mock),
            patch("backend.services.ingest_lock.release_ingest_lock", release_mock),
            patch("backend.services.pipelines.ingest_ticker", ingest_mock),
            patch("backend.services.signals.get_latest_signals", signals_mock),
        ):
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "ok"
        ingest_mock.assert_awaited_once()
        acquire_mock.assert_awaited_once_with("AAPL")
        release_mock.assert_awaited_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_analyze_stock_returns_persisted_signals(self) -> None:
        """Signals returned come from DB snapshot, not inline computation."""
        tool = AnalyzeStockTool()
        session = AsyncMock()
        snapshot = _fake_snapshot()

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch("backend.services.ingest_lock.acquire_ingest_lock", AsyncMock(return_value=True)),
            patch("backend.services.ingest_lock.release_ingest_lock", AsyncMock()),
            patch("backend.services.pipelines.ingest_ticker", AsyncMock()),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=snapshot)),
        ):
            result = await tool.execute({"ticker": "TSLA"})

        assert result.status == "ok"
        assert result.data["ticker"] == "TSLA"
        assert result.data["composite_score"] == 7.5
        assert result.data["rsi_value"] == 45.0
        assert result.data["rsi_signal"] == "neutral"
        assert result.data["macd_signal"] == "bullish"

    @pytest.mark.asyncio
    async def test_analyze_stock_ingest_fails_returns_error(self) -> None:
        """When ingest fails AND no snapshot exists, returns safe error message."""
        tool = AnalyzeStockTool()
        session = AsyncMock()

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch("backend.services.ingest_lock.acquire_ingest_lock", AsyncMock(return_value=True)),
            patch("backend.services.ingest_lock.release_ingest_lock", AsyncMock()),
            patch(
                "backend.services.pipelines.ingest_ticker",
                AsyncMock(side_effect=RuntimeError("yfinance down")),
            ),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=None)),
        ):
            result = await tool.execute({"ticker": "XYZW"})

        assert result.status == "error"
        assert "No analysis data available" in result.error
        # Hard Rule #10: must not leak raw exception text
        assert "yfinance" not in result.error

    @pytest.mark.asyncio
    async def test_analyze_stock_lock_contention_still_reads_snapshot(self) -> None:
        """When lock is NOT acquired, still reads existing snapshot from DB."""
        tool = AnalyzeStockTool()
        session = AsyncMock()
        snapshot = _fake_snapshot()
        ingest_mock = AsyncMock()

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch(
                "backend.services.ingest_lock.acquire_ingest_lock",
                AsyncMock(return_value=False),
            ),
            patch("backend.services.ingest_lock.release_ingest_lock", AsyncMock()),
            patch("backend.services.pipelines.ingest_ticker", ingest_mock),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=snapshot)),
        ):
            result = await tool.execute({"ticker": "MSFT"})

        assert result.status == "ok"
        assert result.data["ticker"] == "MSFT"
        # ingest_ticker must NOT be called when lock was not acquired
        ingest_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_ticker_format_returns_error(self) -> None:
        """Ticker containing digits or too long is rejected before any DB call."""
        tool = AnalyzeStockTool()

        for bad_ticker in ("INVALID123", "12345", "TOOLONG", "A B", ""):
            result = await tool.execute({"ticker": bad_ticker})
            if bad_ticker == "":
                assert result.status == "error"
                assert "Missing" in result.error
            else:
                assert result.status == "error", f"Expected error for ticker={bad_ticker!r}"
                assert "Invalid" in result.error, (
                    f"Expected 'Invalid' in error for ticker={bad_ticker!r}"
                )

    @pytest.mark.asyncio
    async def test_no_snapshot_returns_no_data_error(self) -> None:
        """When ingest succeeds but no snapshot in DB, returns no-data error."""
        tool = AnalyzeStockTool()
        session = AsyncMock()

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch("backend.services.ingest_lock.acquire_ingest_lock", AsyncMock(return_value=True)),
            patch("backend.services.ingest_lock.release_ingest_lock", AsyncMock()),
            patch("backend.services.pipelines.ingest_ticker", AsyncMock()),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=None)),
        ):
            result = await tool.execute({"ticker": "NEWT"})

        assert result.status == "error"
        assert "No analysis data available" in result.error

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_generic_error(self) -> None:
        """Unexpected exception from ingest triggers the base class catch-all.

        The base class execute() wraps _run() exceptions in a safe generic message
        rather than leaking stack trace or raw exception text to the caller.
        """
        tool = AnalyzeStockTool()

        with patch(
            "backend.database.async_session_factory",
            side_effect=RuntimeError("DB connection failed"),
        ):
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "error"
        assert result.error == "Failed to execute analyze_stock. Please try again."
        # Hard Rule #10: raw exception text must not appear
        assert "DB connection failed" not in result.error
