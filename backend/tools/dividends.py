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
        results.append(
            {
                "ticker": ticker,
                "ex_date": date.to_pydatetime().replace(tzinfo=timezone.utc),
                "amount": Decimal(str(round(float(amount), 4))),
            }
        )

    logger.info("Fetched %d dividends for %s", len(results), ticker)
    return results


async def store_dividends(ticker: str, dividends: list[dict], db: AsyncSession) -> int:
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
        stmt = stmt.on_conflict_do_nothing(constraint="dividend_payments_pkey")
        result = await db.execute(stmt)
        if result.rowcount > 0:
            inserted += 1

    await db.commit()
    logger.info("Stored %d new dividends for %s", inserted, ticker)
    return inserted


async def get_dividends(ticker: str, db: AsyncSession, limit: int = 100) -> list[DividendPayment]:
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


async def get_dividend_summary(
    ticker: str, db: AsyncSession, current_price: float | None = None
) -> dict:
    """Compute dividend summary stats for a ticker.

    Args:
        ticker: Stock symbol.
        db: Async SQLAlchemy session.
        current_price: Latest stock price for yield calculation.

    Returns:
        Dict with keys: ticker, total_received, annual_dividends,
        dividend_yield, last_ex_date, payment_count, history.
    """
    dividends = await get_dividends(ticker, db, limit=200)

    if not dividends:
        return {
            "ticker": ticker.upper().strip(),
            "total_received": 0.0,
            "annual_dividends": 0.0,
            "dividend_yield": None,
            "last_ex_date": None,
            "payment_count": 0,
            "history": [],
        }

    total = sum(float(d.amount) for d in dividends)

    # Annual dividends: sum of payments in the last 12 months
    now = datetime.now(timezone.utc)
    one_year_ago = now.replace(year=now.year - 1)
    annual = sum(float(d.amount) for d in dividends if d.ex_date >= one_year_ago)

    # Dividend yield = annual dividends / current price
    div_yield = None
    if current_price and current_price > 0 and annual > 0:
        div_yield = round((annual / current_price) * 100, 2)

    return {
        "ticker": ticker.upper().strip(),
        "total_received": round(total, 4),
        "annual_dividends": round(annual, 4),
        "dividend_yield": div_yield,
        "last_ex_date": dividends[0].ex_date,
        "payment_count": len(dividends),
        "history": dividends,
    }
