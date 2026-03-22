"""Recommendation engine hardening tests — portfolio-aware logic, thresholds, edge cases."""

from backend.tools.recommendations import generate_recommendation
from backend.tools.signals import SignalResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    ticker: str = "TST",
    composite_score: float = 6.5,
    rsi_value: float = 55.0,
    rsi_signal: str = "NEUTRAL",
    macd_histogram: float = 0.3,
    macd_signal_label: str = "BULLISH",
    sma_signal: str = "ABOVE_200",
) -> SignalResult:
    """Create a minimal SignalResult for recommendation testing."""
    return SignalResult(
        ticker=ticker,
        rsi_value=rsi_value,
        rsi_signal=rsi_signal,
        macd_value=1.5,
        macd_histogram=macd_histogram,
        macd_signal_label=macd_signal_label,
        sma_50=150.0,
        sma_200=145.0,
        sma_signal=sma_signal,
        bb_upper=160.0,
        bb_lower=140.0,
        bb_position="MIDDLE",
        annual_return=0.15,
        volatility=0.22,
        sharpe_ratio=0.48,
        composite_score=composite_score,
        composite_weights={"total": composite_score},
    )


def _make_portfolio_state(
    is_held: bool = False,
    allocation_pct: float = 0.0,
    sector_allocation_pct: float = 0.0,
    total_value: float = 100_000.0,
) -> dict:
    """Create a portfolio state dict matching the generate_recommendation() interface."""
    return {
        "is_held": is_held,
        "allocation_pct": allocation_pct,
        "sector_allocation_pct": sector_allocation_pct,
        "total_value": total_value,
    }


# ===========================================================================
# Score threshold tests
# ===========================================================================


class TestScoreThresholds:
    """Verify BUY/WATCH/AVOID thresholds at boundaries."""

    def test_score_above_buy_threshold_gives_buy(self):
        """Score >= 8.0 without portfolio context → BUY."""
        signal = _make_signal(composite_score=8.5)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.action == "BUY"
        assert rec.is_actionable is True

    def test_score_at_buy_boundary_gives_buy(self):
        """Score exactly 8.0 → BUY."""
        signal = _make_signal(composite_score=8.0)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.action == "BUY"

    def test_score_in_watch_range_gives_watch(self):
        """Score 5.0 <= x < 8.0 → WATCH."""
        signal = _make_signal(composite_score=6.5)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.action == "WATCH"
        assert rec.is_actionable is False

    def test_score_below_watch_gives_avoid(self):
        """Score < 5.0 → AVOID."""
        signal = _make_signal(composite_score=3.0)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.action == "AVOID"
        assert rec.is_actionable is False


# ===========================================================================
# Portfolio-aware tests
# ===========================================================================


class TestPortfolioAware:
    """Portfolio context modifies recommendation behavior."""

    def test_buy_capped_at_max_position_pct(self):
        """When held at max position, BUY becomes HOLD."""
        signal = _make_signal(composite_score=9.0)
        state = _make_portfolio_state(is_held=True, allocation_pct=5.0)
        rec = generate_recommendation(
            signal, current_price=150.0, portfolio_state=state, max_position_pct=5.0
        )
        assert rec.action == "HOLD"

    def test_held_stock_in_watch_range_gives_hold(self):
        """Score 5-8 + already held → HOLD."""
        signal = _make_signal(composite_score=6.0)
        state = _make_portfolio_state(is_held=True, allocation_pct=3.0)
        rec = generate_recommendation(signal, current_price=150.0, portfolio_state=state)
        assert rec.action == "HOLD"

    def test_low_score_held_gives_sell(self):
        """Score < 5 + held → SELL."""
        signal = _make_signal(composite_score=3.0)
        state = _make_portfolio_state(is_held=True, allocation_pct=4.0)
        rec = generate_recommendation(signal, current_price=150.0, portfolio_state=state)
        assert rec.action == "SELL"
        assert rec.is_actionable is True

    def test_very_low_score_sell_high_confidence(self):
        """Score < 2 + held → SELL with HIGH confidence."""
        signal = _make_signal(composite_score=1.5)
        state = _make_portfolio_state(is_held=True, allocation_pct=4.0)
        rec = generate_recommendation(signal, current_price=150.0, portfolio_state=state)
        assert rec.action == "SELL"
        assert rec.confidence == "HIGH"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Edge cases that must not crash."""

    def test_none_portfolio_state_no_crash(self):
        """None portfolio_state should still work."""
        signal = _make_signal(composite_score=7.0)
        rec = generate_recommendation(signal, current_price=150.0, portfolio_state=None)
        assert rec.action in ("BUY", "WATCH", "AVOID", "HOLD", "SELL")

    def test_reasoning_has_required_keys(self):
        """Recommendation reasoning dict must have signals and summary."""
        signal = _make_signal(composite_score=8.5)
        rec = generate_recommendation(signal, current_price=150.0)
        assert "signals" in rec.reasoning
        assert "summary" in rec.reasoning

    def test_recommendation_preserves_ticker(self):
        """Recommendation result keeps the original ticker."""
        signal = _make_signal(ticker="AAPL", composite_score=7.5)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.ticker == "AAPL"

    def test_recommendation_preserves_price(self):
        """Recommendation result keeps the input price."""
        signal = _make_signal(composite_score=7.5)
        rec = generate_recommendation(signal, current_price=123.45)
        assert rec.current_price == 123.45

    def test_high_score_buy_confidence(self):
        """Score >= 9 → BUY with HIGH confidence."""
        signal = _make_signal(composite_score=9.5)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.action == "BUY"
        assert rec.confidence == "HIGH"

    def test_medium_buy_confidence(self):
        """Score 8-9 → BUY with MEDIUM confidence."""
        signal = _make_signal(composite_score=8.2)
        rec = generate_recommendation(signal, current_price=150.0)
        assert rec.action == "BUY"
        assert rec.confidence == "MEDIUM"
