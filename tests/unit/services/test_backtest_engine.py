"""Tests for BacktestEngine walk-forward validation."""

import math
from datetime import date

import pytest

from backend.services.backtesting import BacktestEngine, WindowSpec


class TestExpandingWindows:
    """Test walk-forward expanding window generation."""

    def test_generates_correct_number_of_windows(self):
        """Expanding windows from 3 years of data should produce 12-25 windows."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        assert len(windows) >= 12
        assert len(windows) <= 25

    def test_returns_window_spec_objects(self):
        """Windows should be WindowSpec dataclass instances, not dicts."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        assert all(isinstance(w, WindowSpec) for w in windows)

    def test_training_set_grows_each_window(self):
        """Each successive window must have a later train_end."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        for i in range(1, len(windows)):
            assert windows[i].train_end > windows[i - 1].train_end, (
                f"Window {i} train_end must be after window {i - 1}"
            )

    def test_no_overlap_between_train_and_test(self):
        """Test date must be after training end (no look-ahead bias)."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        for i, w in enumerate(windows):
            assert w.test_date > w.train_end, (
                f"Window {i}: test_date ({w.test_date}) must be after train_end ({w.train_end})"
            )

    def test_all_windows_share_same_train_start(self):
        """Expanding window: train_start is always the data start."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2024, 12, 31),
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        for w in windows:
            assert w.train_start == date(2022, 1, 1)

    def test_insufficient_data_returns_empty(self):
        """Too little data for even one window returns empty list."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2024, 1, 1),
            data_end=date(2024, 6, 1),  # only 5 months
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        assert windows == []

    def test_exact_boundary_excluded(self):
        """Window whose test_date equals data_end is excluded — need data after test_date."""
        engine = BacktestEngine()
        windows = engine._generate_expanding_windows(
            data_start=date(2022, 1, 1),
            data_end=date(2023, 4, 1),  # exactly 1yr + 90d
            min_train_days=365,
            step_days=30,
            horizon_days=90,
        )
        assert len(windows) == 0


class TestMetricComputation:
    """Test MAPE, MAE, RMSE, direction accuracy, CI containment."""

    def test_mape_computation(self):
        """MAPE with known inputs matches hand-calculated value."""
        engine = BacktestEngine()
        actuals = [100.0, 110.0, 90.0, 105.0]
        predicted = [102.0, 108.0, 95.0, 100.0]
        mape = engine._compute_mape(actuals, predicted)
        assert abs(mape - 0.0353) < 0.001

    def test_mape_empty_input(self):
        """MAPE of empty lists returns 0."""
        engine = BacktestEngine()
        assert engine._compute_mape([], []) == 0.0

    def test_mape_all_zero_actuals_returns_nan(self):
        """MAPE is undefined when all actuals are zero — returns NaN."""
        engine = BacktestEngine()
        result = engine._compute_mape([0.0, 0.0, 0.0], [1.0, 2.0, 3.0])
        assert math.isnan(result)

    def test_mape_mismatched_lengths_raises(self):
        """Mismatched input lengths raise ValueError via strict zip."""
        engine = BacktestEngine()
        with pytest.raises(ValueError):
            engine._compute_mape([100.0, 200.0], [102.0])

    def test_mae_computation(self):
        """MAE with known inputs matches hand-calculated value."""
        engine = BacktestEngine()
        actuals = [100.0, 110.0, 90.0, 105.0]
        predicted = [102.0, 108.0, 95.0, 100.0]
        mae = engine._compute_mae(actuals, predicted)
        # |2| + |2| + |5| + |5| = 14 / 4 = 3.5
        assert mae == 3.5

    def test_rmse_computation(self):
        """RMSE with known inputs matches hand-calculated value."""
        engine = BacktestEngine()
        actuals = [100.0, 110.0, 90.0, 105.0]
        predicted = [102.0, 108.0, 95.0, 100.0]
        rmse = engine._compute_rmse(actuals, predicted)
        # (4 + 4 + 25 + 25) / 4 = 14.5, sqrt(14.5) ≈ 3.808
        assert abs(rmse - 3.808) < 0.01

    def test_direction_accuracy(self):
        """Direction accuracy with known up/down patterns."""
        engine = BacktestEngine()
        base_prices = [100.0, 100.0, 100.0, 100.0]
        actuals = [110.0, 90.0, 105.0, 95.0]  # up, down, up, down
        predicted = [108.0, 95.0, 98.0, 92.0]  # up, down, down, down
        acc = engine._compute_direction_accuracy(base_prices, actuals, predicted)
        assert acc == 0.75

    def test_direction_accuracy_empty(self):
        """Direction accuracy of empty lists returns 0."""
        engine = BacktestEngine()
        assert engine._compute_direction_accuracy([], [], []) == 0.0

    def test_direction_accuracy_flat_price(self):
        """Flat price (actual==base) counts as correct — neither direction wrong."""
        engine = BacktestEngine()
        base = [100.0]
        actuals = [100.0]  # flat
        predicted = [100.0]  # also flat
        assert engine._compute_direction_accuracy(base, actuals, predicted) == 1.0

    def test_ci_containment_all_inside(self):
        """All actuals within CI returns 1.0."""
        engine = BacktestEngine()
        actuals = [100.0, 110.0, 90.0, 105.0]
        lowers = [95.0, 105.0, 85.0, 100.0]
        uppers = [108.0, 115.0, 95.0, 110.0]
        containment = engine._compute_ci_containment(actuals, lowers, uppers)
        assert containment == 1.0

    def test_ci_containment_partial(self):
        """One actual outside CI returns 0.5."""
        engine = BacktestEngine()
        actuals = [100.0, 120.0]
        lowers = [95.0, 105.0]
        uppers = [108.0, 115.0]
        containment = engine._compute_ci_containment(actuals, lowers, uppers)
        assert containment == 0.5

    def test_ci_bias_above(self):
        """Systematic upward bias detected."""
        engine = BacktestEngine()
        actuals = [110.0, 120.0, 115.0, 108.0, 112.0]
        predicted = [100.0, 100.0, 100.0, 100.0, 100.0]
        assert engine._compute_ci_bias(actuals, predicted) == "above"

    def test_ci_bias_below(self):
        """Systematic downward bias detected."""
        engine = BacktestEngine()
        actuals = [90.0, 85.0, 88.0, 92.0, 87.0]
        predicted = [100.0, 100.0, 100.0, 100.0, 100.0]
        assert engine._compute_ci_bias(actuals, predicted) == "below"

    def test_ci_bias_balanced(self):
        """No systematic bias returns balanced."""
        engine = BacktestEngine()
        actuals = [105.0, 95.0, 103.0, 97.0, 101.0]
        predicted = [100.0, 100.0, 100.0, 100.0, 100.0]
        assert engine._compute_ci_bias(actuals, predicted) == "balanced"

    def test_ci_bias_empty(self):
        """Empty input returns balanced."""
        engine = BacktestEngine()
        assert engine._compute_ci_bias([], []) == "balanced"

    def test_safe_float_guards_infinity(self):
        """_safe_float returns default for infinity."""
        assert BacktestEngine._safe_float(float("inf")) == 0.0
        assert BacktestEngine._safe_float(float("-inf")) == 0.0

    def test_safe_float_guards_nan(self):
        """_safe_float returns default for NaN."""
        assert BacktestEngine._safe_float(float("nan")) == 0.0

    def test_safe_float_passes_finite(self):
        """_safe_float passes through finite values."""
        assert BacktestEngine._safe_float(3.14) == 3.14
