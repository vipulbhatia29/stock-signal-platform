"""Tests for convergence snapshot computation — direction classifiers and labels."""

from backend.tasks.convergence import (
    _classify_forecast,
    _classify_macd,
    _classify_piotroski,
    _classify_rsi,
    _classify_sma,
    _compute_convergence_label,
)


class TestDirectionClassification:
    """Test individual signal direction classification functions."""

    def test_rsi_bullish(self):
        """RSI below 40 is bullish (oversold recovery)."""
        assert _classify_rsi(35.0) == "bullish"

    def test_rsi_bearish(self):
        """RSI above 70 is bearish (overbought)."""
        assert _classify_rsi(75.0) == "bearish"

    def test_rsi_neutral(self):
        """RSI in 40-70 range is neutral."""
        assert _classify_rsi(55.0) == "neutral"

    def test_rsi_none(self):
        """Missing RSI defaults to neutral."""
        assert _classify_rsi(None) == "neutral"

    def test_rsi_boundary_40(self):
        """RSI exactly 40 is neutral (< 40 threshold)."""
        assert _classify_rsi(40.0) == "neutral"

    def test_rsi_boundary_70(self):
        """RSI exactly 70 is neutral (> 70 threshold)."""
        assert _classify_rsi(70.0) == "neutral"

    def test_macd_bullish(self):
        """Positive and rising MACD histogram is bullish."""
        assert _classify_macd(0.5, 0.3) == "bullish"

    def test_macd_bearish(self):
        """Negative and falling MACD histogram is bearish."""
        assert _classify_macd(-0.5, -0.3) == "bearish"

    def test_macd_neutral_positive_falling(self):
        """Positive but falling MACD histogram is neutral."""
        assert _classify_macd(0.3, 0.5) == "neutral"

    def test_macd_none(self):
        """Missing MACD histogram defaults to neutral."""
        assert _classify_macd(None, None) == "neutral"

    def test_macd_bullish_no_prev(self):
        """Positive MACD with no previous data is bullish."""
        assert _classify_macd(0.5, None) == "bullish"

    def test_sma_bullish(self):
        """Price >2% above SMA-200 is bullish."""
        assert _classify_sma(current_price=210.0, sma_200=200.0) == "bullish"

    def test_sma_bearish(self):
        """Price >2% below SMA-200 is bearish."""
        assert _classify_sma(current_price=190.0, sma_200=200.0) == "bearish"

    def test_sma_neutral_within_2pct(self):
        """Price within 2% of SMA-200 is neutral."""
        assert _classify_sma(current_price=201.0, sma_200=200.0) == "neutral"

    def test_sma_none_price(self):
        """Missing price defaults to neutral."""
        assert _classify_sma(current_price=None, sma_200=200.0) == "neutral"

    def test_sma_zero_sma(self):
        """Zero SMA-200 defaults to neutral (avoid division by zero)."""
        assert _classify_sma(current_price=100.0, sma_200=0) == "neutral"

    def test_piotroski_bullish(self):
        """Piotroski F-Score >= 6 is bullish."""
        assert _classify_piotroski(7) == "bullish"

    def test_piotroski_bearish(self):
        """Piotroski F-Score <= 3 is bearish."""
        assert _classify_piotroski(2) == "bearish"

    def test_piotroski_neutral(self):
        """Piotroski F-Score 4-5 is neutral."""
        assert _classify_piotroski(5) == "neutral"

    def test_piotroski_none(self):
        """Missing Piotroski score defaults to neutral."""
        assert _classify_piotroski(None) == "neutral"

    def test_piotroski_boundary_6(self):
        """Piotroski exactly 6 is bullish (>= 6 threshold)."""
        assert _classify_piotroski(6) == "bullish"

    def test_piotroski_boundary_3(self):
        """Piotroski exactly 3 is bearish (<= 3 threshold)."""
        assert _classify_piotroski(3) == "bearish"

    def test_sma_boundary_positive_2pct(self):
        """Price exactly +2% above SMA-200 is neutral (> 0.02 threshold)."""
        assert _classify_sma(current_price=204.0, sma_200=200.0) == "neutral"

    def test_sma_boundary_negative_2pct(self):
        """Price exactly -2% below SMA-200 is neutral (< -0.02 threshold)."""
        assert _classify_sma(current_price=196.0, sma_200=200.0) == "neutral"

    def test_forecast_bullish(self):
        """Predicted return >+3% is bullish."""
        assert _classify_forecast(0.05) == "bullish"

    def test_forecast_bearish(self):
        """Predicted return <-3% is bearish."""
        assert _classify_forecast(-0.05) == "bearish"

    def test_forecast_neutral(self):
        """Predicted return within ±3% is neutral."""
        assert _classify_forecast(0.01) == "neutral"

    def test_forecast_none(self):
        """Missing forecast defaults to neutral."""
        assert _classify_forecast(None) == "neutral"

    def test_forecast_boundary_positive(self):
        """Predicted return exactly +3% is neutral (> 0.03 threshold)."""
        assert _classify_forecast(0.03) == "neutral"

    def test_forecast_boundary_negative(self):
        """Predicted return exactly -3% is neutral (< -0.03 threshold)."""
        assert _classify_forecast(-0.03) == "neutral"


class TestConvergenceLabels:
    """Test convergence label computation from signal directions."""

    def test_strong_bull(self):
        """4+ bullish, 0 bearish = strong_bull."""
        directions = ["bullish", "bullish", "bullish", "bullish", "neutral"]
        assert _compute_convergence_label(directions) == "strong_bull"

    def test_weak_bull(self):
        """3+ bullish, <=1 bearish = weak_bull."""
        directions = ["bullish", "bullish", "bullish", "bearish", "neutral"]
        assert _compute_convergence_label(directions) == "weak_bull"

    def test_mixed(self):
        """Equal bullish and bearish = mixed."""
        directions = ["bullish", "bullish", "bearish", "bearish", "neutral"]
        assert _compute_convergence_label(directions) == "mixed"

    def test_strong_bear(self):
        """4+ bearish, 0 bullish = strong_bear."""
        directions = ["bearish", "bearish", "bearish", "bearish", "neutral"]
        assert _compute_convergence_label(directions) == "strong_bear"

    def test_weak_bear(self):
        """3+ bearish, <=1 bullish = weak_bear."""
        directions = ["bearish", "bearish", "bearish", "bullish", "neutral"]
        assert _compute_convergence_label(directions) == "weak_bear"

    def test_all_neutral(self):
        """All neutral signals = mixed."""
        directions = ["neutral", "neutral", "neutral", "neutral", "neutral"]
        assert _compute_convergence_label(directions) == "mixed"

    def test_all_bullish(self):
        """All bullish = strong_bull."""
        directions = ["bullish", "bullish", "bullish", "bullish", "bullish"]
        assert _compute_convergence_label(directions) == "strong_bull"

    def test_all_bearish(self):
        """All bearish = strong_bear."""
        directions = ["bearish", "bearish", "bearish", "bearish", "bearish"]
        assert _compute_convergence_label(directions) == "strong_bear"

    def test_empty_directions(self):
        """Empty directions list = mixed."""
        assert _compute_convergence_label([]) == "mixed"
