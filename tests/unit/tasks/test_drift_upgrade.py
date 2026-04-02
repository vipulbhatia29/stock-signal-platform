"""Tests for per-ticker calibrated drift detection."""

import pytest

from backend.tasks.evaluation import (
    CONSECUTIVE_FAILURES_FOR_EXPERIMENTAL,
    DRIFT_BASELINE_MULTIPLIER,
    DRIFT_FALLBACK_THRESHOLD,
    compute_calibrated_threshold,
    should_demote_to_experimental,
)


class TestCalibratedThreshold:
    """Test per-ticker drift threshold computation."""

    def test_uses_backtest_mape_times_multiplier(self):
        """Threshold is backtest MAPE × 1.5."""
        assert compute_calibrated_threshold(0.10) == pytest.approx(0.15)

    def test_fallback_when_no_backtest(self):
        """Falls back to 20% when no backtest data."""
        assert compute_calibrated_threshold(None) == DRIFT_FALLBACK_THRESHOLD

    def test_fallback_when_zero_backtest(self):
        """Falls back to 20% when backtest MAPE is zero."""
        assert compute_calibrated_threshold(0.0) == DRIFT_FALLBACK_THRESHOLD

    def test_fallback_when_negative_backtest(self):
        """Falls back to 20% when backtest MAPE is negative (data error)."""
        assert compute_calibrated_threshold(-0.05) == DRIFT_FALLBACK_THRESHOLD

    def test_low_mape_produces_tight_threshold(self):
        """A well-calibrated model (3% MAPE) gets a tight 4.5% threshold."""
        assert compute_calibrated_threshold(0.03) == pytest.approx(0.045)

    def test_high_mape_produces_wide_threshold(self):
        """A volatile ticker (15% MAPE) gets a 22.5% threshold."""
        assert compute_calibrated_threshold(0.15) == pytest.approx(0.225)

    def test_multiplier_value(self):
        """Multiplier constant is 1.5."""
        assert DRIFT_BASELINE_MULTIPLIER == 1.5


class TestExperimentalDemotion:
    """Test experimental demotion logic."""

    def test_demotes_after_3_failures(self):
        """3 consecutive failures triggers demotion."""
        assert should_demote_to_experimental(3, "degraded") is True

    def test_no_demotion_before_3(self):
        """2 failures is not enough for demotion."""
        assert should_demote_to_experimental(2, "degraded") is False

    def test_no_demotion_if_already_experimental(self):
        """Already experimental models are not re-demoted."""
        assert should_demote_to_experimental(5, "experimental") is False

    def test_demotes_from_active_status(self):
        """Active models can be demoted after 3 failures."""
        assert should_demote_to_experimental(3, "active") is True

    def test_threshold_constant(self):
        """Consecutive failure threshold is 3."""
        assert CONSECUTIVE_FAILURES_FOR_EXPERIMENTAL == 3

    def test_more_than_3_still_demotes(self):
        """4+ failures also triggers demotion (>= not ==)."""
        assert should_demote_to_experimental(10, "active") is True

    def test_zero_failures_no_demotion(self):
        """Zero failures never triggers demotion."""
        assert should_demote_to_experimental(0, "active") is False


class TestSelfHealingLogic:
    """Test that experimental models can self-heal when passing threshold."""

    def test_experimental_not_demoted_again(self):
        """Experimental models stay experimental (no double-demotion)."""
        assert should_demote_to_experimental(10, "experimental") is False

    def test_calibrated_threshold_allows_healing(self):
        """A model with 10% backtest MAPE gets 15% threshold — 12% MAPE passes."""
        threshold = compute_calibrated_threshold(0.10)
        current_mape = 0.12
        # 12% < 15% threshold — model should pass and heal
        assert current_mape <= threshold

    def test_calibrated_threshold_detects_drift(self):
        """A model with 10% backtest MAPE gets 15% threshold — 18% MAPE fails."""
        threshold = compute_calibrated_threshold(0.10)
        current_mape = 0.18
        # 18% > 15% threshold — drift detected
        assert current_mape > threshold
