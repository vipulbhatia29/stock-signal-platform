"""Train Prophet models and generate forecasts for stocks in the database.

Trains a Prophet model per ticker, serializes it to JSON, creates a
ModelVersion row, and generates ForecastResult rows at 90/180/270 day
horizons. Requires stock_prices to already be populated (run seed_prices first).

Tickers with fewer than 200 price data points are skipped (insufficient
for reliable Prophet training).

Delta logic: if a ticker already has an active model, it is retrained
(previous version retired). ForecastResults are inserted fresh per run
(no upsert needed — each forecast_date is unique per ticker+horizon).

Usage:
    # Train a few tickers (quick test)
    uv run python -m scripts.seed_forecasts --tickers AAPL MSFT GOOGL

    # Train all tickers with enough price data
    uv run python -m scripts.seed_forecasts --universe

    # Dry run
    uv run python -m scripts.seed_forecasts --universe --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.price import StockPrice
from backend.models.stock import Stock
from backend.tools.forecasting import MIN_DATA_POINTS, predict_forecast, train_prophet_model

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def get_trainable_tickers(db: AsyncSession) -> list[str]:
    """Get tickers with enough price data for Prophet training.

    Args:
        db: Async database session.

    Returns:
        Sorted list of ticker symbols with >= MIN_DATA_POINTS prices.
    """
    result = await db.execute(
        select(StockPrice.ticker)
        .join(Stock, Stock.ticker == StockPrice.ticker)
        .where(Stock.is_active.is_(True))
        .group_by(StockPrice.ticker)
        .having(func.count(StockPrice.ticker) >= MIN_DATA_POINTS)
        .order_by(StockPrice.ticker)
    )
    return [row[0] for row in result.all()]


async def main(
    tickers: list[str] | None = None,
    use_universe: bool = False,
    dry_run: bool = False,
) -> None:
    """Entry point: train Prophet models and generate forecasts.

    Args:
        tickers: Explicit list of tickers.
        use_universe: If True, train all tickers with enough data.
        dry_run: If True, just log what would happen.
    """
    async with async_session_factory() as db:
        if use_universe:
            ticker_list = await get_trainable_tickers(db)
            if not ticker_list:
                logger.warning("No tickers with enough price data for training.")
                return
            logger.info("Training Prophet models for %d tickers", len(ticker_list))
        elif tickers:
            ticker_list = [t.upper() for t in tickers]
            logger.info("Training Prophet models for %d tickers: %s", len(ticker_list), ticker_list)
        else:
            logger.error("Specify --tickers or --universe")
            return

        if dry_run:
            logger.info("[DRY RUN] Would train models for %d tickers", len(ticker_list))
            for t in ticker_list[:10]:
                logger.info("  %s", t)
            if len(ticker_list) > 10:
                logger.info("  ... and %d more", len(ticker_list) - 10)
            return

        total = len(ticker_list)
        trained = 0
        skipped = 0

        for i, ticker in enumerate(ticker_list, 1):
            start = time.time()
            try:
                model_version = await train_prophet_model(ticker, db)
                forecasts = await predict_forecast(model_version, db)

                for fc in forecasts:
                    db.add(fc)
                await db.commit()

                elapsed = time.time() - start
                trained += 1
                logger.info(
                    "[%d/%d] %s: v%d trained, %d forecasts — %.1fs",
                    i,
                    total,
                    ticker,
                    model_version.version,
                    len(forecasts),
                    elapsed,
                )

            except ValueError as e:
                elapsed = time.time() - start
                skipped += 1
                logger.warning(
                    "[%d/%d] %s: SKIPPED — %s (%.1fs)",
                    i,
                    total,
                    ticker,
                    e,
                    elapsed,
                )
                await db.rollback()

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
                await db.rollback()

        failed = total - trained - skipped
        logger.info(
            "Forecast seed complete: %d trained, %d skipped, %d failed out of %d",
            trained,
            skipped,
            failed,
            total,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train Prophet models and generate forecasts")
    parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific tickers to train (e.g., AAPL MSFT GOOGL)",
    )
    parser.add_argument(
        "--universe",
        action="store_true",
        help="Train all tickers with sufficient price data",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be trained without writing",
    )
    args = parser.parse_args()
    asyncio.run(main(tickers=args.tickers, use_universe=args.universe, dry_run=args.dry_run))
