"""Celery tasks for Prophet model training and forecast refresh."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.models.backtest import BacktestRun
from backend.models.forecast import ModelVersion
from backend.services.backtesting import BacktestEngine
from backend.services.ticker_state import mark_stage_updated
from backend.services.ticker_universe import get_all_referenced_tickers
from backend.tasks import celery_app
from backend.tasks.pipeline import PipelineRunner
from backend.tools.forecasting import MIN_DATA_POINTS

logger = logging.getLogger(__name__)

_runner = PipelineRunner()

MAX_NEW_MODELS_PER_NIGHT = 20


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


async def _model_retrain_all_async() -> dict:
    """Retrain Prophet models for all tickers and generate forecasts.

    Returns:
        Dict with run status and counts.
    """
    from backend.services.ticker_universe import get_all_referenced_tickers
    from backend.tools.forecasting import predict_forecast, train_prophet_model

    async with async_session_factory() as db:
        tickers = await get_all_referenced_tickers(db)
    if not tickers:
        logger.info("No tickers to retrain")
        return {"status": "no_tickers", "trained": 0}

    run_id = await _runner.start_run("model_retrain", "scheduled", len(tickers))
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

    status = await _runner.complete_run(run_id)
    return {"status": status, "trained": trained, "total": len(tickers)}


async def _forecast_refresh_async() -> dict:
    """Refresh forecasts using existing active models (no retraining).

    Returns:
        Dict with refresh status and counts.
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
            return {"status": "no_models", "refreshed": 0}

        run_id = await _runner.start_run("forecast_refresh", "scheduled", len(active_models))
        refreshed = 0

        for model_version in active_models:
            try:
                forecasts = await predict_forecast(model_version, db)
                for fc in forecasts:
                    db.add(fc)
                await db.commit()
                await _runner.record_ticker_success(run_id, model_version.ticker)
                refreshed += 1
            except Exception:
                await db.rollback()
                await _runner.record_ticker_failure(run_id, model_version.ticker, "refresh failed")
                logger.exception("Failed to refresh forecast for %s", model_version.ticker)

        status = await _runner.complete_run(run_id)

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

        return {"status": status, "refreshed": refreshed, "total": len(active_models)}


@celery_app.task(
    name="backend.tasks.forecasting.model_retrain_all_task",
)
def model_retrain_all_task() -> dict:
    """Biweekly full retrain of all Prophet models.

    Returns:
        Dict with training status and counts.
    """
    logger.info("Starting full model retrain")
    return asyncio.run(_model_retrain_all_async())


@celery_app.task(
    name="backend.tasks.forecasting.forecast_refresh_task",
)
def forecast_refresh_task() -> dict:
    """Nightly forecast refresh using existing active models (no retrain).

    Returns:
        Dict with refresh status and counts.
    """
    logger.info("Starting nightly forecast refresh")
    return asyncio.run(_forecast_refresh_async())


@celery_app.task(
    name="backend.tasks.forecasting.retrain_single_ticker_task",
)
def retrain_single_ticker_task(ticker: str) -> dict:
    """Retrain a single ticker's Prophet model (drift-triggered).

    Args:
        ticker: Stock ticker to retrain.

    Returns:
        Dict with training result.
    """

    async def _retrain() -> dict:
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

    logger.info("Retraining %s (drift-triggered)", ticker)
    return asyncio.run(_retrain())


async def _run_backtest_async(ticker: str | None, horizon_days: int) -> dict:
    """Async implementation of walk-forward backtest for one or all tickers.

    Args:
        ticker: Specific ticker symbol, or None to run for all referenced tickers.
        horizon_days: Forecast horizon to validate.

    Returns:
        Dict with status, completed count, failed count, horizon, and ticker.
    """
    from datetime import date

    engine = BacktestEngine()
    completed = 0
    failed: list[str] = []

    async with async_session_factory() as db:
        tickers = [ticker] if ticker else await get_all_referenced_tickers(db)

        for tkr in tickers:
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
                        "skipping BacktestRun row (metrics computed but not persisted)",
                        tkr,
                    )
                else:
                    today = date.today()
                    db.add(
                        BacktestRun(
                            ticker=tkr,
                            model_version_id=model_version.id,
                            config_label="walk_forward",
                            # Use the model's training range as proxy for the
                            # walk-forward window bounds (no per-window state stored)
                            train_start=model_version.training_data_start,
                            train_end=model_version.training_data_end,
                            test_start=today,
                            test_end=today,
                            horizon_days=horizon_days,
                            num_windows=metrics.num_windows,
                            mape=metrics.mape,
                            mae=metrics.mae,
                            rmse=metrics.rmse,
                            direction_accuracy=metrics.direction_accuracy,
                            ci_containment=metrics.ci_containment,
                        )
                    )
                    await db.commit()

                await mark_stage_updated(tkr, "backtest")
                completed += 1

            except Exception:
                await db.rollback()
                logger.exception("Backtest failed for %s", tkr)
                failed.append(tkr)

    return {
        "status": "ok",
        "completed": completed,
        "failed": len(failed),
        "horizon_days": horizon_days,
        "ticker": ticker,
    }


@celery_app.task(name="backend.tasks.forecasting.run_backtest_task")
def run_backtest_task(ticker: str | None = None, horizon_days: int = 90) -> dict:
    """Run walk-forward backtest for a ticker or all active tickers.

    Args:
        ticker: Specific ticker, or None for all active tickers.
        horizon_days: Forecast horizon to backtest.

    Returns:
        Dict with backtest results summary.
    """
    logger.info("Backtest task started: ticker=%s, horizon=%d", ticker or "all", horizon_days)
    return asyncio.run(_run_backtest_async(ticker, horizon_days))


@celery_app.task(name="backend.tasks.forecasting.calibrate_seasonality_task")
def calibrate_seasonality_task(ticker: str | None = None) -> dict:
    """Run seasonality calibration (4 configs per ticker, pick best).

    Args:
        ticker: Specific ticker, or None for all active tickers.

    Returns:
        Dict with calibration results.
    """
    logger.info("Calibration task started: ticker=%s", ticker or "all")
    # Full implementation wired in Sprint 4 integration
    return {"status": "ok", "ticker": ticker}
