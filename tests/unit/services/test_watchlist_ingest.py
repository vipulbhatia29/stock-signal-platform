"""Unit tests for the auto-ingest behaviour added to backend.services.watchlist (Spec C.6).

Tests focus on the ingest path: lock acquisition, ingest_ticker delegation,
error mapping, feature flag, and lock release guarantees.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.exceptions import (
    IngestFailedError,
    IngestInProgressError,
    StockNotFoundError,
)
from backend.services.watchlist import add_to_watchlist

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> AsyncMock:
    """Create a mock AsyncSession with execute/commit/refresh/add."""
    session = AsyncMock()
    session.add = MagicMock()
    return session


def _make_stock(ticker: str = "NVDA") -> MagicMock:
    """Create a mock Stock ORM object."""
    stock = MagicMock()
    stock.ticker = ticker
    stock.name = f"{ticker} Corp"
    stock.sector = "Technology"
    return stock


def _dup_result(exists: bool = False) -> MagicMock:
    """Mock DB result for duplicate watchlist check."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock() if exists else None
    return result


def _count_result(count: int = 0) -> MagicMock:
    """Mock DB result for watchlist size count."""
    result = MagicMock()
    result.scalar_one.return_value = count
    return result


def _stock_result(stock: MagicMock | None) -> MagicMock:
    """Mock DB result for Stock lookup."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = stock
    return result


# ---------------------------------------------------------------------------
# Auto-ingest happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_unknown_ticker_triggers_ingest() -> None:
    """ingest_ticker is called when the stock is not in the DB and auto-ingest is on."""
    user_id = uuid.uuid4()
    db = _make_session()
    stock = _make_stock("NVDA")

    # DB call order: dup check → size count → stock lookup (None) → stock lookup after ingest
    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(0),
        _stock_result(None),  # stock missing → triggers ingest
        _stock_result(stock),  # re-fetch after ingest succeeds
    ]

    mock_ingest = AsyncMock(return_value={"ticker": "NVDA"})

    with (
        patch("backend.services.watchlist.acquire_ingest_lock", return_value=True),
        patch("backend.services.watchlist.release_ingest_lock") as mock_release,
        patch("backend.services.watchlist.ingest_ticker", mock_ingest),
    ):
        result = await add_to_watchlist(user_id, "NVDA", db)

    mock_ingest.assert_awaited_once_with("NVDA", db, user_id=str(user_id))
    mock_release.assert_awaited_once_with("NVDA")
    assert result["ticker"] == "NVDA"


@pytest.mark.asyncio
async def test_add_known_ticker_skips_ingest() -> None:
    """ingest_ticker is NOT called when the stock already exists in the DB."""
    user_id = uuid.uuid4()
    db = _make_session()
    stock = _make_stock("AAPL")

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(3),
        _stock_result(stock),  # stock exists — no ingest needed
    ]

    mock_ingest = AsyncMock()

    with patch("backend.services.watchlist.ingest_ticker", mock_ingest):
        result = await add_to_watchlist(user_id, "AAPL", db)

    mock_ingest.assert_not_awaited()
    assert result["ticker"] == "AAPL"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_failure_raises_stock_not_found() -> None:
    """IngestFailedError from ingest_ticker is translated to StockNotFoundError (404)."""
    user_id = uuid.uuid4()
    db = _make_session()

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(0),
        _stock_result(None),  # stock missing
    ]

    mock_ingest = AsyncMock(side_effect=IngestFailedError("FAKE", "price_fetch"))

    with (
        patch("backend.services.watchlist.acquire_ingest_lock", return_value=True),
        patch("backend.services.watchlist.release_ingest_lock"),
        patch("backend.services.watchlist.ingest_ticker", mock_ingest),
    ):
        with pytest.raises(StockNotFoundError):
            await add_to_watchlist(user_id, "FAKE", db)


@pytest.mark.asyncio
async def test_concurrent_add_raises_ingest_in_progress() -> None:
    """IngestInProgressError raised when the Redis lock cannot be acquired."""
    user_id = uuid.uuid4()
    db = _make_session()

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(0),
        _stock_result(None),  # stock missing → tries to acquire lock
    ]

    with (
        patch("backend.services.watchlist.acquire_ingest_lock", return_value=False),
        patch("backend.services.watchlist.ingest_ticker") as mock_ingest,
    ):
        with pytest.raises(IngestInProgressError):
            await add_to_watchlist(user_id, "TSLA", db)

    mock_ingest.assert_not_awaited()


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feature_flag_disabled_skips_ingest() -> None:
    """When WATCHLIST_AUTO_INGEST=False, missing tickers raise StockNotFoundError immediately."""
    user_id = uuid.uuid4()
    db = _make_session()

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(0),
        _stock_result(None),  # stock missing
    ]

    mock_ingest = AsyncMock()

    with (
        patch("backend.services.watchlist.settings") as mock_settings,
        patch("backend.services.watchlist.ingest_ticker", mock_ingest),
    ):
        mock_settings.WATCHLIST_AUTO_INGEST = False
        with pytest.raises(StockNotFoundError):
            await add_to_watchlist(user_id, "FAKE", db)

    mock_ingest.assert_not_awaited()


# ---------------------------------------------------------------------------
# Lock release guarantees
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_released_on_success() -> None:
    """release_ingest_lock is called after a successful ingest."""
    user_id = uuid.uuid4()
    db = _make_session()
    stock = _make_stock("MSFT")

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(1),
        _stock_result(None),  # missing → ingest
        _stock_result(stock),  # re-fetch
    ]

    mock_ingest = AsyncMock(return_value={"ticker": "MSFT"})

    with (
        patch("backend.services.watchlist.acquire_ingest_lock", return_value=True),
        patch("backend.services.watchlist.release_ingest_lock") as mock_release,
        patch("backend.services.watchlist.ingest_ticker", mock_ingest),
    ):
        await add_to_watchlist(user_id, "MSFT", db)

    mock_release.assert_awaited_once_with("MSFT")


@pytest.mark.asyncio
async def test_lock_released_on_failure() -> None:
    """release_ingest_lock is called even when ingest_ticker raises IngestFailedError."""
    user_id = uuid.uuid4()
    db = _make_session()

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(0),
        _stock_result(None),  # missing → ingest
    ]

    mock_ingest = AsyncMock(side_effect=IngestFailedError("BAD", "price_fetch"))

    with (
        patch("backend.services.watchlist.acquire_ingest_lock", return_value=True),
        patch("backend.services.watchlist.release_ingest_lock") as mock_release,
        patch("backend.services.watchlist.ingest_ticker", mock_ingest),
    ):
        with pytest.raises(StockNotFoundError):
            await add_to_watchlist(user_id, "BAD", db)

    mock_release.assert_awaited_once_with("BAD")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_succeeds_but_stock_still_missing_raises_not_found() -> None:
    """StockNotFoundError raised when ingest_ticker completes but Stock row is still absent.

    This guards against a bug in ingest_ticker that silently skips creating the
    Stock row (e.g., ensure_stock_exists failure masked by a try/except).
    """
    user_id = uuid.uuid4()
    db = _make_session()

    db.execute.side_effect = [
        _dup_result(exists=False),
        _count_result(0),
        _stock_result(None),  # stock missing → triggers ingest
        _stock_result(None),  # re-fetch after ingest STILL returns None
    ]

    mock_ingest = AsyncMock(return_value={"ticker": "GHOST"})

    with (
        patch("backend.services.watchlist.acquire_ingest_lock", return_value=True),
        patch("backend.services.watchlist.release_ingest_lock") as mock_release,
        patch("backend.services.watchlist.ingest_ticker", mock_ingest),
    ):
        with pytest.raises(StockNotFoundError):
            await add_to_watchlist(user_id, "GHOST", db)

    mock_ingest.assert_awaited_once()
    mock_release.assert_awaited_once_with("GHOST")
