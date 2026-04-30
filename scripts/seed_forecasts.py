"""Train LightGBM+XGBoost forecast models and generate predictions.

Delegates to the same ForecastEngine used by the nightly pipeline
(backend.tasks.forecasting._model_retrain_all_async). Requires
historical_features to be populated first (run backfill_features).

Prerequisites (run in order):
    1. uv run python -m scripts.seed_prices --universe
    2. uv run python -m scripts.backfill_features
    3. uv run python -m scripts.seed_forecasts

Usage:
    # Train and predict (default)
    uv run python -m scripts.seed_forecasts

    # Dry run — show what would happen
    uv run python -m scripts.seed_forecasts --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

from backend.database import async_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def main(dry_run: bool = False) -> None:
    """Train cross-ticker LightGBM+XGBoost models and generate forecasts.

    Args:
        dry_run: If True, just log feature row counts.
    """
    # Check prerequisites
    async with async_session_factory() as db:
        query = "SELECT count(*), count(DISTINCT ticker) FROM historical_features"
        r = await db.execute(text(query))
        row = r.fetchone()
        assert row is not None
        total_rows, ticker_count = row

    if total_rows == 0:
        logger.error(
            "No historical_features rows found. "
            "Run 'uv run python -m scripts.backfill_features' first."
        )
        return

    logger.info(
        "Found %d historical_features rows across %d tickers",
        total_rows,
        ticker_count,
    )

    if dry_run:
        logger.info("[DRY RUN] Would train LightGBM+XGBoost models for %d tickers", ticker_count)
        return

    # Delegate to the production retrain task (same code path as nightly pipeline)
    from backend.tasks.forecasting import _model_retrain_all_async

    logger.info("Starting LightGBM+XGBoost model training...")
    result = await _model_retrain_all_async()
    logger.info("Forecast seed complete: %s", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train LightGBM+XGBoost forecast models and generate predictions"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would happen without training",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
