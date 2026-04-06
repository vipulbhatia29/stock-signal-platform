"""Finnhub news provider — primary source for stock-specific news."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

import httpx

from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.news.base import NewsProvider, RawArticle

logger = logging.getLogger(__name__)

# Finnhub free tier: 60 calls/min, use 55 to be safe
RATE_LIMIT_DELAY = 1.1  # seconds between calls


class FinnhubProvider(NewsProvider):
    """Fetches company news from Finnhub REST API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.FINNHUB_API_KEY
        self._base_url = "https://finnhub.io/api/v1"

    @property
    def source_name(self) -> str:
        return "finnhub"

    async def fetch_stock_news(self, ticker: str, since: date) -> list[RawArticle]:
        """Fetch company news from Finnhub."""
        if not self._api_key:
            logger.warning("FINNHUB_API_KEY not set — skipping Finnhub fetch")
            return []

        today = datetime.now(timezone.utc).date()
        url = f"{self._base_url}/company-news"
        params = {
            "symbol": ticker.upper(),
            "from": since.isoformat(),
            "to": today.isoformat(),
            "token": self._api_key,
        }

        try:
            client = get_http_client()
            resp = await client.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            logger.error("Finnhub API error for %s", ticker, exc_info=True)
            return []

        articles: list[RawArticle] = []
        for item in data:
            try:
                published = datetime.fromtimestamp(item["datetime"], tz=timezone.utc)
                articles.append(
                    RawArticle(
                        headline=item.get("headline", ""),
                        summary=item.get("summary"),
                        source=self.source_name,
                        source_url=item.get("url"),
                        ticker=ticker.upper(),
                        published_at=published,
                        event_type=_classify_finnhub_category(item.get("category", "")),
                    )
                )
            except (KeyError, ValueError, TypeError):
                logger.warning("Skipping malformed Finnhub article", exc_info=True)

        await asyncio.sleep(RATE_LIMIT_DELAY)
        return articles

    async def fetch_macro_news(self, since: date) -> list[RawArticle]:
        """Finnhub general news (market-wide)."""
        if not self._api_key:
            return []

        url = f"{self._base_url}/news"
        params = {"category": "general", "token": self._api_key}

        try:
            client = get_http_client()
            resp = await client.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            logger.error("Finnhub general news API error", exc_info=True)
            return []

        articles: list[RawArticle] = []
        for item in data:
            try:
                published = datetime.fromtimestamp(item["datetime"], tz=timezone.utc)
                if published.date() < since:
                    continue
                articles.append(
                    RawArticle(
                        headline=item.get("headline", ""),
                        summary=item.get("summary"),
                        source=self.source_name,
                        source_url=item.get("url"),
                        ticker=None,
                        published_at=published,
                    )
                )
            except (KeyError, ValueError, TypeError):
                logger.warning("Skipping malformed Finnhub article", exc_info=True)

        await asyncio.sleep(RATE_LIMIT_DELAY)
        return articles


def _classify_finnhub_category(category: str) -> str | None:
    """Map Finnhub category to our event_type taxonomy."""
    mapping = {
        "company news": "general",
        "forex": "macro",
        "crypto": None,
        "merger": "m_and_a",
    }
    return mapping.get(category.lower(), "general")
