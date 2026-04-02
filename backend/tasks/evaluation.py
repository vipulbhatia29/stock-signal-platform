"""Celery tasks for forecast evaluation, recommendation evaluation, and drift detection."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory
from backend.tasks import celery_app
from backend.tasks.pipeline import PipelineRunner

logger = logging.getLogger(__name__)

_runner = PipelineRunner()

# Drift thresholds
VOLATILITY_SPIKE_MULTIPLIER = 2.0
VIX_HIGH_THRESHOLD = 30

# Calibrated drift detection
DRIFT_BASELINE_MULTIPLIER = 1.5  # threshold = backtest MAPE × 1.5
DRIFT_FALLBACK_THRESHOLD = 0.20  # used when no backtest data exists
CONSECUTIVE_FAILURES_FOR_EXPERIMENTAL = 3

# Recommendation evaluation horizons
EVAL_HORIZONS = [30, 90, 180]


# ---------------------------------------------------------------------------
# Calibrated drift detection helpers
# ---------------------------------------------------------------------------


def compute_calibrated_threshold(backtest_mape: float | None) -> float:
    """Compute per-ticker drift threshold from backtest baseline.

    Args:
        backtest_mape: Best MAPE from backtest runs, or None if no backtests.

    Returns:
        Calibrated threshold (backtest_mape × 1.5), or fallback 20%.
    """
    if backtest_mape is None or backtest_mape <= 0:
        return DRIFT_FALLBACK_THRESHOLD
    return backtest_mape * DRIFT_BASELINE_MULTIPLIER


def should_demote_to_experimental(
    consecutive_failures: int,
    current_status: str,
) -> bool:
    """Determine if model should be demoted to experimental status.

    Args:
        consecutive_failures: Number of consecutive drift threshold breaches.
        current_status: Current model status.

    Returns:
        True if model should be demoted to experimental.
    """
    if current_status == "experimental":
        return False  # already experimental
    return consecutive_failures >= CONSECUTIVE_FAILURES_FOR_EXPERIMENTAL


# ---------------------------------------------------------------------------
# Task 14: Forecast evaluation
# ---------------------------------------------------------------------------


async def _evaluate_forecasts_async() -> dict:
    """Fill actual prices for matured forecasts and compute error metrics.

    Returns:
        Dict with evaluation counts.
    """
    from backend.models.forecast import ForecastResult
    from backend.models.price import StockPrice

    today = date.today()
    evaluated = 0
    errors = 0

    async with async_session_factory() as db:
        # Find forecasts where target_date has passed and actual_price not yet filled
        result = await db.execute(
            select(ForecastResult).where(
                ForecastResult.target_date <= today,
                ForecastResult.actual_price.is_(None),
            )
        )
        pending = result.scalars().all()

        if not pending:
            logger.info("No forecasts to evaluate")
            return {"status": "no_pending", "evaluated": 0}

        for fc in pending:
            try:
                # Look up actual price on target_date
                price_result = await db.execute(
                    select(StockPrice.close)
                    .where(
                        StockPrice.ticker == fc.ticker,
                        StockPrice.time
                        >= datetime.combine(
                            fc.target_date, datetime.min.time(), tzinfo=timezone.utc
                        ),
                        StockPrice.time
                        < datetime.combine(
                            fc.target_date + timedelta(days=1),
                            datetime.min.time(),
                            tzinfo=timezone.utc,
                        ),
                    )
                    .order_by(StockPrice.time.desc())
                    .limit(1)
                )
                actual = price_result.scalar_one_or_none()

                if actual is None:
                    # Try previous business day (weekends/holidays)
                    for lookback in range(1, 4):
                        alt_date = fc.target_date - timedelta(days=lookback)
                        alt_result = await db.execute(
                            select(StockPrice.close)
                            .where(
                                StockPrice.ticker == fc.ticker,
                                StockPrice.time
                                >= datetime.combine(
                                    alt_date, datetime.min.time(), tzinfo=timezone.utc
                                ),
                                StockPrice.time
                                < datetime.combine(
                                    alt_date + timedelta(days=1),
                                    datetime.min.time(),
                                    tzinfo=timezone.utc,
                                ),
                            )
                            .limit(1)
                        )
                        actual = alt_result.scalar_one_or_none()
                        if actual is not None:
                            break

                if actual is None:
                    continue

                # Fill actual price and compute error
                fc.actual_price = float(actual)
                if fc.predicted_price != 0:
                    fc.error_pct = abs(fc.actual_price - fc.predicted_price) / fc.predicted_price
                else:
                    fc.error_pct = 0.0

                evaluated += 1

            except Exception:
                errors += 1
                logger.exception("Failed to evaluate forecast for %s", fc.ticker)

        await db.commit()

        # Update model metrics with rolling MAPE
        await _update_model_mapes(db)

    logger.info("Forecast evaluation: %d evaluated, %d errors", evaluated, errors)
    return {"status": "success", "evaluated": evaluated, "errors": errors}


async def _update_model_mapes(db: AsyncSession) -> None:
    """Update each active model's metrics with rolling MAPE from last 10 evaluations."""
    from backend.models.forecast import ForecastResult, ModelVersion

    result = await db.execute(
        select(ModelVersion).where(
            ModelVersion.is_active.is_(True),
            ModelVersion.model_type == "prophet",
        )
    )
    active_models = result.scalars().all()

    for mv in active_models:
        eval_result = await db.execute(
            select(ForecastResult.error_pct)
            .where(
                ForecastResult.model_version_id == mv.id,
                ForecastResult.error_pct.is_not(None),
            )
            .order_by(ForecastResult.forecast_date.desc())
            .limit(10)
        )
        error_pcts = [r[0] for r in eval_result.all()]

        if error_pcts:
            rolling_mape = sum(error_pcts) / len(error_pcts)
            if mv.metrics is None:
                mv.metrics = {}
            mv.metrics = {
                **mv.metrics,
                "rolling_mape": round(rolling_mape, 4),
                "evaluated_count": len(error_pcts),
            }

    await db.commit()


