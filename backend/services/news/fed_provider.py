"""Fed RSS + FRED provider — macro-level news and economic indicators."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

import httpx
from defusedxml.ElementTree import fromstring as safe_fromstring

from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.news.base import NewsProvider, RawArticle

logger = logging.getLogger(__name__)

FED_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
FRED_BASE_URL = "https://api.stlouisfed.org/fred"


class FedRssProvider(NewsProvider):
    """Fetches Federal Reserve press releases and FRED economic data releases."""

    def __init__(self, fred_api_key: str | None = None) -> None:
        self._fred_api_key = fred_api_key or settings.FRED_API_KEY

    @property
    def source_name(self) -> str:
        return "fed_rss"

    async def fetch_stock_news(self, ticker: str, since: date) -> list[RawArticle]:
        """Fed RSS does not provide stock-specific news."""
        return []

    async def fetch_macro_news(self, since: date) -> list[RawArticle]:
        """Fetch Fed press releases from RSS feed + FRED releases."""
        articles: list[RawArticle] = []

        # 1. Fed RSS
        rss_articles = await self._fetch_fed_rss(since)
        articles.extend(rss_articles)

        # 2. FRED recent releases
        if self._fred_api_key:
            fred_articles = await self._fetch_fred_releases(since)
            articles.extend(fred_articles)

        return articles

    async def _fetch_fed_rss(self, since: date) -> list[RawArticle]:
        """Parse Federal Reserve RSS feed."""
        try:
            client = get_http_client()
            resp = await client.get(FED_RSS_URL, timeout=30)
            resp.raise_for_status()
            xml_text = resp.text
        except httpx.HTTPError:
            logger.error("Fed RSS fetch failed", exc_info=True)
            return []

        return _parse_fed_rss_xml(xml_text, since, self.source_name)

    async def _fetch_fred_releases(self, since: date) -> list[RawArticle]:
        """Fetch recent FRED data releases."""
        url = f"{FRED_BASE_URL}/releases"
        params = {
            "api_key": self._fred_api_key,
            "file_type": "json",
            "realtime_start": since.isoformat(),
            "realtime_end": datetime.now(timezone.utc).date().isoformat(),
        }

        try:
            client = get_http_client()
            resp = await client.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            logger.error("FRED API error", exc_info=True)
            return []

        articles: list[RawArticle] = []
        for release in data.get("releases", []):
            try:
                release_date = release.get("realtime_start", "")
                dt = datetime.strptime(release_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                event_type = _classify_fred_release(release.get("name", ""))
                articles.append(
                    RawArticle(
                        headline=release.get("name", "FRED Release"),
                        summary=release.get("notes"),
                        source="fred",
                        source_url=release.get("link"),
                        ticker=None,
                        published_at=dt,
                        event_type=event_type,
                    )
                )
            except (KeyError, ValueError, TypeError):
                logger.warning("Skipping malformed FRED release", exc_info=True)

        return articles


def _parse_fed_rss_xml(xml_text: str, since: date, source_name: str) -> list[RawArticle]:
    """Parse Fed RSS XML into RawArticle list.

    Args:
        xml_text: Raw XML string from Fed RSS.
        since: Only include articles on or after this date.
        source_name: Source identifier for the articles.

    Returns:
        List of RawArticle objects.
    """
    articles: list[RawArticle] = []
    try:
        root = safe_fromstring(xml_text)
    except ET.ParseError:
        logger.error("Failed to parse Fed RSS XML", exc_info=True)
        return []

    for item in root.iter("item"):
        try:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date_str = item.findtext("pubDate", "")
            description = item.findtext("description")

            # Parse RSS date (RFC 822): "Mon, 01 Jan 2026 12:00:00 EST"
            # Simplified: strip timezone name and parse
            if not pub_date_str:
                continue
            dt = _parse_rss_date(pub_date_str)
            if dt.date() < since:
                continue

            event_type = _classify_fed_press(title)
            articles.append(
                RawArticle(
                    headline=title,
                    summary=description,
                    source=source_name,
                    source_url=link,
                    ticker=None,
                    published_at=dt,
                    event_type=event_type,
                )
            )
        except (ValueError, TypeError):
            logger.warning("Skipping malformed Fed RSS item", exc_info=True)

    return articles


def _parse_rss_date(date_str: str) -> datetime:
    """Parse RFC 822 date from RSS feed."""
    from email.utils import parsedate_to_datetime

    return parsedate_to_datetime(date_str).astimezone(timezone.utc)


def _classify_fed_press(title: str) -> str:
    """Classify Fed press release by title keywords."""
    title_lower = title.lower()
    if "rate" in title_lower or "fomc" in title_lower or "funds rate" in title_lower:
        return "fed_rate"
    if "employment" in title_lower or "labor" in title_lower:
        return "employment"
    if "inflation" in title_lower or "cpi" in title_lower or "pce" in title_lower:
        return "cpi"
    return "macro"


def _classify_fred_release(name: str) -> str:
    """Classify FRED release by name keywords."""
    name_lower = name.lower()
    if "employment" in name_lower or "payroll" in name_lower:
        return "employment"
    if "consumer price" in name_lower or "cpi" in name_lower:
        return "cpi"
    if "gdp" in name_lower:
        return "macro"
    if "interest rate" in name_lower or "funds rate" in name_lower:
        return "fed_rate"
    return "macro"
