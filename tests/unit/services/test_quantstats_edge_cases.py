"""Edge case tests for QuantStats — NaN/Inf, constant prices, degenerate inputs."""

import numpy as np
import pandas as pd
import pytest

from backend.services.signals import compute_quantstats_stock


class TestQuantstatsEdgeCases:
    """Tests for edge cases that could produce NaN/Inf."""

    @pytest.fixture()
    def spy_closes(self) -> pd.Series:
        """Standard SPY benchmark."""
        np.random.seed(123)
        dates = pd.bdate_range("2025-01-01", periods=60)
        return pd.Series(450 + np.cumsum(np.random.randn(60) * 1.0), index=dates)

    def test_constant_prices_no_nan(self, spy_closes):
        """Constant prices → zero variance returns, should not produce NaN."""
        dates = pd.bdate_range("2025-01-01", periods=60)
        closes = pd.Series([100.0] * 60, index=dates)
        result = compute_quantstats_stock(closes, spy_closes)
        for key, val in result.items():
            if val is not None and key != "data_days":
                assert np.isfinite(val), f"{key} is {val}"

    def test_monotonically_increasing_no_crash(self, spy_closes):
        """Steadily rising stock → sortino may be inf, should be handled."""
        dates = pd.bdate_range("2025-01-01", periods=60)
        closes = pd.Series([100.0 + i * 0.5 for i in range(60)], index=dates)
        result = compute_quantstats_stock(closes, spy_closes)
        for key, val in result.items():
            if val is not None and key != "data_days":
                assert np.isfinite(val), f"{key} is {val}"

    def test_single_large_drop_produces_valid_drawdown(self, spy_closes):
        """A big crash in the middle should produce a valid drawdown value."""
        dates = pd.bdate_range("2025-01-01", periods=60)
        prices = [100.0] * 30 + [50.0] * 30  # 50% crash
        closes = pd.Series(prices, index=dates)
        result = compute_quantstats_stock(closes, spy_closes)
        assert result["max_drawdown"] is not None
        assert result["max_drawdown"] > 0

    def test_data_days_returned(self, spy_closes):
        """data_days should reflect the number of common trading days."""
        np.random.seed(42)
        dates = pd.bdate_range("2025-01-01", periods=60)
        closes = pd.Series(100 + np.cumsum(np.random.randn(60)), index=dates)
        result = compute_quantstats_stock(closes, spy_closes)
        assert result["data_days"] is not None
        assert result["data_days"] > 0


class TestSchemaValidation:
    """Tests for Pydantic schema validation."""

    def test_invalid_rebalancing_strategy_rejected(self):
        """Invalid strategy value should fail Pydantic validation."""
        from pydantic import ValidationError

        from backend.schemas.portfolio import UserPreferenceUpdate

        with pytest.raises(ValidationError):
            UserPreferenceUpdate(rebalancing_strategy="invalid_strategy")

    def test_valid_strategies_accepted(self):
        """All three valid strategies should pass validation."""
        from backend.schemas.portfolio import UserPreferenceUpdate

        for strategy in ("min_volatility", "max_sharpe", "risk_parity"):
            update = UserPreferenceUpdate(rebalancing_strategy=strategy)
            assert update.rebalancing_strategy == strategy
