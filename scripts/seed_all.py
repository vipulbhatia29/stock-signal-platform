"""Full database seed orchestrator — runs all seed scripts in dependency order.

This is the single entry point for populating a fresh database with all data
needed for the dashboard to function. Each step is idempotent.

Dependency graph:
    1. sync_sp500       → stock records (503 tickers)
    2. seed_etfs        → ETF stock records + prices (12 ETFs)
    3. sync_indexes     → index memberships (S&P 500, Dow 30)
    4. seed_prices      → 10y OHLCV + signal snapshots (all tickers)
    5. seed_fundamentals → P/E, PEG, FCF, Piotroski, earnings
    6. seed_dividends   → dividend payment history
    7. backfill_features → historical_features table (training data)
    8. seed_forecasts   → LightGBM+XGBoost model training + predictions
    9. news_ingest      → fetch recent news articles
   10. news_scoring     → LLM sentiment scoring
   11. convergence      → signal convergence scores
   12. recommendations  → buy/sell recommendations
   13. alerts           → in-app alerts
   14. seed_portfolio   → (optional) import Fidelity CSV

Usage:
    # Full seed (no portfolio)
    uv run python -m scripts.seed_all

    # Full seed with portfolio import
    uv run python -m scripts.seed_all --csv /path/to/fidelity.csv \\
        --email user@example.com --password Pass123

    # Skip slow steps (prices already seeded)
    uv run python -m scripts.seed_all --skip-prices

    # Dry run
    uv run python -m scripts.seed_all --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger(__name__)


async def run_step(name: str, coro_fn, dry_run: bool = False, **kwargs) -> bool:
    """Run a single seed step with timing and error handling.

    Args:
        name: Human-readable step name.
        coro_fn: Async callable to execute.
        dry_run: If True, skip execution.
        **kwargs: Arguments passed to coro_fn.

    Returns:
        True if step succeeded, False if it failed.
    """
    if dry_run:
        logger.info("[DRY RUN] Would run: %s", name)
        return True

    logger.info("━━━ Step: %s ━━━", name)
    start = time.monotonic()
    try:
        await coro_fn(**kwargs)
        elapsed = time.monotonic() - start
        logger.info("✓ %s completed in %.1fs", name, elapsed)
        return True
    except Exception:
        elapsed = time.monotonic() - start
        logger.exception("✗ %s FAILED after %.1fs", name, elapsed)
        return False


async def main(
    skip_prices: bool = False,
    skip_forecasts: bool = False,
    csv_path: str | None = None,
    email: str | None = None,
    password: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the full seed pipeline in dependency order.

    Args:
        skip_prices: Skip price seeding (if already done).
        skip_forecasts: Skip forecast training (slow).
        csv_path: Optional Fidelity CSV path for portfolio import.
        email: Email for portfolio user.
        password: Password for portfolio user.
        dry_run: Preview what would happen.
    """
    results: dict[str, bool] = {}
    overall_start = time.monotonic()

    # Step 1: Universe
    from scripts.sync_sp500 import main as sync_sp500_main

    results["sync_sp500"] = await run_step("Sync S&P 500 universe", sync_sp500_main, dry_run)

    # Step 2: ETFs
    from scripts.seed_etfs import main as seed_etfs_main

    results["seed_etfs"] = await run_step("Seed ETFs", seed_etfs_main, dry_run)

    # Step 3: Index memberships
    from scripts.sync_indexes import main as sync_indexes_main

    results["sync_indexes"] = await run_step("Sync index memberships", sync_indexes_main, dry_run)

    # Step 4: Prices + signals
    if skip_prices:
        logger.info("⏭ Skipping prices (--skip-prices)")
        results["seed_prices"] = True
    else:
        from scripts.seed_prices import main as seed_prices_main

        results["seed_prices"] = await run_step(
            "Seed prices (10y, full universe)",
            seed_prices_main,
            dry_run,
            use_universe=True,
            period="10y",
        )

    # Step 5 & 6: Fundamentals + Dividends (parallel, independent)
    from scripts.seed_dividends import main as seed_dividends_main
    from scripts.seed_fundamentals import main as seed_fundamentals_main

    if dry_run:
        await run_step("Seed fundamentals", seed_fundamentals_main, dry_run)
        await run_step("Seed dividends", seed_dividends_main, dry_run)
    else:
        logger.info("━━━ Steps 5-6: Fundamentals + Dividends (parallel) ━━━")
        start = time.monotonic()
        fund_task = asyncio.create_task(
            run_step("Seed fundamentals", seed_fundamentals_main, dry_run, use_universe=True)
        )
        div_task = asyncio.create_task(
            run_step("Seed dividends", seed_dividends_main, dry_run, use_universe=True)
        )
        fund_ok, div_ok = await asyncio.gather(fund_task, div_task)
        results["seed_fundamentals"] = fund_ok
        results["seed_dividends"] = div_ok
        logger.info("Steps 5-6 completed in %.1fs", time.monotonic() - start)

    # Step 7: Backfill features (needs prices)
    from scripts.backfill_features import run_backfill

    results["backfill_features"] = await run_step(
        "Backfill historical features", run_backfill, dry_run
    )

    # Step 8: Forecast training (needs features)
    if skip_forecasts:
        logger.info("⏭ Skipping forecasts (--skip-forecasts)")
        results["seed_forecasts"] = True
    else:
        from scripts.seed_forecasts import main as seed_forecasts_main

        results["seed_forecasts"] = await run_step(
            "Train forecast models (LightGBM+XGBoost)", seed_forecasts_main, dry_run
        )

    # Step 9-10: News ingestion + scoring
    from backend.tasks.news_sentiment import _ingest_news, _score_sentiment

    results["news_ingest"] = await run_step(
        "Ingest news articles", _ingest_news, dry_run, lookback_days=7
    )
    results["news_scoring"] = await run_step(
        "Score news sentiment", _score_sentiment, dry_run, lookback_days=7
    )

    # Step 11: Convergence
    from backend.tasks.convergence import _compute_convergence_snapshot_async

    results["convergence"] = await run_step(
        "Compute convergence scores", _compute_convergence_snapshot_async, dry_run
    )

    # Step 12: Recommendations
    from backend.tasks.recommendations import _generate_recommendations_async

    results["recommendations"] = await run_step(
        "Generate recommendations", _generate_recommendations_async, dry_run
    )

    # Step 13: Alerts
    from backend.tasks.alerts import _generate_alerts_async

    results["alerts"] = await run_step("Generate alerts", _generate_alerts_async, dry_run)

    # Step 14: Portfolio (optional)
    if csv_path and email and password:
        from scripts.seed_portfolio import seed as seed_portfolio

        results["portfolio"] = await run_step(
            "Import portfolio from CSV",
            seed_portfolio,
            dry_run,
            csv_path=csv_path,
            email=email,
            password=password,
        )

    # Summary
    elapsed = time.monotonic() - overall_start
    passed = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)

    logger.info("")
    logger.info("═══ Seed Pipeline Complete ═══")
    logger.info("Total time: %.1fs", elapsed)
    logger.info("Steps: %d passed, %d failed out of %d", passed, failed, len(results))
    if failed:
        failed_steps = [k for k, v in results.items() if not v]
        logger.warning("Failed steps: %s", failed_steps)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full database seed orchestrator")
    parser.add_argument("--skip-prices", action="store_true", help="Skip price seeding")
    parser.add_argument("--skip-forecasts", action="store_true", help="Skip forecast training")
    parser.add_argument("--csv", help="Fidelity CSV path for portfolio import")
    parser.add_argument("--email", help="Email for portfolio user")
    parser.add_argument("--password", help="Password for portfolio user")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would happen")
    args = parser.parse_args()

    asyncio.run(
        main(
            skip_prices=args.skip_prices,
            skip_forecasts=args.skip_forecasts,
            csv_path=args.csv,
            email=args.email,
            password=args.password,
            dry_run=args.dry_run,
        )
    )
