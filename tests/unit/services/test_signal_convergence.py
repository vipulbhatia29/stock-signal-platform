"""Unit tests for SignalConvergenceService — direction classification, labels, divergence.

Tests cover the pure-logic classification and convergence computation
without DB interaction. DB-dependent methods (bulk fetch, hit rate)
are tested at the API level with mocked sessions.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.signal_convergence import (
    SignalConvergenceService,
    classify_news_sentiment,
)
from backend.tasks.convergence import (
    _classify_forecast,
    _classify_macd,
    _classify_piotroski,
    _classify_rsi,
    _classify_sma,
    _compute_convergence_label,
)

# ---------------------------------------------------------------------------
# RSI classification
# ---------------------------------------------------------------------------


class TestClassifyRsi:
    """Tests for RSI direction classification."""

    def test_rsi_none_returns_neutral(self) -> None:
        """None RSI is classified as neutral."""
        assert _classify_rsi(None) == "neutral"

    def test_rsi_below_40_returns_bullish(self) -> None:
        """RSI < 40 (oversold recovery) is bullish."""
        assert _classify_rsi(35.0) == "bullish"

    def test_rsi_above_70_returns_bearish(self) -> None:
        """RSI > 70 (overbought) is bearish."""
        assert _classify_rsi(75.0) == "bearish"

    def test_rsi_at_boundary_40_returns_neutral(self) -> None:
        """RSI == 40 is neutral (boundary is exclusive)."""
        assert _classify_rsi(40.0) == "neutral"

    def test_rsi_at_boundary_70_returns_neutral(self) -> None:
        """RSI == 70 is neutral (boundary is exclusive)."""
        assert _classify_rsi(70.0) == "neutral"

    def test_rsi_midrange_returns_neutral(self) -> None:
        """RSI in 40-70 range is neutral."""
        assert _classify_rsi(55.0) == "neutral"


# ---------------------------------------------------------------------------
# MACD classification
# ---------------------------------------------------------------------------


class TestClassifyMacd:
    """Tests for MACD histogram direction classification."""

    def test_macd_none_returns_neutral(self) -> None:
        """None MACD histogram is neutral."""
        assert _classify_macd(None, None) == "neutral"

    def test_macd_positive_rising_returns_bullish(self) -> None:
        """Positive and rising MACD histogram is bullish."""
        assert _classify_macd(0.05, 0.02) == "bullish"

    def test_macd_negative_falling_returns_bearish(self) -> None:
        """Negative and falling MACD histogram is bearish."""
        assert _classify_macd(-0.05, -0.02) == "bearish"

    def test_macd_positive_not_rising_returns_neutral(self) -> None:
        """Positive but not rising MACD is neutral."""
        assert _classify_macd(0.05, 0.08) == "neutral"

    def test_macd_negative_not_falling_returns_neutral(self) -> None:
        """Negative but not falling MACD is neutral."""
        assert _classify_macd(-0.02, -0.05) == "neutral"


# ---------------------------------------------------------------------------
# SMA classification
# ---------------------------------------------------------------------------


class TestClassifySma:
    """Tests for SMA-200 price direction classification."""

    def test_sma_none_price_returns_neutral(self) -> None:
        """None current price is neutral."""
        assert _classify_sma(None, 100.0) == "neutral"

    def test_sma_none_sma_returns_neutral(self) -> None:
        """None SMA is neutral."""
        assert _classify_sma(100.0, None) == "neutral"

    def test_price_above_sma_by_more_than_2pct_returns_bullish(self) -> None:
        """Price > SMA + 2% is bullish."""
        assert _classify_sma(105.0, 100.0) == "bullish"

    def test_price_below_sma_by_more_than_2pct_returns_bearish(self) -> None:
        """Price < SMA - 2% is bearish."""
        assert _classify_sma(95.0, 100.0) == "bearish"

    def test_price_within_2pct_of_sma_returns_neutral(self) -> None:
        """Price within ±2% of SMA is neutral."""
        assert _classify_sma(101.0, 100.0) == "neutral"


# ---------------------------------------------------------------------------
# Piotroski classification
# ---------------------------------------------------------------------------


class TestClassifyPiotroski:
    """Tests for Piotroski F-Score direction classification."""

    def test_piotroski_none_returns_neutral(self) -> None:
        """None Piotroski is neutral."""
        assert _classify_piotroski(None) == "neutral"

    def test_piotroski_high_returns_bullish(self) -> None:
        """F-Score >= 6 is bullish."""
        assert _classify_piotroski(7) == "bullish"

    def test_piotroski_low_returns_bearish(self) -> None:
        """F-Score <= 3 is bearish."""
        assert _classify_piotroski(2) == "bearish"

    def test_piotroski_mid_returns_neutral(self) -> None:
        """F-Score 4-5 is neutral."""
        assert _classify_piotroski(4) == "neutral"

    def test_piotroski_boundary_6_returns_bullish(self) -> None:
        """F-Score == 6 is bullish (boundary inclusive)."""
        assert _classify_piotroski(6) == "bullish"

    def test_piotroski_boundary_3_returns_bearish(self) -> None:
        """F-Score == 3 is bearish (boundary inclusive)."""
        assert _classify_piotroski(3) == "bearish"


# ---------------------------------------------------------------------------
# Forecast classification
# ---------------------------------------------------------------------------


class TestClassifyForecast:
    """Tests for forecast return direction classification."""

    def test_forecast_none_returns_neutral(self) -> None:
        """None predicted return is neutral."""
        assert _classify_forecast(None) == "neutral"

    def test_forecast_above_3pct_returns_bullish(self) -> None:
        """Return > +3% is bullish."""
        assert _classify_forecast(0.05) == "bullish"

    def test_forecast_below_neg3pct_returns_bearish(self) -> None:
        """Return < -3% is bearish."""
        assert _classify_forecast(-0.05) == "bearish"

    def test_forecast_within_3pct_returns_neutral(self) -> None:
        """Return between -3% and +3% is neutral."""
        assert _classify_forecast(0.01) == "neutral"


# ---------------------------------------------------------------------------
# News sentiment classification
# ---------------------------------------------------------------------------


class TestClassifyNewsSentiment:
    """Tests for news sentiment direction classification."""

    def test_sentiment_none_returns_neutral(self) -> None:
        """None sentiment is neutral."""
        assert classify_news_sentiment(None) == "neutral"

    def test_sentiment_positive_returns_bullish(self) -> None:
        """Sentiment > +0.3 is bullish."""
        assert classify_news_sentiment(0.5) == "bullish"

    def test_sentiment_negative_returns_bearish(self) -> None:
        """Sentiment < -0.3 is bearish."""
        assert classify_news_sentiment(-0.5) == "bearish"

    def test_sentiment_near_zero_returns_neutral(self) -> None:
        """Sentiment between -0.3 and +0.3 is neutral."""
        assert classify_news_sentiment(0.1) == "neutral"

    def test_sentiment_boundary_positive_returns_neutral(self) -> None:
        """Sentiment == +0.3 is neutral (boundary exclusive)."""
        assert classify_news_sentiment(0.3) == "neutral"

    def test_sentiment_boundary_negative_returns_neutral(self) -> None:
        """Sentiment == -0.3 is neutral (boundary exclusive)."""
        assert classify_news_sentiment(-0.3) == "neutral"


# ---------------------------------------------------------------------------
# Convergence label computation
# ---------------------------------------------------------------------------


class TestComputeConvergenceLabel:
    """Tests for convergence label logic with revised thresholds."""

    def test_strong_bull_4_bullish_0_bearish(self) -> None:
        """4 bullish + 0 bearish → strong_bull."""
        dirs = ["bullish", "bullish", "bullish", "bullish", "neutral", "neutral"]
        assert _compute_convergence_label(dirs) == "strong_bull"

    def test_strong_bull_6_bullish(self) -> None:
        """All 6 bullish → strong_bull."""
        dirs = ["bullish"] * 6
        assert _compute_convergence_label(dirs) == "strong_bull"

    def test_weak_bull_3_bullish_1_bearish(self) -> None:
        """3 bullish + 1 bearish → weak_bull."""
        dirs = ["bullish", "bullish", "bullish", "bearish", "neutral", "neutral"]
        assert _compute_convergence_label(dirs) == "weak_bull"

    def test_strong_bear_4_bearish_0_bullish(self) -> None:
        """4 bearish + 0 bullish → strong_bear."""
        dirs = ["bearish", "bearish", "bearish", "bearish", "neutral", "neutral"]
        assert _compute_convergence_label(dirs) == "strong_bear"

    def test_weak_bear_3_bearish_1_bullish(self) -> None:
        """3 bearish + 1 bullish → weak_bear."""
        dirs = ["bearish", "bearish", "bearish", "bullish", "neutral", "neutral"]
        assert _compute_convergence_label(dirs) == "weak_bear"

    def test_mixed_2_bullish_2_bearish(self) -> None:
        """2 bullish + 2 bearish → mixed."""
        dirs = ["bullish", "bullish", "bearish", "bearish", "neutral", "neutral"]
        assert _compute_convergence_label(dirs) == "mixed"

    def test_mixed_3_bullish_2_bearish(self) -> None:
        """3 bullish + 2 bearish → mixed (bearish > 1)."""
        dirs = ["bullish", "bullish", "bullish", "bearish", "bearish", "neutral"]
        assert _compute_convergence_label(dirs) == "mixed"

    def test_all_neutral_returns_mixed(self) -> None:
        """All neutral → mixed."""
        dirs = ["neutral"] * 6
        assert _compute_convergence_label(dirs) == "mixed"

    def test_mixed_4_bullish_2_bearish(self) -> None:
        """4 bullish + 2 bearish → mixed (bearish > 0, not strong_bull)."""
        dirs = ["bullish", "bullish", "bullish", "bullish", "bearish", "bearish"]
        assert _compute_convergence_label(dirs) == "mixed"

    @pytest.mark.regression
    def test_mixed_4_bullish_2_bearish_edge_case_not_strong_bull(self) -> None:
        """Regression: 4 bullish + 2 bearish must produce 'mixed', NOT 'strong_bull'.

        strong_bull requires 4+ bullish AND 0 bearish. Two bearish signals prevent
        the strong_bull classification even though bullish count meets the threshold.
        This edge case was identified in KAN-394 (M7) as lacking explicit test coverage.
        """
        dirs = ["bullish", "bullish", "bullish", "bullish", "bearish", "bearish"]
        label = _compute_convergence_label(dirs)
        assert label == "mixed", (
            f"Expected 'mixed' for 4 bullish + 2 bearish but got '{label}'. "
            "strong_bull requires 0 bearish signals."
        )

    @pytest.mark.regression
    def test_mixed_4_bullish_2_bearish_order_independent(self) -> None:
        """Regression: label is order-independent — bearish signals anywhere produce mixed.

        The classification function must count directions, not depend on their order.
        """
        for dirs in [
            ["bearish", "bearish", "bullish", "bullish", "bullish", "bullish"],
            ["bullish", "bearish", "bullish", "bearish", "bullish", "bullish"],
            ["bullish", "bullish", "bearish", "bullish", "bullish", "bearish"],
        ]:
            label = _compute_convergence_label(dirs)
            assert label == "mixed", f"Expected 'mixed' for dirs={dirs} but got '{label}'"


# ---------------------------------------------------------------------------
# Schema validation (C3 — ensure Pydantic round-trip works)
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    """Ensure service output can be serialized by Pydantic response schemas."""

    def test_convergence_response_round_trip(self) -> None:
        """ConvergenceResponse schema accepts service-layer data."""
        from backend.schemas.convergence import ConvergenceResponse

        data = ConvergenceResponse(
            ticker="AAPL",
            date="2026-04-03",
            signals=[
                {"signal": "rsi", "direction": "bullish", "value": 35.0},
                {"signal": "macd", "direction": "neutral", "value": 0.0},
                {"signal": "sma", "direction": "bullish", "value": 200.0},
                {"signal": "piotroski", "direction": "neutral", "value": None},
                {"signal": "forecast", "direction": "bearish", "value": -0.05},
                {"signal": "news", "direction": "neutral", "value": 0.1},
            ],
            signals_aligned=2,
            convergence_label="mixed",
            composite_score=7.5,
            divergence={
                "is_divergent": True,
                "forecast_direction": "bearish",
                "technical_majority": "bullish",
                "historical_hit_rate": 0.61,
                "sample_count": 23,
            },
            rationale="Test rationale.",
        )
        dumped = data.model_dump()
        assert dumped["convergence_label"] == "mixed"
        assert dumped["divergence"]["is_divergent"] is True

    def test_portfolio_convergence_response_round_trip(self) -> None:
        """PortfolioConvergenceResponse schema accepts service-layer data."""
        from backend.schemas.convergence import PortfolioConvergenceResponse

        data = PortfolioConvergenceResponse(
            portfolio_id="abc-123",
            date="2026-04-03",
            positions=[],
            bullish_pct=0.6,
            bearish_pct=0.3,
            mixed_pct=0.1,
            divergent_positions=["MSFT"],
        )
        dumped = data.model_dump()
        assert dumped["bullish_pct"] == 0.6


# ---------------------------------------------------------------------------
# Service _compute_convergence (integration of classification)
# ---------------------------------------------------------------------------


class TestServiceComputeConvergence:
    """Tests for SignalConvergenceService._compute_convergence method."""

    def _make_signal(
        self,
        rsi: float | None = 50.0,
        macd_histogram: float | None = 0.0,
        current_price: float | None = 100.0,
        sma_200: float | None = 100.0,
        composite_score: float | None = 7.5,
        piotroski_score: int | None = None,
    ) -> SimpleNamespace:
        """Create a fake SignalSnapshot-like object.

        Args:
            rsi: RSI value.
            macd_histogram: MACD histogram.
            current_price: Current stock price.
            sma_200: 200-day SMA.
            composite_score: Composite score.
            piotroski_score: Piotroski F-Score (stored in composite_weights).

        Returns:
            SimpleNamespace mimicking SignalSnapshot.
        """
        weights: dict = {}
        if piotroski_score is not None:
            weights["gate_5_fundamental"] = {"piotroski": piotroski_score}
            weights["mode"] = "confirmation_gate_v2"
        return SimpleNamespace(
            rsi_value=rsi,
            macd_histogram=macd_histogram,
            current_price=current_price,
            sma_200=sma_200,
            composite_score=composite_score,
            composite_weights=weights,
            piotroski_score=piotroski_score,
            ticker="AAPL",
        )

    @staticmethod
    def _make_forecast(
        expected_return_pct: float,
    ) -> SimpleNamespace:
        """Create a fake ForecastResult-like object.

        Args:
            expected_return_pct: Expected return percentage (e.g. 5.0 for +5%).

        Returns:
            SimpleNamespace mimicking ForecastResult.
        """
        return SimpleNamespace(
            expected_return_pct=expected_return_pct,
            confidence_score=0.65,
            direction="bullish" if expected_return_pct > 0 else "bearish",
            base_price=100.0,
            drivers=None,
            forecast_signal=None,
        )

    def test_all_bullish_signals(self) -> None:
        """All signals bullish → strong_bull with 6 aligned."""
        signal = self._make_signal(
            rsi=30.0,  # bullish (<40)
            macd_histogram=0.05,  # bullish (>0 and rising)
            current_price=110.0,  # bullish (>2% above SMA)
            sma_200=100.0,
            piotroski_score=8,  # bullish (>=6)
        )
        # Forecast: expected_return_pct=9.0 → +9% → bullish
        forecast = self._make_forecast(9.0)
        service = SignalConvergenceService()
        # prev_macd=0.02 makes histogram rising (0.05 > 0.02) → bullish
        result = service._compute_convergence(
            "AAPL",
            signal,
            0.5,
            forecast,
            prev_macd_histogram=0.02,
        )

        assert result.ticker == "AAPL"
        assert result.convergence_label == "strong_bull"
        assert result.signals_aligned == 6
        assert len(result.signals) == 6
        # Verify every signal is bullish
        for sig in result.signals:
            assert sig.direction == "bullish", f"{sig.signal} should be bullish"

    def test_all_neutral_signals(self) -> None:
        """All signals neutral → mixed, aligned=0."""
        signal = self._make_signal(
            rsi=55.0,
            macd_histogram=0.0,
            current_price=100.0,
            sma_200=100.0,
            piotroski_score=5,
        )
        # Forecast: expected_return_pct=1.0 → +1% → neutral
        forecast = self._make_forecast(1.0)
        service = SignalConvergenceService()
        result = service._compute_convergence("AAPL", signal, 0.0, forecast)

        assert result.convergence_label == "mixed"
        assert result.signals_aligned == 0

    def test_divergence_detected(self) -> None:
        """Forecast bearish while technicals bullish → divergence."""
        signal = self._make_signal(
            rsi=30.0,  # bullish
            macd_histogram=0.05,  # neutral (no prev)
            current_price=110.0,  # bullish
            sma_200=100.0,
            piotroski_score=8,  # bullish
        )
        # Forecast: expected_return_pct=-9.0 → -9% → bearish
        forecast = self._make_forecast(-9.0)
        service = SignalConvergenceService()
        result = service._compute_convergence("AAPL", signal, None, forecast)

        assert result.divergence.is_divergent is True
        assert result.divergence.forecast_direction == "bearish"
        assert result.divergence.technical_majority == "bullish"

    def test_no_divergence_when_forecast_neutral(self) -> None:
        """No divergence when forecast is neutral."""
        signal = self._make_signal(
            rsi=30.0,
            current_price=110.0,
            sma_200=100.0,
            piotroski_score=8,
        )
        # Forecast: expected_return_pct=0.9 → +0.9% → neutral
        forecast = self._make_forecast(0.9)
        service = SignalConvergenceService()
        result = service._compute_convergence("AAPL", signal, None, forecast)

        assert result.divergence.is_divergent is False

    def test_no_forecast_gives_neutral_direction(self) -> None:
        """No forecast data → forecast direction is neutral."""
        signal = self._make_signal(rsi=30.0, current_price=110.0, sma_200=100.0)
        service = SignalConvergenceService()
        result = service._compute_convergence("AAPL", signal, None, None)

        forecast_sig = [s for s in result.signals if s.signal == "forecast"][0]
        assert forecast_sig.direction == "neutral"

    def test_piotroski_from_column(self) -> None:
        """Piotroski is extracted from piotroski_score column (with JSONB fallback)."""
        signal = self._make_signal(piotroski_score=8)
        service = SignalConvergenceService()
        result = service._compute_convergence("AAPL", signal, None, None)

        pio_sig = [s for s in result.signals if s.signal == "piotroski"][0]
        assert pio_sig.direction == "bullish"
        assert pio_sig.value == 8

    def test_signals_list_has_all_six(self) -> None:
        """Result always contains exactly 6 signal directions."""
        signal = self._make_signal()
        service = SignalConvergenceService()
        result = service._compute_convergence("AAPL", signal, None)

        signal_names = {s.signal for s in result.signals}
        assert signal_names == {"rsi", "macd", "sma", "piotroski", "forecast", "news"}


# ---------------------------------------------------------------------------
# Service _labels_for_direction helper
# ---------------------------------------------------------------------------


class TestLabelsForDirection:
    """Tests for the _labels_for_direction helper."""

    def test_bullish_maps_to_bull_labels(self) -> None:
        """Bullish direction maps to strong_bull and weak_bull."""
        assert SignalConvergenceService._labels_for_direction("bullish") == [
            "strong_bull",
            "weak_bull",
        ]

    def test_bearish_maps_to_bear_labels(self) -> None:
        """Bearish direction maps to strong_bear and weak_bear."""
        assert SignalConvergenceService._labels_for_direction("bearish") == [
            "strong_bear",
            "weak_bear",
        ]

    def test_neutral_maps_to_mixed(self) -> None:
        """Neutral direction maps to mixed."""
        assert SignalConvergenceService._labels_for_direction("neutral") == ["mixed"]
