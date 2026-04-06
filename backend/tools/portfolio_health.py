"""Portfolio health score computation and agent tool.

Computes a 0-10 health score from 5 weighted components:
diversification (HHI), signal quality, risk (Sharpe), income (yield),
and sector balance. All scoring functions are pure (testable without DB).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# ── Component weights ────────────────────────────────────────────────────────

COMPONENT_WEIGHTS = {
    "diversification": 0.25,
    "signal_quality": 0.25,
    "risk": 0.20,
    "income": 0.10,
    "sector_balance": 0.20,
}


# ── Scoring functions (pure, no DB) ─────────────────────────────────────────


def _score_diversification(hhi: float) -> float:
    """Score diversification from HHI (Herfindahl-Hirschman Index).

    HHI < 500 = well diversified (10), HHI > 2500 = concentrated (0).
    """
    if hhi <= 500:
        return 10.0
    if hhi >= 2500:
        return 0.0
    return round(10.0 * (2500 - hhi) / 2000, 1)


def _score_signal_quality(weighted_composite: float) -> float:
    """Score signal quality from portfolio-weighted composite score (0-10 pass-through)."""
    return round(max(0.0, min(10.0, weighted_composite)), 1)


def _score_risk(
    weighted_sharpe: float,
    weighted_sortino: float | None = None,
    weighted_drawdown: float | None = None,
) -> float:
    """Score risk from portfolio-weighted Sharpe, Sortino, and max drawdown.

    Combines three inputs (equal weight when all available):
    - Sharpe: > 1.5 = excellent (10), < 0 = poor (0)
    - Sortino: > 2.0 = excellent (10), < 0 = poor (0)
    - Max drawdown: < 5% = excellent (10), > 30% = poor (0)

    Falls back to Sharpe-only when Sortino/drawdown are None (no QuantStats data).
    """
    sharpe_score = max(0.0, min(10.0, 10.0 * weighted_sharpe / 1.5))

    # If no QuantStats data, fall back to Sharpe-only
    if weighted_sortino is None and weighted_drawdown is None:
        return round(sharpe_score, 1)

    sortino_score = max(0.0, min(10.0, 10.0 * (weighted_sortino or 0.0) / 2.0))
    dd_val = weighted_drawdown or 0.0
    dd_score = max(0.0, min(10.0, 10.0 * (1.0 - dd_val / 0.30)))

    combined = (sharpe_score + sortino_score + dd_score) / 3.0
    return round(combined, 1)


def _score_income(weighted_yield: float) -> float:
    """Score income from portfolio-weighted dividend yield.

    Yield 2-4% = optimal (10), 0% = minimal income (3), >8% = suspicious (5).
    """
    if weighted_yield <= 0:
        return 3.0
    if 0.02 <= weighted_yield <= 0.04:
        return 10.0
    if weighted_yield < 0.02:
        return round(3.0 + 7.0 * (weighted_yield / 0.02), 1)
    if weighted_yield <= 0.08:
        return round(10.0 - 5.0 * ((weighted_yield - 0.04) / 0.04), 1)
    return 5.0


def _score_sector_balance(max_sector_pct: float) -> float:
    """Score sector balance from max single-sector allocation %.

    Max < 25% = balanced (10), Max > 50% = concentrated (0).
    """
    if max_sector_pct <= 25.0:
        return 10.0
    if max_sector_pct >= 50.0:
        return 0.0
    return round(10.0 * (50.0 - max_sector_pct) / 25.0, 1)


def _score_to_grade(score: float) -> str:
    """Convert 0-10 score to letter grade."""
    if score >= 9.5:
        return "A+"
    if score >= 9.0:
        return "A"
    if score >= 8.5:
        return "A-"
    if score >= 8.0:
        return "B+"
    if score >= 7.5:
        return "B"
    if score >= 7.0:
        return "B"
    if score >= 6.5:
        return "B-"
    if score >= 6.0:
        return "C+"
    if score >= 5.0:
        return "C"
    if score >= 4.0:
        return "C-"
    if score >= 3.0:
        return "D"
    return "F"


def _compute_composite(component_scores: dict[str, float]) -> float:
    """Compute weighted composite health score from components."""
    total = 0.0
    for name, score in component_scores.items():
        weight = COMPONENT_WEIGHTS.get(name, 0.0)
        total += score * weight
    return round(total, 1)


# ── Agent tool ───────────────────────────────────────────────────────────────


async def compute_portfolio_health(
    portfolio_id: Any,
    db: Any,
) -> Any:
    """Compute portfolio health for a given portfolio ID using provided DB session.

    This is the standalone computation function used by both the agent tool
    and the Celery snapshot task. Returns None if portfolio has no positions.

    Args:
        portfolio_id: UUID of the portfolio.
        db: Async SQLAlchemy session.

    Returns:
        PortfolioHealthResult or None if no active positions.
    """
    from collections import defaultdict

    from sqlalchemy import func, select

    from backend.models.portfolio import Position
    from backend.models.signal import SignalSnapshot
    from backend.models.stock import Stock
    from backend.schemas.portfolio_health import (
        HealthComponent,
        PortfolioHealthResult,
        PositionHealth,
    )

    stmt = (
        select(Position, Stock)
        .join(Stock, Position.ticker == Stock.ticker)
        .where(Position.portfolio_id == portfolio_id)
        .where(Position.shares > 0)
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        return None

    total_value = sum(float(pos.shares) * float(pos.avg_cost_basis) for pos, _ in rows)
    if total_value <= 0:
        return None

    tickers = [pos.ticker for pos, _ in rows]
    latest_signals_subq = (
        select(
            SignalSnapshot.ticker,
            func.max(SignalSnapshot.computed_at).label("max_date"),
        )
        .where(SignalSnapshot.ticker.in_(tickers))
        .group_by(SignalSnapshot.ticker)
        .subquery()
    )
    signals_stmt = select(SignalSnapshot).join(
        latest_signals_subq,
        (SignalSnapshot.ticker == latest_signals_subq.c.ticker)
        & (SignalSnapshot.computed_at == latest_signals_subq.c.max_date),
    )
    signal_rows = (await db.execute(signals_stmt)).scalars().all()
    signal_map = {s.ticker: s for s in signal_rows}

    position_details = []
    weights = []
    sector_allocs: dict[str, float] = defaultdict(float)
    weighted_composite = 0.0
    weighted_sharpe = 0.0
    weighted_sortino: float | None = None
    weighted_drawdown: float | None = None
    weighted_yield = 0.0
    weighted_beta = 0.0

    for pos, stock in rows:
        value = float(pos.shares) * float(pos.avg_cost_basis)
        weight_pct = (value / total_value) * 100
        weights.append(weight_pct)

        sector = stock.sector or "Unknown"
        sector_allocs[sector] += weight_pct

        signal = signal_map.get(pos.ticker)
        signal_score = float(signal.composite_score) if signal and signal.composite_score else None
        sharpe = float(signal.sharpe_ratio) if signal and signal.sharpe_ratio else 0.0

        w = weight_pct / 100
        if signal_score is not None:
            weighted_composite += signal_score * w
        weighted_sharpe += sharpe * w

        # Accumulate QuantStats metrics (None until at least one stock has data)
        if signal and signal.sortino is not None:
            if weighted_sortino is None:
                weighted_sortino = 0.0
            if weighted_drawdown is None:
                weighted_drawdown = 0.0
            weighted_sortino += float(signal.sortino) * w
            weighted_drawdown += float(signal.max_drawdown or 0) * w

        weighted_yield += (stock.dividend_yield or 0.0) * w
        weighted_beta += (stock.beta or 1.0) * w

        contribution = "strength" if (signal_score or 0) >= 7.0 else "drag"
        position_details.append(
            PositionHealth(
                ticker=pos.ticker,
                weight_pct=round(weight_pct, 1),
                signal_score=round(signal_score, 1) if signal_score else None,
                sector=sector,
                contribution=contribution,
            )
        )

    hhi = sum(w**2 for w in weights)
    max_sector_pct = max(sector_allocs.values()) if sector_allocs else 0.0
    component_scores = {
        "diversification": _score_diversification(hhi),
        "signal_quality": _score_signal_quality(weighted_composite),
        "risk": _score_risk(weighted_sharpe, weighted_sortino, weighted_drawdown),
        "income": _score_income(weighted_yield),
        "sector_balance": _score_sector_balance(max_sector_pct),
    }

    health_score = _compute_composite(component_scores)
    grade = _score_to_grade(health_score)

    components = [
        HealthComponent(
            name=name,
            score=score,
            weight=COMPONENT_WEIGHTS[name],
            detail=f"{name}: {score}/10",
        )
        for name, score in component_scores.items()
    ]

    concerns = []
    strengths = []
    if hhi > 1500:
        concerns.append(f"Portfolio is concentrated (HHI={hhi:.0f})")
    if max_sector_pct > 35:
        top_sector = max(sector_allocs, key=sector_allocs.get)  # type: ignore[arg-type]
        concerns.append(f"{top_sector} sector overweight at {max_sector_pct:.0f}%")
    for pd_item in position_details:
        if pd_item.signal_score is not None and pd_item.signal_score < 5.0:
            concerns.append(f"{pd_item.ticker} has weak signals ({pd_item.signal_score})")
        if pd_item.weight_pct > 25:
            concerns.append(f"{pd_item.ticker} overweight at {pd_item.weight_pct:.0f}%")
        if pd_item.signal_score is not None and pd_item.signal_score >= 8.0:
            strengths.append(f"{pd_item.ticker} has strong signals ({pd_item.signal_score})")
    if hhi < 1000:
        strengths.append("Well diversified portfolio")

    return PortfolioHealthResult(
        health_score=health_score,
        grade=grade,
        components=components,
        metrics={
            "hhi": round(hhi, 0),
            "effective_stocks": len(rows),
            "weighted_beta": round(weighted_beta, 2),
            "weighted_sharpe": round(weighted_sharpe, 2),
            "weighted_yield": round(weighted_yield, 4),
            "max_sector_pct": round(max_sector_pct, 1),
            "total_value": round(total_value, 2),
        },
        top_concerns=concerns[:5],
        top_strengths=strengths[:5],
        position_details=position_details,
    )


class PortfolioHealthInput(BaseModel):
    """Input schema for portfolio health tool."""

    pass  # Uses current user's portfolio automatically


class PortfolioHealthTool(BaseTool):
    """Compute portfolio health score with component breakdown.

    Analyzes diversification, signal quality, risk, income, and sector balance
    across the user's portfolio positions.
    """

    name = "portfolio_health"
    description = (
        "Compute a 0-10 health score for the user's portfolio. "
        "Analyzes diversification (HHI), signal quality, risk (Sharpe), "
        "income (dividend yield), and sector balance. Returns grade, "
        "component breakdown, concerns, and strengths."
    )
    category = "portfolio"
    parameters = {"type": "object", "properties": {}, "required": []}
    args_schema = PortfolioHealthInput
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute portfolio health computation."""
        try:
            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.portfolio import Portfolio
            from backend.request_context import current_user_id

            user_id = current_user_id.get()
            if not user_id:
                return ToolResult(status="error", error="No user context")

            async with async_session_factory() as db:
                portfolio = (
                    await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
                ).scalar_one_or_none()
                if not portfolio:
                    return ToolResult(
                        status="ok",
                        data={"message": "No portfolio found. Add positions first."},
                    )

                result = await compute_portfolio_health(portfolio.id, db)
                if result is None:
                    return ToolResult(
                        status="ok",
                        data={"message": "Portfolio has no active positions."},
                    )

                return ToolResult(status="ok", data=result.model_dump())

        except Exception:
            logger.exception("Failed to compute portfolio health")
            return ToolResult(status="error", error="Failed to compute portfolio health")
