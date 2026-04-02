"""Walk-forward backtesting engine for Prophet model validation."""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

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
