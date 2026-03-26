"""Response schemas for stock recommendation tool."""

from __future__ import annotations

from pydantic import BaseModel


class StockCandidate(BaseModel):
    """A single recommended stock candidate."""

    ticker: str
    name: str
    sector: str | None = None
    recommendation_score: float  # 0-10
    sources: list[str]  # which scoring dimensions contributed
    rationale: list[str]
    signal_score: float | None = None
    forward_pe: float | None = None
    dividend_yield: float | None = None


class RecommendationResult(BaseModel):
    """Complete recommendation response."""

    candidates: list[StockCandidate]
    portfolio_context: dict  # underweight sectors, current allocation, etc.
