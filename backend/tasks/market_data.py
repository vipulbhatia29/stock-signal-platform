"""Celery tasks for market data refresh operations."""

import asyncio
import logging
from datetime import date

from backend.database import async_session_factory
from backend.tasks import celery_app
from backend.tasks.pipeline import PipelineRunner, detect_gap, set_watermark_status
from backend.tools.market_data import fetch_prices_delta, load_prices_df
from backend.tools.signals import compute_signals, store_signal_snapshot

logger = logging.getLogger(__name__)

_runner = PipelineRunner()


async def _refresh_ticker_async(ticker: str) -> dict:
    """Async implementation: fetch prices, compute signals, store snapshot.

    Args:
        ticker: The stock ticker symbol.

    Returns:
        A dict with ticker and status.
    """
    async with async_session_factory() as db:
        await fetch_prices_delta(ticker, db)
        full_df = await load_prices_df(ticker, db)

        if full_df.empty:
            logger.warning("No price data found for %s — skipping signal computation", ticker)
            return {"ticker": ticker, "status": "no_data"}

        signal_result = compute_signals(ticker, full_df)
        await store_signal_snapshot(signal_result, db)
        await db.commit()
        logger.info("Refreshed %s — composite_score=%.1f", ticker, signal_result.composite_score)
        return {"ticker": ticker, "status": "ok"}


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=4,
    retry_backoff=True,
    retry_backoff_max=60,
    name="backend.tasks.market_data.refresh_ticker_task",
)
def refresh_ticker_task(self, ticker: str) -> dict:
    """Fetch latest prices and recompute signals for a single ticker.

    Args:
        ticker: The stock ticker symbol to refresh (e.g. "AAPL").

    Returns:
        A dict with ticker and status on success.

    Raises:
        Exception: Re-raised after max_retries exhausted, triggering Celery retry.
    """
    try:
        logger.info("Refreshing ticker %s (attempt %d)", ticker, self.request.retries + 1)
        return asyncio.run(_refresh_ticker_async(ticker))
    except Exception:
        logger.exception(
            "refresh_ticker_task failed for %s (attempt %d/%d)",
            ticker,
            self.request.retries + 1,
            self.max_retries + 1,
        )
        raise


async def _get_all_watchlist_tickers() -> list[str]:
    """Query DB for all distinct tickers currently in any user's watchlist.

    Returns:
        Sorted list of unique ticker symbols.
    """
    from sqlalchemy import distinct, select

    from backend.models.stock import Watchlist

    async with async_session_factory() as db:
        result = await db.execute(select(distinct(Watchlist.ticker)))
        return sorted(row[0] for row in result.all())


async def _nightly_price_refresh_async() -> dict:
    """Price refresh with PipelineRunner tracking and gap detection.

    Returns:
        Dict with pipeline run results.
    """
    # Detect stale runs from previous failures
    stale_ids = await _runner.detect_stale_runs()
    if stale_ids:
        logger.warning("Cleaned up %d stale pipeline runs", len(stale_ids))

    # Check for gaps
    missing_days = await detect_gap("price_refresh")
    if missing_days:
        logger.info("Backfilling %d missing days before nightly refresh", len(missing_days))
        await set_watermark_status("price_refresh", "backfilling")
        # Gap backfill is best-effort — log but don't block the nightly run

    # Get all tickers to refresh
    tickers = await _get_all_watchlist_tickers()
    if not tickers:
        logger.warning("No watchlisted tickers to refresh")
        return {"status": "no_tickers", "tickers_total": 0}

    # Start tracked run
    run_id = await _runner.start_run("price_refresh", "scheduled", len(tickers))

    for ticker in tickers:
        try:
            result = await _refresh_ticker_async(ticker)
            if result["status"] == "ok":
                await _runner.record_ticker_success(run_id, ticker)
            else:
                await _runner.record_ticker_failure(run_id, ticker, result["status"])
        except Exception as e:
            await _runner.record_ticker_failure(run_id, ticker, str(e))
            logger.exception("Failed to refresh %s in nightly pipeline", ticker)

    status = await _runner.complete_run(run_id)
    await _runner.update_watermark("price_refresh", date.today())

    return {"status": status, "run_id": str(run_id), "tickers_total": len(tickers)}


@celery_app.task(
    name="backend.tasks.market_data.nightly_price_refresh_task",
)
def nightly_price_refresh_task() -> dict:
    """Nightly price refresh with pipeline tracking — used in the nightly chain.

    Returns:
        Dict with pipeline run status.
    """
    logger.info("Starting nightly price refresh pipeline")
    return asyncio.run(_nightly_price_refresh_async())


@celery_app.task(
    name="backend.tasks.market_data.nightly_pipeline_chain_task",
)
def nightly_pipeline_chain_task() -> dict:
    """Orchestrate the full nightly pipeline chain.

    Runs sequentially: price refresh → recommendation generation → portfolio snapshot.
    Future stories will add: forecast refresh, forecast evaluation,
    recommendation evaluation, and alert generation.

    Returns:
        Dict with results from each step.
    """
    results: dict = {}

    # Step 1: Price refresh + signal computation (with PipelineRunner tracking)
    logger.info("Nightly chain step 1/3: price refresh")
    results["price_refresh"] = nightly_price_refresh_task()

    # Step 2: Recommendation generation
    logger.info("Nightly chain step 2/3: recommendation generation")
    from backend.tasks.recommendations import generate_recommendations_task

    results["recommendations"] = generate_recommendations_task()

    # Step 3: Portfolio snapshots
    logger.info("Nightly chain step 3/3: portfolio snapshots")
    from backend.tasks.portfolio import snapshot_all_portfolios_task

    results["portfolio_snapshots"] = snapshot_all_portfolios_task()

    # Future steps (S4/S5/S6 will add):
    # - forecast_refresh (retrain/predict)
    # - forecast_evaluation (fill actuals)
    # - recommendation_evaluation (compare vs SPY)
    # - alert_generation (signal changes, drift, etc.)

    logger.info("Nightly pipeline chain complete: %s", results)
    return results


@celery_app.task(
    name="backend.tasks.market_data.refresh_all_watchlist_tickers_task",
)
def refresh_all_watchlist_tickers_task() -> dict:
    """Fan-out: enqueue a refresh_ticker_task for every watchlisted ticker.

    Runs on the Celery Beat schedule (intraday). Queries all unique tickers
    across all user watchlists, then dispatches one refresh_ticker_task per ticker.

    Returns:
        A dict with the count of tasks dispatched.
    """
    tickers = asyncio.run(_get_all_watchlist_tickers())
    dispatched = 0
    for ticker in tickers:
        refresh_ticker_task.delay(ticker)
        dispatched += 1
        logger.info("Beat: enqueued refresh for %s", ticker)
    logger.info("Beat: dispatched %d refresh tasks", dispatched)
    return {"dispatched": dispatched, "tickers": tickers}
