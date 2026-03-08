"""Recommendation engine — generate Buy/Watch/Avoid decisions from signals.

This module takes computed signal results and turns them into actionable
recommendations. In Phase 1, the logic is simple:

  Score >= 8  → BUY   (strong technical signals across the board)
  Score 5-7   → WATCH (mixed signals, worth monitoring)
  Score < 5   → AVOID (weak or bearish signals)

Phase 3 will add portfolio-aware logic:
  - Position sizing (how many dollars to invest)
  - Sector concentration checks (don't put too much in one sector)
  - Cash reserve enforcement (always keep 10% in cash)
  - Stop-loss alerts (sell when price drops below threshold)

Decision Confidence Levels:
  HIGH   — Multiple indicators agree, clear direction
  MEDIUM — Some indicators agree, but mixed signals
  LOW    — Only marginal signals, high uncertainty

What is a "recommendation snapshot"?
  Each recommendation is a point-in-time record. We save the stock's price
  at the time of recommendation so we can later evaluate whether the
  recommendation was correct (did the stock actually go up after a BUY?).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.recommendation import RecommendationSnapshot
from backend.tools.signals import SignalResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Score thresholds — these define the boundaries for each action
# ─────────────────────────────────────────────────────────────────────────────
BUY_THRESHOLD = 8.0  # Score >= 8 → BUY
WATCH_THRESHOLD = 5.0  # Score >= 5 but < 8 → WATCH
# Below 5 → AVOID


# ─────────────────────────────────────────────────────────────────────────────
# Action and Confidence enums (as string constants)
# ─────────────────────────────────────────────────────────────────────────────
class Action:
    """Possible recommendation actions.

    BUY:   Strong buy signal — consider purchasing this stock.
    WATCH: Mixed signals — add to watchlist and monitor.
    AVOID: Weak signals — don't buy, or consider selling if held.
    HOLD:  Currently unused in Phase 1 (needs portfolio context in Phase 3).
    SELL:  Currently unused in Phase 1 (needs portfolio context in Phase 3).
    """

    BUY = "BUY"
    WATCH = "WATCH"
    AVOID = "AVOID"
    HOLD = "HOLD"
    SELL = "SELL"


class Confidence:
    """Confidence level for a recommendation.

    HIGH:   Multiple indicators agree strongly (e.g., score 9+ or score < 2).
    MEDIUM: Some agreement but not overwhelming.
    LOW:    Marginal signals, borderline scores.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation result — the output of the decision engine
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class RecommendationResult:
    """The output of the recommendation engine for a single stock.

    This captures the decision (action), how confident we are, and the
    reasoning behind it. The reasoning dict is stored as JSONB in the
    database so we can inspect why each recommendation was made.
    """

    ticker: str
    action: str  # BUY, WATCH, or AVOID
    confidence: str  # HIGH, MEDIUM, or LOW
    composite_score: float  # The score that drove the decision
    current_price: float  # Stock price at time of recommendation
    reasoning: dict  # Human-readable explanation of why
    is_actionable: bool  # True if the user should act on this