# ---------------------------------------------------------------------------
# Task 15: Drift detection
# ---------------------------------------------------------------------------


async def _check_drift_async() -> dict:
    """Check for model drift using per-ticker calibrated baselines.

    Uses backtest MAPE × 1.5 as threshold instead of flat 20%.
    Tracks consecutive failures and demotes to experimental after 3.

    Returns:
        Dict with drift detection results.
    """
    from backend.models.backtest import BacktestRun
    from backend.models.forecast import ModelVersion

    retrain_triggered: list[str] = []
    degraded: list[str] = []
    experimental_demoted: list[str] = []

    async with async_session_factory() as db:
        # Get all active Prophet models
        result = await db.execute(
            select(ModelVersion).where(
                ModelVersion.is_active.is_(True),
                ModelVersion.model_type == "prophet",
            )
        )
        active_models = result.scalars().all()

        # Batch-fetch best backtest MAPE per ticker (avoids N+1)
        tickers = [mv.ticker for mv in active_models]
        if tickers:
            bt_result = await db.execute(
                select(
                    BacktestRun.ticker,
                    func.min(BacktestRun.mape).label("best_mape"),
                )
                .where(BacktestRun.ticker.in_(tickers))
                .group_by(BacktestRun.ticker)
            )
            backtest_mapes: dict[str, float] = {
                row.ticker: float(row.best_mape) for row in bt_result.all()
            }
        else:
            backtest_mapes = {}

        # Check each model against its calibrated threshold
        for mv in active_models:
            mape = (mv.metrics or {}).get("rolling_mape")
            if mape is None:
                continue

            backtest_mape = backtest_mapes.get(mv.ticker)
            threshold = compute_calibrated_threshold(backtest_mape)

            if mape > threshold:
                # Track consecutive failures
                metrics = dict(mv.metrics or {})
                failures = metrics.get("consecutive_drift_failures", 0) + 1
                metrics["consecutive_drift_failures"] = failures
                metrics["drift_threshold_used"] = round(threshold, 4)
                mv.metrics = metrics

                # Check for experimental demotion
                if should_demote_to_experimental(failures, mv.status):
                    mv.status = "experimental"
                    experimental_demoted.append(mv.ticker)
                    logger.warning(
                        "Model demoted to experimental for %s: %d consecutive failures",
                        mv.ticker,
                        failures,
                    )
                else:
                    mv.status = "degraded"
                    degraded.append(mv.ticker)

                retrain_triggered.append(mv.ticker)
                logger.warning(
                    "Drift detected for %s: MAPE=%.1f%% > %.1f%% calibrated threshold "
                    "(backtest baseline=%.1f%%, failures=%d)",
                    mv.ticker,
                    mape * 100,
                    threshold * 100,
                    (backtest_mape or 0) * 100,
                    failures,
                )
            else:
                # Reset consecutive failures on passing check
                metrics = dict(mv.metrics or {})
                if metrics.get("consecutive_drift_failures", 0) > 0:
                    metrics["consecutive_drift_failures"] = 0
                    mv.metrics = metrics

                # Self-healing: experimental → active if now passing
                if mv.status == "experimental":
                    mv.status = "active"
                    logger.info(
                        "Model self-healed for %s: MAPE=%.1f%% within threshold",
                        mv.ticker,
                        mape * 100,
                    )

        # Check volatility spikes for each ticker
        for mv in active_models:
            try:
                vol_result = await _check_volatility_spike(mv.ticker, db)
                if vol_result and mv.ticker not in retrain_triggered:
                    retrain_triggered.append(mv.ticker)
                    logger.warning("Volatility spike for %s — queuing retrain", mv.ticker)
            except Exception:
                logger.exception("Volatility check failed for %s", mv.ticker)

        await db.commit()

    # Queue retrains
    from backend.tasks.forecasting import retrain_single_ticker_task

    for ticker in retrain_triggered:
        retrain_single_ticker_task.delay(ticker)

    # Check VIX regime
    vix_regime = await _check_vix_regime()

    logger.info(
        "Drift check: %d degraded, %d experimental, %d retrain queued, VIX=%s",
        len(degraded),
        len(experimental_demoted),
        len(retrain_triggered),
        vix_regime,
    )
    return {
        "degraded": degraded,
        "experimental_demoted": experimental_demoted,
        "retrain_triggered": retrain_triggered,
        "vix_regime": vix_regime,
    }


