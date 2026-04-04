"""Prophet forecasting engine — training, prediction, Sharpe direction, correlation."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from prophet import Prophet
from prophet.serialize import model_from_json, model_to_json
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.forecast import ForecastResult, ModelVersion
from backend.models.news_sentiment import NewsSentimentDaily
from backend.models.price import StockPrice
from backend.models.signal import SignalSnapshot

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
    df = pd.DataFrame(rows, columns=["ds", "y"])
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    df["y"] = df["y"].astype(float)

    # Configure and fit
    model = Prophet(**PROPHET_CONFIG)

    # ── Sentiment regressors (feature-flagged: only if data exists) ──
    sentiment_df = await _fetch_sentiment_regressors(ticker, df["ds"].min(), df["ds"].max(), db)
    if sentiment_df is not None and not sentiment_df.empty:
        df = df.merge(sentiment_df, on="ds", how="left").fillna(0.0)
        model.add_regressor("stock_sentiment")
        model.add_regressor("sector_sentiment")
        model.add_regressor("macro_sentiment")
        logger.info(
            "Added 3 sentiment regressors for %s (%d data points)",
            ticker,
            len(sentiment_df),
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


def predict_forecast(
    model_version: ModelVersion,
    horizons: list[int] | None = None,
) -> list[ForecastResult]:
    """Generate forecasts from a trained Prophet model.

    Args:
        model_version: The ModelVersion with artifact_path.
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

    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
    results: list[ForecastResult] = []

    # Determine if model was trained with sentiment regressors
    sentiment_regressor_names = ["stock_sentiment", "sector_sentiment", "macro_sentiment"]
    has_sentiment_regressors = any(r in model.extra_regressors for r in sentiment_regressor_names)

    for horizon in horizons:
        # Create future dataframe for the specific target date
        target_date = today + timedelta(days=horizon)
        future = model.make_future_dataframe(periods=horizon, freq="D")

        # Add sentiment regressor columns to future DataFrame if model uses them.
        # KNOWN LIMITATION: Historical dates also get 0.0 instead of the actual
        # sentiment used during training. This underestimates the regressor effect
        # in Prophet's predictions. Future work: fetch historical sentiment from DB
        # (requires making predict_forecast async) or cache in model artifact.
        if has_sentiment_regressors:
            future["stock_sentiment"] = 0.0
            future["sector_sentiment"] = 0.0
            future["macro_sentiment"] = 0.0

        forecast = model.predict(future)

        # Get the prediction for the target date
        target_row = forecast[forecast["ds"].dt.date == target_date]
        if target_row.empty:
            # Fallback: use the last row (closest to target)
            target_row = forecast.tail(1)

        row = target_row.iloc[0]
        results.append(
            ForecastResult(
                forecast_date=today,
                ticker=model_version.ticker,
                horizon_days=horizon,
                model_version_id=model_version.id,
                predicted_price=round(float(row["yhat"]), 2),
                predicted_lower=round(float(row["yhat_lower"]), 2),
                predicted_upper=round(float(row["yhat_upper"]), 2),
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


async def _fetch_sentiment_regressors(
    ticker: str,
    start_date: datetime | pd.Timestamp,
    end_date: datetime | pd.Timestamp,
    db: AsyncSession,
) -> pd.DataFrame | None:
    """Fetch daily sentiment data as Prophet regressors.

    Args:
        ticker: Stock ticker symbol.
        start_date: Training data start date.
        end_date: Training data end date.
        db: Async database session.

    Returns:
        DataFrame with columns [ds, stock_sentiment, sector_sentiment, macro_sentiment],
        or None if no sentiment data exists for this ticker.
    """
    start_d = start_date.date() if hasattr(start_date, "date") else start_date
    end_d = end_date.date() if hasattr(end_date, "date") else end_date

    result = await db.execute(
        select(
            NewsSentimentDaily.date,
            NewsSentimentDaily.stock_sentiment,
            NewsSentimentDaily.sector_sentiment,
            NewsSentimentDaily.macro_sentiment,
        ).where(
            NewsSentimentDaily.ticker == ticker,
            NewsSentimentDaily.date >= start_d,
            NewsSentimentDaily.date <= end_d,
        )
    )
    rows = result.all()
    if not rows:
        return None

    df = pd.DataFrame(
        rows,
        columns=["ds", "stock_sentiment", "sector_sentiment", "macro_sentiment"],
    )
    df["ds"] = pd.to_datetime(df["ds"]).dt.tz_localize(None)
    return df


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

    df = pd.DataFrame(rows, columns=["ticker", "time", "close"])
    df["time"] = pd.to_datetime(df["time"]).dt.date
    pivot = df.pivot_table(index="time", columns="ticker", values="close")
    pivot = pivot.dropna(axis=1, thresh=len(pivot) // 2)

    if pivot.shape[1] < 2:
        return pd.DataFrame()

    returns_df = pivot.pct_change(fill_method=None).dropna()
    corr_matrix = returns_df.corr()
    return corr_matrix.fillna(0.0)
