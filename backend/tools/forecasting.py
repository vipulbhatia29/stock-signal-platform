"""Prophet forecasting engine — training, prediction, Sharpe direction, correlation."""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pandas as pd
from prophet import Prophet
from prophet.serialize import model_from_json, model_to_json
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.forecast import ForecastResult, ModelVersion
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot

# Re-export for backwards-compat — the canonical home is
# ``backend.services.sentiment_regressors`` so the BacktestEngine can import
# the helper without dragging Prophet into its module load chain. Tests that
# previously patched ``backend.tools.forecasting.fetch_sentiment_regressors``
# continue to work via this binding.
from backend.services.sentiment_regressors import (  # noqa: F401  (re-export)
    fetch_sentiment_regressors,
)

logger = logging.getLogger(__name__)

# Directory for serialized Prophet models
MODEL_DIR = Path("data/models/prophet")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# Prophet configuration (spec §4.2)
PROPHET_CONFIG = {
    "changepoint_prior_scale": 0.05,
    "seasonality_prior_scale": 10,
    "yearly_seasonality": True,
    "weekly_seasonality": True,
    "daily_seasonality": False,
    "interval_width": 0.80,
    "mcmc_samples": 0,
}

# Default forecast horizons (spec §4.3)
DEFAULT_HORIZONS = [90, 180, 270]

# Minimum training data points
MIN_DATA_POINTS = 200

# Minimum sentiment coverage ratio to include regressors in Prophet.
# Below this threshold, the sparse regressor matrix causes numerically
# unstable coefficient estimates (divide-by-zero in prediction).
MIN_SENTIMENT_COVERAGE = 0.3


async def train_prophet_model(ticker: str, db: AsyncSession) -> ModelVersion:
    """Train a Prophet model for a ticker and store the versioned artifact.

    Args:
        ticker: Stock ticker symbol.
        db: Async database session.

    Returns:
        The newly created ModelVersion row.

    Raises:
        ValueError: If insufficient price data for training.
    """
    # Fetch 2 years of adjusted close prices
    two_years_ago = datetime.now(timezone.utc).date() - timedelta(days=730)
    result = await db.execute(
        select(StockPrice.time, StockPrice.adj_close)
        .where(StockPrice.ticker == ticker, StockPrice.time >= two_years_ago)
        .order_by(StockPrice.time)
    )
    rows = result.all()

    if len(rows) < MIN_DATA_POINTS:
        raise ValueError(
            f"Insufficient data for {ticker}: {len(rows)} points (need {MIN_DATA_POINTS})"
        )

    # Build Prophet DataFrame
    df = pd.DataFrame(rows, columns=pd.Index(["ds", "y"]))
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    df["y"] = df["y"].astype(float)

    # Configure and fit
    model = Prophet(**PROPHET_CONFIG)

    # ── Sentiment regressors (coverage-gated to avoid numerical instability) ──
    ds_min = cast(date, pd.Timestamp(str(df["ds"].min())).date())
    ds_max = cast(date, pd.Timestamp(str(df["ds"].max())).date())
    sentiment_df = await fetch_sentiment_regressors(ticker, ds_min, ds_max, db)
    if sentiment_df is not None and not sentiment_df.empty:
        coverage = len(sentiment_df) / len(df)
        if coverage >= MIN_SENTIMENT_COVERAGE:
            df = df.merge(sentiment_df, on="ds", how="left").fillna(0.0)
            model.add_regressor("stock_sentiment")
            model.add_regressor("sector_sentiment")
            model.add_regressor("macro_sentiment")
            logger.info(
                "Added 3 sentiment regressors for %s (coverage=%.0f%%, %d/%d days)",
                ticker,
                coverage * 100,
                len(sentiment_df),
                len(df),
            )
        else:
            logger.info(
                "Skipping sentiment regressors for %s (coverage=%.0f%%, need %.0f%%)",
                ticker,
                coverage * 100,
                MIN_SENTIMENT_COVERAGE * 100,
            )

    model.fit(df)

    # Determine next version number
    version_result = await db.execute(
        select(ModelVersion.version)
        .where(ModelVersion.ticker == ticker, ModelVersion.model_type == "prophet")
        .order_by(ModelVersion.version.desc())
        .limit(1)
    )
    last_version = version_result.scalar_one_or_none()
    next_version = (last_version or 0) + 1

    # Retire previous active model
    await db.execute(
        update(ModelVersion)
        .where(
            ModelVersion.ticker == ticker,
            ModelVersion.model_type == "prophet",
            ModelVersion.is_active.is_(True),
        )
        .values(is_active=False, status="retired")
    )

    # Serialize model artifact using Prophet's JSON serialization (safe, no pickle)
    artifact_path = str(MODEL_DIR / f"{ticker}_prophet_v{next_version}.json")
    with open(artifact_path, "w") as f:
        f.write(model_to_json(model))

    # Create ModelVersion row
    model_version = ModelVersion(
        id=uuid.uuid4(),
        ticker=ticker,
        model_type="prophet",
        version=next_version,
        is_active=True,
        trained_at=datetime.now(timezone.utc),
        training_data_start=df["ds"].min().date(),
        training_data_end=df["ds"].max().date(),
        data_points=len(df),
        hyperparameters=PROPHET_CONFIG,
        metrics={},
        status="active",
        artifact_path=artifact_path,
    )
    db.add(model_version)
    await db.flush()

    logger.info(
        "Trained Prophet v%d for %s (%d data points, %s to %s)",
        next_version,
        ticker,
        len(df),
        model_version.training_data_start,
        model_version.training_data_end,
    )
    return model_version


