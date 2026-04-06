"""Google News RSS provider — fallback source when primary providers are unavailable."""

from __future__ import annotations

import logging
from datetime import date, timezone

import httpx
from defusedxml.ElementTree import fromstring as safe_fromstring

from backend.services.http_client import get_http_client
from backend.services.news.base import NewsProvider, RawArticle

logger = logging.getLogger(__name__)

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


class GoogleNewsProvider(NewsProvider):
    """Fetches news from Google News RSS feed. Used as fallback."""

    @property
    def source_name(self) -> str:
        return "google_news"

    async def fetch_stock_news(self, ticker: str, since: date) -> list[RawArticle]:
        """Fetch stock news from Google News RSS."""
        query = f"{ticker} stock"
        return await self._fetch_rss(query, ticker=ticker.upper(), since=since)

    async def fetch_macro_news(self, since: date) -> list[RawArticle]:
        """Fetch macro news from Google News RSS."""
        query = "stock market economy"
        return await self._fetch_rss(query, ticker=None, since=since)

    async def _fetch_rss(self, query: str, ticker: str | None, since: date) -> list[RawArticle]:
        """Fetch and parse Google News RSS feed."""
        params = {"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"}

        try:
            client = get_http_client()
            resp = await client.get(GOOGLE_NEWS_RSS, params=params, timeout=30)
            resp.raise_for_status()
            xml_text = resp.text
        except httpx.HTTPError:
            logger.error("Google News RSS error for query '%s'", query, exc_info=True)
            return []

        return _parse_google_rss(xml_text, ticker, since, self.source_name)


def _parse_google_rss(
    xml_text: str, ticker: str | None, since: date, source_name: str
) -> list[RawArticle]:
    """Parse Google News RSS XML into RawArticle list."""
    articles: list[RawArticle] = []
    try:
        root = safe_fromstring(xml_text)
    except Exception:
        logger.error("Failed to parse Google News RSS XML", exc_info=True)
        return []

    for item in root.iter("item"):
        try:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date_str = item.findtext("pubDate", "")

            if not pub_date_str:
                continue

            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(pub_date_str).astimezone(timezone.utc)
            if dt.date() < since:
                continue

            articles.append(
                RawArticle(
                    headline=title,
                    summary=None,
                    source=source_name,
                    source_url=link,
                    ticker=ticker,
                    published_at=dt,
                )
            )
        except (ValueError, TypeError):
            logger.warning("Skipping malformed Google News item", exc_info=True)

    return articles
