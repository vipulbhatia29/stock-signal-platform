"""Unit tests for the daily feature population Celery task.

Tests exercise _populate_daily_features_async directly via bypass_tracked,
mocking all I/O (DB session, yfinance, build_feature_dataframe, upsert).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
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


def _noop_session():
    """Return a fresh async context manager that yields a dummy session."""

    @asynccontextmanager
    async def _cm():
        yield MagicMock()

    return _cm()


@pytest.mark.asyncio
async def test_populates_features_for_all_tickers():
    """When enabled, the task upserts a feature row for each ticker in the universe.

    Mocks: DB session factory, get_all_referenced_tickers, _fetch_ticker_prices,
    _fetch_vix_and_spy, build_feature_dataframe, _upsert_daily_feature_row.
    Verifies that _upsert_daily_feature_row is called once per ticker.
    """
    from backend.tasks.forecasting import _populate_daily_features_async

    closes = _make_closes()
    features = _make_features_df()
    vix = _make_closes(252)
    spy = _make_closes(252)

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
            "backend.tasks.forecasting._fetch_ticker_prices",
            new_callable=AsyncMock,
            return_value=closes,
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
        mock_db.async_session_factory.side_effect = lambda: _noop_session()

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
async def test_handles_ticker_failure_gracefully():
    """When one ticker raises during _fetch_ticker_prices, others still succeed.

    The failing ticker appears in failed_tickers and status is 'degraded'.
    The succeeding ticker is still upserted.
    """
    from backend.tasks.forecasting import _populate_daily_features_async

    closes = _make_closes()
    features = _make_features_df()
    vix = _make_closes(252)
    spy = _make_closes(252)

    call_count = {"n": 0}

    async def _prices_side_effect(ticker: str, db: object) -> pd.Series:
        """Raise for the first ticker; succeed for the second."""
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError(f"No price data for {ticker}")
        return closes

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
            "backend.tasks.forecasting._fetch_ticker_prices",
            side_effect=_prices_side_effect,
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
        mock_db.async_session_factory.side_effect = lambda: _noop_session()

        result = await bypass_tracked(_populate_daily_features_async)(run_id=uuid.uuid4())

    assert result["status"] == "degraded"
    assert result["populated"] == 1
    assert result["failed"] == 1
    assert "FAIL" in result["failed_tickers"]
    assert mock_upsert.call_count == 1
