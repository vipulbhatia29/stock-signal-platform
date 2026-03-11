"""Seed historical prices and compute signals for stocks in the database.

Fetches OHLCV data via yfinance for stocks in the universe (or a custom list),
stores prices in TimescaleDB, computes technical signals, and generates
recommendations.

Usage:
    # Seed a few tickers (quick test)
    uv run python -m scripts.seed_prices --tickers AAPL MSFT GOOGL

    # Seed all S&P 500 stocks in the database (run sync_sp500 first)
    uv run python -m scripts.seed_prices --universe

    # Seed with a shorter lookback period
    uv run python -m scripts.seed_prices --tickers AAPL --period 2y

    # Dry run — show what would be fetched
    uv run python -m scripts.seed_prices --tickers AAPL MSFT --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.index import StockIndexMembership
from backend.models.stock import Stock
from backend.tools.market_data import ensure_stock_exists, fetch_prices, get_latest_price
from backend.tools.recommendations import generate_recommendation
from backend.tools.signals import compute_signals, store_signal_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)

# Rate limit: pause between yfinance calls to avoid getting blocked
RATE_LIMIT_SECONDS = 0.5

# Default tickers for quick testing
DEFAULT_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "JPM", "V", "UNH"]


async def get_universe_tickers(db: AsyncSession) -> list[str]:
    """Get all active tickers in the stock universe from the database.

    Args:
        db: Async database session.

    Returns:
        List of ticker symbols.
    """
    # Subquery: tickers that are current members of any index
    current_members = (
        select(StockIndexMembership.ticker)
        .where(StockIndexMembership.removed_date.is_(None))
        .distinct()
        .subquery()
    )

    result = await db.execute(
        select(Stock.ticker)
        .where(Stock.is_active.is_(True))
        .where(Stock.ticker.in_(select(current_members.c.ticker)))
        .order_by(Stock.ticker)
    )
    return [row[0] for row in result.all()]


async def seed_ticker(
    ticker: str,
    period: str,
    db: AsyncSession,
) -> dict[str, str | float | None]:
    """Fetch prices, compute signals, and generate recommendation for one ticker.

    Args:
        ticker: Stock symbol like "AAPL".
        period: Lookback period for yfinance (e.g., "10y", "2y").
        db: Async database session.

    Returns:
        Dict summarizing what was done for this ticker.
    """
    result: dict[str, str | float | None] = {"ticker": ticker, "status": "ok"}

    try:
        # Step 1: Ensure stock record exists
        await ensure_stock_exists(ticker, db)

        # Step 2: Fetch and store prices
        df = await fetch_prices(ticker, period=period, db=db)
        result["price_rows"] = len(df)

        # Step 3: Compute technical signals
        signals = compute_signals(ticker, df)
        await store_signal_snapshot(signals, db)
        result["composite_score"] = signals.composite_score

        # Step 4: Generate recommendation (computed but not persisted —
        # recommendations require a user_id and are stored per-user via API)
        latest_price = await get_latest_price(ticker, db)
        rec = generate_recommendation(signals, current_price=latest_price)
        result["action"] = rec.action
        result["confidence"] = rec.confidence

    except Exception as e:
        logger.error("Failed to seed %s: %s", ticker, e)
        result["status"] = "error"
        result["error"] = str(e)

    return result


async def main(
    tickers: list[str] | None = None,
    use_universe: bool = False,
    period: str = "10y",
    dry_run: bool = False,
) -> None:
    """Entry point: seed prices and signals for the given tickers.

    Args:
        tickers: Explicit list of tickers to seed.
        use_universe: If True, seed all stocks in the universe (from database).
        period: Lookback period for yfinance.
        dry_run: If True, just log what would happen.
    """
    async with async_session_factory() as db:
        # Determine which tickers to process
        if use_universe:
            ticker_list = await get_universe_tickers(db)
            if not ticker_list:
                logger.warning("No stocks in universe. Run 'python -m scripts.sync_sp500' first.")
                return
            logger.info("Seeding %d universe stocks", len(ticker_list))
        elif tickers:
            ticker_list = [t.upper() for t in tickers]
            logger.info("Seeding %d specified tickers: %s", len(ticker_list), ticker_list)
        else:
            ticker_list = DEFAULT_TICKERS
            logger.info("No tickers specified, using defaults: %s", ticker_list)

        if dry_run:
            logger.info("[DRY RUN] Would seed %d tickers with period=%s", len(ticker_list), period)
            for t in ticker_list:
                logger.info("  %s", t)
            return

        # Process each ticker
        results: list[dict] = []
        total = len(ticker_list)

        for i, ticker in enumerate(ticker_list, 1):
            logger.info("[%d/%d] Seeding %s...", i, total, ticker)
            start = time.time()

            result = await seed_ticker(ticker, period, db)
            elapsed = time.time() - start

            if result["status"] == "ok":
                logger.info(
                    "[%d/%d] %s: %s rows, score=%.1f, action=%s (%s) — %.1fs",
                    i,
                    total,
                    ticker,
                    result.get("price_rows", 0),
                    result.get("composite_score") or 0,
                    result.get("action", "N/A"),
                    result.get("confidence", "N/A"),
                    elapsed,
                )
            else:
                logger.error(
                    "[%d/%d] %s: FAILED — %s (%.1fs)",
                    i,
                    total,
                    ticker,
                    result.get("error", "unknown"),
                    elapsed,
                )

            results.append(result)

            # Rate limit to avoid yfinance throttling
            if i < total:
                await asyncio.sleep(RATE_LIMIT_SECONDS)

        # Summary
        ok_count = sum(1 for r in results if r["status"] == "ok")
        err_count = sum(1 for r in results if r["status"] == "error")
        logger.info("Seed complete: %d succeeded, %d failed out of %d", ok_count, err_count, total)

        if err_count > 0:
            logger.warning("Failed tickers:")
            for r in results:
                if r["status"] == "error":
                    logger.warning("  %s: %s", r["ticker"], r.get("error", "unknown"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed stock prices and compute signals")
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific tickers to seed (e.g., AAPL MSFT GOOGL)",
    )
    parser.add_argument(
        "--universe",
        action="store_true",
        help="Seed all stocks in the S&P 500 universe (run sync_sp500 first)",
    )
    parser.add_argument(
        "--period",
        default="10y",
        help="Lookback period for price data (default: 10y)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched without writing",
    )
    args = parser.parse_args()
    asyncio.run(
        main(
            tickers=args.tickers,
            use_universe=args.universe,
            period=args.period,
            dry_run=args.dry_run,
        )
    )
