"""Walk-forward backtesting engine for ForecastEngine model validation."""

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.historical_feature import HistoricalFeature
from backend.services.forecast_engine import FEATURE_NAMES, ForecastEngine

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
    """Walk-forward validation for ForecastEngine models.

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

    def _empty_metrics(self) -> "BacktestMetrics":
        """Return zeroed BacktestMetrics for no-data cases."""
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

    async def run_walk_forward(
        self,
        ticker: str,
        db: AsyncSession,
        horizon_days: int = 60,
        min_train_days: int = 365,
        step_days: int = 30,
    ) -> "BacktestMetrics":
        """Run walk-forward validation for a ticker using ForecastEngine.

        Loads historical_features for ALL tickers (cross-ticker training),
        generates expanding windows by date, trains a ForecastEngine per
        window, and predicts the target ticker's forward return at each
        test_date.

        Args:
            ticker: Stock ticker to evaluate predictions for.
            db: Async database session.
            horizon_days: Days ahead to forecast (60 or 90).
            min_train_days: Minimum training period in days.
            step_days: Days to advance between walk-forward windows.

        Returns:
            BacktestMetrics aggregating all windows.
        """
        target_col = f"forward_return_{horizon_days}d"

        # ── 1. Load all historical features (cross-ticker) ──────────────
        result = await db.execute(select(HistoricalFeature).order_by(HistoricalFeature.date))
        all_rows = result.scalars().all()

        if not all_rows:
            logger.warning("run_walk_forward: no historical features found")
            return self._empty_metrics()

        # Build DataFrame from ORM rows
        records = []
        for row in all_rows:
            record: dict = {"date": row.date, "ticker": row.ticker}
            for name in FEATURE_NAMES:
                record[name] = getattr(row, name, None)
            record["forward_return_60d"] = row.forward_return_60d
            record["forward_return_90d"] = row.forward_return_90d
            records.append(record)
        features_df = pd.DataFrame(records)

        # Filter to rows that have the target return
        features_df = features_df.dropna(subset=[target_col])
        if features_df.empty:
            logger.warning("run_walk_forward: no rows with %s for any ticker", target_col)
            return self._empty_metrics()

        # Get date range for the target ticker
        ticker_dates = sorted(features_df.loc[features_df["ticker"] == ticker, "date"].unique())
        if not ticker_dates:
            logger.warning("run_walk_forward: ticker %s not found in historical features", ticker)
            return self._empty_metrics()

        data_start = features_df["date"].min()
        data_end = features_df["date"].max()

        # ── 2. Generate windows ─────────────────────────────────────────
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
            return self._empty_metrics()

        # ── 3. Walk through windows ─────────────────────────────────────
        engine = ForecastEngine()
        actuals: list[float] = []
        predicted: list[float] = []
        lowers: list[float] = []
        uppers: list[float] = []

        for window in windows:
            # Training slice: all tickers, dates up to train_end
            # Purge buffer: exclude rows where the target would be unknown
            # (date must be <= train_end - horizon_days for the target to be realised)
            train_cutoff = window.train_end - timedelta(days=horizon_days)
            train_slice = features_df[features_df["date"] <= train_cutoff]
            if len(train_slice) < 10:
                continue

            # Test: get target ticker's feature row at test_date
            test_rows = features_df[
                (features_df["ticker"] == ticker) & (features_df["date"] == window.test_date)
            ]
            if test_rows.empty:
                # Try nearest date within ±5 days
                for offset in range(1, 6):
                    for delta in [timedelta(days=offset), timedelta(days=-offset)]:
                        candidate = window.test_date + delta
                        test_rows = features_df[
                            (features_df["ticker"] == ticker) & (features_df["date"] == candidate)
                        ]
                        if not test_rows.empty:
                            break
                    if not test_rows.empty:
                        break
            if test_rows.empty:
                continue

            test_row = test_rows.iloc[0]
            actual_return = test_row[target_col]
            if actual_return is None or (
                isinstance(actual_return, float) and math.isnan(actual_return)
            ):
                continue

            # Train model on the training slice
            try:
                artifact_bytes, _train_metrics = await asyncio.to_thread(
                    engine.train, train_slice, horizon_days
                )
            except Exception:
                logger.exception(
                    "ForecastEngine train failed for window %s–%s; skipping",
                    window.train_start,
                    window.train_end,
                )
                continue

            # Predict for the test row
            feature_dict = {name: test_row.get(name) for name in FEATURE_NAMES}
            try:
                pred = await asyncio.to_thread(
                    engine.predict, feature_dict, artifact_bytes, None, False
                )
            except Exception:
                logger.exception(
                    "ForecastEngine predict failed for %s at %s; skipping",
                    ticker,
                    window.test_date,
                )
                continue

            # pred returns percentages; actual_return is log return
            # Convert predicted return from percentage to log return for comparison
            pred_return = math.log(1.0 + pred["expected_return_pct"] / 100.0)
            pred_lower = math.log(1.0 + pred["return_lower_pct"] / 100.0)
            pred_upper = math.log(1.0 + pred["return_upper_pct"] / 100.0)

            actuals.append(float(actual_return))
            predicted.append(pred_return)
            lowers.append(pred_lower)
            uppers.append(pred_upper)

        # ── 4. Aggregate metrics ────────────────────────────────────────
        if not actuals:
            return self._empty_metrics()

        # For direction accuracy with returns: base is 0 (positive = up, negative = down)
        base_prices = [0.0] * len(actuals)
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
