"""Response schemas for stock news and intelligence endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class NewsItem(BaseModel):
    """A single news article."""

    title: str
    link: str
    publisher: str | None = None
    published: str | None = None
    source: str  # "yfinance" or "google_news"


class StockNewsResponse(BaseModel):
    """Response for GET /stocks/{ticker}/news."""

    ticker: str
    articles: list[NewsItem]
    fetched_at: str


class UpgradeDowngrade(BaseModel):
    """A single analyst rating change."""

    firm: str
    to_grade: str
    from_grade: str | None = None
    action: str
    date: str


class InsiderTransaction(BaseModel):
    """A single insider transaction."""

    insider_name: str
    relation: str | None = None
    transaction_type: str
    shares: int
    value: float | None = None
    date: str


class StockIntelligenceResponse(BaseModel):
    """Response for GET /stocks/{ticker}/intelligence."""

    ticker: str
    upgrades_downgrades: list[UpgradeDowngrade]
    insider_transactions: list[InsiderTransaction]
    next_earnings_date: str | None = None
    eps_revisions: dict | None = None
    fetched_at: str
