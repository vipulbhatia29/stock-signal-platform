"""News fetch functions — yfinance + Google News RSS.

All functions are either synchronous (for yfinance, run in thread pool)
or async (for Google News RSS). Caller is responsible for caching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import yfinance as yf

from backend.services.http_client import get_http_client

logger = logging.getLogger(__name__)


def fetch_yfinance_news(ticker: str) -> list[dict]:
    """Fetch recent news from yfinance (synchronous).

    Args:
        ticker: Stock symbol.

    Returns:
        List of article dicts with title, link, publisher, published, source.
    """
    try:
        t = yf.Ticker(ticker.upper())
        raw = t.news or []
    except Exception:
        logger.warning("yfinance news fetch failed for %s", ticker)
        return []

    articles = []
    for item in raw[:10]:
        published = None
        ts = item.get("providerPublishTime")
        if ts:
            try:
                published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OSError):
                pass

        articles.append(
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "publisher": item.get("publisher", ""),
                "published": published,
                "source": "yfinance",
            }
        )
    return articles


async def fetch_google_news_rss(ticker: str) -> list[dict]:
    """Fetch financial news from Google News RSS (async, free, no API key).

    Args:
        ticker: Stock symbol to search for.

    Returns:
        List of article dicts with title, link, publisher, published, source.
    """
    import defusedxml.ElementTree as ET

    url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
    try:
        client = get_http_client()
        resp = await client.get(url, timeout=5.0)
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.text)
        articles = []
        for item in root.findall(".//item")[:10]:
            articles.append(
                {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "publisher": item.findtext("source", "Google News"),
                    "published": item.findtext("pubDate"),
                    "source": "google_news",
                }
            )
        return articles
    except Exception:
        logger.warning("Google News RSS fetch failed for %s", ticker)
        return []


def merge_and_deduplicate(articles: list[dict], max_results: int = 15) -> list[dict]:
    """Merge articles from multiple sources, deduplicate by URL.

    Args:
        articles: Combined list from all sources.
        max_results: Maximum articles to return.

    Returns:
        Deduplicated, sorted list (newest first).
    """
    seen_urls: set[str] = set()
    unique: list[dict] = []
    for a in articles:
        link = a.get("link", "")
        if link and link not in seen_urls:
            seen_urls.add(link)
            unique.append(a)
    unique.sort(key=lambda x: x.get("published") or "", reverse=True)
    return unique[:max_results]