async def predict_forecast(
    model_version: ModelVersion,
    db: AsyncSession,
    horizons: list[int] | None = None,
) -> list[ForecastResult]:
    """Generate forecasts from a trained Prophet model.

    Args:
        model_version: The ModelVersion with artifact_path.
        db: Async database session, used to fetch real sentiment regressors
            for the predict-time future DataFrame (KAN-422 Spec B B3).
        horizons: List of horizon days (default: [90, 180, 270]).

    Returns:
        List of ForecastResult objects (not yet persisted).

    Raises:
        FileNotFoundError: If model artifact is missing.
    """
    if horizons is None:
        horizons = DEFAULT_HORIZONS

    artifact_path = model_version.artifact_path
    if not artifact_path or not Path(artifact_path).exists():
        raise FileNotFoundError(
            f"Model artifact not found: {artifact_path} "
            f"(ticker={model_version.ticker}, v{model_version.version})"
        )

    with open(artifact_path) as f:
        model: Prophet = model_from_json(f.read())

    # Extract last training price for scale-appropriate price floor.
    # Prophet can extrapolate to negative values for volatile/declining stocks;
    # equities cannot trade below $0, so we clamp to 1% of last known price
    # (minimum $0.01) to prevent negative prices from poisoning downstream math.
    history = getattr(model, "history", None)
    last_known_price = (
        float(history["y"].iloc[-1]) if history is not None and len(history) > 0 else 0.0
    )
    price_floor = max(0.01, last_known_price * 0.01)

    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
    results: list[ForecastResult] = []

    # Determine if model was trained with sentiment regressors
    sentiment_regressor_names = ["stock_sentiment", "sector_sentiment", "macro_sentiment"]
    has_sentiment_regressors = any(r in model.extra_regressors for r in sentiment_regressor_names)

    # KAN-422 Spec B B3 fix — build the regressor series that Prophet will see
    # at predict time. The previous implementation hard-coded 0.0 for every row
    # of the future DataFrame, silently zeroing the trained regressor beta
    # contribution. This revision uses a hybrid source:
    #
    #   1. HISTORICAL ROWS (ds <= training_end): read straight from
    #      ``model.history``, which is Prophet's snapshot of the exact values
    #      it was fit on. No DB query for these dates — eliminates any
    #      training-serving skew from downstream news reprocessing, and the
    #      values are guaranteed to match the training fit 1:1.
    #
    #   2. POST-TRAINING ROWS (training_end < ds <= today): fetch FRESH values
    #      from NewsSentimentDaily for this narrow window only. These dates
    #      were never in the training frame, so there is no skew risk, and
    #      we capture the most recent real signal for the gap between model
    #      training and today — the exact rows the earlier implementation
    #      silently clobbered with a stale projection.
    #
    #   3. FORECAST ROWS (ds > today): filled with a 7-day trailing mean
    #      anchored to the **most recent available** sentiment date (not
    #      training_end). For a model trained 30 days ago, this means
    #      "sentiment as of today, held constant" rather than "sentiment as
    #      of a month ago, held constant" — a meaningful quality improvement
    #      for the nightly refresh path.
    combined_sentiment_df: pd.DataFrame | None = None
    sentiment_projection: dict[str, float] = {}
    training_end: date | None = None
    if settings.PROPHET_REAL_SENTIMENT_ENABLED and has_sentiment_regressors:
        _hist = getattr(model, "history", None)
        if _hist is None or len(_hist) == 0:
            raise RuntimeError(
                f"predict_forecast: model {model_version.ticker} "
                f"v{model_version.version} has sentiment regressors but no "
                "training history — artifact is corrupt or empty"
            )

        training_end = _hist["ds"].max().date()
        assert isinstance(training_end, date)

        # Step 1 — historical rows straight from the serialized model.
        cols = ["ds", *sentiment_regressor_names]
        history_sent_df: pd.DataFrame = _hist[cols].copy()

        # Step 2 — post-training-window fresh fetch.
        if training_end < today:
            post_start_date = training_end + timedelta(days=1)
            post_df = await fetch_sentiment_regressors(
                model_version.ticker,
                post_start_date,
                today,
                db,
            )
            if post_df is not None and not post_df.empty:
                combined_sentiment_df = pd.concat([history_sent_df, post_df], ignore_index=True)
            else:
                combined_sentiment_df = history_sent_df
                logger.warning(
                    "predict_forecast: no post-training sentiment data found "
                    "for %s in window (%s, %s]; forecasts will project from "
                    "training-window sentiment only, which may be stale",
                    model_version.ticker,
                    training_end,
                    today,
                )
        else:
            combined_sentiment_df = history_sent_df

        # Step 3 — 7-day trailing mean anchored to the most recent available
        # date (training_end for same-day predictions, today for stale models
        # that ingested fresh post-training sentiment). Falls back to the
        # full-window mean if there's less than 7 days of data at all.
        most_recent_date = combined_sentiment_df["ds"].max()
        cutoff = most_recent_date - pd.Timedelta(days=7)
        recent = combined_sentiment_df[combined_sentiment_df["ds"] >= cutoff]
        if recent.empty:
            recent = combined_sentiment_df

        for col in sentiment_regressor_names:
            sentiment_projection[col] = float(recent[col].mean()) if not recent.empty else 0.0

        # Loud degradation warning — the whole reason this PR exists is to
        # eliminate silent 0.0 projection. If the computed projection is still
        # all-zero despite having regressors, operators need to know so they
        # can investigate ingestion upstream. This is NOT a quiet fallback.
        if all(abs(v) < 1e-9 for v in sentiment_projection.values()):
            logger.error(
                "predict_forecast: %s v%d was trained with sentiment "
                "regressors but the projection collapsed to all-zero (training "
                "and post-training sentiment are both zero). Predictions will "
                "silently ignore the trained sentiment beta. Check "
                "news_sentiment_daily ingestion for %s.",
                model_version.ticker,
                model_version.version,
                model_version.ticker,
            )

    for horizon in horizons:
        # Create future dataframe for the specific target date
        target_date = today + timedelta(days=horizon)
        future = model.make_future_dataframe(periods=horizon, freq="D")

        # Merge real sentiment values for historical + post-training rows.
        # The combined frame covers every date <= today; anything past today
        # is NaN after the left-join and gets the projection. We NEVER
        # overwrite non-NaN cells, so real merged values are preserved.
        if settings.PROPHET_REAL_SENTIMENT_ENABLED and has_sentiment_regressors:
            if combined_sentiment_df is None or training_end is None:
                raise RuntimeError(
                    "predict_forecast invariant violated: "
                    "has_sentiment_regressors=True but sentiment state is None"
                )
            future = future.merge(combined_sentiment_df, on="ds", how="left")
            for col, projected in sentiment_projection.items():
                nan_mask = future[col].isna()
                future.loc[nan_mask, col] = projected
                # Cast to float64 once rows are filled; asserts there are no
                # lingering NaNs so a future bug can't silently zero the col.
                future[col] = future[col].astype("float64")
                if bool(future[col].isna().any()):
                    raise RuntimeError(
                        f"predict_forecast: {col} still has NaN after merge + "
                        f"projection for {model_version.ticker} — refusing to "
                        "silently zero (regression of the KAN-422 B3 bug)"
                    )
        elif has_sentiment_regressors:
            # PROPHET_REAL_SENTIMENT_ENABLED=False — emergency rollback path.
            # Fill all sentiment regressor columns with 0.0, reproducing the
            # pre-B3 behavior. Logged at WARNING so operators know the flag
            # is active and forecasts are degraded.
            logger.warning(
                "predict_forecast: PROPHET_REAL_SENTIMENT_ENABLED=False — "
                "zeroing sentiment regressors for %s (rollback mode)",
                model_version.ticker,
            )
            for col in sentiment_regressor_names:
                future[col] = 0.0

        # Prophet's predict() is CPU-bound (NumPy + Stan), so we run it on a
        # worker thread to avoid starving the event loop in async Celery tasks.
        forecast = await asyncio.to_thread(model.predict, future)

        # Get the prediction for the target date
        target_row = forecast[forecast["ds"].dt.date == target_date]
        if target_row.empty:
            # Fallback: use the last row (closest to target)
            target_row = forecast.tail(1)

        row = target_row.iloc[0]
        raw_price = float(row["yhat"])
        raw_lower = float(row["yhat_lower"])
        raw_upper = float(row["yhat_upper"])

        # Apply price floor — log a warning when clamping occurs
        if raw_price < price_floor or raw_lower < price_floor or raw_upper < price_floor:
            logger.warning(
                "Prophet predicted non-positive price for %s horizon=%dd "
                "(yhat=%.4f, lower=%.4f, upper=%.4f); flooring to %.4f",
                model_version.ticker,
                horizon,
                raw_price,
                raw_lower,
                raw_upper,
                price_floor,
            )

        results.append(
            ForecastResult(
                forecast_date=today,
                ticker=model_version.ticker,
                horizon_days=horizon,
                model_version_id=model_version.id,
                predicted_price=round(max(raw_price, price_floor), 2),
                predicted_lower=round(max(raw_lower, price_floor), 2),
                predicted_upper=round(max(raw_upper, price_floor), 2),
                target_date=target_date,
                created_at=now,
            )
        )

    logger.info(
        "Generated %d forecasts for %s (v%d): %s",
        len(results),
        model_version.ticker,
        model_version.version,
        [f"+{h}d" for h in horizons],
    )
    return results


