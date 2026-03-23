"""Tests for the price seed script."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from scripts.seed_prices import DEFAULT_TICKERS, seed_ticker


# ---------------------------------------------------------------------------
# Helper: generate a simple price DataFrame like yfinance returns
# ---------------------------------------------------------------------------
def _make_price_df(rows: int = 300, start_price: float = 150.0) -> pd.DataFrame:
    """Create a mock OHLCV DataFrame similar to yfinance output."""
    dates = pd.bdate_range(end=datetime.now(), periods=rows)
    prices = [start_price + i * 0.1 for i in range(rows)]
    return pd.DataFrame(
        {
            "Open": prices,
            "High": [p + 2 for p in prices],
            "Low": [p - 2 for p in prices],
            "Close": [p + 0.5 for p in prices],
            "Adj Close": [p + 0.5 for p in prices],
            "Volume": [50_000_000] * rows,
        },
        index=dates,
    )


# ---------------------------------------------------------------------------
# seed_ticker — the per-ticker pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("scripts.seed_prices.get_latest_price", new_callable=AsyncMock, return_value=180.0)
@patch("scripts.seed_prices.store_signal_snapshot", new_callable=AsyncMock)
@patch("scripts.seed_prices.fetch_prices", new_callable=AsyncMock)
@patch("scripts.seed_prices.ensure_stock_exists", new_callable=AsyncMock)
async def test_seed_ticker_success(mock_ensure, mock_fetch, mock_store_signal, mock_price):
    """seed_ticker should fetch prices, compute signals, and return success."""
    mock_fetch.return_value = _make_price_df(300)
    db = AsyncMock()

    result = await seed_ticker("AAPL", "2y", db)

    assert result["ticker"] == "AAPL"
    assert result["status"] == "ok"
    assert result["price_rows"] == 300
    assert result["composite_score"] is not None
    assert result["action"] in ("BUY", "WATCH", "AVOID")
    assert result["confidence"] in ("HIGH", "MEDIUM", "LOW")

    mock_ensure.assert_called_once_with("AAPL", db)
    mock_fetch.assert_called_once_with("AAPL", period="2y", db=db)
    mock_store_signal.assert_called_once()


@pytest.mark.asyncio
@patch(
    "scripts.seed_prices.ensure_stock_exists",
    new_callable=AsyncMock,
    side_effect=ValueError("Bad ticker"),
)
async def test_seed_ticker_error_returns_error_status(mock_ensure):
    """seed_ticker should catch exceptions and return error status."""
    db = AsyncMock()

    result = await seed_ticker("INVALID", "2y", db)

    assert result["status"] == "error"
    assert result["ticker"] == "INVALID"
    assert "Bad ticker" in result["error"]


@pytest.mark.asyncio
@patch("scripts.seed_prices.get_latest_price", new_callable=AsyncMock, return_value=180.0)
@patch("scripts.seed_prices.store_signal_snapshot", new_callable=AsyncMock)
@patch("scripts.seed_prices.fetch_prices", new_callable=AsyncMock)
@patch("scripts.seed_prices.ensure_stock_exists", new_callable=AsyncMock)
async def test_seed_ticker_computes_signals(mock_ensure, mock_fetch, mock_store_signal, mock_price):
    """seed_ticker should call compute_signals and store the snapshot."""
    mock_fetch.return_value = _make_price_df(300)
    db = AsyncMock()

    result = await seed_ticker("MSFT", "10y", db)

    assert result["status"] == "ok"
    # Signal snapshot should be stored
    mock_store_signal.assert_called_once()
    signal_result = mock_store_signal.call_args[0][0]
    assert signal_result.ticker == "MSFT"


@pytest.mark.asyncio
@patch("scripts.seed_prices.get_latest_price", new_callable=AsyncMock, return_value=50.0)
@patch("scripts.seed_prices.store_signal_snapshot", new_callable=AsyncMock)
@patch("scripts.seed_prices.fetch_prices", new_callable=AsyncMock)
@patch("scripts.seed_prices.ensure_stock_exists", new_callable=AsyncMock)
async def test_seed_ticker_generates_recommendation(
    mock_ensure, mock_fetch, mock_store_signal, mock_price
):
    """seed_ticker should generate a recommendation (but not persist it)."""
    mock_fetch.return_value = _make_price_df(300)
    db = AsyncMock()

    result = await seed_ticker("TSLA", "2y", db)

    assert result["status"] == "ok"
    assert "action" in result
    assert "confidence" in result


# ---------------------------------------------------------------------------
# Default tickers
# ---------------------------------------------------------------------------


def test_default_tickers_not_empty():
    """DEFAULT_TICKERS should contain at least a few well-known tickers."""
    assert len(DEFAULT_TICKERS) >= 5
    assert "AAPL" in DEFAULT_TICKERS
    assert "MSFT" in DEFAULT_TICKERS
