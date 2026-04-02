"""Unit tests for SignalConvergenceDaily model instantiation."""

from datetime import date

from backend.models.convergence import SignalConvergenceDaily


def test_convergence_daily_instantiation():
    """SignalConvergenceDaily can be instantiated with nullable news_sentiment."""
    row = SignalConvergenceDaily(
        date=date(2026, 4, 1),
        ticker="AAPL",
        rsi_direction="bullish",
        macd_direction="bullish",
        sma_direction="bullish",
        piotroski_direction="bullish",
        forecast_direction="neutral",
        news_sentiment=None,
        signals_aligned=4,
        convergence_label="strong_bull",
        composite_score=8.5,
    )
    assert row.signals_aligned == 4
    assert row.convergence_label == "strong_bull"
    assert row.news_sentiment is None  # nullable until Spec B


def test_convergence_daily_repr():
    """SignalConvergenceDaily repr includes ticker and convergence label."""
    row = SignalConvergenceDaily(
        date=date(2026, 4, 1),
        ticker="MSFT",
        convergence_label="mixed",
    )
    assert "MSFT" in repr(row)
    assert "mixed" in repr(row)
