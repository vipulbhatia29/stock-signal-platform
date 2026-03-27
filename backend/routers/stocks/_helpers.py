"""Shared helpers for stock sub-routers."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.stock import Stock


async def require_stock(ticker: str, db: AsyncSession) -> Stock:
    """Look up a stock by ticker, raising 404 if not found.

    This is a helper used by multiple endpoints to validate that a
    ticker exists in our database before proceeding.

    Args:
        ticker: Stock ticker symbol (case-insensitive).
        db: Async database session.

    Returns:
        The Stock ORM object.

    Raises:
        HTTPException: 404 if the ticker doesn't exist.
    """
    result = await db.execute(select(Stock).where(Stock.ticker == ticker.upper()))
    stock = result.scalar_one_or_none()

    if stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stock '{ticker.upper()}' not found. "
            "Make sure the ticker is correct and has been added to the system.",
        )

    return stock
