"""Seed fundamentals, analyst data, and earnings for stocks in the database.

Fetches fundamental metrics (P/E, PEG, FCF yield, Piotroski F-Score),
analyst target prices, and quarterly earnings history via yfinance.
Persists enriched data to the stocks table and earnings_snapshots table.

All operations are idempotent — earnings use ON CONFLICT DO UPDATE,
stock fields are overwritten with latest data.

Usage:
    # Seed a few tickers (quick test)
    uv run python -m scripts.seed_fundamentals --tickers AAPL MSFT GOOGL

    # Seed all active stocks in the database
    uv run python -m scripts.seed_fundamentals --universe

    # Dry run — show what would be fetched
    uv run python -m scripts.seed_fundamentals --universe --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.stock import Stock
from backend.tools.fundamentals import (
    fetch_analyst_data,
    fetch_earnings_history,
    fetch_fundamentals,
    persist_earnings_snapshots,
    persist_enriched_fundamentals,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limit: pause between yfinance calls to avoid getting blocked
RATE_LIMIT_SECONDS = 0.5


async def get_active_tickers(db: AsyncSession) -> list[str]:
    """Get all active tickers from the stocks table.

    Args:
        db: Async database session.

    Returns:
        Sorted list of ticker symbols.
    """
    result = await db.execute(
        select(Stock.ticker).where(Stock.is_active.is_(True)).order_by(Stock.ticker)
    )
    return [row[0] for row in result.all()]


async def seed_fundamentals_for_ticker(
    ticker: str, db: AsyncSession
) -> dict[str, str | int | None]:
    """Fetch and persist fundamentals, analyst data, and earnings for one ticker.

    Args:
        ticker: Stock symbol.
        db: Async database session.

    Returns:
        Summary dict with ticker, status, and counts.
    """
    result: dict[str, str | int | None] = {"ticker": ticker, "status": "ok"}

    try:
        # Step 1: Fetch fundamentals (sync — yfinance call)
        fundamentals = fetch_fundamentals(ticker)
        result["piotroski"] = fundamentals.piotroski_score

        # Step 2: Fetch analyst data (sync — yfinance call)
        analyst_data = fetch_analyst_data(ticker)

        # Step 3: Persist to Stock model
        stock_result = await db.execute(select(Stock).where(Stock.ticker == ticker))
        stock = stock_result.scalar_one_or_none()
        if stock:
            await persist_enriched_fundamentals(stock, fundamentals, analyst_data, db)

        # Step 4: Fetch and persist earnings history
        earnings = fetch_earnings_history(ticker)
        earnings_count = await persist_earnings_snapshots(ticker, earnings, db)
        result["earnings"] = earnings_count

        await db.commit()

    except Exception as e:
        logger.error("Failed to seed fundamentals for %s: %s", ticker, e)
        await db.rollback()
        result["status"] = "error"
        result["error"] = str(e)

    return result


async def main(
    tickers: list[str] | None = None,
    use_universe: bool = False,
    dry_run: bool = False,
) -> None:
    """Entry point: seed fundamentals for the given tickers.

    Args:
        tickers: Explicit list of tickers.
        use_universe: If True, seed all active stocks.
        dry_run: If True, just log what would happen.
    """
    async with async_session_factory() as db:
        if use_universe:
            ticker_list = await get_active_tickers(db)
            if not ticker_list:
                logger.warning("No active stocks found in database.")
                return
            logger.info("Seeding fundamentals for %d stocks", len(ticker_list))
        elif tickers:
            ticker_list = [t.upper() for t in tickers]
            logger.info("Seeding fundamentals for %d tickers: %s", len(ticker_list), ticker_list)
        else:
            logger.error("Specify --tickers or --universe")
            return

        if dry_run:
            logger.info("[DRY RUN] Would seed fundamentals for %d tickers", len(ticker_list))
            for t in ticker_list[:10]:
                logger.info("  %s", t)
            if len(ticker_list) > 10:
                logger.info("  ... and %d more", len(ticker_list) - 10)
            return

        results: list[dict] = []
        total = len(ticker_list)

        for i, ticker in enumerate(ticker_list, 1):
            logger.info("[%d/%d] Seeding fundamentals for %s...", i, total, ticker)
            start = time.time()

            r = await seed_fundamentals_for_ticker(ticker, db)
            elapsed = time.time() - start

            if r["status"] == "ok":
                logger.info(
                    "[%d/%d] %s: piotroski=%s, earnings=%s — %.1fs",
                    i,
                    total,
                    ticker,
                    r.get("piotroski", "N/A"),
                    r.get("earnings", 0),
                    elapsed,
                )
            else:
                logger.error(
                    "[%d/%d] %s: FAILED — %s (%.1fs)",
                    i,
                    total,
                    ticker,
                    r.get("error", "unknown"),
                    elapsed,
                )

            results.append(r)

            if i < total:
                await asyncio.sleep(RATE_LIMIT_SECONDS)

        ok_count = sum(1 for r in results if r["status"] == "ok")
        err_count = sum(1 for r in results if r["status"] == "error")
        logger.info(
            "Fundamentals seed complete: %d succeeded, %d failed out of %d",
            ok_count,
            err_count,
            total,
        )

        if err_count > 0:
            logger.warning("Failed tickers:")
            for r in results:
                if r["status"] == "error":
                    logger.warning("  %s: %s", r["ticker"], r.get("error", "unknown"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed stock fundamentals and earnings")
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific tickers to seed (e.g., AAPL MSFT GOOGL)",
    )
    parser.add_argument(
        "--universe",
        action="store_true",
        help="Seed all active stocks in the database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched without writing",
    )
    args = parser.parse_args()
    asyncio.run(main(tickers=args.tickers, use_universe=args.universe, dry_run=args.dry_run))
