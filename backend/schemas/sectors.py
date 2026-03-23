"""Pydantic v2 response schemas for the sectors endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SectorSummary(BaseModel):
    """Summary stats for a single sector."""

    sector: str
    stock_count: int
    avg_composite_score: float | None = None
    avg_return_pct: float | None = None
    your_stock_count: int = 0
    allocation_pct: float | None = None


class SectorSummaryResponse(BaseModel):
    """List of sector summaries."""

    sectors: list[SectorSummary]


class SectorStock(BaseModel):
    """A stock within a sector drill-down."""

    ticker: str
    name: str
    composite_score: float | None = None
    current_price: float | None = None
    return_pct: float | None = None
    is_held: bool = False
    is_watched: bool = False


class SectorStocksResponse(BaseModel):
    """Stocks belonging to a specific sector."""

    sector: str
    stocks: list[SectorStock]


class ExcludedTicker(BaseModel):
    """A ticker excluded from correlation computation."""

    ticker: str
    reason: str


class CorrelationResponse(BaseModel):
    """Price correlation matrix for tickers within a sector."""

    sector: str
    tickers: list[str]
    matrix: list[list[float]]
    period_days: int = Field(ge=1)
    excluded_tickers: list[ExcludedTicker] = []
