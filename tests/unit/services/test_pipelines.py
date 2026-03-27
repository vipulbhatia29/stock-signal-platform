"""Tests for backend.services.pipelines — ingest pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.services.exceptions import IngestFailedError
from backend.services.pipelines import ingest_ticker


@pytest.fixture()
def mock_db():
    """Create a mock async DB session."""
    db = AsyncMock()
    return db


@pytest.fixture()
def mock_stock():
    """Create a mock Stock ORM object."""
    stock = MagicMock()
    stock.name = "Apple Inc."
    stock.last_fetched_at = None  # new stock
    return stock


@pytest.fixture()
def mock_signal_result():
    """Create a mock SignalResult."""
    sr = MagicMock()
    sr.composite_score = 7.5
    sr.ticker = "AAPL"
    return sr


@pytest.fixture()
def mock_fundamentals():
    """Create a mock FundamentalResult."""
    f = MagicMock()
    f.piotroski_score = 6
    return f


@pytest.fixture()
def _patch_all(mock_stock, mock_signal_result, mock_fundamentals):
    """Patch all service calls used by ingest_ticker."""
    full_df = pd.DataFrame(
        {"Close": [100.0, 101.0, 102.0]},
        index=pd.date_range("2024-01-01", periods=3),
    )
    delta_df = pd.DataFrame(
        {"Close": [102.0]},
        index=pd.date_range("2024-01-03", periods=1),
    )

    patches = {
        "ensure_stock_exists": AsyncMock(return_value=mock_stock),
        "fetch_prices_delta": AsyncMock(return_value=delta_df),
        "load_prices_df": AsyncMock(return_value=full_df),
        "fetch_fundamentals": MagicMock(return_value=mock_fundamentals),
        "fetch_analyst_data": MagicMock(return_value={"analyst_target_mean": 180.0}),
        "fetch_earnings_history": MagicMock(return_value=[]),
        "persist_enriched_fundamentals": AsyncMock(),
        "persist_earnings_snapshots": AsyncMock(),
        "compute_signals": MagicMock(return_value=mock_signal_result),
        "store_signal_snapshot": AsyncMock(),
        "update_last_fetched_at": AsyncMock(),
    }

    base = "backend.services.pipelines"
    with (
        patch(f"{base}.ensure_stock_exists", patches["ensure_stock_exists"]),
        patch(f"{base}.fetch_prices_delta", patches["fetch_prices_delta"]),
        patch(f"{base}.load_prices_df", patches["load_prices_df"]),
        patch(f"{base}.fetch_fundamentals", patches["fetch_fundamentals"]),
        patch(f"{base}.fetch_analyst_data", patches["fetch_analyst_data"]),
        patch(f"{base}.fetch_earnings_history", patches["fetch_earnings_history"]),
        patch(f"{base}.persist_enriched_fundamentals", patches["persist_enriched_fundamentals"]),
        patch(f"{base}.persist_earnings_snapshots", patches["persist_earnings_snapshots"]),
        patch(f"{base}.compute_signals", patches["compute_signals"]),
        patch(f"{base}.store_signal_snapshot", patches["store_signal_snapshot"]),
        patch(f"{base}.update_last_fetched_at", patches["update_last_fetched_at"]),
    ):
        yield patches


@pytest.mark.asyncio()
async def test_ingest_ticker_full_pipeline(mock_db, _patch_all):
    """All service calls execute in the correct order for a full ingest."""
    patches = _patch_all

    result = await ingest_ticker("AAPL", mock_db)

    # Verify each step was called
    patches["ensure_stock_exists"].assert_awaited_once_with("AAPL", mock_db)
    patches["fetch_prices_delta"].assert_awaited_once_with("AAPL", mock_db)
    patches["load_prices_df"].assert_awaited_once_with("AAPL", mock_db)
    patches["persist_enriched_fundamentals"].assert_awaited_once()
    patches["persist_earnings_snapshots"].assert_awaited_once()
    patches["compute_signals"].assert_called_once()
    patches["store_signal_snapshot"].assert_awaited_once()
    patches["update_last_fetched_at"].assert_awaited_once_with("AAPL", mock_db)

    # Verify result shape
    assert result["ticker"] == "AAPL"
    assert result["stock_name"] == "Apple Inc."
    assert result["rows_fetched"] == 1
    assert result["composite_score"] == 7.5
    assert result["is_new"] is True
    assert result["recommendation"] is None  # no user_id provided


@pytest.mark.asyncio()
async def test_ingest_ticker_stock_lookup_fails(mock_db):
    """IngestFailedError raised when ensure_stock_exists fails."""
    base = "backend.services.pipelines"
    with patch(f"{base}.ensure_stock_exists", AsyncMock(side_effect=ValueError("Not found"))):
        with pytest.raises(IngestFailedError) as exc_info:
            await ingest_ticker("FAKE", mock_db)
        assert exc_info.value.ticker == "FAKE"
        assert exc_info.value.step == "ensure_stock_exists"


@pytest.mark.asyncio()
async def test_ingest_ticker_price_fetch_fails(mock_db, mock_stock):
    """IngestFailedError raised when fetch_prices_delta fails."""
    base = "backend.services.pipelines"
    with (
        patch(f"{base}.ensure_stock_exists", AsyncMock(return_value=mock_stock)),
        patch(f"{base}.fetch_prices_delta", AsyncMock(side_effect=ValueError("No data"))),
    ):
        with pytest.raises(IngestFailedError) as exc_info:
            await ingest_ticker("AAPL", mock_db)
        assert exc_info.value.ticker == "AAPL"
        assert exc_info.value.step == "fetch_prices_delta"


@pytest.mark.asyncio()
async def test_ingest_ticker_skips_recommendation_without_user(mock_db, _patch_all):
    """Recommendation is None when no user_id is provided."""
    result = await ingest_ticker("AAPL", mock_db, user_id=None)

    assert result["recommendation"] is None


@pytest.mark.asyncio()
async def test_ingest_ticker_skips_signals_when_no_data(mock_db, mock_stock, mock_fundamentals):
    """Signals and recommendation are skipped when price history is empty."""
    empty_df = pd.DataFrame()
    delta_df = pd.DataFrame()

    base = "backend.services.pipelines"
    with (
        patch(f"{base}.ensure_stock_exists", AsyncMock(return_value=mock_stock)),
        patch(f"{base}.fetch_prices_delta", AsyncMock(return_value=delta_df)),
        patch(f"{base}.load_prices_df", AsyncMock(return_value=empty_df)),
        patch(f"{base}.fetch_fundamentals", MagicMock(return_value=mock_fundamentals)),
        patch(f"{base}.fetch_analyst_data", MagicMock(return_value={})),
        patch(f"{base}.fetch_earnings_history", MagicMock(return_value=[])),
        patch(f"{base}.persist_enriched_fundamentals", AsyncMock()),
        patch(f"{base}.persist_earnings_snapshots", AsyncMock()),
        patch(f"{base}.compute_signals", MagicMock()) as mock_compute,
        patch(f"{base}.store_signal_snapshot", AsyncMock()) as mock_store,
        patch(f"{base}.update_last_fetched_at", AsyncMock()),
    ):
        result = await ingest_ticker("AAPL", mock_db)

    assert result["composite_score"] is None
    assert result["recommendation"] is None
    mock_compute.assert_not_called()
    mock_store.assert_not_called()


@pytest.mark.asyncio()
async def test_ingest_ticker_uppercases_ticker(mock_db, _patch_all):
    """Ticker is uppercased before processing."""
    patches = _patch_all

    result = await ingest_ticker("aapl", mock_db)

    assert result["ticker"] == "AAPL"
    patches["ensure_stock_exists"].assert_awaited_once_with("AAPL", mock_db)


@pytest.mark.asyncio()
async def test_ingest_ticker_existing_stock_not_new(mock_db, _patch_all, mock_stock):
    """is_new is False when stock has a last_fetched_at timestamp."""
    from datetime import datetime, timezone

    mock_stock.last_fetched_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    result = await ingest_ticker("AAPL", mock_db)

    assert result["is_new"] is False
