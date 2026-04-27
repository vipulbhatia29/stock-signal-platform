"""Watchlist CRUD service.

Extracts watchlist query and mutation logic (previously inline in
routers/stocks.py) into a dedicated service layer.

Public API:
  - get_watchlist(): fetch user's watchlist with joined prices/signals
  - add_to_watchlist(): add a ticker, raise DuplicateWatchlistError if exists
  - remove_from_watchlist(): delete entry, raise StockNotFoundError if missing
  - acknowledge_price(): set price_acknowledged_at timestamp
  - get_watchlist_tickers(): return bare ticker list for a user (batch ops)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.services.exceptions import (
    DuplicateWatchlistError,
    IngestFailedError,
    IngestInProgressError,
    StockNotFoundError,
)
from backend.services.ingest_lock import acquire_ingest_lock, release_ingest_lock
from backend.services.pipelines import ingest_ticker

logger = logging.getLogger(__name__)

MAX_WATCHLIST_SIZE = 100


async def get_watchlist(user_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Fetch the user's watchlist with latest price, signal data, and recommendation.

    Joins Watchlist → Stock, plus the most recent SignalSnapshot and
    StockPrice per ticker (via row_number window subqueries).

    Args:
        user_id: The authenticated user's UUID.
        db: Async database session.

    Returns:
        List of dicts matching WatchlistItemResponse shape.
    """
    # Subquery: latest signal snapshot per ticker
    latest_signal = (
        select(
            SignalSnapshot.ticker.label("sig_ticker"),
            SignalSnapshot.composite_score.label("composite_score"),
            SignalSnapshot.change_pct.label("change_pct"),
            SignalSnapshot.macd_signal_label.label("macd_signal_label"),
            SignalSnapshot.rsi_value.label("rsi_value"),
            func.row_number()
            .over(
                partition_by=SignalSnapshot.ticker,
                order_by=SignalSnapshot.computed_at.desc(),
            )
            .label("rn"),
        )
    ).subquery("latest_signal")

    # Subquery: latest price per ticker
    latest_price = (
        select(
            StockPrice.ticker.label("price_ticker"),
            StockPrice.adj_close.label("current_price"),
            StockPrice.time.label("price_updated_at"),
            func.row_number()
            .over(
                partition_by=StockPrice.ticker,
                order_by=StockPrice.time.desc(),
            )
            .label("rn"),
        )
    ).subquery("latest_price")

    # Join Watchlist + Stock + latest signal + latest price
    result = await db.execute(
        select(
            Watchlist,
            Stock,
            latest_signal.c.composite_score,
            latest_price.c.current_price,
            latest_price.c.price_updated_at,
            latest_signal.c.change_pct,
            latest_signal.c.macd_signal_label,
            latest_signal.c.rsi_value,
        )
        .join(Stock, Watchlist.ticker == Stock.ticker)
        .outerjoin(
            latest_signal,
            (latest_signal.c.sig_ticker == Watchlist.ticker) & (latest_signal.c.rn == 1),
        )
        .outerjoin(
            latest_price,
            (latest_price.c.price_ticker == Watchlist.ticker) & (latest_price.c.rn == 1),
        )
        .where(Watchlist.user_id == user_id)
        .order_by(Watchlist.added_at.desc())
    )
    rows = result.all()

    def _derive_recommendation(score: float | None) -> str | None:
        """Derive BUY/WATCH/AVOID from composite_score (0-10 scale)."""
        if score is None:
            return None
        if score >= 8:
            return "BUY"
        if score >= 5:
            return "WATCH"
        return "AVOID"

    return [
        {
            "id": watchlist.id,
            "ticker": watchlist.ticker,
            "name": stock.name,
            "sector": stock.sector,
            "composite_score": composite_score,
            "added_at": watchlist.added_at,
            "current_price": float(current_price) if current_price is not None else None,
            "price_updated_at": price_updated_at,
            "price_acknowledged_at": watchlist.price_acknowledged_at,
            "change_pct": float(change_pct) if change_pct is not None else None,
            "macd_signal_label": macd_signal_label,
            "rsi_value": float(rsi_value) if rsi_value is not None else None,
            "recommendation": _derive_recommendation(composite_score),
        }
        for (
            watchlist,
            stock,
            composite_score,
            current_price,
            price_updated_at,
            change_pct,
            macd_signal_label,
            rsi_value,
        ) in rows
    ]


