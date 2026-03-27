"""Recommendation generation, position sizing, and query service.

Extracts recommendation logic (previously in tools/recommendations.py) and
recommendation query logic (previously inline in routers/stocks.py) into a
dedicated service layer.

Public API:
  - PortfolioState: TypedDict for portfolio context
  - Action, Confidence: string-constant classes for recommendation actions/confidence
  - RecommendationResult: dataclass holding a single recommendation
  - generate_recommendation(): generate BUY/WATCH/AVOID/HOLD/SELL from signals
  - store_recommendation(): persist a recommendation snapshot to DB
  - calculate_position_size(): compute suggested dollar amount for a BUY
  - get_recommendations(): query user's recommendations with filters + pagination

Constants:
  - BUY_THRESHOLD, WATCH_THRESHOLD, MIN_TRADE_SIZE
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.recommendation import RecommendationSnapshot
from backend.services.signals import SignalResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio context type — passed in from the caller (no DB calls here)
# ─────────────────────────────────────────────────────────────────────────────


class PortfolioState(TypedDict, total=False):
    """Minimal portfolio context passed to the recommendation engine.

    is_held:        True if the user currently holds this ticker.
    allocation_pct: Current portfolio allocation as a percentage (0-100).
                    None if the stock is not held.
    """

    is_held: bool
    allocation_pct: float | None


# ─────────────────────────────────────────────────────────────────────────────
# Score thresholds — these define the boundaries for each action
# ─────────────────────────────────────────────────────────────────────────────
BUY_THRESHOLD = 8.0  # Score >= 8 → BUY
WATCH_THRESHOLD = 5.0  # Score >= 5 but < 8 → WATCH
# Below 5 → AVOID
MIN_TRADE_SIZE = 100.0  # minimum dollar amount worth recommending


# ─────────────────────────────────────────────────────────────────────────────
# Action and Confidence enums (as string constants)
# ─────────────────────────────────────────────────────────────────────────────
class Action:
    """Possible recommendation actions.

    BUY:   Strong buy signal — consider purchasing this stock.
    WATCH: Mixed signals — add to watchlist and monitor.
    AVOID: Weak signals — don't buy, or consider selling if held.
    HOLD:  You hold this stock; signals are neutral — keep the position.
    SELL:  Weak signals and you hold this stock — consider exiting.
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
    action: str  # BUY, WATCH, AVOID, HOLD, or SELL
    confidence: str  # HIGH, MEDIUM, or LOW
    composite_score: float  # The score that drove the decision
    current_price: float  # Stock price at time of recommendation
    reasoning: dict  # Human-readable explanation of why
    is_actionable: bool  # True if the user should act on this
    suggested_amount: float | None = None  # dollar amount to invest (BUY only)


