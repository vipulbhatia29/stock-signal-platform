"""NewsProvider ABC and RawArticle dataclass."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class RawArticle:
    """Normalized article from any news source.

    Attributes:
        headline: Article title (max 500 chars for LLM prompt safety).
        summary: Optional article summary/snippet.
        source: Provider name (e.g. "finnhub", "edgar", "fed_rss").
        source_url: Original article URL.
        ticker: Associated ticker symbol (None for macro news).
        published_at: Publication datetime (UTC).
        event_type: Optional pre-classification (e.g. "earnings", "fda").
        dedupe_hash: SHA256 of headline+source+date for deduplication.
    """

    headline: str
    summary: str | None
    source: str
    source_url: str | None
    ticker: str | None
    published_at: datetime
    event_type: str | None = None
    dedupe_hash: str = ""

    def __post_init__(self) -> None:
        """Compute dedupe_hash if not provided, and truncate headline."""
        # Truncate headline for LLM prompt injection mitigation
        if len(self.headline) > 500:
            self.headline = self.headline[:500]
        # Compute dedupe hash
        if not self.dedupe_hash:
            raw = f"{self.headline}|{self.source}|{self.published_at.date().isoformat()}"
            self.dedupe_hash = hashlib.sha256(raw.encode()).hexdigest()


class NewsProvider(ABC):
    """Abstract base class for news data providers."""

    @abstractmethod
    async def fetch_stock_news(self, ticker: str, since: date) -> list[RawArticle]:
        """Fetch stock-specific news articles.

        Args:
            ticker: Stock ticker symbol.
            since: Fetch articles published on or after this date.

        Returns:
            List of RawArticle objects.
        """

    @abstractmethod
    async def fetch_macro_news(self, since: date) -> list[RawArticle]:
        """Fetch macro/market-wide news articles.

        Args:
            since: Fetch articles published on or after this date.

        Returns:
            List of RawArticle objects.
        """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the provider's source identifier (e.g. 'finnhub')."""
