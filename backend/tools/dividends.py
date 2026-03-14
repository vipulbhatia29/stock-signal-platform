"""Dividend data tool: fetch from yfinance and store to TimescaleDB."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.dividend import DividendPayment

logger = logging.getLogger(__name__)


def fetch_dividends(ticker: str) -> list[dict]:
    """Fetch dividend history from yfinance (synchronous).

    Args:
        ticker: Stock symbol (e.g. "AAPL"). Case-insensitive.

    Returns:
        List of dicts with keys: ticker, ex_date (datetime), amount (Decimal).
        Empty list if no dividends or yfinance fails.
    """
    ticker = ticker.upper().strip()
    try:
        t = yf.Ticker(ticker)
        div_series = t.dividends
    except Exception:
        logger.warning("yfinance failed fetching dividends for %s", ticker)
        return []

    if div_series is None or div_series.empty:
        return []

    results = []
    for date, amount in div_series.items():
        results.append({
            "ticker": ticker,
            "ex_date": date.to_pydatetime().replace(tzinfo=timezone.utc),
            "amount": Decimal(str(round(float(amount), 4))),
        })

    logger.info("Fetched %d dividends for %s", len(results), ticker)
    return results


async def store_dividends(
    ticker: str, dividends: list[dict], db: AsyncSession
) -> int:
    """Upsert dividend records into the database.

    Uses ON CONFLICT DO NOTHING since dividend amounts are immutable
    once published. Only new ex_dates are inserted.

    Args:
        ticker: Stock symbol.
        dividends: List of dicts from fetch_dividends().
        db: Async SQLAlchemy session.

    Returns:
        Number of new rows inserted.
    """
    if not dividends:
        return 0

    inserted = 0
    for div in dividends:
        stmt = pg_insert(DividendPayment).values(
            ticker=div["ticker"],
            ex_date=div["ex_date"],
            amount=div["amount"],
        )
        stmt = stmt.on_conflict_do_nothing(
            constraint="dividend_payments_pkey"
        )
        result = await db.execute(stmt)
        if result.rowcount > 0:
            inserted += 1

    await db.commit()
    logger.info("Stored %d new dividends for %s", inserted, ticker)
    return inserted


async def get_dividends(
    ticker: str, db: AsyncSession, limit: int = 100
) -> list[DividendPayment]:
    """Fetch stored dividend history for a ticker.

    Args:
        ticker: Stock symbol.
        db: Async SQLAlchemy session.
        limit: Max records to return (default 100).

    Returns:
        List of DividendPayment rows, ordered by ex_date descending.
    """
    result = await db.execute(
        select(DividendPayment)
        .where(DividendPayment.ticker == ticker.upper().strip())
        .order_by(DividendPayment.ex_date.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