def generate_recommendation(
    signal: SignalResult,
    current_price: float,
    portfolio_state: PortfolioState | None = None,
    max_position_pct: float = 5.0,
) -> RecommendationResult:
    """Generate a BUY/WATCH/AVOID/HOLD/SELL recommendation from a signal result.

    This is the Phase 3 decision engine. It uses simple score thresholds
    to decide what action to recommend. When portfolio_state is supplied and
    the stock is currently held, portfolio-aware overrides apply:

      Held + score >= BUY_THRESHOLD + at max allocation → HOLD (HIGH)
      Held + score >= WATCH_THRESHOLD                  → HOLD (MEDIUM)
      Held + score < WATCH_THRESHOLD                   → SELL (MEDIUM or HIGH)

    Without portfolio context (portfolio_state=None or is_held=False), the
    original Phase 1 logic applies:

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
        portfolio_state: Optional portfolio context. If the stock is held,
                         portfolio-aware HOLD/SELL overrides may apply.
        max_position_pct: Maximum allowed portfolio allocation as a percentage
                          (default 5.0%). Used to gate the BUY→HOLD override.

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

    # ── Portfolio-aware overrides ────────────────────────────────────
    # When the user already holds this stock, context changes the action.
    # HOLD means "keep it, don't buy more"; SELL means "signals are weak, exit".
    if portfolio_state and portfolio_state.get("is_held"):
        alloc = portfolio_state.get("allocation_pct") or 0.0

        if score >= BUY_THRESHOLD and alloc >= max_position_pct:
            # Strong signal but position is already at the size cap → HOLD
            reasoning["summary"] = (
                f"Strong signals (score {score}/10) but already at target allocation "
                f"({alloc:.1f}% \u2265 {max_position_pct:.1f}%). Hold current position."
            )
            return RecommendationResult(
                ticker=signal.ticker,
                action=Action.HOLD,
                confidence=Confidence.HIGH,
                composite_score=score,
                current_price=current_price,
                reasoning=reasoning,
                is_actionable=True,
            )

        # score >= BUY_THRESHOLD but alloc < max_position_pct → fall through to BUY

        if BUY_THRESHOLD > score >= WATCH_THRESHOLD:
            # Moderate signal while held → HOLD (no reason to add or exit)
            reasoning["summary"] = (
                f"Moderate signals (score {score}/10). You hold this stock — hold your position."
            )
            return RecommendationResult(
                ticker=signal.ticker,
                action=Action.HOLD,
                confidence=Confidence.MEDIUM,
                composite_score=score,
                current_price=current_price,
                reasoning=reasoning,
                is_actionable=False,
            )

        if score < WATCH_THRESHOLD:
            # Weak signal while held → SELL
            confidence = Confidence.HIGH if score < 2.0 else Confidence.MEDIUM
            reasoning["summary"] = (
                f"Weak signals (score {score}/10) and you hold this stock. "
                "Consider exiting the position."
            )
            return RecommendationResult(
                ticker=signal.ticker,
                action=Action.SELL,
                confidence=confidence,
                composite_score=score,
                current_price=current_price,
                reasoning=reasoning,
                is_actionable=True,
            )

        # score >= BUY_THRESHOLD and alloc < max_position_pct → fall through to BUY logic

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


def calculate_position_size(
    ticker: str,
    current_allocation_pct: float,
    total_value: float,
    available_cash: float,
    num_target_positions: int,
    max_position_pct: float,
    sector_allocation_pct: float,
    max_sector_pct: float,
) -> float:
    """Calculate how many dollars to invest in a BUY recommendation.

    Uses equal-weight targeting capped by max_position_pct and sector cap.
    Returns 0 if the sector is full, the position is already at target,
    or the suggested amount is below the minimum trade size ($100).

    Args:
        ticker: Stock ticker (used for logging only).
        current_allocation_pct: Current position size as % of portfolio.
        total_value: Total portfolio market value in dollars.
        available_cash: Cash available (total_value - sum of position values).
        num_target_positions: Number of positions to target for equal weighting.
        max_position_pct: Maximum single-position size (from UserPreference).
        sector_allocation_pct: Current sector allocation as % of portfolio.
        max_sector_pct: Maximum sector concentration (from UserPreference).

    Returns:
        Suggested dollar amount to invest, rounded to 2 decimal places.
        Returns 0.0 if the position should not be added to.
    """
    # Sector cap check — if sector is full, don't add more exposure
    if sector_allocation_pct >= max_sector_pct:
        logger.debug(
            "Skipping %s: sector at cap (%.1f%% >= %.1f%%)",
            ticker,
            sector_allocation_pct,
            max_sector_pct,
        )
        return 0.0

    # Equal-weight target, capped by max_position_pct
    equal_weight_pct = 100.0 / max(num_target_positions, 1)
    target_pct = min(max_position_pct, equal_weight_pct)

    # How much more room do we have?
    gap_pct = target_pct - current_allocation_pct
    if gap_pct <= 0:
        return 0.0

    # Dollar amount needed to fill the gap, limited by available cash
    suggested = round(min(gap_pct / 100.0 * total_value, available_cash), 2)

    if suggested < MIN_TRADE_SIZE:
        return 0.0

    return suggested


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
        return (
            f"RSI at {value} — oversold territory."
            " The stock may be undervalued, creating a potential buying opportunity."
        )
    elif label == "OVERBOUGHT":
        return (
            f"RSI at {value} — overbought territory."
            " The stock may be overvalued and due for a pullback."
        )
    else:
        return f"RSI at {value} — neutral range. No strong momentum signal."


def _macd_interpretation(histogram: float | None, label: str | None) -> str:
    """Generate a human-readable interpretation of the MACD."""
    if label == "BULLISH":
        return (
            f"MACD histogram at {histogram:.4f} — positive momentum."
            " Short-term trend is above long-term trend."
        )
    else:
        return (
            f"MACD histogram at {histogram:.4f} — negative momentum."
            " Short-term trend is below long-term trend."
        )


def _sma_interpretation(label: str | None) -> str:
    """Generate a human-readable interpretation of the SMA crossover."""
    interpretations = {
        "GOLDEN_CROSS": (
            "Golden Cross detected — the 50-day SMA just crossed above"
            " the 200-day SMA, a strong bullish signal."
        ),
        "DEATH_CROSS": (
            "Death Cross detected — the 50-day SMA just crossed below"
            " the 200-day SMA, a strong bearish signal."
        ),
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


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers — extracted from routers/stocks.py inline queries
# ─────────────────────────────────────────────────────────────────────────────


async def get_recommendations(
    user_id: str,
    db: AsyncSession,
    action: str | None = None,
    confidence: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[RecommendationSnapshot], int]:
    """Query the user's recommendations with optional filters and pagination.

    Returns recommendations from the last 24 hours, ordered by composite
    score descending. Older recommendations are excluded because they are
    based on stale signals.

    Args:
        user_id: UUID of the user to fetch recommendations for.
        db: Async database session.
        action: Optional filter — BUY, WATCH, AVOID, HOLD, or SELL.
        confidence: Optional filter — HIGH, MEDIUM, or LOW.
        limit: Page size (default 50).
        offset: Pagination offset (default 0).

    Returns:
        A tuple of (list of RecommendationSnapshot rows, total count).
    """
    query = select(RecommendationSnapshot).where(RecommendationSnapshot.user_id == user_id)

    if action is not None:
        query = query.where(RecommendationSnapshot.action == action.upper())

    if confidence is not None:
        query = query.where(RecommendationSnapshot.confidence == confidence.upper())

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    query = query.where(RecommendationSnapshot.generated_at >= cutoff)

    # Count total before pagination
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    query = query.order_by(RecommendationSnapshot.composite_score.desc())
    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    recs = list(result.scalars().all())

    return recs, total