async def _check_volatility_spike(ticker: str, db: AsyncSession) -> bool:
    """Check if a ticker's 5-day volatility exceeds 2x its 90-day average.

    Args:
        ticker: Stock ticker symbol.
        db: Async database session.

    Returns:
        True if volatility spike detected.
    """
    from backend.models.price import StockPrice

    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    result = await db.execute(
        select(StockPrice.close)
        .where(StockPrice.ticker == ticker, StockPrice.time >= ninety_days_ago)
        .order_by(StockPrice.time)
    )
    prices = [float(r[0]) for r in result.all()]

    if len(prices) < 10:
        return False

    import numpy as np

    returns = np.diff(np.log(prices))
    if len(returns) < 6:
        return False

    vol_5d = float(np.std(returns[-5:]))
    vol_90d = float(np.std(returns))

    return vol_90d > 0 and vol_5d > VOLATILITY_SPIKE_MULTIPLIER * vol_90d


async def _check_vix_regime() -> str:
    """Check VIX level to determine market regime.

    Returns:
        "high" if VIX > 30, "normal" otherwise.
    """
    try:
        import yfinance as yf

        vix = yf.Ticker("^VIX")
        hist = vix.history(period="1d")
        if not hist.empty:
            current_vix = float(hist["Close"].iloc[-1])
            return "high" if current_vix > VIX_HIGH_THRESHOLD else "normal"
    except Exception:
        logger.warning("Failed to fetch VIX — defaulting to 'normal'")

    return "normal"


# ---------------------------------------------------------------------------
# Task 16: Recommendation evaluation
# ---------------------------------------------------------------------------


