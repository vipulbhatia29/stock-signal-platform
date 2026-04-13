"""Tests for AnalyzeStockTool canonical ingest path (KAN-450 PR2).

Covers the four scenarios specified in Spec C PR2:
1. ingest_ticker is called when lock acquired
2. signals come from DB snapshot (not inline computation)
3. ingest fails + no snapshot → returns safe error
4. lock contention but snapshot exists → returns data
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
    """Return a MagicMock that resembles a SignalSnapshot ORM row."""
    snap = MagicMock()
    snap.composite_score = 8.2
    snap.rsi_value = 38.5
    snap.rsi_signal = "oversold"
    snap.macd_signal_label = "bullish"
    snap.sma_signal = "above_sma50"
    snap.bb_position = "lower"
    snap.annual_return = 0.25
    snap.volatility = 0.19
    snap.sharpe_ratio = 1.4
    snap.computed_at = None
    return snap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAnalyzeStockCanonical:
    """Canonical ingest path for AnalyzeStockTool — KAN-450 Spec C PR2."""

    @pytest.mark.asyncio
    async def test_analyze_stock_calls_ingest_ticker(self) -> None:
        """ingest_ticker is awaited exactly once when the ingest lock is acquired.

        Verifies the canonical pipeline (not the old lightweight path) is invoked.
        """
        tool = AnalyzeStockTool()
        session = AsyncMock()
        snapshot = _fake_snapshot()
        ingest_mock = AsyncMock()

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=_make_session_cm(session),
            ),
            patch("backend.services.ingest_lock.acquire_ingest_lock", AsyncMock(return_value=True)),
            patch("backend.services.ingest_lock.release_ingest_lock", AsyncMock()),
            patch("backend.services.pipelines.ingest_ticker", ingest_mock),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=snapshot)),
        ):
            result = await tool.execute({"ticker": "NVDA"})

        assert result.status == "ok"
        ingest_mock.assert_awaited_once()
        # Verify canonical pipeline was called with the correct ticker
        call_args = ingest_mock.await_args
        assert call_args.args[0] == "NVDA"

    @pytest.mark.asyncio
    async def test_analyze_stock_returns_persisted_signals(self) -> None:
        """Signal data returned to caller comes from the DB snapshot, not inline computation.

        Ensures chat and stock page agree on signal values because both read
        from the same persisted SignalSnapshot row.
        """
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
            result = await tool.execute({"ticker": "AAPL"})

        assert result.status == "ok"
        data = result.data
        assert data["ticker"] == "AAPL"
        assert data["composite_score"] == snapshot.composite_score
        assert data["rsi_value"] == snapshot.rsi_value
        assert data["rsi_signal"] == snapshot.rsi_signal
        assert data["macd_signal"] == snapshot.macd_signal_label
        assert data["sma_signal"] == snapshot.sma_signal
        assert data["bb_position"] == snapshot.bb_position
        assert data["annual_return"] == snapshot.annual_return
        assert data["computed_at"] is None  # snapshot.computed_at is None

    @pytest.mark.asyncio
    async def test_analyze_stock_ingest_fails_returns_error(self) -> None:
        """When ingest raises an exception and no snapshot exists, a safe error is returned.

        The error message must NOT contain raw exception text (Hard Rule #10).
        """
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
                AsyncMock(side_effect=ConnectionError("provider unreachable")),
            ),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=None)),
        ):
            result = await tool.execute({"ticker": "XYZW"})

        assert result.status == "error"
        assert "No analysis data available" in result.error
        # Hard Rule #10 — no raw exception text in user-facing output
        assert "provider unreachable" not in result.error

    @pytest.mark.asyncio
    async def test_analyze_stock_lock_contention_still_reads_snapshot(self) -> None:
        """When the ingest lock is NOT acquired, ingest is skipped but snapshot is still read.

        This handles the case where another request is already ingesting the same ticker.
        The caller gets existing stale data rather than waiting or returning an error.
        """
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
                AsyncMock(return_value=False),  # lock NOT acquired
            ),
            patch("backend.services.ingest_lock.release_ingest_lock", AsyncMock()),
            patch("backend.services.pipelines.ingest_ticker", ingest_mock),
            patch("backend.services.signals.get_latest_signals", AsyncMock(return_value=snapshot)),
        ):
            result = await tool.execute({"ticker": "MSFT"})

        assert result.status == "ok"
        assert result.data["ticker"] == "MSFT"
        # ingest_ticker MUST NOT be called when lock was not acquired
        ingest_mock.assert_not_awaited()
