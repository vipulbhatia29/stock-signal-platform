"""Factory-boy factory for SignalConvergenceDaily test instances."""

from __future__ import annotations

from datetime import datetime, timezone

import factory

from backend.models.convergence import SignalConvergenceDaily


class SignalConvergenceDailyFactory(factory.Factory):
    """Factory for SignalConvergenceDaily model instances.

    Produces sane defaults for convergence snapshot rows.
    Override date, ticker, and directional fields per test scenario.
    """

    class Meta:
        model = SignalConvergenceDaily

    date = factory.LazyFunction(lambda: datetime.now(timezone.utc).date())
    ticker = factory.Sequence(lambda n: f"TST{n}")
    rsi_direction = "neutral"
    macd_direction = "neutral"
    sma_direction = "neutral"
    piotroski_direction = "neutral"
    forecast_direction = "neutral"
    news_sentiment = None
    signals_aligned = 0
    convergence_label = "mixed"
    composite_score = 7.5
    actual_return_90d = None
    actual_return_180d = None
