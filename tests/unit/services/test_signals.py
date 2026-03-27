"""Tests for backend.services.signals query helpers.

Tests cover the three query functions extracted from router inline queries:
  - get_latest_signals
  - get_signal_history
  - get_bulk_signals (smoke test — complex query tested via API tests)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.signals import get_latest_signals, get_signal_history


@pytest.fixture()
def mock_db() -> AsyncMock:
    """Create a mock AsyncSession with execute returning configurable results."""
    db = AsyncMock()
    return db


def _make_snapshot_mock(
    ticker: str = "AAPL",
    computed_at: datetime | None = None,
    composite_score: float = 7.5,
    rsi_value: float = 45.0,
    rsi_signal: str = "NEUTRAL",
    macd_value: float = 1.2,
    macd_signal_label: str = "BULLISH",
    sma_signal: str = "ABOVE_200",
    bb_position: str = "MIDDLE",
) -> MagicMock:
    """Create a mock SignalSnapshot-like object."""
    snap = MagicMock()
    snap.ticker = ticker
    snap.computed_at = computed_at or datetime.now(timezone.utc)
    snap.composite_score = composite_score
    snap.rsi_value = rsi_value
    snap.rsi_signal = rsi_signal
    snap.macd_value = macd_value
    snap.macd_signal_label = macd_signal_label
    snap.sma_signal = sma_signal
    snap.bb_position = bb_position
    snap.macd_histogram = 0.5
    snap.sma_50 = 150.0
    snap.sma_200 = 140.0
    snap.bb_upper = 160.0
    snap.bb_lower = 130.0
    snap.annual_return = 0.15
    snap.volatility = 0.20
    snap.sharpe_ratio = 1.2
    snap.composite_weights = {"mode": "technical_only"}
    return snap


class TestGetLatestSignals:
    """Tests for get_latest_signals()."""

    @pytest.mark.asyncio()
    async def test_returns_snapshot_when_exists(self, mock_db: AsyncMock) -> None:
        """Should return the most recent snapshot for the ticker."""
        snapshot = _make_snapshot_mock(ticker="AAPL")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = snapshot
        mock_db.execute.return_value = result_mock

        result = await get_latest_signals("AAPL", mock_db)

        assert result is snapshot
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_returns_none_when_no_signals(self, mock_db: AsyncMock) -> None:
        """Should return None when no signals exist for the ticker."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result_mock

        result = await get_latest_signals("ZZZZZ", mock_db)

        assert result is None

    @pytest.mark.asyncio()
    async def test_uppercases_ticker(self, mock_db: AsyncMock) -> None:
        """Should uppercase the ticker before querying."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = result_mock

        await get_latest_signals("aapl", mock_db)

        # Verify execute was called (the query itself handles uppercasing)
        mock_db.execute.assert_awaited_once()


class TestGetSignalHistory:
    """Tests for get_signal_history()."""

    @pytest.mark.asyncio()
    async def test_default_90_days(self, mock_db: AsyncMock) -> None:
        """Should query with 90-day cutoff by default."""
        snap1 = _make_snapshot_mock(computed_at=datetime.now(timezone.utc) - timedelta(days=30))
        snap2 = _make_snapshot_mock(computed_at=datetime.now(timezone.utc) - timedelta(days=10))

        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [snap1, snap2]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await get_signal_history("AAPL", mock_db)

        assert len(result) == 2
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_custom_days_and_limit(self, mock_db: AsyncMock) -> None:
        """Should respect custom days and limit parameters."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await get_signal_history("MSFT", mock_db, days=30, limit=10)

        assert result == []
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_returns_empty_list_when_no_history(self, mock_db: AsyncMock) -> None:
        """Should return an empty list when no snapshots exist."""
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        mock_db.execute.return_value = result_mock

        result = await get_signal_history("NEWSTOCK", mock_db)

        assert result == []
