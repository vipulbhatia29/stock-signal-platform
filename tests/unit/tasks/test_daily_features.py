"""Unit tests for the daily feature population Celery task.

Tests exercise _populate_daily_features_async directly via bypass_tracked,
mocking all I/O (DB session, yfinance, build_feature_dataframe, upsert).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


def _make_closes(n: int = 300) -> pd.Series:
    """Return a synthetic close-price Series with UTC DatetimeIndex."""
    idx = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    return pd.Series([100.0 + i * 0.1 for i in range(n)], index=idx, name="adj_close")


def _make_features_df() -> pd.DataFrame:
    """Return a minimal features DataFrame with one row (the 'today' row)."""
    idx = pd.date_range("2024-10-28", periods=1, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "momentum_21d": [0.05],
            "momentum_63d": [0.10],
            "momentum_126d": [0.15],
            "rsi_value": [55.0],
            "macd_histogram": [0.002],
            "sma_cross": [2],
            "bb_position": [1],
            "volatility": [0.015],
            "sharpe_ratio": [1.2],
            "vix_level": [18.5],
            "spy_momentum_21d": [0.03],
        },
        index=idx,
    )


def _make_price_rows(ticker: str, n: int = 300) -> list:
    """Return synthetic price rows matching (ticker, time, close, high, low, volume)."""
    rows = []
    for i in range(n):
        row = MagicMock()
        row.ticker = ticker
        from datetime import timedelta

        row.time = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
        price = 100.0 + i * 0.1
        row.close = price
        row.high = price * 1.01
        row.low = price * 0.99
        row.volume = 1_000_000.0
        rows.append(row)
    return rows


def _noop_session(price_rows: list | None = None):
    """Return a fresh async context manager that yields a mock session.

    If price_rows is provided, the session's execute() returns a result
    whose .all() returns those rows (for the batch price fetch).
    """

    @asynccontextmanager
    async def _cm():
        session = MagicMock()
        if price_rows is not None:
            mock_result = MagicMock()
            mock_result.all.return_value = price_rows
            session.execute = AsyncMock(return_value=mock_result)
        yield session

    return _cm()


@pytest.mark.asyncio
async def test_populates_features_for_all_tickers():
    """Batch-fetches prices once, then upserts a feature row for each ticker in the universe.

    The batch DB query returns price rows for both tickers. Verifies that
    _upsert_daily_feature_row is called once per ticker.
    """
    from backend.tasks.forecasting import _populate_daily_features_async

    features = _make_features_df()
    vix = _make_closes(252)
    spy = _make_closes(252)

    # Build batch price rows for both tickers (300 rows each)
    aapl_rows = _make_price_rows("AAPL", 300)
    msft_rows = _make_price_rows("MSFT", 300)
    all_price_rows = aapl_rows + msft_rows

    call_count = {"n": 0}

    def _session_factory_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: fetch tickers + VIX/SPY (no price mock needed)
            return _noop_session()
        elif call_count["n"] == 2:
            # Second call: batch price fetch — returns all price rows
            return _noop_session(price_rows=all_price_rows)
        else:
            # Subsequent calls: upsert sessions
            return _noop_session()

    with (
        patch("backend.tasks.forecasting.settings") as mock_settings,
        patch("backend.tasks.forecasting._db") as mock_db,
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=["AAPL", "MSFT"],
        ),
        patch(
            "backend.tasks.forecasting._fetch_vix_and_spy",
            new_callable=AsyncMock,
            return_value=(vix, spy),
        ),
        patch(
            "backend.tasks.forecasting.build_feature_dataframe",
            return_value=features,
        ),
        patch(
            "backend.tasks.forecasting._upsert_daily_feature_row",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        mock_settings.DAILY_FEATURES_ENABLED = True
        mock_db.async_session_factory.side_effect = _session_factory_side_effect

        result = await bypass_tracked(_populate_daily_features_async)(run_id=uuid.uuid4())

    assert result["status"] in ("ok", "degraded")
    assert result["populated"] == 2
    assert result["failed"] == 0
    assert result["failed_tickers"] == []
    assert mock_upsert.call_count == 2


@pytest.mark.asyncio
async def test_disabled_via_config():
    """When DAILY_FEATURES_ENABLED=False, the task returns immediately with status='disabled'.

    No DB session should be opened and no helpers should be called.
    """
    from backend.tasks.forecasting import _populate_daily_features_async

    with patch("backend.tasks.forecasting.settings") as mock_settings:
        mock_settings.DAILY_FEATURES_ENABLED = False

        result = await bypass_tracked(_populate_daily_features_async)(run_id=uuid.uuid4())

    assert result == {"status": "disabled"}


@pytest.mark.asyncio
async def test_handles_ticker_with_insufficient_data():
    """When one ticker has fewer than 250 price rows, it is skipped; others still succeed.

    The failing ticker appears in failed_tickers and status is 'degraded'.
    The succeeding ticker is still upserted.
    """
    from backend.tasks.forecasting import _populate_daily_features_async

    features = _make_features_df()
    vix = _make_closes(252)
    spy = _make_closes(252)

    # FAIL ticker: only 10 rows (below 250 threshold)
    fail_rows = _make_price_rows("FAIL", 10)
    # MSFT: 300 rows (sufficient)
    msft_rows = _make_price_rows("MSFT", 300)
    all_price_rows = fail_rows + msft_rows

    call_count = {"n": 0}

    def _session_factory_side_effect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First call: fetch tickers + VIX/SPY
            return _noop_session()
        elif call_count["n"] == 2:
            # Second call: batch price fetch
            return _noop_session(price_rows=all_price_rows)
        else:
            # Upsert sessions
            return _noop_session()

    with (
        patch("backend.tasks.forecasting.settings") as mock_settings,
        patch("backend.tasks.forecasting._db") as mock_db,
        patch(
            "backend.tasks.forecasting.get_all_referenced_tickers",
            new_callable=AsyncMock,
            return_value=["FAIL", "MSFT"],
        ),
        patch(
            "backend.tasks.forecasting._fetch_vix_and_spy",
            new_callable=AsyncMock,
            return_value=(vix, spy),
        ),
        patch(
            "backend.tasks.forecasting.build_feature_dataframe",
            return_value=features,
        ),
        patch(
            "backend.tasks.forecasting._upsert_daily_feature_row",
            new_callable=AsyncMock,
        ) as mock_upsert,
    ):
        mock_settings.DAILY_FEATURES_ENABLED = True
        mock_db.async_session_factory.side_effect = _session_factory_side_effect

        result = await bypass_tracked(_populate_daily_features_async)(run_id=uuid.uuid4())

    assert result["status"] == "degraded"
    assert result["populated"] == 1
    assert result["failed"] == 1
    assert "FAIL" in result["failed_tickers"]
    assert mock_upsert.call_count == 1