def generate_recommendation(
    signal: SignalResult,
    current_price: float,
) -> RecommendationResult:
    """Generate a BUY/WATCH/AVOID recommendation from a signal result.

    This is the Phase 1 decision engine. It uses simple score thresholds
    to decide what action to recommend. The logic is intentionally simple:

      Score >= 8  →  BUY with HIGH confidence
      Score >= 7  →  BUY with MEDIUM confidence (strong but not overwhelming)
      Score >= 5  →  WATCH with MEDIUM confidence
      Score < 5   →  AVOID
      Score < 2   →  AVOID with HIGH confidence (very bearish)

    The reasoning dict captures exactly WHY the recommendation was made,
    including which signals contributed most to the score. This is important
    for transparency — you should always be able to explain a recommendation.

    Args:
        signal: A SignalResult from compute_signals(). Contains all
                technical indicator values and the composite score.
        current_price: The current stock price. Stored so we can later
                       evaluate if the recommendation was correct.

    Returns:
        A RecommendationResult with the action, confidence, and reasoning.
    """
    score = signal.composite_score

    # ── Handle missing score ─────────────────────────────────────────
    # If signals couldn't be computed (not enough data), we can't recommend
    if score is None:
        return RecommendationResult(
            ticker=signal.ticker,
            action=Action.AVOID,
            confidence=Confidence.LOW,
            composite_score=0.0,
            current_price=current_price,
            reasoning={
                "summary": "Insufficient data to compute signals",
                "detail": "Need at least 200 trading days of price data",
            },
            is_actionable=False,
        )

    # ── Build the reasoning dict ─────────────────────────────────────
    # This captures a snapshot of all the signals that led to this decision.
    # When you look at a recommendation later, you can see exactly what the
    # indicators were saying at the time.
    reasoning = _build_reasoning(signal)

    # ── Apply decision rules ─────────────────────────────────────────
    if score >= BUY_THRESHOLD:
        # Score 8+: Strong buy signal
        # If score is 9+, we're especially confident because almost all
        # indicators agree (each contributes max 2.5, so 9/10 = 3.6/4 agree)
        action = Action.BUY
        confidence = Confidence.HIGH if score >= 9.0 else Confidence.MEDIUM
        reasoning["summary"] = (
            f"Strong buy signal — composite score {score}/10. "
            "Multiple technical indicators are bullish."
        )
        is_actionable = True

    elif score >= WATCH_THRESHOLD:
        # Score 5-7: Mixed signals — worth monitoring but not a clear buy
        action = Action.WATCH
        confidence = Confidence.MEDIUM if score >= 6.5 else Confidence.LOW
        reasoning["summary"] = (
            f"Mixed signals — composite score {score}/10. "
            "Monitor this stock for improving indicators."
        )
        is_actionable = False

    else:
        # Score < 5: Weak signals — avoid buying
        action = Action.AVOID
        confidence = Confidence.HIGH if score < 2.0 else Confidence.MEDIUM
        reasoning["summary"] = (
            f"Weak signals — composite score {score}/10. Technical indicators are mostly bearish."
        )
        is_actionable = False

    return RecommendationResult(
        ticker=signal.ticker,
        action=action,
        confidence=confidence,
        composite_score=score,
        current_price=current_price,
        reasoning=reasoning,
        is_actionable=is_actionable,
    )


def _build_reasoning(signal: SignalResult) -> dict:
    """Build a detailed reasoning dict from signal values.

    This creates a human-readable breakdown of each signal that contributed
    to the composite score. It's stored as JSONB in the database, so you
    can query it later and understand exactly what happened.

    Example output:
    {
        "signals": {
            "rsi": {"value": 28.5, "label": "OVERSOLD", "interpretation": "..."},
            "macd": {"value": 0.45, "histogram": 0.12, "label": "BULLISH", ...},
            ...
        },
        "returns": {"annual": "15.2%", "volatility": "22.1%", "sharpe": 0.48},
        "score_breakdown": {"rsi": 2.5, "macd": 1.5, "sma": 1.5, "sharpe": 0.5}
    }
    """
    signals = {}

    # RSI breakdown
    if signal.rsi_value is not None:
        signals["rsi"] = {
            "value": signal.rsi_value,
            "label": signal.rsi_signal,
            "interpretation": _rsi_interpretation(signal.rsi_value, signal.rsi_signal),
        }

    # MACD breakdown
    if signal.macd_value is not None:
        signals["macd"] = {
            "value": signal.macd_value,
            "histogram": signal.macd_histogram,
            "label": signal.macd_signal_label,
            "interpretation": _macd_interpretation(signal.macd_histogram, signal.macd_signal_label),
        }

    # SMA breakdown
    if signal.sma_50 is not None or signal.sma_200 is not None:
        signals["sma"] = {
            "sma_50": signal.sma_50,
            "sma_200": signal.sma_200,
            "label": signal.sma_signal,
            "interpretation": _sma_interpretation(signal.sma_signal),
        }

    # Bollinger Bands breakdown
    if signal.bb_upper is not None:
        signals["bollinger"] = {
            "upper": signal.bb_upper,
            "lower": signal.bb_lower,
            "position": signal.bb_position,
        }

    # Risk/return metrics
    returns = {}
    if signal.annual_return is not None:
        returns["annual_return"] = f"{signal.annual_return * 100:.1f}%"
    if signal.volatility is not None:
        returns["volatility"] = f"{signal.volatility * 100:.1f}%"
    if signal.sharpe_ratio is not None:
        returns["sharpe_ratio"] = signal.sharpe_ratio

    reasoning = {
        "signals": signals,
        "returns": returns,
    }

    # Include the score breakdown if available
    if signal.composite_weights is not None:
        reasoning["score_breakdown"] = signal.composite_weights

    return reasoning


