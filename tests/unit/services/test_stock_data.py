"""Unit tests for backend.services.stock_data."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.stock_data import ensure_stock_exists, get_latest_price

# ─────────────────────────────────────────────────────────────────────────────
# ensure_stock_exists
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_stock_exists_returns_existing() -> None:
    """When a Stock record already exists, return it without calling yfinance."""
    mock_stock = MagicMock()
    mock_stock.ticker = "AAPL"
    mock_stock.name = "Apple Inc."

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_stock

    db = AsyncMock()
    db.execute.return_value = mock_result

    stock = await ensure_stock_exists("AAPL", db)

    assert stock.ticker == "AAPL"
    # Should NOT have called commit (no new record created)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_stock_exists_creates_when_missing() -> None:
    """When no Stock record exists, create one using yfinance info."""
    # First call: SELECT returns None (stock doesn't exist)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = mock_result

    fake_info = {
        "regularMarketPrice": 150.0,
        "shortName": "Apple Inc.",
        "exchange": "NMS",
        "sector": "Technology",
        "industry": "Consumer Electronics",
    }

    with patch(
        "backend.services.stock_data._get_ticker_info",
        return_value=fake_info,
    ):
        await ensure_stock_exists("AAPL", db)

    # Should have added and committed the new stock
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()

    # The created Stock object should have the right ticker
    created_stock = db.add.call_args[0][0]
    assert created_stock.ticker == "AAPL"
    assert created_stock.name == "Apple Inc."
    assert created_stock.sector == "Technology"


# ─────────────────────────────────────────────────────────────────────────────
# get_latest_price
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_latest_price_returns_most_recent() -> None:
    """Returns the latest adj_close as a float."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = Decimal("150.25")

    db = AsyncMock()
    db.execute.return_value = mock_result

    price = await get_latest_price("AAPL", db)

    assert price == 150.25
    assert isinstance(price, float)


@pytest.mark.asyncio
async def test_get_latest_price_returns_none_when_no_data() -> None:
    """Returns None when no price rows exist for the ticker."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.return_value = mock_result

    price = await get_latest_price("NONEXISTENT", db)

    assert price is None
