"""Canonical ticker universe — single source of truth for referenced tickers."""

from __future__ import annotations

import logging

from sqlalchemy import union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.models.index import StockIndexMembership
from backend.models.portfolio import Position
from backend.models.stock import Watchlist

logger = logging.getLogger(__name__)


async def get_all_referenced_tickers(db: AsyncSession) -> list[str]:
    """All tickers the system actively cares about (deduped, sorted).

    Union of:
    - Current index members (removed_date IS NULL)
    - All watchlist tickers (across all users)
    - Portfolio positions with shares > 0 (across all users)

    Args:
        db: Async database session.

    Returns:
        Sorted list of unique ticker symbols.
    """
    stmt = union(
        select(StockIndexMembership.ticker).where(StockIndexMembership.removed_date.is_(None)),
        select(Watchlist.ticker),
        select(Position.ticker).where(Position.shares > 0),
    )
    result = await db.execute(select(stmt.subquery().c.ticker).order_by("ticker"))
    return [row[0] for row in result.all()]
