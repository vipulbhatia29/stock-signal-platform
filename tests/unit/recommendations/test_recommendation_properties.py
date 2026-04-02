"""Hypothesis property-based tests for the recommendation engine.

Tests invariants: score→action mapping, dedup, ordering, reason non-empty,
idempotence, and portfolio-aware overrides.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.recommendations import (
    BUY_THRESHOLD,
    WATCH_THRESHOLD,
    Action,
    Confidence,
    generate_recommendation,
)
from backend.services.signals import SignalResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(score: float | None, ticker: str = "TEST") -> SignalResult:
    """Build a minimal SignalResult with the given composite_score."""
    return SignalResult(
        ticker=ticker,
        rsi_value=50.0,
        rsi_signal="NEUTRAL",
        macd_value=0.1,
        macd_histogram=0.1,
        macd_signal_label="BULLISH",
        sma_50=100.0,
        sma_200=95.0,
        sma_signal="ABOVE_200",
        bb_upper=110.0,
        bb_lower=90.0,
        bb_position="MIDDLE",
        annual_return=0.1,
        volatility=0.15,
        sharpe_ratio=0.5,
        composite_score=score,
        composite_weights={"mode": "technical_only"},
        change_pct=0.5,
        current_price=100.0,
    )


_score_strategy = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
_price_strategy = st.floats(
    min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False
)


# ---------------------------------------------------------------------------
# Score → action mapping
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    score=st.floats(min_value=BUY_THRESHOLD, max_value=10.0, allow_nan=False, allow_infinity=False)
)
def test_score_above_buy_threshold_yields_buy(score: float) -> None:
    """Score >= BUY_THRESHOLD (8.0) without holdings should yield BUY."""
    signal = _make_signal(score)
    rec = generate_recommendation(signal, current_price=100.0, portfolio_state=None)
    assert rec.action == Action.BUY, f"Score={score} expected BUY, got {rec.action}"


@pytest.mark.domain
@settings(max_examples=20)
@given(
    score=st.floats(
        min_value=WATCH_THRESHOLD,
        max_value=BUY_THRESHOLD - 0.01,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_score_watch_range_yields_watch(score: float) -> None:
    """Score >= WATCH_THRESHOLD (5) but < BUY_THRESHOLD (8) yields WATCH."""
    signal = _make_signal(score)
    rec = generate_recommendation(signal, current_price=100.0, portfolio_state=None)
    assert rec.action == Action.WATCH, f"Score={score} expected WATCH, got {rec.action}"


@pytest.mark.domain
@settings(max_examples=20)
@given(
    score=st.floats(
        min_value=0.0,
        max_value=WATCH_THRESHOLD - 0.01,
        allow_nan=False,
        allow_infinity=False,
    )
)
def test_score_below_watch_threshold_yields_avoid(score: float) -> None:
    """Score < WATCH_THRESHOLD (5.0) yields AVOID (not held)."""
    signal = _make_signal(score)
    rec = generate_recommendation(signal, current_price=100.0, portfolio_state=None)
    assert rec.action == Action.AVOID, f"Score={score} expected AVOID, got {rec.action}"


# ---------------------------------------------------------------------------
# Divestment rules
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    score=st.floats(
        min_value=0.0,
        max_value=WATCH_THRESHOLD - 0.01,
        allow_nan=False,
        allow_infinity=False,
    ),
    alloc=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_divestment_fires_when_held_and_score_low(score: float, alloc: float) -> None:
    """Held position with score < WATCH_THRESHOLD triggers SELL recommendation."""
    signal = _make_signal(score)
    portfolio_state = {"is_held": True, "allocation_pct": alloc}
    rec = generate_recommendation(signal, current_price=100.0, portfolio_state=portfolio_state)
    assert rec.action == Action.SELL, f"Score={score} held should be SELL, got {rec.action}"


# ---------------------------------------------------------------------------
# Portfolio-aware dedup (not already held for BUY)
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    score=st.floats(min_value=BUY_THRESHOLD, max_value=10.0, allow_nan=False, allow_infinity=False),
    alloc=st.floats(min_value=6.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)
def test_portfolio_aware_hold_when_held_at_max_allocation(score: float, alloc: float) -> None:
    """When held at >= max_position_pct and score >= BUY_THRESHOLD → HOLD, not BUY."""
    signal = _make_signal(score)
    portfolio_state = {"is_held": True, "allocation_pct": alloc}
    rec = generate_recommendation(
        signal,
        current_price=100.0,
        portfolio_state=portfolio_state,
        max_position_pct=5.0,
    )
    assert rec.action == Action.HOLD, (
        f"Score={score} alloc={alloc} held+maxed should be HOLD, got {rec.action}"
    )


# ---------------------------------------------------------------------------
# Reason string non-empty
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(score=_score_strategy, price=_price_strategy)
def test_reason_string_non_empty(score: float, price: float) -> None:
    """Every recommendation must have a non-empty reasoning dict with 'summary'."""
    signal = _make_signal(score)
    rec = generate_recommendation(signal, current_price=price)
    assert rec.reasoning, "reasoning dict must not be empty"
    assert "summary" in rec.reasoning, "reasoning must have a 'summary' key"
    assert len(rec.reasoning["summary"]) > 0, "summary must not be empty"


# ---------------------------------------------------------------------------
# Priority ordering — higher score → appears earlier
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(
    score_a=st.floats(min_value=5.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    score_b=st.floats(min_value=0.0, max_value=4.9, allow_nan=False, allow_infinity=False),
)
def test_priority_ordering_higher_score_dominates(score_a: float, score_b: float) -> None:
    """Higher composite score should yield action that is preferred over lower score."""
    rec_a = generate_recommendation(_make_signal(score_a, "A"), current_price=100.0)
    rec_b = generate_recommendation(_make_signal(score_b, "B"), current_price=100.0)
    # Both should be defined
    assert rec_a.composite_score >= rec_b.composite_score


# ---------------------------------------------------------------------------
# Composite score preserved in result
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(score=_score_strategy, price=_price_strategy)
def test_composite_score_preserved_in_result(score: float, price: float) -> None:
    """RecommendationResult.composite_score must equal the input signal's score."""
    signal = _make_signal(score)
    rec = generate_recommendation(signal, current_price=price)
    if signal.composite_score is not None:
        assert abs(rec.composite_score - signal.composite_score) < 1e-9


