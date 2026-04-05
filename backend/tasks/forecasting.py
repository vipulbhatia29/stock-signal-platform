"""Celery tasks for Prophet model training and forecast refresh."""

import asyncio
import logging

from backend.database import async_session_factory
from backend.tasks import celery_app
from backend.tasks.pipeline import PipelineRunner

logger = logging.getLogger(__name__)

_runner = PipelineRunner()


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
                forecasts = predict_forecast(model_version)

                for fc in forecasts:
                    db.add(fc)

                await db.commit()
                await _runner.record_ticker_success(run_id, ticker)
                trained += 1

            except Exception as e:
                await db.rollback()
                await _runner.record_ticker_failure(run_id, ticker, str(e))
                logger.exception("Failed to retrain %s", ticker)

    status = await _runner.complete_run(run_id)
    return {"status": status, "trained": trained, "total": len(tickers)}


async def _forecast_refresh_async() -> dict:
    """Refresh forecasts using existing active models (no retraining).

    Returns:
        Dict with refresh status and counts.
    """
    from sqlalchemy import select

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
                forecasts = predict_forecast(model_version)
                for fc in forecasts:
                    db.add(fc)
                await db.commit()
                await _runner.record_ticker_success(run_id, model_version.ticker)
                refreshed += 1
            except Exception as e:
                await db.rollback()
                await _runner.record_ticker_failure(run_id, model_version.ticker, str(e))
                logger.exception("Failed to refresh forecast for %s", model_version.ticker)

        status = await _runner.complete_run(run_id)
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
            forecasts = predict_forecast(model_version)
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
    # Full implementation wired in Sprint 4 integration
    return {"status": "ok", "ticker": ticker, "horizon_days": horizon_days}


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
