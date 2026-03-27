"""Tests for backend.services.recommendations.

Tests cover the recommendation generation logic and the query helper:
  - generate_recommendation with BUY/AVOID/WATCH signals
  - get_recommendations with action filtering
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services.recommendations import (
    Action,
    Confidence,
    generate_recommendation,
    get_recommendations,
)
from backend.services.signals import SignalResult


def _make_signal(
    ticker: str = "AAPL",
    composite_score: float | None = 8.5,
    rsi_value: float | None = 35.0,
    rsi_signal: str | None = "NEUTRAL",
    macd_value: float | None = 1.5,
    macd_histogram: float | None = 0.3,
    macd_signal_label: str | None = "BULLISH",
    sma_50: float | None = 150.0,
    sma_200: float | None = 140.0,
    sma_signal: str | None = "ABOVE_200",
    bb_upper: float | None = 165.0,
    bb_lower: float | None = 135.0,
    bb_position: str | None = "MIDDLE",
    annual_return: float | None = 0.15,
    volatility: float | None = 0.20,
    sharpe_ratio: float | None = 1.2,
    composite_weights: dict | None = None,
) -> SignalResult:
    """Create a SignalResult with sensible defaults for testing."""
    return SignalResult(
        ticker=ticker,
        composite_score=composite_score,
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
        composite_weights=composite_weights,
    )


class TestGenerateRecommendation:
    """Tests for generate_recommendation()."""

    def test_buy_signal_high_score(self) -> None:
        """Score >= 9 should produce BUY with HIGH confidence."""
        signal = _make_signal(composite_score=9.2)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.BUY
        assert rec.confidence == Confidence.HIGH
        assert rec.composite_score == 9.2
        assert rec.is_actionable is True
        assert rec.ticker == "AAPL"

    def test_buy_signal_medium_confidence(self) -> None:
        """Score >= 8 but < 9 should produce BUY with MEDIUM confidence."""
        signal = _make_signal(composite_score=8.3)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.BUY
        assert rec.confidence == Confidence.MEDIUM
        assert rec.is_actionable is True

    def test_avoid_signal_low_score(self) -> None:
        """Score < 5 should produce AVOID with MEDIUM confidence."""
        signal = _make_signal(composite_score=3.5)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.AVOID
        assert rec.confidence == Confidence.MEDIUM
        assert rec.is_actionable is False

    def test_avoid_signal_very_low_score(self) -> None:
        """Score < 2 should produce AVOID with HIGH confidence."""
        signal = _make_signal(composite_score=1.5)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.AVOID
        assert rec.confidence == Confidence.HIGH
        assert rec.is_actionable is False

    def test_watch_signal_moderate_score(self) -> None:
        """Score >= 5 but < 8 should produce WATCH."""
        signal = _make_signal(composite_score=6.0)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.WATCH
        assert rec.confidence == Confidence.LOW
        assert rec.is_actionable is False

    def test_watch_signal_higher_moderate(self) -> None:
        """Score >= 6.5 but < 8 should produce WATCH with MEDIUM confidence."""
        signal = _make_signal(composite_score=7.0)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.WATCH
        assert rec.confidence == Confidence.MEDIUM

    def test_none_score_returns_avoid(self) -> None:
        """Missing composite score should produce AVOID with LOW confidence."""
        signal = _make_signal(composite_score=None)
        rec = generate_recommendation(signal, current_price=150.0)

        assert rec.action == Action.AVOID
        assert rec.confidence == Confidence.LOW
        assert rec.composite_score == 0.0
        assert rec.is_actionable is False
        assert "Insufficient data" in rec.reasoning["summary"]

    def test_portfolio_held_strong_at_cap_returns_hold(self) -> None:
        """Held stock at max allocation with strong score should HOLD."""
        signal = _make_signal(composite_score=9.0)
        portfolio = {"is_held": True, "allocation_pct": 6.0}
        rec = generate_recommendation(
            signal, current_price=150.0, portfolio_state=portfolio, max_position_pct=5.0
        )

        assert rec.action == Action.HOLD
        assert rec.confidence == Confidence.HIGH

    def test_portfolio_held_moderate_returns_hold(self) -> None:
        """Held stock with moderate score (5-8) should HOLD."""
        signal = _make_signal(composite_score=6.5)
        portfolio = {"is_held": True, "allocation_pct": 3.0}
        rec = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio)

        assert rec.action == Action.HOLD
        assert rec.confidence == Confidence.MEDIUM

    def test_portfolio_held_weak_returns_sell(self) -> None:
        """Held stock with weak score (<5) should SELL."""
        signal = _make_signal(composite_score=3.0)
        portfolio = {"is_held": True, "allocation_pct": 3.0}
        rec = generate_recommendation(signal, current_price=150.0, portfolio_state=portfolio)

        assert rec.action == Action.SELL
        assert rec.is_actionable is True

    def test_reasoning_has_signals_key(self) -> None:
        """Reasoning dict should contain signals breakdown."""
        signal = _make_signal(composite_score=8.5)
        rec = generate_recommendation(signal, current_price=150.0)

        assert "signals" in rec.reasoning
        assert "rsi" in rec.reasoning["signals"]
        assert "macd" in rec.reasoning["signals"]


class TestGetRecommendations:
    """Tests for get_recommendations() query helper."""

    @pytest.mark.asyncio()
    async def test_filters_by_action(self) -> None:
        """Should apply action filter to the query."""
        mock_db = AsyncMock()

        # Mock count query result
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        # Mock data query result
        rec_mock = MagicMock()
        rec_mock.ticker = "AAPL"
        rec_mock.action = "BUY"
        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = [rec_mock]

        mock_db.execute = AsyncMock(side_effect=[count_result, data_result])

        recs, total = await get_recommendations(
            user_id="test-user-id",
            db=mock_db,
            action="BUY",
        )

        assert total == 1
        assert len(recs) == 1
        assert recs[0].action == "BUY"
        assert mock_db.execute.call_count == 2

    @pytest.mark.asyncio()
    async def test_returns_empty_when_no_results(self) -> None:
        """Should return empty list and zero total when no recommendations."""
        mock_db = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[count_result, data_result])

        recs, total = await get_recommendations(
            user_id="test-user-id",
            db=mock_db,
        )

        assert total == 0
        assert len(recs) == 0

    @pytest.mark.asyncio()
    async def test_pagination_params_passed(self) -> None:
        """Should execute queries even with custom limit/offset."""
        mock_db = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        data_result = MagicMock()
        data_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[count_result, data_result])

        recs, total = await get_recommendations(
            user_id="test-user-id",
            db=mock_db,
            limit=10,
            offset=20,
        )

        assert total == 0
        assert mock_db.execute.call_count == 2