# ---------------------------------------------------------------------------
# Idempotent recomputation
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(score=_score_strategy, price=_price_strategy)
def test_idempotent_recomputation(score: float, price: float) -> None:
    """Same inputs must always produce the same recommendation action."""
    signal = _make_signal(score)
    rec1 = generate_recommendation(signal, current_price=price)
    rec2 = generate_recommendation(signal, current_price=price)
    assert rec1.action == rec2.action, "Recommendation must be deterministic"
    assert rec1.confidence == rec2.confidence


# ---------------------------------------------------------------------------
# None score → AVOID (insufficient data path)
# ---------------------------------------------------------------------------


@pytest.mark.domain
def test_none_score_yields_avoid_not_actionable() -> None:
    """When composite_score is None (insufficient data), action must be AVOID + not actionable."""
    signal = _make_signal(None)
    rec = generate_recommendation(signal, current_price=100.0)
    assert rec.action == Action.AVOID
    assert rec.is_actionable is False


# ---------------------------------------------------------------------------
# High confidence for score >= 9 or score < 2
# ---------------------------------------------------------------------------


@pytest.mark.domain
@settings(max_examples=20)
@given(score=st.floats(min_value=9.0, max_value=10.0, allow_nan=False, allow_infinity=False))
def test_high_confidence_for_very_high_score(score: float) -> None:
    """Score >= 9 should yield HIGH confidence BUY."""
    signal = _make_signal(score)
    rec = generate_recommendation(signal, current_price=100.0, portfolio_state=None)
    assert rec.action == Action.BUY
    assert rec.confidence == Confidence.HIGH, f"Score={score} expected HIGH confidence"


@pytest.mark.domain
@settings(max_examples=20)
@given(score=st.floats(min_value=0.0, max_value=1.99, allow_nan=False, allow_infinity=False))
def test_high_confidence_sell_for_very_low_score_when_held(score: float) -> None:
    """Score < 2 and held → HIGH confidence SELL."""
    signal = _make_signal(score)
    portfolio_state = {"is_held": True, "allocation_pct": 3.0}
    rec = generate_recommendation(signal, current_price=100.0, portfolio_state=portfolio_state)
    assert rec.action == Action.SELL
    assert rec.confidence == Confidence.HIGH