async def compute_sharpe_direction(ticker: str, db: AsyncSession) -> str:
    """Compute the direction of Sharpe ratio trend over the last 30 days.

    Args:
        ticker: Stock ticker symbol.
        db: Async database session.

    Returns:
        One of "improving", "flat", or "declining".
    """
    # Latest Sharpe ratio
    latest_result = await db.execute(
        select(SignalSnapshot.sharpe_ratio, SignalSnapshot.computed_at)
        .where(SignalSnapshot.ticker == ticker)
        .order_by(SignalSnapshot.computed_at.desc())
        .limit(1)
    )
    latest = latest_result.first()

    if latest is None or latest.sharpe_ratio is None:
        return "flat"

    # Sharpe ratio from ~30 days ago
    thirty_days_ago = latest.computed_at - timedelta(days=30)
    past_result = await db.execute(
        select(SignalSnapshot.sharpe_ratio)
        .where(
            SignalSnapshot.ticker == ticker,
            SignalSnapshot.computed_at <= thirty_days_ago,
        )
        .order_by(SignalSnapshot.computed_at.desc())
        .limit(1)
    )
    past = past_result.scalar_one_or_none()

    if past is None:
        return "flat"

    diff = latest.sharpe_ratio - past
    if diff > 0.1:
        return "improving"
    elif diff < -0.1:
        return "declining"
    return "flat"


async def compute_portfolio_correlation_matrix(
    tickers: list[str],
    db: AsyncSession,
    period_days: int = 90,
) -> pd.DataFrame:
    """Compute daily-returns correlation matrix for a set of tickers.

    Args:
        tickers: List of ticker symbols.
        db: Async database session.
        period_days: Number of days of price history to use.

    Returns:
        Symmetric n×n correlation DataFrame with tickers as index/columns.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)

    result = await db.execute(
        select(StockPrice.ticker, StockPrice.time, StockPrice.close)
        .where(
            StockPrice.ticker.in_(tickers),
            StockPrice.time >= cutoff,
        )
        .order_by(StockPrice.time)
    )
    rows = result.all()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=pd.Index(["ticker", "time", "close"]))
    df["time"] = pd.to_datetime(df["time"]).dt.date
    pivot = df.pivot_table(index="time", columns="ticker", values="close")
    pivot = pivot.dropna(axis=1, thresh=len(pivot) // 2)

    if pivot.shape[1] < 2:
        return pd.DataFrame()

    returns_df = pivot.pct_change(fill_method=None).dropna()
    corr_matrix = returns_df.corr()
    return corr_matrix.fillna(0.0)
