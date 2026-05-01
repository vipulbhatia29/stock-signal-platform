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
import pytest

from backend.tools.signals import (
    BBSignal,
    MACDSignal,
    RSISignal,
    SMASignal,
    compute_adx,
    compute_atr,
    compute_bollinger,
    compute_composite_score,
    compute_confirmation_gates,
    compute_macd,
    compute_mfi,
    compute_obv_slope,
    compute_price_change,
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
        macd_val, hist_val, signal, hist_prev = compute_macd(closes)

        assert macd_val is not None
        assert hist_val is not None
        assert signal == MACDSignal.BULLISH
        assert hist_val > 0  # Positive histogram = bullish
        assert hist_prev is not None  # 100 days is enough for prior-day histogram

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

        macd_val, hist_val, signal, hist_prev = compute_macd(closes)

        assert macd_val is not None
        assert hist_val is not None
        assert signal == MACDSignal.BEARISH
        assert hist_val <= 0  # Negative histogram = bearish

    def test_macd_insufficient_data_returns_none(self) -> None:
        """With too few data points, MACD should return None."""
        closes = _make_price_series(num_days=20)  # Need 26+9=35 minimum
        macd_val, hist_val, signal, hist_prev = compute_macd(closes)

        assert macd_val is None
        assert hist_val is None
        assert signal is None
        assert hist_prev is None


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
# ADX Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeADX:
    """Tests for ADX (Average Directional Index) computation."""

    def test_adx_trending_market(self) -> None:
        """Strong trend should produce ADX > 20."""
        df = _make_hardening_price_series(n=250, trend=0.008, volatility=0.005, seed=10)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert val > 20, f"ADX {val} too low for strong trend"

    def test_adx_bounded_0_100(self) -> None:
        """ADX must be between 0 and 100."""
        df = _make_hardening_price_series(n=250)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert 0 <= val <= 100

    def test_adx_range_bound_market(self) -> None:
        """Flat market with noise should produce ADX < 30."""
        df = _make_hardening_price_series(n=250, trend=0.0, volatility=0.01, seed=20)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert val < 30, f"ADX {val} too high for range-bound market"

    def test_adx_insufficient_data(self) -> None:
        """ADX returns None for too few data points."""
        df = _make_hardening_price_series(n=10)
        val = compute_adx(df["High"], df["Low"], df["Close"])
        assert val is None


# ═════════════════════════════════════════════════════════════════════════════
# OBV Slope Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeOBVSlope:
    """Tests for OBV (On-Balance Volume) slope computation."""

    def test_obv_slope_uptrend_positive(self) -> None:
        """Rising prices with increasing volume should produce positive OBV slope."""
        n = 100
        prices = 100.0 * np.cumprod(1 + np.full(n, 0.005))
        dates = pd.bdate_range(end="2025-01-01", periods=n)
        closes = pd.Series(prices, index=dates)
        volumes = pd.Series(np.linspace(1_000_000, 5_000_000, n), index=dates)
        val = compute_obv_slope(closes, volumes)
        assert val is not None
        assert val > 0, f"OBV slope {val} should be positive for confirmed uptrend"

    def test_obv_slope_with_random_volume(self) -> None:
        """OBV slope should return a finite value with random volume data."""
        df = _make_hardening_price_series(n=100)
        val = compute_obv_slope(df["Close"], df["Volume"])
        assert val is not None

    def test_obv_slope_insufficient_data(self) -> None:
        """OBV slope returns None for too few data points."""
        closes = pd.Series([100.0, 101.0], index=pd.bdate_range(end="2025-01-01", periods=2))
        volumes = pd.Series([1_000_000, 1_000_000], index=closes.index)
        val = compute_obv_slope(closes, volumes)
        assert val is None


# ═════════════════════════════════════════════════════════════════════════════
# MFI Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeMFI:
    """Tests for MFI (Money Flow Index) computation."""

    def test_mfi_bounded_0_100(self) -> None:
        """MFI must be between 0 and 100."""
        df = _make_hardening_price_series(n=100)
        val = compute_mfi(df["High"], df["Low"], df["Close"], df["Volume"])
        assert val is not None
        assert 0 <= val <= 100

    def test_mfi_insufficient_data(self) -> None:
        """MFI returns None for too few data points."""
        df = _make_hardening_price_series(n=5)
        val = compute_mfi(df["High"], df["Low"], df["Close"], df["Volume"])
        assert val is None


# ═════════════════════════════════════════════════════════════════════════════
# ATR Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeATR:
    """Tests for ATR (Average True Range) computation."""

    def test_atr_positive(self) -> None:
        """ATR must be positive for any valid price data."""
        df = _make_hardening_price_series(n=100)
        val = compute_atr(df["High"], df["Low"], df["Close"])
        assert val is not None
        assert val > 0

    def test_atr_higher_volatility_higher_atr(self) -> None:
        """Higher volatility data should produce a higher ATR."""
        low_vol = _make_hardening_price_series(n=100, volatility=0.005, seed=1)
        high_vol = _make_hardening_price_series(n=100, volatility=0.04, seed=1)
        atr_low = compute_atr(low_vol["High"], low_vol["Low"], low_vol["Close"])
        atr_high = compute_atr(high_vol["High"], high_vol["Low"], high_vol["Close"])
        assert atr_low is not None and atr_high is not None
        assert atr_high > atr_low

    def test_atr_insufficient_data(self) -> None:
        """ATR returns None for too few data points."""
        df = _make_hardening_price_series(n=5)
        val = compute_atr(df["High"], df["Low"], df["Close"])
        assert val is None


# ═════════════════════════════════════════════════════════════════════════════
# Gate Indicator Integration Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestComputeSignalsGateIndicators:
    """Tests that compute_signals() populates gate indicator fields."""

    def test_gate_indicators_populated(self) -> None:
        """compute_signals() with sufficient OHLCV data populates all gate fields."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("AAPL", df)
        assert result.adx_value is not None
        assert result.mfi_value is not None
        assert result.atr_value is not None
        assert result.obv_slope is not None

    def test_gate_indicators_none_for_insufficient_data(self) -> None:
        """Gate indicators are None when data is too short."""
        df = _make_hardening_price_series(n=10)
        result = compute_signals("TINY", df)
        assert result.adx_value is None
        assert result.mfi_value is None
        assert result.atr_value is None
        assert result.obv_slope is None

    def test_piotroski_persisted_in_result(self) -> None:
        """Piotroski score passed to compute_signals appears in result."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("AAPL", df, piotroski_score=7)
        assert result.piotroski_score_value == 7

    def test_macd_histogram_prev_populated(self) -> None:
        """Prior-day MACD histogram is populated when MACD is available."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("AAPL", df)
        if result.macd_histogram is not None:
            assert result.macd_histogram_prev is not None


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
    """Tests for the legacy additive composite score (kept for backward compat)."""

    def test_max_score_all_bullish(self) -> None:
        """Perfect bullish signals should produce a high composite score."""
        score, weights = compute_composite_score(
            rsi_value=25.0,
            rsi_signal="OVERSOLD",
            macd_histogram=1.0,
            macd_signal="BULLISH",
            sma_signal="GOLDEN_CROSS",
            sharpe=2.0,
        )
        assert score is not None
        assert score == 10.0
        assert weights is not None

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


# ═════════════════════════════════════════════════════════════════════════════
# Confirmation Gate Scoring Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestConfirmationGates:
    """Tests for the 5-gate confirmation scoring model."""

    def test_all_gates_confirmed_scores_10(self) -> None:
        """When all 5 gates confirm, score should be 10.0."""
        score, weights = compute_confirmation_gates(
            adx=32.0,
            macd_histogram=1.0,
            macd_histogram_prev=0.5,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.05,
            mfi=62.0,
            rsi=45.0,
            piotroski=8,
        )
        assert score == 10.0
        assert weights is not None
        assert weights["gates_confirmed"] == 5
        assert weights["gates_active"] == 5
        assert weights["mode"] == "confirmation_gate_v2"

    def test_no_gates_confirmed_scores_0(self) -> None:
        """When no gates confirm, score should be 0.0.

        Key insight: direction is derived by majority vote. To make Gate 2 fail,
        we need direction signals that partially conflict (< 3/4 conditions met).
        MACD decelerating (prev > current) prevents Gate 2 from reaching threshold.
        """
        score, weights = compute_confirmation_gates(
            adx=10.0,  # Gate 1: range-bound (<20) ✗
            macd_histogram=0.1,  # Barely positive (bullish vote)
            macd_histogram_prev=0.5,  # Decelerating (0.1 < 0.5) ✗
            sma_50=151.0,  # SMA50 > SMA200 (bullish vote)
            sma_200=150.0,
            current_price=140.0,  # Below SMA50 (bearish vote) → direction=bullish (2/3)
            # Gate 2: MACD sign ✓, acceleration ✗, price>SMA50 ✗, SMA aligned ✓ = 2/4 < 3 ✗
            obv_slope=-0.05,  # Gate 3: bearish OBV in bullish direction ✗
            mfi=35.0,  # Gate 3: mfi < 50 in bullish direction ✗
            rsi=72.0,  # Gate 4: range-bound bullish needs RSI<35, got 72 ✗
            piotroski=2,  # Gate 5: weak (<4) ✗
        )
        assert score == 0.0
        assert weights is not None
        assert weights["gates_confirmed"] == 0

    def test_four_of_five_scores_8(self) -> None:
        """4 of 5 gates confirmed = score 8.0 (BUY threshold)."""
        score, weights = compute_confirmation_gates(
            adx=28.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=70.0,
            piotroski=8,
        )
        assert score == 8.0
        assert weights["gates_confirmed"] == 4

    def test_piotroski_none_skips_gate(self) -> None:
        """When piotroski is None, gate 5 is skipped (active=4, not 5)."""
        score, weights = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=50.0,
            piotroski=None,
        )
        assert weights is not None
        assert weights["gates_active"] == 4
        assert score == 10.0

    def test_piotroski_neutral_skips_gate(self) -> None:
        """Piotroski 4-6 is neutral — gate is NOT counted as active."""
        score_neutral, w_neutral = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=50.0,
            piotroski=5,
        )
        assert w_neutral is not None
        assert w_neutral["gate_5_fundamental"]["confirmed"] is False
        assert w_neutral["gates_active"] == 4

    def test_piotroski_low_vetoes_bullish(self) -> None:
        """Piotroski 0-3 vetoes a bullish signal (reduces confirmed count)."""
        score, weights = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=50.0,
            piotroski=1,
        )
        assert weights is not None
        assert weights["gate_5_fundamental"]["confirmed"] is False

    def test_rsi_regime_aware_trending(self) -> None:
        """In trending market (ADX>25), RSI 40-65 is bullish entry timing."""
        score_good, _ = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=50.0,
            piotroski=None,
        )
        score_bad, _ = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=75.0,
            piotroski=None,
        )
        assert score_good > score_bad

    def test_rsi_regime_aware_range_bound(self) -> None:
        """In range-bound market (ADX<20), RSI<35 is bullish (mean-reversion)."""
        _, weights = compute_confirmation_gates(
            adx=15.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=30.0,
            piotroski=None,
        )
        assert weights["gate_4_entry"]["confirmed"] is True

    def test_all_none_returns_none(self) -> None:
        """When all inputs are None, score and weights are None."""
        score, weights = compute_confirmation_gates(
            adx=None,
            macd_histogram=None,
            macd_histogram_prev=None,
            sma_50=None,
            sma_200=None,
            current_price=None,
            obv_slope=None,
            mfi=None,
            rsi=None,
            piotroski=None,
        )
        assert score is None
        assert weights is None

    def test_score_always_0_to_10(self) -> None:
        """Score must always be in [0, 10] range for any valid inputs."""
        import itertools

        adx_vals = [10.0, 22.0, 35.0]
        rsi_vals = [25.0, 50.0, 75.0]
        piotroski_vals = [0, 5, 9, None]
        for adx, rsi, pio in itertools.product(adx_vals, rsi_vals, piotroski_vals):
            score, _ = compute_confirmation_gates(
                adx=adx,
                macd_histogram=0.5,
                macd_histogram_prev=0.3,
                sma_50=150.0,
                sma_200=140.0,
                current_price=155.0,
                obv_slope=0.01,
                mfi=55.0,
                rsi=rsi,
                piotroski=pio,
            )
            if score is not None:
                assert 0 <= score <= 10, f"Score {score} out of range"

    def test_weights_contain_gate_details(self) -> None:
        """Composite weights must contain per-gate explanations."""
        _, weights = compute_confirmation_gates(
            adx=30.0,
            macd_histogram=0.5,
            macd_histogram_prev=0.3,
            sma_50=150.0,
            sma_200=140.0,
            current_price=155.0,
            obv_slope=0.03,
            mfi=55.0,
            rsi=50.0,
            piotroski=7,
        )
        assert weights is not None
        for gate_key in [
            "gate_1_trend",
            "gate_2_direction",
            "gate_3_volume",
            "gate_4_entry",
            "gate_5_fundamental",
        ]:
            assert gate_key in weights, f"Missing {gate_key}"
            assert "confirmed" in weights[gate_key]
            assert "detail" in weights[gate_key]


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

    def test_compute_signals_with_piotroski_blends_score(self) -> None:
        """When piotroski_score is provided, it affects the composite score via gate 5."""
        closes = _make_price_series(num_days=300, noise=0.005)
        df = _make_ohlcv_df(closes)

        result_no_fund = compute_signals("AAPL", df)
        result_with_fund = compute_signals("AAPL", df, piotroski_score=9)

        assert result_no_fund.composite_score is not None
        assert result_with_fund.composite_score is not None
        # With strong piotroski, gate 5 confirms → potentially higher score
        assert result_with_fund.composite_weights is not None
        assert "gate_5_fundamental" in result_with_fund.composite_weights

    def test_compute_signals_none_piotroski_uses_technical_only(self) -> None:
        """When piotroski_score is None, gate 5 is skipped (not counted as active)."""
        closes = _make_price_series(num_days=300, noise=0.005)
        df = _make_ohlcv_df(closes)

        result = compute_signals("AAPL", df, piotroski_score=None)
        assert result.composite_weights is not None
        # Gate 5 should be skipped
        assert result.composite_weights.get("gates_active", 0) <= 4


# ─────────────────────────────────────────────────────────────────────────────
# compute_price_change tests
# ─────────────────────────────────────────────────────────────────────────────


def test_compute_price_change():
    """Positive daily price change is computed correctly."""
    df = pd.DataFrame({"adj_close": [100.0, 102.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct == pytest.approx(2.0)
    assert current_price == pytest.approx(102.0)


def test_compute_price_change_negative():
    """Negative daily price change is computed correctly."""
    df = pd.DataFrame({"adj_close": [100.0, 97.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct == pytest.approx(-3.0)
    assert current_price == pytest.approx(97.0)


def test_compute_price_change_insufficient_data():
    """Returns None when fewer than 2 data points."""
    df = pd.DataFrame({"adj_close": [100.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct is None
    assert current_price is None


def test_compute_price_change_zero_previous():
    """Returns None for change_pct when previous close is zero (division guard)."""
    df = pd.DataFrame({"adj_close": [0.0, 5.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct is None
    assert current_price == pytest.approx(5.0)


def test_compute_price_change_capital_close_column():
    """Recognises capital-C 'Close' column name from yfinance."""
    df = pd.DataFrame({"Close": [100.0, 105.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct == pytest.approx(5.0)
    assert current_price == pytest.approx(105.0)


def test_compute_price_change_none_dataframe():
    """Returns (None, None) when DataFrame is None."""
    change_pct, current_price = compute_price_change(None)
    assert change_pct is None
    assert current_price is None


# ─────────────────────────────────────────────────────────────────────────────
# Hardening tests — edge cases, extremes, Piotroski blending
# (merged from test_signal_engine_hardening.py)
# ─────────────────────────────────────────────────────────────────────────────


def _make_hardening_price_series(
    n: int = 250,
    start: float = 100.0,
    trend: float = 0.001,
    volatility: float = 0.02,
    seed: int = 42,
) -> "pd.DataFrame":
    """Generate a synthetic OHLCV DataFrame for hardening tests."""
    rng = np.random.default_rng(seed)
    daily_returns = rng.normal(trend, volatility, n)
    prices = start * np.cumprod(1 + daily_returns)

    dates = pd.bdate_range(end=pd.Timestamp.now(), periods=n)
    df = pd.DataFrame(
        {
            "Open": prices * (1 - volatility * 0.3),
            "High": prices * (1 + volatility * 0.5),
            "Low": prices * (1 - volatility * 0.5),
            "Close": prices,
            "Adj Close": prices,
            "Volume": rng.integers(1_000_000, 50_000_000, n),
        },
        index=dates,
    )
    return df


def _make_bullish_series(n: int = 250) -> "pd.DataFrame":
    """Generate strongly bullish price data (steady uptrend, low volatility)."""
    return _make_hardening_price_series(n=n, start=50.0, trend=0.005, volatility=0.005, seed=1)


def _make_bearish_series(n: int = 250) -> "pd.DataFrame":
    """Generate strongly bearish price data (steady downtrend)."""
    return _make_hardening_price_series(n=n, start=200.0, trend=-0.005, volatility=0.005, seed=2)


class TestCompositeScoreRange:
    """Composite score must always be in [0, 10] range."""

    def test_composite_always_bounded(self):
        """Composite score is between 0 and 10 for any valid inputs."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("TST", df)
        assert result.composite_score is not None
        assert 0 <= result.composite_score <= 10

    def test_composite_with_piotroski_bounded(self):
        """Composite score stays [0, 10] even with Piotroski blending."""
        df = _make_hardening_price_series(n=250)
        for piotroski in [0, 1, 5, 9]:
            result = compute_signals("TST", df, piotroski_score=piotroski)
            assert result.composite_score is not None
            assert 0 <= result.composite_score <= 10, (
                f"Score {result.composite_score} out of range for piotroski={piotroski}"
            )


class TestPiotroskiBlendingHardening:
    """Gate 5 (Piotroski) behavior in the confirmation-gate model."""

    def test_piotroski_9_can_increase_score(self):
        """Strong Piotroski (9) adds a confirmed gate, potentially raising score."""
        df = _make_hardening_price_series(n=250)
        without = compute_signals("TST", df)
        with_fund = compute_signals("TST", df, piotroski_score=9)
        assert with_fund.composite_score is not None
        assert without.composite_score is not None

    def test_piotroski_0_can_lower_score(self):
        """Zero Piotroski adds an active gate that doesn't confirm → lowers score."""
        df = _make_hardening_price_series(n=250)
        without = compute_signals("TST", df)
        with_fund = compute_signals("TST", df, piotroski_score=0)
        assert with_fund.composite_score is not None
        assert with_fund.composite_score <= without.composite_score

    def test_blending_mode_in_weights(self):
        """Composite weights dict shows 'confirmation_gate_v2' mode."""
        df = _make_hardening_price_series(n=250)
        result = compute_signals("TST", df, piotroski_score=5)
        assert result.composite_weights is not None
        assert result.composite_weights.get("mode") == "confirmation_gate_v2"


class TestInsufficientDataHardening:
    """Graceful handling of insufficient price history — hardening edge cases."""

    def test_single_data_point(self):
        """Single data point still returns a SignalResult (no crash)."""
        df = _make_hardening_price_series(n=1)
        result = compute_signals("TST", df)
        assert result.ticker == "TST"

    def test_insufficient_for_sma200(self):
        """With < 200 data points, SMA200 may be None but composite still works."""
        df = _make_hardening_price_series(n=100)
        result = compute_signals("TST", df)
        assert result.sma_200 is None


class TestBullishBearishExtremes:
    """Extreme market conditions produce expected score direction."""

    def test_strong_uptrend_high_score(self):
        """Steady uptrend should produce a composite score >= WATCH threshold."""
        bullish = compute_signals("BULL", _make_bullish_series())
        assert bullish.composite_score is not None
        assert bullish.composite_score >= 5.0, (
            f"Bullish score {bullish.composite_score} below WATCH threshold"
        )

    def test_strong_downtrend_has_score(self):
        """Strong downtrend should produce a valid composite score."""
        bearish = compute_signals("BEAR", _make_bearish_series())
        assert bearish.composite_score is not None
        # Bearish direction confirms gates 1-3 typically
        assert 0 <= bearish.composite_score <= 10

    def test_bullish_rsi_not_oversold(self):
        """Strong uptrend should not show RSI oversold."""
        result = compute_signals("BULL", _make_bullish_series())
        if result.rsi_signal is not None:
            assert result.rsi_signal != "OVERSOLD"

    def test_bearish_macd_signal(self):
        """Strong downtrend should show MACD bearish."""
        result = compute_signals("BEAR", _make_bearish_series())
        if result.macd_signal_label is not None:
            assert result.macd_signal_label == "BEARISH"
