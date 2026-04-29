"""Walk-forward backtesting engine for Prophet model validation."""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.price import StockPrice
from backend.services.sentiment_regressors import fetch_sentiment_regressors

logger = logging.getLogger(__name__)


@dataclass
class WindowSpec:
    """Single walk-forward window definition."""

    train_start: date
    train_end: date
    test_date: date  # the date we're predicting for


@dataclass
class BacktestMetrics:
    """Computed metrics from a backtest run."""

    mape: float
    mae: float
    rmse: float
    direction_accuracy: float
    ci_containment: float
    ci_bias: str  # "above", "below", "balanced"
    avg_interval_width: float
    num_windows: int
    per_window_results: list[dict] = field(default_factory=list)


class BacktestEngine:
    """Walk-forward validation for Prophet models.

    Uses expanding window: training set grows with each step.
    Test point is always one step ahead of training data.
    No overlap between any test period and training data.
    """

    @staticmethod
    def _safe_float(value: float, default: float = 0.0) -> float:
        """Return value if finite, else default. Guards against NaN/Inf."""
        return value if math.isfinite(value) else default

    def _generate_expanding_windows(
        self,
        data_start: date,
        data_end: date,
        min_train_days: int = 365,
        step_days: int = 30,
        horizon_days: int = 90,
    ) -> list[WindowSpec]:
        """Generate expanding window specifications.

        Args:
            data_start: First available data point.
            data_end: Last available data point.
            min_train_days: Minimum training period.
            step_days: Days to advance between windows.
            horizon_days: Forecast horizon.

        Returns:
            List of WindowSpec with train_start, train_end, test_date.
        """
        windows: list[WindowSpec] = []
        first_train_end = data_start + timedelta(days=min_train_days)
        current_train_end = first_train_end

        while True:
            test_date = current_train_end + timedelta(days=horizon_days)
            # Strict >=: we need actual price data *after* test_date to verify
            # the prediction, so test_date must be strictly before data_end.
            if test_date >= data_end:
                break

            windows.append(
                WindowSpec(
                    train_start=data_start,
                    train_end=current_train_end,
                    test_date=test_date,
                )
            )
            current_train_end += timedelta(days=step_days)

        return windows

    def _compute_mape(self, actuals: list[float], predicted: list[float]) -> float:
        """Mean Absolute Percentage Error.

        Skips zero actuals (MAPE undefined). Returns NaN if all actuals
        are zero — caller should check with math.isfinite().
        """
        if not actuals:
            return 0.0
        errors = []
        for a, p in zip(actuals, predicted, strict=True):
            if a != 0:
                errors.append(abs(a - p) / abs(a))
        if not errors:
            logger.warning("MAPE: all actuals are zero — returning NaN")
            return float("nan")
        return self._safe_float(sum(errors) / len(errors))

    def _compute_mae(self, actuals: list[float], predicted: list[float]) -> float:
        """Mean Absolute Error."""
        if not actuals:
            return 0.0
        return self._safe_float(
            sum(abs(a - p) for a, p in zip(actuals, predicted, strict=True)) / len(actuals)
        )

    def _compute_rmse(self, actuals: list[float], predicted: list[float]) -> float:
        """Root Mean Squared Error."""
        if not actuals:
            return 0.0
        mse = sum((a - p) ** 2 for a, p in zip(actuals, predicted, strict=True)) / len(actuals)
        return self._safe_float(math.sqrt(mse))

    def _compute_direction_accuracy(
        self,
        base_prices: list[float],
        actuals: list[float],
        predicted: list[float],
    ) -> float:
        """Percentage of correct up/down predictions.

        When actual == base (flat), both actual_up and pred_up are False,
        so it counts as correct. This is intentional: neither direction
        was wrong when the price didn't move.
        """
        if not actuals:
            return 0.0
        correct = 0
        for base, actual, pred in zip(base_prices, actuals, predicted, strict=True):
            actual_up = actual > base
            pred_up = pred > base
            if actual_up == pred_up:
                correct += 1
        return correct / len(actuals)

    def _compute_ci_containment(
        self,
        actuals: list[float],
        lowers: list[float],
        uppers: list[float],
    ) -> float:
        """Percentage of actuals within predicted confidence interval."""
        if not actuals:
            return 0.0
        contained = sum(
            1 for a, lo, hi in zip(actuals, lowers, uppers, strict=True) if lo <= a <= hi
        )
        return contained / len(actuals)

    def _compute_ci_bias(
        self,
        actuals: list[float],
        predicted: list[float],
    ) -> str:
        """Whether actuals are systematically above/below predictions."""
        if not actuals:
            return "balanced"
        above = sum(1 for a, p in zip(actuals, predicted, strict=True) if a > p)
        ratio = above / len(actuals)
        if ratio > 0.6:
            return "above"
        elif ratio < 0.4:
            return "below"
        return "balanced"

    @staticmethod
    def _fit_and_predict_sync(
        train_df: pd.DataFrame,
        test_date: date,
        horizon_days: int,
        has_sentiment: bool,
    ) -> tuple[float, float, float]:
        """Fit a throwaway Prophet model and predict for test_date.

        This is a pure-sync function designed to run inside
        ``asyncio.to_thread`` — Prophet's Stan backend is CPU-bound.

        Args:
            train_df: Training DataFrame with columns [ds, y] and optionally
                [stock_sentiment, sector_sentiment, macro_sentiment].
            test_date: The date we want a prediction for.
            horizon_days: Number of days from last train date to test_date.
            has_sentiment: Whether sentiment regressor columns are present.

        Returns:
            Tuple of (expected_return_pct, return_lower_pct, return_upper_pct).
        """
        from prophet import Prophet  # lazy import — Prophet is heavy

        from backend.tools.forecasting import PROPHET_CONFIG

        model = Prophet(**PROPHET_CONFIG)
        if has_sentiment:
            model.add_regressor("stock_sentiment")
            model.add_regressor("sector_sentiment")
            model.add_regressor("macro_sentiment")

        model.fit(train_df)

        # Make a future dataframe extending to test_date
        future = model.make_future_dataframe(periods=horizon_days, freq="D")

        # Fill sentiment for future rows with the trailing 7-day mean if available
        if has_sentiment:
            for col in ("stock_sentiment", "sector_sentiment", "macro_sentiment"):
                mean_val = float(train_df[col].tail(7).mean()) if col in train_df.columns else 0.0
                if col not in future.columns:
                    future[col] = 0.0
                future[col] = future[col].fillna(mean_val)

        forecast = model.predict(future)

        # Find the row closest to test_date
        test_ts = pd.Timestamp(test_date)
        target_row = forecast[forecast["ds"].dt.date == test_date]
        if target_row.empty:
            # Fallback: closest row by absolute distance
            idx = (forecast["ds"] - test_ts).abs().idxmin()
            target_row = forecast.loc[[idx]]

        row = target_row.iloc[0]
        return float(row["yhat"]), float(row["yhat_lower"]), float(row["yhat_upper"])

    async def run_walk_forward(
        self,
        ticker: str,
        db: AsyncSession,
        horizon_days: int = 90,
        min_train_days: int = 365,
        step_days: int = 30,
    ) -> "BacktestMetrics":
        """Run walk-forward validation for a ticker using Prophet.

        Expands the training window in ``step_days`` increments, fits a
        throwaway Prophet model for each window, and compares predictions
        against held-out actuals at ``horizon_days`` out.

        Args:
            ticker: Stock ticker symbol.
            db: Async database session.
            horizon_days: Days ahead to forecast at each window.
            min_train_days: Minimum training period in days.
            step_days: Days to advance between walk-forward windows.

        Returns:
            BacktestMetrics aggregating all windows.
        """
        # ── 1. Load all prices for the ticker ──────────────────────────────
        result = await db.execute(
            select(StockPrice.time, StockPrice.close)
            .where(StockPrice.ticker == ticker)
            .order_by(StockPrice.time)
        )
        rows = result.all()

        if not rows:
            logger.warning("run_walk_forward: no price data for %s", ticker)
            return BacktestMetrics(
                mape=0.0,
                mae=0.0,
                rmse=0.0,
                direction_accuracy=0.0,
                ci_containment=0.0,
                ci_bias="balanced",
                avg_interval_width=0.0,
                num_windows=0,
            )

        # Build a {date: close} lookup and sorted date list
        price_by_date: dict[date, float] = {}
        for time_val, close in rows:
            if hasattr(time_val, "date"):
                d = time_val.date()
            else:
                d = time_val
            price_by_date[d] = float(close)

        sorted_dates = sorted(price_by_date.keys())
        data_start = sorted_dates[0]
        data_end = sorted_dates[-1]

        # ── 2. Generate windows ────────────────────────────────────────────
        windows = self._generate_expanding_windows(
            data_start=data_start,
            data_end=data_end,
            min_train_days=min_train_days,
            step_days=step_days,
            horizon_days=horizon_days,
        )

        if not windows:
            logger.info(
                "run_walk_forward: insufficient data for %s (%d days, need %d + %d)",
                ticker,
                (data_end - data_start).days,
                min_train_days,
                horizon_days,
            )
            return BacktestMetrics(
                mape=0.0,
                mae=0.0,
                rmse=0.0,
                direction_accuracy=0.0,
                ci_containment=0.0,
                ci_bias="balanced",
                avg_interval_width=0.0,
                num_windows=0,
            )

        # ── 3a. Pre-load sentiment ONCE for the full data range ────────────
        # Previously this was fetched per-window inside the loop, which issued
        # ~110 redundant queries per ticker against news_sentiment_daily.
        # Now: one bounded-range query, then in-memory slice per window.
        #
        # Wrapped in try/except so a transient DB blip on the bulk fetch
        # gracefully degrades to "no sentiment for this run" instead of
        # killing all ~110 windows for the ticker (the per-window pattern
        # would have only lost one window).
        sentiment_df: pd.DataFrame | None
        try:
            sentiment_df = await fetch_sentiment_regressors(
                ticker,
                data_start,
                data_end,
                db,
            )
        except Exception:
            logger.warning(
                "Failed to pre-load sentiment for %s backtest — "
                "falling back to no sentiment regressors",
                ticker,
                exc_info=True,
            )
            sentiment_df = None

        sentiment_indexed: pd.DataFrame | None = None
        if sentiment_df is not None and not sentiment_df.empty:
            sentiment_indexed = sentiment_df.set_index("ds").sort_index()

        # ── 3. Walk through windows ────────────────────────────────────────
        actuals: list[float] = []
        predicted: list[float] = []
        base_prices: list[float] = []
        lowers: list[float] = []
        uppers: list[float] = []

        for window in windows:
            # Slice training prices for this window
            train_dates = [d for d in sorted_dates if window.train_start <= d <= window.train_end]
            if len(train_dates) < 30:  # need at least 30 observations
                continue

            actual_price = price_by_date.get(window.test_date)
            if actual_price is None:
                # Look for the nearest available date within ±5 days
                for offset in range(1, 6):
                    actual_price = price_by_date.get(window.test_date + timedelta(days=offset))
                    if actual_price is not None:
                        break
                    actual_price = price_by_date.get(window.test_date - timedelta(days=offset))
                    if actual_price is not None:
                        break
            if actual_price is None:
                continue

            # Base price = last training price (for direction accuracy)
            base_price = price_by_date.get(window.train_end) or price_by_date.get(train_dates[-1])
            if base_price is None:
                continue

            # Build training DataFrame
            train_closes = [price_by_date[d] for d in train_dates]
            train_df = pd.DataFrame(
                {
                    "ds": pd.to_datetime(train_dates),
                    "y": train_closes,
                }
            )

            # Slice the pre-loaded sentiment frame in memory (no DB call).
            # .loc[start:end] is inclusive on both ends for a sorted index.
            window_sentiment: pd.DataFrame | None = None
            if sentiment_indexed is not None:
                start_ts = pd.Timestamp(window.train_start)
                end_ts = pd.Timestamp(window.train_end)
                slice_df = sentiment_indexed.loc[start_ts:end_ts]
                if not slice_df.empty:
                    window_sentiment = slice_df.reset_index()

            has_sentiment = window_sentiment is not None and not window_sentiment.empty
            if has_sentiment and window_sentiment is not None:
                train_df = train_df.merge(window_sentiment, on="ds", how="left").fillna(0.0)

            # Compute horizon from last train date to test date
            actual_horizon = (window.test_date - window.train_end).days

            try:
                yhat, yhat_lower, yhat_upper = await asyncio.to_thread(
                    self._fit_and_predict_sync,
                    train_df,
                    window.test_date,
                    actual_horizon,
                    has_sentiment,
                )
            except Exception:
                logger.exception(
                    "Prophet fit failed for %s window %s–%s → %s; skipping",
                    ticker,
                    window.train_start,
                    window.train_end,
                    window.test_date,
                )
                continue

            # Apply price floor to predictions (equities can't go negative)
            price_floor = max(0.01, base_price * 0.01)
            yhat = max(yhat, price_floor)
            yhat_lower = max(yhat_lower, price_floor)
            yhat_upper = max(yhat_upper, price_floor)

            actuals.append(actual_price)
            predicted.append(yhat)
            base_prices.append(base_price)
            lowers.append(yhat_lower)
            uppers.append(yhat_upper)

        # ── 4. Aggregate metrics ───────────────────────────────────────────
        if not actuals:
            return BacktestMetrics(
                mape=0.0,
                mae=0.0,
                rmse=0.0,
                direction_accuracy=0.0,
                ci_containment=0.0,
                ci_bias="balanced",
                avg_interval_width=0.0,
                num_windows=0,
            )

        avg_width = sum(hi - lo for lo, hi in zip(lowers, uppers)) / len(lowers) if lowers else 0.0

        return BacktestMetrics(
            mape=self._compute_mape(actuals, predicted),
            mae=self._compute_mae(actuals, predicted),
            rmse=self._compute_rmse(actuals, predicted),
            direction_accuracy=self._compute_direction_accuracy(base_prices, actuals, predicted),
            ci_containment=self._compute_ci_containment(actuals, lowers, uppers),
            ci_bias=self._compute_ci_bias(actuals, predicted),
            avg_interval_width=self._safe_float(avg_width),
            num_windows=len(actuals),
        )