async def _evaluate_recommendations_async() -> dict:
    """Evaluate past BUY/SELL recommendations at 30/90/180d horizons.

    Returns:
        Dict with evaluation counts.
    """
    import uuid as uuid_mod

    from backend.models.forecast import RecommendationOutcome
    from backend.models.recommendation import RecommendationSnapshot
    from backend.models.user import User

    today_dt = datetime.now(timezone.utc)
    evaluated = 0
    errors = 0

    async with async_session_factory() as db:
        # Get all users
        users = (await db.execute(select(User))).scalars().all()

        for user in users:
            # Get directional recommendations (BUY/SELL only)
            recs_result = await db.execute(
                select(RecommendationSnapshot).where(
                    RecommendationSnapshot.user_id == user.id,
                    RecommendationSnapshot.action.in_(["BUY", "SELL"]),
                )
            )
            recs = recs_result.scalars().all()

            for rec in recs:
                for horizon in EVAL_HORIZONS:
                    eval_date = rec.generated_at + timedelta(days=horizon)
                    if eval_date > today_dt:
                        continue

                    # Check if outcome already exists
                    existing = await db.execute(
                        select(RecommendationOutcome.id).where(
                            RecommendationOutcome.rec_generated_at == rec.generated_at,
                            RecommendationOutcome.rec_ticker == rec.ticker,
                            RecommendationOutcome.user_id == user.id,
                            RecommendationOutcome.horizon_days == horizon,
                        )
                    )
                    if existing.scalar_one_or_none() is not None:
                        continue

                    try:
                        # Get actual price at horizon date
                        actual = await _get_price_near_date(rec.ticker, eval_date.date(), db)
                        spy_at_rec = await _get_price_near_date("SPY", rec.generated_at.date(), db)
                        spy_at_eval = await _get_price_near_date("SPY", eval_date.date(), db)

                        if actual is None or spy_at_rec is None or spy_at_eval is None:
                            continue

                        price_at_rec = float(rec.price_at_recommendation)
                        return_pct = (actual - price_at_rec) / price_at_rec
                        spy_return_pct = (
                            (spy_at_eval - spy_at_rec) / spy_at_rec if spy_at_rec else 0.0
                        )
                        alpha_pct = return_pct - spy_return_pct

                        # BUY correct if return > 0, SELL correct if return < 0
                        if rec.action == "BUY":
                            was_correct = return_pct > 0
                        else:
                            was_correct = return_pct < 0

                        outcome = RecommendationOutcome(
                            id=uuid_mod.uuid4(),
                            user_id=user.id,
                            rec_generated_at=rec.generated_at,
                            rec_ticker=rec.ticker,
                            action=rec.action,
                            price_at_recommendation=price_at_rec,
                            horizon_days=horizon,
                            evaluated_at=today_dt,
                            actual_price=actual,
                            return_pct=round(return_pct, 4),
                            spy_return_pct=round(spy_return_pct, 4),
                            alpha_pct=round(alpha_pct, 4),
                            action_was_correct=was_correct,
                            created_at=today_dt,
                        )
                        db.add(outcome)
                        evaluated += 1

                    except Exception:
                        errors += 1
                        logger.exception(
                            "Failed to evaluate rec %s %s at %dd",
                            rec.ticker,
                            rec.action,
                            horizon,
                        )

            await db.commit()

    logger.info("Recommendation evaluation: %d evaluated, %d errors", evaluated, errors)
    return {"status": "success", "evaluated": evaluated, "errors": errors}


async def _get_price_near_date(ticker: str, target: date, db: AsyncSession) -> float | None:
    """Get closing price on or near a target date (handles weekends/holidays).

    Args:
        ticker: Stock ticker.
        target: Target date.
        db: Async database session.

    Returns:
        Closing price or None if not found.
    """
    from backend.models.price import StockPrice

    for offset in range(4):  # Try target, then up to 3 days before
        check_date = target - timedelta(days=offset)
        result = await db.execute(
            select(StockPrice.close)
            .where(
                StockPrice.ticker == ticker,
                StockPrice.time
                >= datetime.combine(check_date, datetime.min.time(), tzinfo=timezone.utc),
                StockPrice.time
                < datetime.combine(
                    check_date + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ),
            )
            .limit(1)
        )
        price = result.scalar_one_or_none()
        if price is not None:
            return float(price)

    return None


# ---------------------------------------------------------------------------
# Celery task wrappers
# ---------------------------------------------------------------------------


@celery_app.task(name="backend.tasks.evaluation.evaluate_forecasts_task")
def evaluate_forecasts_task() -> dict:
    """Nightly forecast evaluation — fill actuals and compute MAPE.

    Returns:
        Dict with evaluation status.
    """
    logger.info("Starting forecast evaluation")
    return asyncio.run(_evaluate_forecasts_async())


@celery_app.task(name="backend.tasks.evaluation.check_drift_task")
def check_drift_task() -> dict:
    """Check for model drift, volatility spikes, and VIX regime.

    Returns:
        Dict with drift detection results.
    """
    logger.info("Starting drift detection")
    return asyncio.run(_check_drift_async())


@celery_app.task(name="backend.tasks.evaluation.evaluate_recommendations_task")
def evaluate_recommendations_task() -> dict:
    """Evaluate past BUY/SELL recommendations against actuals.

    Returns:
        Dict with evaluation status.
    """
    logger.info("Starting recommendation evaluation")
    return asyncio.run(_evaluate_recommendations_async())