async def add_to_watchlist(
    user_id: uuid.UUID,
    ticker: str,
    db: AsyncSession,
) -> dict:
    """Add a ticker to the user's watchlist, triggering auto-ingest if needed.

    Ordering: duplicate → size → ingest (if enabled) → insert.

    If ``settings.WATCHLIST_AUTO_INGEST`` is True (default) and the stock does
    not yet exist in the DB, the full ingest pipeline is run inline so the
    ticker is available immediately after the call returns.

    Args:
        user_id: The authenticated user's UUID.
        ticker: Stock ticker symbol (case-insensitive, uppercased internally).
        db: Async database session.

    Returns:
        Dict matching WatchlistItemResponse shape.

    Raises:
        DuplicateWatchlistError: If the ticker is already on the watchlist.
        ValueError: If the watchlist is at the size limit.
        IngestInProgressError: If another caller is already ingesting the ticker.
        StockNotFoundError: If the ticker is invalid / ingest fails.
    """
    ticker = ticker.upper().strip()

    # 1. Check for duplicate first — avoids wasted ingest work
    existing = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.ticker == ticker,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise DuplicateWatchlistError(ticker)

    # 2. Check watchlist size limit
    count_result = await db.execute(
        select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id)
    )
    watchlist_count = count_result.scalar_one()
    if watchlist_count >= MAX_WATCHLIST_SIZE:
        msg = f"Watchlist is full (maximum {MAX_WATCHLIST_SIZE} tickers)"
        raise ValueError(msg)

    # 3. Auto-ingest if feature flag is on and stock not yet in DB
    if settings.WATCHLIST_AUTO_INGEST:
        stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
        stock = stock_result.scalar_one_or_none()

        if stock is None:
            if not await acquire_ingest_lock(ticker):
                raise IngestInProgressError(ticker)
            try:
                await ingest_ticker(ticker, db, user_id=str(user_id))
            except IngestFailedError as exc:
                logger.warning("Ingest failed for %s — returning StockNotFoundError", ticker)
                raise StockNotFoundError(ticker) from exc
            finally:
                await release_ingest_lock(ticker)

            # Re-fetch after ingest
            stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
            stock = stock_result.scalar_one_or_none()
            if stock is None:
                raise StockNotFoundError(ticker)
    else:
        # Feature flag off — original behaviour: 404 if stock missing
        stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
        stock = stock_result.scalar_one_or_none()
        if stock is None:
            raise StockNotFoundError(ticker)

    # 4. Create the watchlist entry
    entry = Watchlist(user_id=user_id, ticker=ticker)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {
        "id": entry.id,
        "ticker": entry.ticker,
        "name": stock.name,
        "sector": stock.sector,
        "added_at": entry.added_at,
    }


async def remove_from_watchlist(
    user_id: uuid.UUID,
    ticker: str,
    db: AsyncSession,
) -> None:
    """Remove a ticker from the user's watchlist.

    Args:
        user_id: The authenticated user's UUID.
        ticker: Stock ticker symbol (case-insensitive, uppercased internally).
        db: Async database session.

    Raises:
        StockNotFoundError: If the ticker is not in the user's watchlist.
    """
    ticker = ticker.upper()

    result = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.ticker == ticker,
        )
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise StockNotFoundError(ticker)

    await db.execute(
        delete(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.ticker == ticker,
        )
    )
    await db.commit()


async def acknowledge_price(
    user_id: uuid.UUID,
    ticker: str,
    db: AsyncSession,
) -> dict:
    """Set price_acknowledged_at to now for a watchlist entry.

    Clears the stale-data amber indicator in the UI until a newer
    price arrives.

    Args:
        user_id: The authenticated user's UUID.
        ticker: Stock ticker symbol (case-insensitive, uppercased internally).
        db: Async database session.

    Returns:
        Dict matching WatchlistItemResponse shape.

    Raises:
        StockNotFoundError: If the ticker is not in the user's watchlist.
    """
    ticker = ticker.upper()

    result = await db.execute(
        select(Watchlist).where(
            Watchlist.user_id == user_id,
            Watchlist.ticker == ticker,
        )
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        raise StockNotFoundError(ticker)

    entry.price_acknowledged_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(entry)
    logger.info("Acknowledged stale price for %s (user=%s)", ticker, user_id)

    # Fetch stock info for full response shape
    stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
    stock = stock_result.scalar_one()

    return {
        "id": entry.id,
        "ticker": entry.ticker,
        "name": stock.name,
        "sector": stock.sector,
        "added_at": entry.added_at,
        "price_acknowledged_at": entry.price_acknowledged_at,
    }


async def get_watchlist_tickers(user_id: uuid.UUID, db: AsyncSession) -> list[str]:
    """Return bare ticker list for a user's watchlist.

    Useful for batch operations (e.g., refresh-all, bulk ingest).

    Args:
        user_id: The authenticated user's UUID.
        db: Async database session.

    Returns:
        List of ticker strings.
    """
    result = await db.execute(select(Watchlist.ticker).where(Watchlist.user_id == user_id))
    return [row[0] for row in result.all()]
