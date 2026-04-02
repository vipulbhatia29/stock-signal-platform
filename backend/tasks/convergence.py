"""Celery task for computing daily signal convergence snapshots."""

import asyncio
import logging

from backend.tasks import celery_app

logger = logging.getLogger(__name__)


def _classify_rsi(rsi: float | None) -> str:
    """Classify RSI signal direction.

    Args:
        rsi: RSI value (0-100) or None.

    Returns:
        'bullish' if oversold recovery (<40), 'bearish' if overbought (>70), else 'neutral'.
    """
    if rsi is None:
        return "neutral"
    if rsi < 40:
        return "bullish"
    if rsi > 70:
        return "bearish"
    return "neutral"


def _classify_macd(histogram: float | None, prev_histogram: float | None) -> str:
    """Classify MACD signal direction.

    Args:
        histogram: Current MACD histogram value.
        prev_histogram: Previous period MACD histogram.

    Returns:
        'bullish' if positive and rising, 'bearish' if negative and falling, else 'neutral'.
    """
    if histogram is None:
        return "neutral"
    if histogram > 0 and (prev_histogram is None or histogram > prev_histogram):
        return "bullish"
    if histogram < 0 and (prev_histogram is None or histogram < prev_histogram):
        return "bearish"
    return "neutral"


def _classify_sma(current_price: float | None, sma_200: float | None) -> str:
    """Classify SMA signal direction.

    Args:
        current_price: Current stock price.
        sma_200: 200-day simple moving average.

    Returns:
        'bullish' if >2% above SMA-200, 'bearish' if >2% below, else 'neutral'.
    """
    if current_price is None or sma_200 is None or sma_200 == 0:
        return "neutral"
    pct_diff = (current_price - sma_200) / sma_200
    if pct_diff > 0.02:
        return "bullish"
    if pct_diff < -0.02:
        return "bearish"
    return "neutral"


def _classify_piotroski(score: int | None) -> str:
    """Classify Piotroski F-Score signal direction.

    Args:
        score: Piotroski F-Score (0-9).

    Returns:
        'bullish' if >=6, 'bearish' if <=3, else 'neutral'.
    """
    if score is None:
        return "neutral"
    if score >= 6:
        return "bullish"
    if score <= 3:
        return "bearish"
    return "neutral"


def _classify_forecast(predicted_return: float | None) -> str:
    """Classify forecast signal direction.

    Args:
        predicted_return: Predicted percentage return (e.g., 0.05 = +5%).

    Returns:
        'bullish' if >+3%, 'bearish' if <-3%, else 'neutral'.
    """
    if predicted_return is None:
        return "neutral"
    if predicted_return > 0.03:
        return "bullish"
    if predicted_return < -0.03:
        return "bearish"
    return "neutral"


def _compute_convergence_label(directions: list[str]) -> str:
    """Compute convergence label from signal directions.

    Revised thresholds (per domain review):
    - Strong Bull: 4+ bullish, 0 bearish
    - Weak Bull: 3+ bullish, <=1 bearish
    - Strong Bear: 4+ bearish, 0 bullish
    - Weak Bear: 3+ bearish, <=1 bullish
    - Mixed: everything else

    Args:
        directions: List of signal directions ('bullish', 'bearish', 'neutral').

    Returns:
        Convergence label string.
    """
    bullish = directions.count("bullish")
    bearish = directions.count("bearish")

    if bullish >= 4 and bearish == 0:
        return "strong_bull"
    if bullish >= 3 and bearish <= 1:
        return "weak_bull"
    if bearish >= 4 and bullish == 0:
        return "strong_bear"
    if bearish >= 3 and bullish <= 1:
        return "weak_bear"
    return "mixed"


@celery_app.task(name="backend.tasks.convergence.compute_convergence_snapshot_task")
def compute_convergence_snapshot_task():
    """Nightly task: compute convergence state for all tracked tickers.

    Also backfills actual_return_90d/180d for rows from 90/180 days ago.
    """
    return asyncio.run(_compute_convergence_snapshot_async())


async def _compute_convergence_snapshot_async() -> dict:
    """Compute and store daily convergence snapshot.

    Returns:
        Status dict with count of computed snapshots.
    """
    # Implementation: query latest signals, classify directions,
    # compute labels, store rows, backfill actual returns.
    # Full DB wiring deferred to Sprint 4 integration.
    logger.info("Convergence snapshot task — implementation pending full wiring")
    return {"status": "ok", "computed": 0}
