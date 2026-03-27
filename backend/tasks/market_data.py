"""Celery tasks for market data refresh operations."""

import asyncio
import logging
from datetime import date

from sqlalchemy import select

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

        # Refresh beta/yield/forward_pe from yfinance info
        try:
            import yfinance as yf

            from backend.models.stock import Stock

            info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info or {})
            result = await db.execute(select(Stock).where(Stock.ticker == ticker))
            stock_obj = result.scalar_one_or_none()
            if stock_obj and info:
                for yf_key, field in [
                    ("beta", "beta"),
                    ("dividendYield", "dividend_yield"),
                    ("forwardPE", "forward_pe"),
                ]:
                    val = info.get(yf_key)
                    if val is not None:
                        try:
                            setattr(stock_obj, field, float(val))
                        except (TypeError, ValueError):
                            pass
                db.add(stock_obj)
        except Exception:
            logger.warning("Failed to refresh beta/yield for %s", ticker, exc_info=True)

        # Sync dividends
        try:
            from backend.tools.dividends import fetch_dividends, store_dividends

            divs = await asyncio.to_thread(fetch_dividends, ticker)
            if divs:
                await store_dividends(ticker, divs, db)
        except Exception:
            logger.warning("Failed to sync dividends for %s", ticker, exc_info=True)

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
    """Orchestrate the full nightly pipeline chain with parallelized phases.

    Dependency graph (steps that share a phase run concurrently)::

        Phase 0: Cache invalidation
            |
        Phase 1: Price refresh + signal computation
            |
        Phase 2 (parallel):
            ├── Forecast refresh        (needs fresh prices)
            ├── Recommendation gen      (needs fresh signals)
            ├── Forecast evaluation      (needs fresh prices for matured forecasts)
            ├── Recommendation eval      (needs fresh prices for past recs)
            └── Portfolio snapshots      (needs fresh prices)
            |
        Phase 3: Drift detection         (needs forecast eval MAPE updates)
            |
        Phase 4 (parallel):
            ├── Alert generation         (needs drift context + new recs)
            └── Health snapshots         (needs portfolio snapshots)

    Steps 4-6 will no-op until enough time has passed for forecasts
    and recommendations to mature (30-90 days).

    Returns:
        Dict with results from each step.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from backend.tasks.alerts import generate_alerts_task
    from backend.tasks.evaluation import (
        check_drift_task,
        evaluate_forecasts_task,
        evaluate_recommendations_task,
    )
    from backend.tasks.forecasting import forecast_refresh_task
    from backend.tasks.portfolio import snapshot_all_portfolios_task, snapshot_health_task
    from backend.tasks.recommendations import generate_recommendations_task

    results: dict = {}

    # Phase 0: Invalidate stale app-wide cache before recomputation
    try:
        import redis

        from backend.config import settings

        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        deleted = 0
        for pattern in ("app:screener:*", "app:sectors:*", "app:signals:*", "app:forecast:*"):
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    r.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break
        r.close()
        logger.info("Nightly cache invalidation: cleared %d keys", deleted)
    except Exception:
        logger.warning("Nightly cache invalidation failed", exc_info=True)

    # Phase 1: Price refresh + signal computation (everything else depends on this)
    logger.info("Nightly chain phase 1: price refresh")
    results["price_refresh"] = nightly_price_refresh_task()

    # Phase 2: Five independent steps run in parallel threads.
    # Each task calls asyncio.run() internally, so each thread gets its own event loop.
    phase2_tasks = {
        "forecast_refresh": forecast_refresh_task,
        "recommendations": generate_recommendations_task,
        "forecast_evaluation": evaluate_forecasts_task,
        "recommendation_evaluation": evaluate_recommendations_task,
        "portfolio_snapshots": snapshot_all_portfolios_task,
    }
    logger.info("Nightly chain phase 2: running %d steps in parallel", len(phase2_tasks))
    results.update(_run_tasks_parallel(phase2_tasks))

    # Phase 3: Drift detection (depends on forecast evaluation updating model MAPEs)
    logger.info("Nightly chain phase 3: drift detection")
    results["drift"] = check_drift_task()

    # Phase 4: Alerts + health snapshots run in parallel.
    # Alerts needs drift context + new recs (both complete).
    # Health snapshots needs portfolio snapshots (complete from phase 2).
    phase4_tasks: dict[str, tuple] = {
        "alerts": (generate_alerts_task, {"pipeline_context": results.get("drift")}),
        "health_snapshots": (snapshot_health_task, {}),
    }
    logger.info("Nightly chain phase 4: running %d steps in parallel", len(phase4_tasks))

    with ThreadPoolExecutor(max_workers=len(phase4_tasks)) as executor:
        futures = {}
        for name, (fn, kwargs) in phase4_tasks.items():
            futures[executor.submit(fn, **kwargs)] = name

        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception:
                logger.exception("Phase 4 step '%s' failed", name)
                results[name] = {"status": "failed"}

    logger.info("Nightly pipeline chain complete: %s", results)
    return results


def _run_tasks_parallel(tasks: dict[str, object]) -> dict:
    """Run multiple no-arg Celery task functions concurrently in threads.

    Each task calls asyncio.run() internally, so each thread gets its own
    event loop — no nested-loop issues.

    Args:
        tasks: Mapping of result-key to callable (no-arg task function).

    Returns:
        Dict mapping result-key to the task's return value (or error dict).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception:
                logger.exception("Parallel step '%s' failed", name)
                results[name] = {"status": "failed"}
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
