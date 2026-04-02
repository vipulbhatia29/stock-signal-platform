"""Unit tests for NewsArticle and NewsSentimentDaily model instantiation."""

import uuid
from datetime import date, datetime, timezone

from backend.models.news_sentiment import NewsArticle, NewsSentimentDaily


def test_news_article_instantiation():
    article = NewsArticle(
        id=uuid.uuid4(),
        published_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        ticker="AAPL",
        headline="Apple beats Q2 earnings estimates",
        summary="Revenue up 12% YoY...",
        source="finnhub",
        source_url="https://example.com/article",
        event_type="earnings",
        dedupe_hash="abc123def456",
    )
    assert article.source == "finnhub"
    assert article.scored_at is None


def test_news_article_repr():
    article = NewsArticle(
        source="finnhub",
        ticker="AAPL",
        published_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert "finnhub" in repr(article)


def test_sentiment_daily_instantiation():
    sentiment = NewsSentimentDaily(
        date=date(2026, 4, 1),
        ticker="AAPL",
        stock_sentiment=0.7,
        sector_sentiment=0.3,
        macro_sentiment=-0.2,
        article_count=5,
        confidence=0.85,
        dominant_event_type="earnings",
        quality_flag="ok",
    )
    assert sentiment.stock_sentiment == 0.7
    assert sentiment.quality_flag == "ok"


def test_sentiment_macro_ticker():
    """Macro sentiment uses special ticker '__MACRO__'."""
    macro = NewsSentimentDaily(
        date=date(2026, 4, 1),
        ticker="__MACRO__",
        stock_sentiment=0.0,
        sector_sentiment=0.0,
        macro_sentiment=-0.5,
        article_count=3,
        confidence=0.9,
    )
    assert macro.ticker == "__MACRO__"
