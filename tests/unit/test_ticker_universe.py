"""Unit tests for the canonical ticker universe query."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.ticker_universe import get_all_referenced_tickers


def _make_db(rows: list[tuple[str, ...]]) -> AsyncMock:
    """Create a mock AsyncSession whose execute().all() returns *rows*."""
    db = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    db.execute.return_value = result
    return db


@pytest.mark.asyncio
async def test_returns_deduped_sorted_union() -> None:
    """Tickers from all three sources are combined, deduped, and sorted."""
    db = _make_db([("AAPL",), ("GOOG",), ("MSFT",), ("SPY",), ("TSLA",)])

    result = await get_all_referenced_tickers(db)

    assert result == ["AAPL", "GOOG", "MSFT", "SPY", "TSLA"]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_result_returns_empty_list() -> None:
    """When no tickers exist in any source, an empty list is returned."""
    db = _make_db([])

    result = await get_all_referenced_tickers(db)

    assert result == []
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_execute_call() -> None:
    """Function issues a single DB execute (SQL UNION, not 3 separate queries)."""
    db = _make_db([("AAPL",), ("TSLA",)])

    await get_all_referenced_tickers(db)

    assert db.execute.await_count == 1
