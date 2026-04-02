"""News articles and sentiment aggregation models."""

from __future__ import annotations

import uuid as _uuid
from datetime import date, datetime

from sqlalchemy import Date, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, TimestampMixin


class NewsArticle(TimestampMixin, Base):
    """Ingested news article metadata. No full article text stored."""

    __tablename__ = "news_articles"

    published_at: Mapped[datetime] = mapped_column(
        primary_key=True
    )  # hypertable time column — composite PK with id
    id: Mapped[_uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    ticker: Mapped[str | None] = mapped_column(String(10), nullable=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    dedupe_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scored_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Composite PK: (published_at, id) — required for TimescaleDB hypertable.
    # Dedupe uniqueness enforced via unique index (dedupe_hash, published_at).
    __table_args__ = (Index("ix_news_articles_ticker_published", "ticker", "published_at"),)

    def __repr__(self) -> str:
        return f"<NewsArticle {self.source} {self.ticker} {self.published_at:%Y-%m-%d}>"


class NewsSentimentDaily(TimestampMixin, Base):
    """Aggregated daily sentiment per ticker. '__MACRO__' for macro-level."""

    __tablename__ = "news_sentiment_daily"

    date: Mapped[date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(10), primary_key=True)
    stock_sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sector_sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    macro_sentiment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    article_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dominant_event_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rationale_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_flag: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ok"
    )  # 'ok', 'suspect', 'invalidated'

    def __repr__(self) -> str:
        return f"<NewsSentimentDaily {self.ticker} {self.date} s={self.stock_sentiment:.2f}>"
