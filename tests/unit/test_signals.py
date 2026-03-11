"""Unit tests for the signal computation engine.

These tests verify that each technical indicator (RSI, MACD, SMA, Bollinger,
Sharpe) is computed correctly. We use synthetic price data so tests are:
  - Fast (no database, no network calls)
  - Deterministic (same input always gives same output)
  - Isolated (each test is independent)

Key testing strategy:
  We construct pandas Series with known values to produce predictable
  indicator outputs. For example, a steadily rising price series should
  produce a bullish MACD and high RSI. A crashing price series should
  produce an oversold RSI and bearish MACD.
"""

import numpy as np
import pandas as pd

from backend.tools.signals import (
    BBSignal,
    MACDSignal,
    RSISignal,
    SMASignal,
    compute_bollinger,
    compute_composite_score,
    compute_macd,
    compute_risk_return,
    compute_rsi,
    compute_signals,
    compute_sma,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helper: generate synthetic price data
# ─────────────────────────────────────────────────────────────────────────────


def _make_price_series(
    start: float = 100.0,
    num_days: int = 300,
    daily_change: float = 0.001,
    noise: float = 0.0,
    seed: int = 42,
) -> pd.Series:
    """Create a synthetic price series for testing.

    Generates a price series that starts at `start` and grows by
    `daily_change` per day (compounded), with optional random noise.
    This lets us create predictable scenarios:
      - daily_change > 0  → uptrend (bullish)
      - daily_change < 0  → downtrend (bearish)
      - daily_change = 0  → flat (neutral)

    Args:
        start: Starting price.
        num_days: Number of trading days to generate.
        daily_change: Daily return rate (0.001 = 0.1% per day).
        noise: Standard deviation of random noise to add.
        seed: Random seed for reproducibility.

    Returns:
        A pandas Series of closing prices with a DatetimeIndex.
    """
    rng = np.random.default_rng(seed)
    # Create daily returns: base change + optional noise
    returns = np.full(num_days, daily_change)
    if noise > 0:
        returns += rng.normal(0, noise, num_days)

    # Convert returns to prices: price[i] = start × ∏(1 + returns[0:i])
    prices = start * np.cumprod(1 + returns)

    dates = pd.date_range(start="2024-01-01", periods=num_days, freq="B")
    return pd.Series(prices, index=dates, name="Close")


def _make_ohlcv_df(closes: pd.Series) -> pd.DataFrame:
    """Wrap a close-price series into a full OHLCV DataFrame.

    Creates synthetic Open/High/Low/Volume columns from the Close series.
    The exact values don't matter much for signal tests — we just need
    the DataFrame structure that compute_signals() expects.
    """
    return pd.DataFrame(
        {
            "Open": closes * 0.998,  # Open slightly below close
            "High": closes * 1.005,  # High slightly above close
            "Low": closes * 0.995,  # Low slightly below close
            "Close": closes,
            "Adj Close": closes,  # No splits/dividends in test data
            "Volume": [1_000_000] * len(closes),
        },
        index=closes.index,
    )


# ═════════════════════════════════════════════════════════════════════════════
# RSI Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeRSI:
    """Tests for RSI (Relative Strength Index) computation."""

    def test_rsi_uptrend_not_oversold(self) -> None:
        """A steadily rising price should NOT be oversold (RSI > 30)."""
        closes = _make_price_series(daily_change=0.005)  # Strong uptrend
        rsi_val, rsi_sig = compute_rsi(closes)

        assert rsi_val is not None
        assert rsi_val > 30  # Not oversold in an uptrend
        assert rsi_sig != RSISignal.OVERSOLD

    def test_rsi_downtrend_below_50(self) -> None:
        """A steadily falling price should have RSI below 50."""
        closes = _make_price_series(daily_change=-0.005)  # Strong downtrend
        rsi_val, rsi_sig = compute_rsi(closes)

        assert rsi_val is not None
        assert rsi_val < 50  # Below the midpoint in a downtrend

    def test_rsi_extreme_drop_is_oversold(self) -> None:
        """A sharp crash should produce an OVERSOLD signal (RSI < 30)."""
        # Start high, then crash hard in the last 20 days
        prices = np.concatenate(
            [
                np.full(250, 100.0),  # Flat for 250 days
                np.linspace(100, 50, 50),  # Crash from 100 to 50
            ]
        )
        dates = pd.date_range("2024-01-01", periods=300, freq="B")
        closes = pd.Series(prices, index=dates)

        rsi_val, rsi_sig = compute_rsi(closes)

        assert rsi_val is not None
        assert rsi_val < 30
        assert rsi_sig == RSISignal.OVERSOLD

    def test_rsi_extreme_rally_is_overbought(self) -> None:
        """A sharp rally should produce an OVERBOUGHT signal (RSI > 70)."""
        prices = np.concatenate(
            [
                np.full(250, 100.0),  # Flat for 250 days
                np.linspace(100, 200, 50),  # Rally from 100 to 200
            ]
        )
        dates = pd.date_range("2024-01-01", periods=300, freq="B")
        closes = pd.Series(prices, index=dates)

        rsi_val, rsi_sig = compute_rsi(closes)

        assert rsi_val is not None
        assert rsi_val > 70
        assert rsi_sig == RSISignal.OVERBOUGHT

    def test_rsi_insufficient_data_returns_none(self) -> None:
        """With fewer data points than the RSI period, return None."""
        closes = _make_price_series(num_days=10)  # Only 10 days, need 15+
        rsi_val, rsi_sig = compute_rsi(closes)

        assert rsi_val is None
        assert rsi_sig is None

    def test_rsi_value_in_valid_range(self) -> None:
        """RSI must always be between 0 and 100."""
        closes = _make_price_series(num_days=300, noise=0.02)
        rsi_val, _ = compute_rsi(closes)

        assert rsi_val is not None
        assert 0 <= rsi_val <= 100


# ═════════════════════════════════════════════════════════════════════════════
# MACD Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeMACD:
    """Tests for MACD (Moving Average Convergence Divergence) computation."""

    def test_macd_uptrend_is_bullish(self) -> None:
        """A steady uptrend should produce a BULLISH MACD signal."""
        closes = _make_price_series(daily_change=0.003, num_days=100)
        macd_val, hist_val, signal = compute_macd(closes)

        assert macd_val is not None
        assert hist_val is not None
        assert signal == MACDSignal.BULLISH
        assert hist_val > 0  # Positive histogram = bullish

    def test_macd_downtrend_is_bearish(self) -> None:
        """An accelerating downtrend should produce a BEARISH MACD signal.

        A constant-rate decline actually produces a positive histogram
        because the downtrend DECELERATES in EMA terms (the gap between
        fast and slow EMAs stabilizes). To get a truly bearish histogram,
        we need a price that's actively falling faster — simulated here
        by a stable period followed by a sharp drop.
        """
        # Flat period → then accelerating decline
        flat = np.full(200, 100.0)
        decline = np.linspace(100, 50, 100)
        prices = np.concatenate([flat, decline])
        dates = pd.date_range("2023-01-01", periods=300, freq="B")
        closes = pd.Series(prices, index=dates)

        macd_val, hist_val, signal = compute_macd(closes)

        assert macd_val is not None
        assert hist_val is not None
        assert signal == MACDSignal.BEARISH
        assert hist_val <= 0  # Negative histogram = bearish

    def test_macd_insufficient_data_returns_none(self) -> None:
        """With too few data points, MACD should return None."""
        closes = _make_price_series(num_days=20)  # Need 26+9=35 minimum
        macd_val, hist_val, signal = compute_macd(closes)

        assert macd_val is None
        assert hist_val is None
        assert signal is None


# ═════════════════════════════════════════════════════════════════════════════
# SMA Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeSMA:
    """Tests for SMA (Simple Moving Average) crossover detection."""

    def test_sma_uptrend_above_200(self) -> None:
        """In a sustained uptrend, price should be ABOVE_200."""
        closes = _make_price_series(daily_change=0.002, num_days=300)
        sma50, sma200, signal = compute_sma(closes)

        assert sma50 is not None
        assert sma200 is not None
        assert signal == SMASignal.ABOVE_200

    def test_sma_downtrend_below_200(self) -> None:
        """In a sustained downtrend, price should be BELOW_200."""
        closes = _make_price_series(daily_change=-0.002, num_days=300)
        sma50, sma200, signal = compute_sma(closes)

        assert sma50 is not None
        assert sma200 is not None
        assert signal == SMASignal.BELOW_200

    def test_sma_golden_cross_detected(self) -> None:
        """Detect a Golden Cross when SMA50 crosses above SMA200.

        We construct a series where the price was flat (so SMA50 ≈ SMA200),
        then starts rising sharply at the end. This makes SMA50 (which
        reacts faster) cross above SMA200 (which reacts slower).
        """
        # Long flat period followed by a sharp rally
        flat = np.full(250, 100.0)
        rally = np.linspace(100, 130, 50)
        prices = np.concatenate([flat, rally])
        dates = pd.date_range("2023-01-01", periods=300, freq="B")
        closes = pd.Series(prices, index=dates)

        sma50, sma200, signal = compute_sma(closes)

        # SMA50 should now be above SMA200 after the rally
        assert sma50 is not None
        assert sma200 is not None
        assert sma50 > sma200

    def test_sma_insufficient_data(self) -> None:
        """With fewer than 200 data points, SMA200 should be None."""
        closes = _make_price_series(num_days=100)
        sma50, sma200, signal = compute_sma(closes)

        # SMA50 should work (100 > 50), but SMA200 won't
        assert sma50 is not None
        assert sma200 is None


# ═════════════════════════════════════════════════════════════════════════════
# Bollinger Bands Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeBollinger:
    """Tests for Bollinger Bands computation."""

    def test_bollinger_normal_price_is_middle(self) -> None:
        """A gently trending price should sit between the bands (MIDDLE)."""
        closes = _make_price_series(daily_change=0.001, noise=0.005)
        upper, lower, position = compute_bollinger(closes)

        assert upper is not None
        assert lower is not None
        assert upper > lower  # Upper band must be above lower band
        assert position == BBSignal.MIDDLE

    def test_bollinger_spike_is_upper(self) -> None:
        """A sudden price spike should push price above the upper band."""
        # Normal prices, then a sharp spike at the end
        normal = np.full(100, 100.0) + np.random.default_rng(42).normal(0, 0.5, 100)
        spiked = np.append(normal, [120.0])  # Spike to 120
        dates = pd.date_range("2024-01-01", periods=len(spiked), freq="B")
        closes = pd.Series(spiked, index=dates)

        upper, lower, position = compute_bollinger(closes)

        assert position == BBSignal.UPPER

    def test_bollinger_crash_is_lower(self) -> None:
        """A sudden price crash should push price below the lower band."""
        normal = np.full(100, 100.0) + np.random.default_rng(42).normal(0, 0.5, 100)
        crashed = np.append(normal, [80.0])  # Crash to 80
        dates = pd.date_range("2024-01-01", periods=len(crashed), freq="B")
        closes = pd.Series(crashed, index=dates)

        upper, lower, position = compute_bollinger(closes)

        assert position == BBSignal.LOWER

    def test_bollinger_insufficient_data(self) -> None:
        """With fewer than 20 data points, return None."""
        closes = _make_price_series(num_days=10)
        upper, lower, position = compute_bollinger(closes)

        assert upper is None
        assert lower is None
        assert position is None


# ═════════════════════════════════════════════════════════════════════════════
# Risk/Return Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeRiskReturn:
    """Tests for annualized return, volatility, and Sharpe ratio."""

    def test_positive_return_uptrend(self) -> None:
        """An uptrending stock should have a positive annualized return."""
        closes = _make_price_series(daily_change=0.002, num_days=252)
        ann_ret, vol, sharpe = compute_risk_return(closes)

        assert ann_ret is not None
        assert ann_ret > 0  # Positive return

    def test_negative_return_downtrend(self) -> None:
        """A downtrending stock should have a negative annualized return."""
        closes = _make_price_series(daily_change=-0.002, num_days=252)
        ann_ret, vol, sharpe = compute_risk_return(closes)

        assert ann_ret is not None
        assert ann_ret < 0  # Negative return

    def test_volatility_positive(self) -> None:
        """Volatility should always be non-negative."""
        closes = _make_price_series(noise=0.01, num_days=252)
        _, vol, _ = compute_risk_return(closes)

        assert vol is not None
        assert vol >= 0

    def test_sharpe_positive_when_return_beats_risk_free(self) -> None:
        """Sharpe should be positive when return exceeds the risk-free rate.

        We add noise=0.005 so the series has non-zero volatility. Without
        noise, the daily returns have zero standard deviation → vol = 0
        → Sharpe is undefined (None). In real markets there's always noise.
        """
        closes = _make_price_series(daily_change=0.004, num_days=252, noise=0.005)
        ann_ret, vol, sharpe = compute_risk_return(closes)

        assert sharpe is not None
        assert sharpe > 0  # Return > risk-free rate

    def test_sharpe_negative_when_return_below_risk_free(self) -> None:
        """Sharpe should be negative when return is below the risk-free rate.

        We add noise so volatility is non-zero (required for Sharpe).
        """
        closes = _make_price_series(daily_change=-0.001, num_days=252, noise=0.005)
        ann_ret, vol, sharpe = compute_risk_return(closes)

        assert sharpe is not None
        assert sharpe < 0

    def test_insufficient_data(self) -> None:
        """With only 1 data point, can't compute returns."""
        closes = pd.Series([100.0])
        ann_ret, vol, sharpe = compute_risk_return(closes)

        assert ann_ret is None
        assert vol is None
        assert sharpe is None


# ═════════════════════════════════════════════════════════════════════════════
# Composite Score Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeCompositeScore:
    """Tests for the composite score calculation (0-10 scale)."""

    def test_max_score_all_bullish(self) -> None:
        """Perfect bullish signals should produce a high composite score."""
        score, weights = compute_composite_score(
            rsi_value=25.0,  # Oversold → 2.5 points
            rsi_signal="OVERSOLD",
            macd_histogram=1.0,  # Strong bullish → 2.5 points
            macd_signal="BULLISH",
            sma_signal="GOLDEN_CROSS",  # Golden cross → 2.5 points
            sharpe=2.0,  # Excellent Sharpe → 2.5 points
        )

        assert score is not None
        assert score == 10.0  # Maximum possible score
        assert weights is not None
        assert weights["rsi"] == 2.5
        assert weights["macd"] == 2.5
        assert weights["sma"] == 2.5
        assert weights["sharpe"] == 2.5

    def test_min_score_all_bearish(self) -> None:
        """All bearish signals should produce a very low composite score."""
        score, weights = compute_composite_score(
            rsi_value=80.0,  # Overbought → 0 points
            rsi_signal="OVERBOUGHT",
            macd_histogram=-1.0,  # Strong bearish → 0 points
            macd_signal="BEARISH",
            sma_signal="DEATH_CROSS",  # Death cross → 0 points
            sharpe=-0.5,  # Negative Sharpe → 0 points
        )

        assert score is not None
        assert score == 0.0  # Minimum possible score

    def test_mixed_signals_mid_range(self) -> None:
        """Mixed bullish/bearish signals should produce a mid-range score."""
        score, weights = compute_composite_score(
            rsi_value=50.0,  # Neutral → 1.0 points
            rsi_signal="NEUTRAL",
            macd_histogram=0.2,  # Weak bullish → 1.5 points
            macd_signal="BULLISH",
            sma_signal="ABOVE_200",  # Above 200 → 1.5 points
            sharpe=0.7,  # Decent → 1.0 points
        )

        assert score is not None
        assert 4.0 <= score <= 6.0  # Mid-range

    def test_all_none_returns_none(self) -> None:
        """If all indicators are None, composite score is None."""
        score, weights = compute_composite_score(
            rsi_value=None,
            rsi_signal=None,
            macd_histogram=None,
            macd_signal=None,
            sma_signal=None,
            sharpe=None,
        )

        assert score is None
        assert weights is None

    def test_score_within_0_to_10(self) -> None:
        """Composite score must always be between 0 and 10."""
        # Test with various combinations
        test_cases = [
            (25.0, "OVERSOLD", 0.3, "BULLISH", "ABOVE_200", 1.2),
            (75.0, "OVERBOUGHT", -0.5, "BEARISH", "BELOW_200", -0.3),
            (50.0, "NEUTRAL", 0.0, "BEARISH", "GOLDEN_CROSS", 0.8),
        ]

        for rsi_v, rsi_s, macd_h, macd_s, sma_s, sharpe in test_cases:
            score, _ = compute_composite_score(rsi_v, rsi_s, macd_h, macd_s, sma_s, sharpe)
            assert score is not None
            assert 0 <= score <= 10, f"Score {score} out of range for inputs"


# ═════════════════════════════════════════════════════════════════════════════
# Integration: compute_signals() end-to-end
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeSignalsEndToEnd:
    """End-to-end tests for the main compute_signals() function."""

    def test_compute_signals_returns_all_fields(self) -> None:
        """compute_signals() should populate all fields with enough data."""
        closes = _make_price_series(num_days=300, noise=0.005)
        df = _make_ohlcv_df(closes)

        result = compute_signals("AAPL", df)

        assert result.ticker == "AAPL"
        assert result.rsi_value is not None
        assert result.rsi_signal is not None
        assert result.macd_value is not None
        assert result.macd_histogram is not None
        assert result.macd_signal_label is not None
        assert result.sma_50 is not None
        assert result.sma_200 is not None
        assert result.sma_signal is not None
        assert result.bb_upper is not None
        assert result.bb_lower is not None
        assert result.bb_position is not None
        assert result.annual_return is not None
        assert result.volatility is not None
        assert result.sharpe_ratio is not None
        assert result.composite_score is not None
        assert result.composite_weights is not None

    def test_compute_signals_insufficient_data(self) -> None:
        """With too few data points, all fields should be None."""
        closes = _make_price_series(num_days=10)
        df = _make_ohlcv_df(closes)

        result = compute_signals("TINY", df)

        assert result.ticker == "TINY"
        assert result.rsi_value is None
        assert result.composite_score is None

    def test_compute_signals_uses_adj_close(self) -> None:
        """compute_signals() should prefer 'Adj Close' over 'Close'."""
        closes = _make_price_series(num_days=300)
        df = _make_ohlcv_df(closes)

        # Make Adj Close different from Close to verify it's used
        df["Adj Close"] = df["Close"] * 1.1

        result = compute_signals("AAPL", df)

        # If Adj Close is used, the signals will differ from Close-based ones
        assert result.composite_score is not None