def _rsi_interpretation(value: float, label: str | None) -> str:
    """Generate a human-readable interpretation of the RSI value."""
    if label == "OVERSOLD":
        return f"RSI at {value} — oversold territory. The stock may be undervalued, creating a potential buying opportunity."
    elif label == "OVERBOUGHT":
        return f"RSI at {value} — overbought territory. The stock may be overvalued and due for a pullback."
    else:
        return f"RSI at {value} — neutral range. No strong momentum signal."


def _macd_interpretation(histogram: float | None, label: str | None) -> str:
    """Generate a human-readable interpretation of the MACD."""
    if label == "BULLISH":
        return f"MACD histogram at {histogram:.4f} — positive momentum. Short-term trend is above long-term trend."
    else:
        return f"MACD histogram at {histogram:.4f} — negative momentum. Short-term trend is below long-term trend."


def _sma_interpretation(label: str | None) -> str:
    """Generate a human-readable interpretation of the SMA crossover."""
    interpretations = {
        "GOLDEN_CROSS": "Golden Cross detected — the 50-day SMA just crossed above the 200-day SMA, a strong bullish signal.",
        "DEATH_CROSS": "Death Cross detected — the 50-day SMA just crossed below the 200-day SMA, a strong bearish signal.",
        "ABOVE_200": "Price is above the 200-day SMA, indicating a healthy uptrend.",
        "BELOW_200": "Price is below the 200-day SMA, indicating a potential downtrend.",
    }
    return interpretations.get(label, "Unable to determine SMA signal.")


# ─────────────────────────────────────────────────────────────────────────────
# Database persistence
# ─────────────────────────────────────────────────────────────────────────────


async def store_recommendation(
    result: RecommendationResult,
    user_id: str,
    db: AsyncSession,
    generated_at: datetime | None = None,
) -> None:
    """Store a recommendation snapshot in the database.

    Each recommendation is saved with:
      - The action (BUY/WATCH/AVOID)
      - The composite score at the time
      - The stock price at the time (for later accuracy evaluation)
      - Detailed reasoning (as JSONB)

    Uses ON CONFLICT DO UPDATE so re-generating recommendations for the
    same (ticker, user, timestamp) replaces the old one.

    Args:
        result: The RecommendationResult to store.
        user_id: UUID of the user this recommendation is for.
        db: Async database session.
        generated_at: Timestamp of generation. Defaults to now.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    values = {
        "generated_at": generated_at,
        "ticker": result.ticker.upper(),
        "user_id": user_id,
        "action": result.action,
        "confidence": result.confidence,
        "composite_score": result.composite_score,
        "price_at_recommendation": result.current_price,
        "reasoning": result.reasoning,
        "is_actionable": result.is_actionable,
        "acknowledged": False,
    }

    stmt = pg_insert(RecommendationSnapshot).values(values)
    stmt = stmt.on_conflict_do_update(
        # Composite PK: (generated_at, ticker)
        # plus user_id is not part of PK but we match on the timestamp+ticker
        index_elements=["generated_at", "ticker"],
        set_={k: v for k, v in values.items() if k not in ("generated_at", "ticker")},
    )

    await db.execute(stmt)
    await db.commit()

    logger.info(
        "Stored recommendation for %s: %s (confidence=%s, score=%.1f)",
        result.ticker,
        result.action,
        result.confidence,
        result.composite_score,
    )
