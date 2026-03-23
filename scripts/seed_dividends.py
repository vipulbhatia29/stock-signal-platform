"""Seed dividend history for stocks in the database.

Fetches full dividend payment history via yfinance and stores in the
dividend_payments table. Uses ON CONFLICT DO NOTHING — fully idempotent,
only new ex_dates are inserted.

Usage:
    # Seed a few tickers (quick test)
    uv run python -m scripts.seed_dividends --tickers AAPL MSFT GOOGL

    # Seed all active stocks in the database
    uv run python -m scripts.seed_dividends --universe

    # Dry run — show what would be fetched
    uv run python -m scripts.seed_dividends --universe --dry-run
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
from backend.tools.dividends import fetch_dividends, store_dividends

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

RATE_LIMIT_SECONDS = 0.3


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


async def main(
    tickers: list[str] | None = None,
    use_universe: bool = False,
    dry_run: bool = False,
) -> None:
    """Entry point: seed dividends for the given tickers.

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
            logger.info("Seeding dividends for %d stocks", len(ticker_list))
        elif tickers:
            ticker_list = [t.upper() for t in tickers]
            logger.info("Seeding dividends for %d tickers: %s", len(ticker_list), ticker_list)
        else:
            logger.error("Specify --tickers or --universe")
            return

        if dry_run:
            logger.info("[DRY RUN] Would seed dividends for %d tickers", len(ticker_list))
            for t in ticker_list[:10]:
                logger.info("  %s", t)
            if len(ticker_list) > 10:
                logger.info("  ... and %d more", len(ticker_list) - 10)
            return

        total = len(ticker_list)
        ok_count = 0
        total_divs = 0

        for i, ticker in enumerate(ticker_list, 1):
            start = time.time()
            try:
                dividends = fetch_dividends(ticker)
                if dividends:
                    inserted = await store_dividends(ticker, dividends, db)
                    total_divs += inserted
                    elapsed = time.time() - start
                    logger.info(
                        "[%d/%d] %s: %d total, %d new — %.1fs",
                        i,
                        total,
                        ticker,
                        len(dividends),
                        inserted,
                        elapsed,
                    )
                else:
                    elapsed = time.time() - start
                    logger.info(
                        "[%d/%d] %s: no dividends — %.1fs",
                        i,
                        total,
                        ticker,
                        elapsed,
                    )
                ok_count += 1
            except Exception as e:
                elapsed = time.time() - start
                logger.error(
                    "[%d/%d] %s: FAILED — %s (%.1fs)",
                    i,
                    total,
                    ticker,
                    e,
                    elapsed,
                )

            if i < total:
                await asyncio.sleep(RATE_LIMIT_SECONDS)

        err_count = total - ok_count
        logger.info(
            "Dividend seed complete: %d succeeded, %d failed, %d new dividends stored",
            ok_count,
            err_count,
            total_divs,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed stock dividend history")
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
