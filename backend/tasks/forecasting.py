"""Celery tasks for Prophet model training and forecast refresh."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import async_session_factory
from backend.models.backtest import BacktestRun
from backend.models.forecast import ModelVersion
from backend.services.backtesting import BacktestEngine
from backend.services.ticker_state import mark_stages_updated
from backend.services.ticker_universe import get_all_referenced_tickers
from backend.tasks import celery_app
from backend.tasks._asyncio_bridge import safe_asyncio_run
from backend.tasks.pipeline import PipelineRunner, tracked_task
from backend.tools.forecasting import MIN_DATA_POINTS

logger = logging.getLogger(__name__)

_runner = PipelineRunner()

MAX_NEW_MODELS_PER_NIGHT = 100


async def _get_price_data_counts(tickers: list[str], db: AsyncSession) -> dict[str, int]:
    """Count price data points per ticker (last 2 years) in a single query.

    Args:
        tickers: List of ticker symbols to check.
        db: Async database session.

    Returns:
        Dict mapping ticker to count of price data points.
    """
    from datetime import timedelta

    from sqlalchemy import func

    from backend.models.price import StockPrice

    two_years_ago = datetime.now(timezone.utc).date() - timedelta(days=730)
    result = await db.execute(
        select(StockPrice.ticker, func.count().label("cnt"))
        .where(StockPrice.ticker.in_(tickers), StockPrice.time >= two_years_ago)
        .group_by(StockPrice.ticker)
    )
    return {row.ticker: row.cnt for row in result.all()}


@tracked_task("model_retrain", trigger="scheduled")
async def _model_retrain_all_async(*, run_id: uuid.UUID) -> dict:
    """Retrain Prophet models for all tickers and generate forecasts.

    Returns:
        Dict with training counts. Pipeline status lives in pipeline_runs row.
    """
    from backend.services.ticker_universe import get_all_referenced_tickers
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    async with async_session_factory() as db:
        tickers = await get_all_referenced_tickers(db)
    if not tickers:
        logger.info("No tickers to retrain")
        return {"trained": 0, "total": 0}

    trained = 0

    async with async_session_factory() as db:
        for ticker in tickers:
            try:
                model_version = await train_prophet_model(ticker, db)
                forecasts = await predict_forecast(model_version, db)

                for fc in forecasts:
                    db.add(fc)

                await db.commit()
                await _runner.record_ticker_success(run_id, ticker)
                trained += 1

            except Exception:
                await db.rollback()
                await _runner.record_ticker_failure(run_id, ticker, "retrain failed")
                logger.exception("Failed to retrain %s", ticker)

    return {"trained": trained, "total": len(tickers)}


@tracked_task("forecast_refresh", trigger="scheduled")
async def _forecast_refresh_async(*, run_id: uuid.UUID) -> dict:
    """Refresh forecasts using existing active models (no retraining).

    Returns:
        Dict with refresh counts. Pipeline status lives in pipeline_runs row.
    """
    from backend.models.forecast import ModelVersion
    from backend.tools.forecasting import predict_forecast

    async with async_session_factory() as db:
        result = await db.execute(
            select(ModelVersion).where(
                ModelVersion.is_active.is_(True),
                ModelVersion.model_type == "prophet",
            )
        )
        active_models = result.scalars().all()

        if not active_models:
            logger.info("No active models — skipping forecast refresh")
            return {"refreshed": 0, "total": 0}

        refreshed = 0
        refreshed_tickers: list[str] = []

        for model_version in active_models:
            try:
                forecasts = await predict_forecast(model_version, db)
                for fc in forecasts:
                    db.add(fc)
                await db.commit()
                await _runner.record_ticker_success(run_id, model_version.ticker)
                refreshed_tickers.append(model_version.ticker)
                refreshed += 1
            except Exception:
                await db.rollback()
                await _runner.record_ticker_failure(run_id, model_version.ticker, "refresh failed")
                logger.exception("Failed to refresh forecast for %s", model_version.ticker)

        # ── Phase 2: Dispatch training for new tickers without models ──
        try:
            from backend.services.ticker_universe import get_all_referenced_tickers

            all_tickers = await get_all_referenced_tickers(db)
            modeled_tickers = {mv.ticker for mv in active_models}
            new_tickers = [t for t in all_tickers if t not in modeled_tickers]

            if new_tickers:
                counts = await _get_price_data_counts(new_tickers, db)
                dispatched = 0
                for ticker in new_tickers:
                    if dispatched >= MAX_NEW_MODELS_PER_NIGHT:
                        break
                    if counts.get(ticker, 0) >= MIN_DATA_POINTS:
                        retrain_single_ticker_task.delay(ticker)
                        dispatched += 1
                        logger.info(
                            "Dispatched first-time training for %s (%d data points)",
                            ticker,
                            counts[ticker],
                        )
                    else:
                        logger.debug(
                            "Skipping %s: only %d data points (need %d)",
                            ticker,
                            counts.get(ticker, 0),
                            MIN_DATA_POINTS,
                        )

                if dispatched:
                    logger.info("Dispatched training for %d new tickers", dispatched)
        except Exception:
            logger.warning("Failed to dispatch new-ticker training", exc_info=True)

        # Mark forecast stage freshness for all successfully refreshed tickers
        if refreshed_tickers:
            await mark_stages_updated(refreshed_tickers, "forecast")

        return {"refreshed": refreshed, "total": len(active_models)}


@celery_app.task(
    name="backend.tasks.forecasting.model_retrain_all_task",
)
def model_retrain_all_task() -> dict:
    """Weekly full retrain of all Prophet models (Sunday 02:00 ET).

    Returns:
        Dict with training status and counts.
    """
    logger.info("Starting weekly full model retrain")

    return safe_asyncio_run(_model_retrain_all_async())  # type: ignore[arg-type]  # wrapper is async def, pyright sees Awaitable not Coroutine


@celery_app.task(
    name="backend.tasks.forecasting.forecast_refresh_task",
)
def forecast_refresh_task() -> dict:
    """Nightly forecast refresh using existing active models (no retrain).

    Returns:
        Dict with refresh status and counts.
    """
    logger.info("Starting nightly forecast refresh")

    return safe_asyncio_run(_forecast_refresh_async())  # type: ignore[arg-type]  # wrapper is async def, pyright sees Awaitable not Coroutine


@tracked_task("single_ticker_retrain")
async def _retrain_single_ticker_async(ticker: str, *, run_id: uuid.UUID) -> dict:
    """Async implementation: retrain a single ticker's Prophet model.

    Args:
        ticker: Stock ticker to retrain.
        run_id: Pipeline run ID injected by @tracked_task.

    Returns:
        Dict with training result.
    """
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    async with async_session_factory() as db:
        model_version = await train_prophet_model(ticker, db)
        forecasts = await predict_forecast(model_version, db)
        for fc in forecasts:
            db.add(fc)
        await db.commit()
        return {
            "ticker": ticker,
            "version": model_version.version,
            "forecasts": len(forecasts),
        }


@celery_app.task(
    name="backend.tasks.forecasting.retrain_single_ticker_task",
)
def retrain_single_ticker_task(ticker: str, priority: bool = False) -> dict:
    """Retrain a single ticker's Prophet model.

    Args:
        ticker: Stock ticker to retrain.
        priority: If True, user-initiated retrain that bypasses the nightly
            sweep cap (Spec E.1). Passed through from ingest_ticker.

    Returns:
        Dict with training result.
    """
    logger.info("Retraining %s (priority=%s)", ticker, priority)

    return safe_asyncio_run(_retrain_single_ticker_async(ticker))  # type: ignore[arg-type]


@tracked_task("backtest")
async def _run_backtest_async(ticker: str | None, horizon_days: int, *, run_id: uuid.UUID) -> dict:
    """Async implementation of walk-forward backtest for one or all tickers.

    Args:
        ticker: Specific ticker symbol, or None to run for all referenced tickers.
        horizon_days: Forecast horizon to validate.

    Returns:
        Dict with status, completed count, failed count, horizon, and ticker.
    """
    if not settings.BACKTEST_ENABLED:
        logger.info("BACKTEST_ENABLED=False — skipping")
        return {"status": "disabled"}

    engine = BacktestEngine()
    completed = 0
    failed: list[str] = []
    successful_tickers: list[str] = []

    # Resolve the ticker universe in its own short-lived session so we never
    # hold a connection open while iterating below.
    async with async_session_factory() as db:
        tickers = [ticker] if ticker else await get_all_referenced_tickers(db)

    for tkr in tickers:
        # Per-ticker session: the primary motivation is session-state
        # isolation — a SQLAlchemy InvalidRequestError / PendingRollbackError
        # from a poisoned transaction in one ticker must not bleed into
        # the next iteration's reads. (Per-ticker checkouts add modest
        # connection-pool churn vs the old single-session pattern, but
        # that trade-off is intentional.) The outer try/except also catches
        # transient session-acquisition failures (asyncpg connection drop,
        # pool timeout) so one bad checkout cannot abort the weekly chain.
        try:
            async with async_session_factory() as db:
                try:
                    metrics = await engine.run_walk_forward(tkr, db, horizon_days=horizon_days)

                    # Look up the active model version for this ticker — required FK
                    mv_result = await db.execute(
                        select(ModelVersion)
                        .where(
                            ModelVersion.ticker == tkr,
                            ModelVersion.model_type == "prophet",
                            ModelVersion.is_active.is_(True),
                        )
                        .limit(1)
                    )
                    model_version = mv_result.scalar_one_or_none()
                    if model_version is None:
                        logger.warning(
                            "run_backtest_task: no active ModelVersion for %s — "
                            "cannot persist BacktestRun row; marking as failed",
                            tkr,
                        )
                        failed.append(tkr)
                        continue

                    today = datetime.now(timezone.utc).date()
                    values = {
                        "ticker": tkr,
                        "model_version_id": model_version.id,
                        "config_label": "walk_forward",
                        "train_start": model_version.training_data_start,
                        "train_end": model_version.training_data_end,
                        "test_start": today,
                        "test_end": today,
                        "horizon_days": horizon_days,
                        "num_windows": metrics.num_windows,
                        "mape": metrics.mape,
                        "mae": metrics.mae,
                        "rmse": metrics.rmse,
                        "direction_accuracy": metrics.direction_accuracy,
                        "ci_containment": metrics.ci_containment,
                    }
                    stmt = pg_insert(BacktestRun).values(values)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_backtest_runs_ticker_mv_config_date_horizon",
                        set_={
                            **{
                                k: stmt.excluded[k]
                                for k in (
                                    "train_start",
                                    "train_end",
                                    "test_end",
                                    "num_windows",
                                    "mape",
                                    "mae",
                                    "rmse",
                                    "direction_accuracy",
                                    "ci_containment",
                                )
                            },
                            "updated_at": func.now(),
                        },
                    )
                    await db.execute(stmt)
                    await db.commit()
                    successful_tickers.append(tkr)
                    completed += 1

                except Exception:
                    await db.rollback()
                    logger.exception("Backtest failed for %s", tkr)
                    failed.append(tkr)
        except Exception:
            # Failure to acquire a session — log and skip this ticker so the
            # run continues. Without this guard a transient pool blip would
            # abort the entire weekly chain with hundreds of tickers unprocessed.
            logger.exception(
                "Failed to acquire session for backtest of %s — skipping",
                tkr,
            )
            failed.append(tkr)

    # ── Bulk-mark backtest stage for every successful ticker ──────────
    # Single bulk upsert outside the per-ticker session loop. Fire-and-forget
    # — observability state, must not roll back the BacktestRun rows we
    # already persisted above.
    if successful_tickers:
        await mark_stages_updated(successful_tickers, "backtest")

    status = "degraded" if failed else "ok"
    return {
        "status": status,
        "completed": completed,
        "failed": len(failed),
        "failed_tickers": failed,
        "horizon_days": horizon_days,
        "ticker": ticker,
    }


@celery_app.task(
    name="backend.tasks.forecasting.run_backtest_task",
    soft_time_limit=3300,
    time_limit=3600,
)
def run_backtest_task(ticker: str | None = None, horizon_days: int = 90) -> dict:
    """Run walk-forward backtest for a ticker or all active tickers.

    Args:
        ticker: Specific ticker, or None for all active tickers.
        horizon_days: Forecast horizon to backtest.

    Returns:
        Dict with backtest results summary.
    """
    logger.info("Backtest task started: ticker=%s, horizon=%d", ticker or "all", horizon_days)

    return safe_asyncio_run(_run_backtest_async(ticker, horizon_days))  # type: ignore[arg-type]
