"""Unit tests for the recommendation engine.

These tests verify the decision logic that turns composite scores
into actionable BUY/WATCH/AVOID recommendations. No database or
network calls — pure logic testing.

Test strategy:
  We construct SignalResult objects with specific composite scores
  and verify the recommendation engine produces the correct action,
  confidence level, and reasoning.
"""

from backend.tools.recommendations import (
    Action,
    Confidence,
    generate_recommendation,
)
from backend.tools.signals import SignalResult

# ─────────────────────────────────────────────────────────────────────────────
# Helper: create a SignalResult with a specific composite score
# ─────────────────────────────────────────────────────────────────────────────


def _make_signal(
    ticker: str = "AAPL",
    composite_score: float | None = 7.0,
    rsi_value: float = 55.0,
    rsi_signal: str = "NEUTRAL",
    macd_value: float = 1.5,
    macd_histogram: float = 0.3,
    macd_signal_label: str = "BULLISH",
    sma_50: float = 150.0,
    sma_200: float = 145.0,
    sma_signal: str = "ABOVE_200",
    bb_upper: float = 160.0,
    bb_lower: float = 140.0,
    bb_position: str = "MIDDLE",
    annual_return: float = 0.15,
    volatility: float = 0.22,
    sharpe_ratio: float = 0.48,
) -> SignalResult:
    """Create a SignalResult with sensible defaults that can be overridden.

    This makes tests readable — you only specify the values you care about
    and let the defaults handle the rest.
    """
    return SignalResult(
        ticker=ticker,
        rsi_value=rsi_value,
        rsi_signal=rsi_signal,
        macd_value=macd_value,
        macd_histogram=macd_histogram,
        macd_signal_label=macd_signal_label,
        sma_50=sma_50,
        sma_200=sma_200,
        sma_signal=sma_signal,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        bb_position=bb_position,
        annual_return=annual_return,
        volatility=volatility,
        sharpe_ratio=sharpe_ratio,
        composite_score=composite_score,
        composite_weights={
            "rsi": 1.0,
            "macd": 1.5,
            "sma": 1.5,
            "sharpe": 0.5,
            "total": composite_score or 0,
        },
    )


# ═════════════════════════════════════════════════════════════════════════════
# BUY recommendation tests
# ═════════════════════════════════════════════════════════════════════════════


