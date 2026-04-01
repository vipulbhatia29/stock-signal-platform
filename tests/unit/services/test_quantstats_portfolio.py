"""Tests for compute_quantstats_portfolio() — portfolio-level QuantStats metrics."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.services.portfolio import compute_quantstats_portfolio


def _make_snapshot_row(date, value):
    """Create a mock row matching the select(snapshot_date, total_value) query."""
    row = MagicMock()
    row.snapshot_date = date
    row.total_value = Decimal(str(value))
    return row


def _make_spy_row(date, close):
    """Create a mock row matching the select(time, close) query."""
    row = MagicMock()
    row.time = date
    row.close = Decimal(str(close))
    return row


class TestComputeQuantstatsPortfolio:
    @pytest.mark.asyncio
    async def test_insufficient_data_returns_nulls(self):
        """Under 2 snapshots → all None with data_days."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.all.return_value = [_make_snapshot_row(datetime.now(timezone.utc), 10000)]
        db.execute.return_value = result_mock

        result = await compute_quantstats_portfolio(uuid4(), db)
        assert result["sharpe"] is None
        assert result["data_days"] == 1

    @pytest.mark.asyncio
    async def test_under_30_data_points_returns_nulls(self):
        """Under 30 returns → all None."""
        db = AsyncMock()
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        # 15 snapshots → 14 returns (< 30)
        rows = [_make_snapshot_row(base + timedelta(days=i), 10000 + i * 10) for i in range(15)]

        result_mock = MagicMock()
        result_mock.all.return_value = rows
        db.execute.return_value = result_mock

        result = await compute_quantstats_portfolio(uuid4(), db)
        assert result["sharpe"] is None
        assert result["data_days"] == 14

    @pytest.mark.asyncio
    async def test_sufficient_data_returns_metrics(self):
        """60+ snapshots → at least some metrics computed."""
        import random

        db = AsyncMock()
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        # 90 snapshots — add some variance so QuantStats doesn't return inf
        random.seed(42)
        rows = [
            _make_snapshot_row(
                base + timedelta(days=i),
                10000 + i * 5 + random.uniform(-50, 50),
            )
            for i in range(90)
        ]

        # No SPY data (alpha/beta will be None)
        spy_result = MagicMock()
        spy_result.all.return_value = []

        snap_result = MagicMock()
        snap_result.all.return_value = rows

        db.execute.side_effect = [snap_result, spy_result]

        result = await compute_quantstats_portfolio(uuid4(), db)
        assert result["sharpe"] is not None
        assert result["max_drawdown"] is not None
        assert result["max_drawdown"] >= 0
        assert result["data_days"] == 89  # 90 snapshots → 89 returns
        # No SPY data → alpha/beta should be None
        assert result["alpha"] is None
        assert result["beta"] is None

    @pytest.mark.asyncio
    async def test_with_spy_data_returns_alpha_beta(self):
        """SPY data present → alpha and beta computed."""
        db = AsyncMock()
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        rows = [_make_snapshot_row(base + timedelta(days=i), 10000 + i * 5) for i in range(90)]
        # SPY rows use same tz-aware dates
        spy_rows = [_make_spy_row(base + timedelta(days=i), 450 + i * 0.5) for i in range(90)]

        snap_result = MagicMock()
        snap_result.all.return_value = rows
        spy_result = MagicMock()
        spy_result.all.return_value = spy_rows

        db.execute.side_effect = [snap_result, spy_result]

        result = await compute_quantstats_portfolio(uuid4(), db)
        assert result["alpha"] is not None
        assert result["beta"] is not None
