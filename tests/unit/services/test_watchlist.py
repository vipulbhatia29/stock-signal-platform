"""Unit tests for backend.services.watchlist."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.exceptions import DuplicateWatchlistError, StockNotFoundError
from backend.services.watchlist import (
    add_to_watchlist,
    get_watchlist,
    get_watchlist_tickers,
    remove_from_watchlist,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Create a mock AsyncSession with execute/commit/refresh/add."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _make_stock(
    ticker: str = "AAPL", name: str = "Apple Inc", sector: str = "Technology"
) -> MagicMock:
    """Create a mock Stock ORM object."""
    stock = MagicMock()
    stock.ticker = ticker
    stock.name = name
    stock.sector = sector
    return stock


def _make_watchlist_entry(
    ticker: str = "AAPL",
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a mock Watchlist ORM object."""
    entry = MagicMock()
    entry.id = uuid.uuid4()
    entry.ticker = ticker
    entry.user_id = user_id or uuid.uuid4()
    entry.added_at = datetime.now(timezone.utc)
    entry.price_acknowledged_at = None
    return entry


# ---------------------------------------------------------------------------
# get_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_returns_data() -> None:
    """get_watchlist returns transformed rows from the joined query."""
    user_id = uuid.uuid4()
    db = _make_session()

    # Simulate joined row: (Watchlist, Stock, composite_score, current_price, price_updated_at)
    watchlist_entry = _make_watchlist_entry(ticker="AAPL", user_id=user_id)
    stock = _make_stock()
    now = datetime.now(timezone.utc)
    mock_row = MagicMock()
    mock_row.__iter__ = MagicMock(return_value=iter((watchlist_entry, stock, 8.5, 185.50, now)))

    mock_result = MagicMock()
    mock_result.all.return_value = [
        (watchlist_entry, stock, 8.5, 185.50, now),
    ]
    db.execute.return_value = mock_result

    items = await get_watchlist(user_id, db)

    assert len(items) == 1
    assert items[0]["ticker"] == "AAPL"
    assert items[0]["name"] == "Apple Inc"
    assert items[0]["composite_score"] == 8.5
    assert items[0]["current_price"] == 185.50
    assert items[0]["price_updated_at"] == now


@pytest.mark.asyncio
async def test_get_watchlist_empty() -> None:
    """get_watchlist returns empty list when user has no watchlist entries."""
    db = _make_session()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute.return_value = mock_result

    items = await get_watchlist(uuid.uuid4(), db)

    assert items == []


# ---------------------------------------------------------------------------
# add_to_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_to_watchlist_success() -> None:
    """add_to_watchlist creates entry when stock exists and not a duplicate.

    New execute order (Spec C.6): 1) duplicate check, 2) count, 3) stock lookup.
    When stock already exists in DB, ingest is skipped.
    """
    user_id = uuid.uuid4()
    db = _make_session()
    stock = _make_stock()

    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None  # no duplicate

    count_result = MagicMock()
    count_result.scalar_one.return_value = 5  # under limit

    stock_result = MagicMock()
    stock_result.scalar_one_or_none.return_value = stock  # stock exists — no ingest needed

    db.execute.side_effect = [dup_result, count_result, stock_result]

    result = await add_to_watchlist(user_id, "aapl", db)

    assert result["ticker"] == "AAPL"  # uppercased
    assert result["name"] == "Apple Inc"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_to_watchlist_stock_not_found() -> None:
    """add_to_watchlist raises StockNotFoundError when WATCHLIST_AUTO_INGEST is False.

    With the feature flag disabled, missing tickers still raise StockNotFoundError.
    """
    db = _make_session()

    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None

    count_result = MagicMock()
    count_result.scalar_one.return_value = 0

    stock_result = MagicMock()
    stock_result.scalar_one_or_none.return_value = None  # not found

    db.execute.side_effect = [dup_result, count_result, stock_result]

    with (
        patch("backend.services.watchlist.settings") as mock_settings,
    ):
        mock_settings.WATCHLIST_AUTO_INGEST = False
        with pytest.raises(StockNotFoundError):
            await add_to_watchlist(uuid.uuid4(), "FAKE", db)


@pytest.mark.asyncio
async def test_add_to_watchlist_duplicate() -> None:
    """add_to_watchlist raises DuplicateWatchlistError when already on list.

    Duplicate check happens FIRST in the new order, before size and ingest.
    """
    user_id = uuid.uuid4()
    db = _make_session()

    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = _make_watchlist_entry()  # exists

    db.execute.side_effect = [dup_result]

    with pytest.raises(DuplicateWatchlistError):
        await add_to_watchlist(user_id, "AAPL", db)


@pytest.mark.asyncio
async def test_add_to_watchlist_full() -> None:
    """add_to_watchlist raises ValueError when watchlist is at the size limit."""
    user_id = uuid.uuid4()
    db = _make_session()

    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None  # no duplicate

    count_result = MagicMock()
    count_result.scalar_one.return_value = 100  # at limit

    db.execute.side_effect = [dup_result, count_result]

    with pytest.raises(ValueError, match="full"):
        await add_to_watchlist(user_id, "AAPL", db)


# ---------------------------------------------------------------------------
# remove_from_watchlist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_from_watchlist_success() -> None:
    """remove_from_watchlist deletes the entry when it exists."""
    user_id = uuid.uuid4()
    db = _make_session()

    entry = _make_watchlist_entry(user_id=user_id)
    select_result = MagicMock()
    select_result.scalar_one_or_none.return_value = entry

    delete_result = MagicMock()

    db.execute.side_effect = [select_result, delete_result]

    await remove_from_watchlist(user_id, "aapl", db)

    assert db.execute.await_count == 2  # select + delete
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_from_watchlist_not_found() -> None:
    """remove_from_watchlist raises StockNotFoundError when not on list."""
    db = _make_session()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(StockNotFoundError):
        await remove_from_watchlist(uuid.uuid4(), "AAPL", db)


# ---------------------------------------------------------------------------
# get_watchlist_tickers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_watchlist_tickers() -> None:
    """get_watchlist_tickers returns a flat list of ticker strings."""
    db = _make_session()
    mock_result = MagicMock()
    mock_result.all.return_value = [("AAPL",), ("MSFT",), ("GOOG",)]
    db.execute.return_value = mock_result

    tickers = await get_watchlist_tickers(uuid.uuid4(), db)

    assert tickers == ["AAPL", "MSFT", "GOOG"]