class TestBuyRecommendation:
    """Tests for when the engine should recommend BUY."""

    def test_score_9_plus_is_buy_high_confidence(self) -> None:
        """Score >= 9 should produce BUY with HIGH confidence."""
        signal = _make_signal(composite_score=9.5)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.BUY
        assert result.confidence == Confidence.HIGH
        assert result.is_actionable is True

    def test_score_8_is_buy_medium_confidence(self) -> None:
        """Score >= 8 but < 9 should produce BUY with MEDIUM confidence."""
        signal = _make_signal(composite_score=8.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.BUY
        assert result.confidence == Confidence.MEDIUM
        assert result.is_actionable is True

    def test_score_8_5_is_buy(self) -> None:
        """Score 8.5 should produce BUY (testing boundary)."""
        signal = _make_signal(composite_score=8.5)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.BUY

    def test_buy_has_reasoning(self) -> None:
        """BUY recommendations should include detailed reasoning."""
        signal = _make_signal(composite_score=9.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.reasoning is not None
        assert "summary" in result.reasoning
        assert "signals" in result.reasoning
        assert len(result.reasoning["summary"]) > 0


# ═════════════════════════════════════════════════════════════════════════════
# WATCH recommendation tests
# ═════════════════════════════════════════════════════════════════════════════


class TestWatchRecommendation:
    """Tests for when the engine should recommend WATCH."""

    def test_score_7_is_watch(self) -> None:
        """Score 7 should produce WATCH (below BUY threshold of 8)."""
        signal = _make_signal(composite_score=7.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.WATCH
        assert result.is_actionable is False

    def test_score_5_is_watch(self) -> None:
        """Score 5 should produce WATCH (at the WATCH threshold)."""
        signal = _make_signal(composite_score=5.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.WATCH

    def test_score_6_5_is_watch_medium_confidence(self) -> None:
        """Score 6.5+ within WATCH range should be MEDIUM confidence."""
        signal = _make_signal(composite_score=6.5)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.WATCH
        assert result.confidence == Confidence.MEDIUM

    def test_score_5_5_is_watch_low_confidence(self) -> None:
        """Score 5.5 within WATCH range should be LOW confidence."""
        signal = _make_signal(composite_score=5.5)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.WATCH
        assert result.confidence == Confidence.LOW


# ═════════════════════════════════════════════════════════════════════════════
# AVOID recommendation tests
# ═════════════════════════════════════════════════════════════════════════════


class TestAvoidRecommendation:
    """Tests for when the engine should recommend AVOID."""

    def test_score_4_is_avoid(self) -> None:
        """Score 4 should produce AVOID (below WATCH threshold of 5)."""
        signal = _make_signal(composite_score=4.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.AVOID
        assert result.is_actionable is False

    def test_score_0_is_avoid_high_confidence(self) -> None:
        """Score 0 (all bearish) should produce AVOID with HIGH confidence."""
        signal = _make_signal(composite_score=0.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.AVOID
        assert result.confidence == Confidence.HIGH

    def test_score_1_5_is_avoid_high_confidence(self) -> None:
        """Score < 2 should produce AVOID with HIGH confidence."""
        signal = _make_signal(composite_score=1.5)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.AVOID
        assert result.confidence == Confidence.HIGH

    def test_score_3_is_avoid_medium_confidence(self) -> None:
        """Score 3 (moderate bearish) should produce AVOID with MEDIUM confidence."""
        signal = _make_signal(composite_score=3.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.AVOID
        assert result.confidence == Confidence.MEDIUM


# ═════════════════════════════════════════════════════════════════════════════
# Edge cases and missing data
# ═════════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Tests for edge cases and missing data."""

    def test_none_score_returns_avoid(self) -> None:
        """When composite_score is None, should AVOID with LOW confidence."""
        signal = _make_signal(composite_score=None)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.AVOID
        assert result.confidence == Confidence.LOW
        assert result.is_actionable is False
        assert "Insufficient data" in result.reasoning["summary"]

    def test_current_price_is_preserved(self) -> None:
        """The current price should be stored for later evaluation."""
        signal = _make_signal(composite_score=8.5)
        result = generate_recommendation(signal, current_price=175.50)

        assert result.current_price == 175.50

    def test_ticker_is_preserved(self) -> None:
        """The ticker should be passed through to the result."""
        signal = _make_signal(ticker="MSFT", composite_score=7.0)
        result = generate_recommendation(signal, current_price=350.0)

        assert result.ticker == "MSFT"

    def test_boundary_score_7_99_is_watch(self) -> None:
        """Score 7.99 (just below 8) should be WATCH, not BUY."""
        signal = _make_signal(composite_score=7.99)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.WATCH

    def test_boundary_score_4_99_is_avoid(self) -> None:
        """Score 4.99 (just below 5) should be AVOID, not WATCH."""
        signal = _make_signal(composite_score=4.99)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.AVOID

    def test_exact_threshold_8_is_buy(self) -> None:
        """Score exactly 8.0 should be BUY (>= threshold)."""
        signal = _make_signal(composite_score=8.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.BUY

    def test_exact_threshold_5_is_watch(self) -> None:
        """Score exactly 5.0 should be WATCH (>= threshold)."""
        signal = _make_signal(composite_score=5.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert result.action == Action.WATCH


# ═════════════════════════════════════════════════════════════════════════════
# Reasoning quality tests
# ═════════════════════════════════════════════════════════════════════════════


class TestReasoning:
    """Tests for the quality and structure of recommendation reasoning."""

    def test_reasoning_includes_signal_breakdown(self) -> None:
        """Reasoning should contain per-signal details."""
        signal = _make_signal(composite_score=7.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert "signals" in result.reasoning
        signals = result.reasoning["signals"]

        # Each signal group should be present
        assert "rsi" in signals
        assert "macd" in signals
        assert "sma" in signals

    def test_reasoning_includes_returns(self) -> None:
        """Reasoning should contain return/risk metrics."""
        signal = _make_signal(composite_score=7.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert "returns" in result.reasoning
        returns = result.reasoning["returns"]
        assert "annual_return" in returns
        assert "volatility" in returns
        assert "sharpe_ratio" in returns

    def test_reasoning_includes_score_breakdown(self) -> None:
        """Reasoning should show how each indicator contributed to the score."""
        signal = _make_signal(composite_score=7.0)
        result = generate_recommendation(signal, current_price=150.0)

        assert "score_breakdown" in result.reasoning

    def test_reasoning_rsi_has_interpretation(self) -> None:
        """RSI section of reasoning should have a human-readable interpretation."""
        signal = _make_signal(composite_score=7.0)
        result = generate_recommendation(signal, current_price=150.0)

        rsi_info = result.reasoning["signals"]["rsi"]
        assert "interpretation" in rsi_info
        assert len(rsi_info["interpretation"]) > 10  # Not empty/trivial
