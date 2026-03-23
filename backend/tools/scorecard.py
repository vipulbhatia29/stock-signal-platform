"""Scorecard computation — aggregates recommendation outcomes into hit rates and alpha."""

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.forecast import RecommendationOutcome

logger = logging.getLogger(__name__)


@dataclass
class HorizonBreakdown:
    """Hit rate and alpha for a specific horizon."""

    horizon_days: int
    total: int = 0
    correct: int = 0
    hit_rate: float = 0.0
    avg_alpha: float = 0.0


@dataclass
class ScorecardData:
    """Aggregated recommendation performance data."""

    total_outcomes: int = 0
    overall_hit_rate: float = 0.0
    avg_alpha: float = 0.0
    buy_hit_rate: float = 0.0
    sell_hit_rate: float = 0.0
    worst_miss_pct: float = 0.0
    worst_miss_ticker: str = ""
    horizons: list[HorizonBreakdown] = field(default_factory=list)


async def compute_scorecard(user_id: uuid.UUID, db: AsyncSession) -> ScorecardData:
    """Compute recommendation scorecard for a user.

    Args:
        user_id: UUID of the user.
        db: Async database session.

    Returns:
        ScorecardData with hit rates, alpha, and breakdowns.
    """
    result = await db.execute(
        select(RecommendationOutcome).where(RecommendationOutcome.user_id == user_id)
    )
    outcomes = result.scalars().all()

    if not outcomes:
        return ScorecardData()

    # Overall metrics
    total = len(outcomes)
    correct = sum(1 for o in outcomes if o.action_was_correct)
    alphas = [o.alpha_pct for o in outcomes]

    # Per-action hit rates
    buys = [o for o in outcomes if o.action == "BUY"]
    sells = [o for o in outcomes if o.action == "SELL"]
    buy_correct = sum(1 for o in buys if o.action_was_correct)
    sell_correct = sum(1 for o in sells if o.action_was_correct)

    # Worst miss: largest negative return on a BUY recommendation
    worst_miss_pct = 0.0
    worst_miss_ticker = ""
    for o in buys:
        if o.return_pct < worst_miss_pct:
            worst_miss_pct = o.return_pct
            worst_miss_ticker = o.rec_ticker

    # Per-horizon breakdown
    horizon_map: dict[int, list[RecommendationOutcome]] = {}
    for o in outcomes:
        horizon_map.setdefault(o.horizon_days, []).append(o)

    horizons: list[HorizonBreakdown] = []
    for h in sorted(horizon_map.keys()):
        h_outcomes = horizon_map[h]
        h_correct = sum(1 for o in h_outcomes if o.action_was_correct)
        h_alphas = [o.alpha_pct for o in h_outcomes]
        horizons.append(
            HorizonBreakdown(
                horizon_days=h,
                total=len(h_outcomes),
                correct=h_correct,
                hit_rate=h_correct / len(h_outcomes) if h_outcomes else 0.0,
                avg_alpha=sum(h_alphas) / len(h_alphas) if h_alphas else 0.0,
            )
        )

    return ScorecardData(
        total_outcomes=total,
        overall_hit_rate=correct / total if total else 0.0,
        avg_alpha=sum(alphas) / len(alphas) if alphas else 0.0,
        buy_hit_rate=buy_correct / len(buys) if buys else 0.0,
        sell_hit_rate=sell_correct / len(sells) if sells else 0.0,
        worst_miss_pct=round(worst_miss_pct, 4),
        worst_miss_ticker=worst_miss_ticker,
        horizons=horizons,
    )
