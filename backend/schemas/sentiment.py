"""Pydantic v2 schemas for sentiment API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class DailySentimentResponse(BaseModel):
    """Daily sentiment for a single ticker."""

    date: date
    ticker: str
    stock_sentiment: float
    sector_sentiment: float
    macro_sentiment: float
    article_count: int
    confidence: float
    dominant_event_type: str | None
    rationale_summary: str | None
    quality_flag: str


class SentimentTimeseriesResponse(BaseModel):
    """Sentiment timeseries for a ticker."""

    ticker: str
    data: list[DailySentimentResponse]


class BulkSentimentResponse(BaseModel):
    """Latest sentiment for multiple tickers."""

    tickers: list[DailySentimentResponse]


class MacroSentimentResponse(BaseModel):
    """Macro-level sentiment timeseries."""

    data: list[DailySentimentResponse]


class ArticleSummaryResponse(BaseModel):
    """Article metadata (no full text)."""

    headline: str
    source: str
    source_url: str | None
    ticker: str | None
    published_at: str
    event_type: str | None
    scored_at: str | None


class ArticleListResponse(BaseModel):
    """Paginated list of articles for a ticker."""

    ticker: str
    articles: list[ArticleSummaryResponse]
    total: int
    limit: int
    offset: int
