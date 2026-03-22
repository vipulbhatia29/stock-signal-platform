"""Signal engine hardening tests — edge cases, composite scoring, Piotroski blending."""

import numpy as np
import pandas as pd

from backend.tools.signals import compute_composite_score, compute_signals

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_price_series(
    n: int = 250,
    start: float = 100.0,
    trend: float = 0.001,
    volatility: float = 0.02,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame for signal computation.

    Args:
        n: Number of trading days.
        start: Starting close price.
        trend: Daily drift (positive = uptrend).
        volatility: Daily return standard deviation.
        seed: Random seed for reproducibility.
    """
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


def _make_bullish_series(n: int = 250) -> pd.DataFrame:
    """Generate strongly bullish price data (steady uptrend, low volatility)."""
    return _make_price_series(n=n, start=50.0, trend=0.005, volatility=0.005, seed=1)


def _make_bearish_series(n: int = 250) -> pd.DataFrame:
    """Generate strongly bearish price data (steady downtrend)."""
    return _make_price_series(n=n, start=200.0, trend=-0.005, volatility=0.005, seed=2)


# ===========================================================================
# Composite score tests
# ===========================================================================


class TestCompositeScoreRange:
    """Composite score must always be in [0, 10] range."""

    def test_composite_always_bounded(self):
        """Composite score is between 0 and 10 for any valid inputs."""
        df = _make_price_series(n=250)
        result = compute_signals("TST", df)
        assert result.composite_score is not None
        assert 0 <= result.composite_score <= 10

    def test_composite_with_piotroski_bounded(self):
        """Composite score stays [0, 10] even with Piotroski blending."""
        df = _make_price_series(n=250)
        for piotroski in [0, 1, 5, 9]:
            result = compute_signals("TST", df, piotroski_score=piotroski)
            assert result.composite_score is not None
            assert 0 <= result.composite_score <= 10, (
                f"Score {result.composite_score} out of range for piotroski={piotroski}"
            )


class TestPiotroskiBlending:
    """50/50 blending when piotroski_score is provided."""

    def test_piotroski_changes_score(self):
        """Providing piotroski_score changes the composite score vs technical-only."""
        df = _make_price_series(n=250)
        tech_only = compute_signals("TST", df)
        blended = compute_signals("TST", df, piotroski_score=9)
        assert tech_only.composite_score != blended.composite_score

    def test_piotroski_9_boosts_score(self):
        """Perfect Piotroski (9) should increase score vs technical-only for weak technicals."""
        df = _make_bearish_series()
        tech_only = compute_signals("TST", df)
        blended = compute_signals("TST", df, piotroski_score=9)
        # Piotroski 9 → fundamental_score = 10 → blend lifts the composite
        assert blended.composite_score > tech_only.composite_score

    def test_piotroski_0_lowers_score(self):
        """Zero Piotroski should lower score vs technical-only for strong technicals."""
        df = _make_bullish_series()
        tech_only = compute_signals("TST", df)
        blended = compute_signals("TST", df, piotroski_score=0)
        # Piotroski 0 → fundamental_score = 0 → blend drags the composite down
        assert blended.composite_score < tech_only.composite_score

    def test_blending_mode_in_weights(self):
        """Composite weights dict shows '50/50' mode when piotroski is provided."""
        df = _make_price_series(n=250)
        result = compute_signals("TST", df, piotroski_score=5)
        assert result.composite_weights is not None
        assert result.composite_weights.get("mode") == "50/50"


class TestInsufficientData:
    """Graceful handling of insufficient price history."""

    def test_single_data_point(self):
        """Single data point still returns a SignalResult (no crash)."""
        df = _make_price_series(n=1)
        result = compute_signals("TST", df)
        # May return None indicators but must not crash
        assert result.ticker == "TST"

    def test_insufficient_for_sma200(self):
        """With < 200 data points, SMA200 may be None but composite still works."""
        df = _make_price_series(n=100)
        result = compute_signals("TST", df)
        assert result.sma_200 is None
        # Composite should still be calculated from available indicators
        # (it may or may not be None depending on other indicators)

    def test_sufficient_for_all_indicators(self):
        """With 250+ data points, all indicators should be populated."""
        df = _make_price_series(n=300)
        result = compute_signals("TST", df)
        assert result.rsi_value is not None
        assert result.macd_value is not None
        assert result.sma_50 is not None
        assert result.sma_200 is not None
        assert result.bb_upper is not None
        assert result.composite_score is not None


class TestBullishBearishExtremes:
    """Extreme market conditions produce expected score direction."""

    def test_strong_uptrend_high_score(self):
        """Steady uptrend should produce a higher composite score."""
        bullish = compute_signals("BULL", _make_bullish_series())
        bearish = compute_signals("BEAR", _make_bearish_series())
        assert bullish.composite_score is not None
        assert bearish.composite_score is not None
        assert bullish.composite_score > bearish.composite_score

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


class TestCompositeScoreFunction:
    """Direct tests on compute_composite_score()."""

    def test_all_none_returns_none(self):
        """All None inputs returns None composite."""
        score, weights = compute_composite_score(None, None, None, None, None, None)
        assert score is None

    def test_max_possible_technical_score(self):
        """Perfect technical signals should yield score of 10."""
        score, weights = compute_composite_score(
            rsi_value=25.0,
            rsi_signal="OVERSOLD",
            macd_histogram=1.0,
            macd_signal="BULLISH",
            sma_signal="GOLDEN_CROSS",
            sharpe=2.0,
        )
        assert score == 10.0

    def test_min_possible_technical_score(self):
        """Worst technical signals should yield score of 0."""
        score, weights = compute_composite_score(
            rsi_value=80.0,
            rsi_signal="OVERBOUGHT",
            macd_histogram=-1.0,
            macd_signal="BEARISH",
            sma_signal="DEATH_CROSS",
            sharpe=-0.5,
        )
        assert score == 0.0
