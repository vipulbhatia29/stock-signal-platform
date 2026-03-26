"""Multi-signal stock recommendation engine and agent tool.

Ranks stocks by weighted consensus across signals, fundamentals,
momentum, and portfolio fit. Pure scoring functions are testable without DB.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from backend.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# ── Recommendation weights ───────────────────────────────────────────────────

RECOMMENDATION_WEIGHTS = {
    "signal_score": 0.35,
    "fundamental_score": 0.25,
    "momentum_score": 0.20,
    "portfolio_fit_score": 0.20,
}


def _compute_recommendation_score(
    signal_score: float = 0.0,
    fundamental_score: float = 0.0,
    momentum_score: float = 0.0,
    portfolio_fit_score: float = 0.0,
) -> float:
    """Compute weighted recommendation score from multiple dimensions.

    Args:
        signal_score: Technical signal composite (0-10).
        fundamental_score: Fundamental quality score (0-10).
        momentum_score: Recent price momentum score (0-10).
        portfolio_fit_score: How well it fits the portfolio (0-10).

    Returns:
        Weighted score 0-10.
    """
    scores = {
        "signal_score": signal_score,
        "fundamental_score": fundamental_score,
        "momentum_score": momentum_score,
        "portfolio_fit_score": portfolio_fit_score,
    }
    total = sum(scores[dim] * RECOMMENDATION_WEIGHTS[dim] for dim in RECOMMENDATION_WEIGHTS)
    return round(total, 1)


def _score_fundamentals(
    forward_pe: float | None,
    return_on_equity: float | None,
    piotroski: int | None,
) -> float:
    """Score a stock's fundamentals on a 0-10 scale.

    Args:
        forward_pe: Forward P/E ratio (lower = better, up to a point).
        return_on_equity: Return on equity decimal (higher = better).
        piotroski: Piotroski F-Score (0-9, higher = better).

    Returns:
        Fundamental quality score 0-10.
    """
    pe_score = 5.0
    if forward_pe is not None:
        if forward_pe <= 0:
            pe_score = 2.0
        elif forward_pe <= 15:
            pe_score = 9.0
        elif forward_pe <= 25:
            pe_score = 7.0
        elif forward_pe <= 40:
            pe_score = 4.0
        else:
            pe_score = 2.0

    roe_score = 5.0
    if return_on_equity is not None:
        if return_on_equity >= 0.20:
            roe_score = 9.0
        elif return_on_equity >= 0.10:
            roe_score = 7.0
        elif return_on_equity >= 0.05:
            roe_score = 5.0
        else:
            roe_score = 3.0

    pio_score = 5.0
    if piotroski is not None:
        pio_score = min(10.0, piotroski * 10 / 9)

    return round((pe_score * 0.4 + roe_score * 0.3 + pio_score * 0.3), 1)


# ── Agent tool ───────────────────────────────────────────────────────────────


class RecommendStocksInput(BaseModel):
    """Input schema for recommend stocks tool."""

    pass  # Uses portfolio context automatically


class RecommendStocksTool(BaseTool):
    """Recommend stocks based on multi-signal consensus and portfolio fit.

    Ranks BUY-rated stocks by signal quality, fundamentals, momentum,
    and portfolio fit. Returns top candidates with per-source rationale.
    """

    name = "recommend_stocks"
    description = (
        "Get stock recommendations based on multi-signal analysis. "
        "Considers technical signals, fundamentals (P/E, ROE, Piotroski), "
        "momentum, and portfolio fit (underweight sectors). "
        "Use when the user asks for buy recommendations or what to invest in."
    )
    category = "portfolio"
    parameters = {"type": "object", "properties": {}, "required": []}
    args_schema = RecommendStocksInput
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute recommendation engine."""
        try:
            from collections import defaultdict

            from sqlalchemy import select

            from backend.database import async_session_factory
            from backend.models.portfolio import Portfolio, Position
            from backend.models.signal import SignalSnapshot
            from backend.models.stock import Stock
            from backend.request_context import current_user_id
            from backend.schemas.recommend import RecommendationResult, StockCandidate

            user_id = current_user_id.get()

            async with async_session_factory() as db:
                # Get BUY-rated stocks (composite_score >= 8)
                from sqlalchemy import func

                latest_signals_subq = (
                    select(
                        SignalSnapshot.ticker,
                        func.max(SignalSnapshot.snapshot_date).label("max_date"),
                    )
                    .group_by(SignalSnapshot.ticker)
                    .subquery()
                )
                buy_stmt = (
                    select(SignalSnapshot, Stock)
                    .join(
                        latest_signals_subq,
                        (SignalSnapshot.ticker == latest_signals_subq.c.ticker)
                        & (SignalSnapshot.snapshot_date == latest_signals_subq.c.max_date),
                    )
                    .join(Stock, SignalSnapshot.ticker == Stock.ticker)
                    .where(SignalSnapshot.composite_score >= 8.0)
                    .order_by(SignalSnapshot.composite_score.desc())
                    .limit(20)
                )
                rows = (await db.execute(buy_stmt)).all()

                # Get portfolio context if available
                portfolio_tickers: set[str] = set()
                sector_allocs: dict[str, float] = defaultdict(float)
                if user_id:
                    portfolio = (
                        await db.execute(select(Portfolio).where(Portfolio.user_id == user_id))
                    ).scalar_one_or_none()
                    if portfolio:
                        positions = (
                            await db.execute(
                                select(Position, Stock)
                                .join(Stock, Position.ticker == Stock.ticker)
                                .where(Position.portfolio_id == portfolio.id)
                                .where(Position.shares > 0)
                            )
                        ).all()
                        total_val = sum(
                            float(p.shares) * float(p.avg_cost_basis) for p, _ in positions
                        )
                        for pos, stock in positions:
                            portfolio_tickers.add(pos.ticker)
                            if total_val > 0:
                                w = float(pos.shares) * float(pos.avg_cost_basis) / total_val * 100
                                sector_allocs[stock.sector or "Unknown"] += w

                # Score and rank candidates
                candidates = []
                for signal, stock in rows:
                    if stock.ticker in portfolio_tickers:
                        continue  # Skip stocks already in portfolio

                    signal_score = float(signal.composite_score or 0)
                    fundamental = _score_fundamentals(
                        stock.forward_pe, stock.return_on_equity, None
                    )

                    # Portfolio fit: bonus for underweight sectors
                    stock_sector = stock.sector or "Unknown"
                    current_alloc = sector_allocs.get(stock_sector, 0.0)
                    fit_score = 8.0 if current_alloc < 15 else 5.0 if current_alloc < 30 else 3.0

                    rec_score = _compute_recommendation_score(
                        signal_score=signal_score,
                        fundamental_score=fundamental,
                        momentum_score=signal_score * 0.8,  # proxy from signal
                        portfolio_fit_score=fit_score,
                    )

                    # Build rationale
                    rationale = []
                    sources = []
                    if signal_score >= 8.0:
                        rationale.append(f"Strong technical signals ({signal_score:.1f}/10)")
                        sources.append("signals")
                    if fundamental >= 7.0:
                        rationale.append(f"Solid fundamentals (score {fundamental:.1f})")
                        sources.append("fundamentals")
                    if fit_score >= 7.0:
                        rationale.append(f"Good portfolio fit — {stock_sector} underweight")
                        sources.append("portfolio_fit")

                    candidates.append(
                        StockCandidate(
                            ticker=stock.ticker,
                            name=stock.name or stock.ticker,
                            sector=stock_sector,
                            recommendation_score=rec_score,
                            sources=sources,
                            rationale=rationale,
                            signal_score=signal_score,
                            forward_pe=stock.forward_pe,
                            dividend_yield=stock.dividend_yield,
                        )
                    )

                # Sort by recommendation score and take top 10
                candidates.sort(key=lambda c: c.recommendation_score, reverse=True)
                candidates = candidates[:10]

                result = RecommendationResult(
                    candidates=candidates,
                    portfolio_context={
                        "portfolio_tickers": list(portfolio_tickers),
                        "sector_allocation": dict(sector_allocs),
                    },
                )

                return ToolResult(status="ok", data=result.model_dump())

        except Exception as e:
            logger.error("recommend_stocks_failed", extra={"error": str(e)})
            return ToolResult(status="error", error="Failed to generate recommendations")
