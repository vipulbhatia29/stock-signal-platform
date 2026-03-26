"""Response schemas for market briefing endpoint and tool."""

from __future__ import annotations

from pydantic import BaseModel


class IndexPerformance(BaseModel):
    """Market index daily performance."""

    name: str
    ticker: str
    price: float
    change_pct: float


class SectorPerformance(BaseModel):
    """Sector ETF daily performance."""

    sector: str
    etf: str
    change_pct: float


class MarketBriefingResult(BaseModel):
    """Complete market briefing response."""

    indexes: list[IndexPerformance]
    sector_performance: list[SectorPerformance]
    portfolio_news: list[dict]
    upcoming_earnings: list[dict]
    top_movers: dict  # {gainers: [...], losers: [...]}
    briefing_date: str
