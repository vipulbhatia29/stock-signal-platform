"""EDGAR 8-K provider — SEC filings with item number pre-classification."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

import httpx

from backend.config import settings
from backend.services.http_client import get_http_client
from backend.services.news.base import NewsProvider, RawArticle

logger = logging.getLogger(__name__)

# SEC EDGAR rate limit: 10 requests/sec
EDGAR_RATE_LIMIT_DELAY = 0.15

# Map 8-K item numbers to event types
ITEM_EVENT_MAP: dict[str, str] = {
    "1.01": "m_and_a",  # Entry into material agreement
    "1.02": "m_and_a",  # Termination of material agreement
    "2.01": "m_and_a",  # Completion of acquisition
    "2.02": "earnings",  # Results of operations
    "2.05": "restructuring",  # Costs of exit/disposal
    "2.06": "impairment",  # Material impairments
    "3.01": "regulatory",  # Delisting notice
    "4.01": "regulatory",  # Auditor changes
    "5.02": "management",  # Departure/appointment of officers
    "5.07": "governance",  # Shareholder vote results
    "7.01": "guidance",  # Regulation FD disclosure
    "8.01": "other",  # Other events
    "9.01": "other",  # Financial exhibits
}


class EdgarProvider(NewsProvider):
    """Fetches 8-K filings from SEC EDGAR full-text search API."""

    def __init__(self, user_agent: str | None = None) -> None:
        self._user_agent = user_agent or settings.EDGAR_USER_AGENT

    @property
    def source_name(self) -> str:
        return "edgar"

    async def fetch_stock_news(self, ticker: str, since: date) -> list[RawArticle]:
        """Fetch recent 8-K filings for a ticker from EDGAR EFTS."""
        url = "https://efts.sec.gov/LATEST/search-index"
        params = {
            "q": f'"{ticker.upper()}"',
            "dateRange": "custom",
            "startdt": since.isoformat(),
            "enddt": datetime.now(timezone.utc).date().isoformat(),
            "forms": "8-K",
        }
        headers = {"User-Agent": self._user_agent}

        try:
            client = get_http_client()
            resp = await client.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError:
            logger.error("EDGAR API error for %s", ticker, exc_info=True)
            return []

        articles: list[RawArticle] = []
        for hit in data.get("hits", {}).get("hits", []):
            try:
                source = hit.get("_source", {})
                filed_str = source.get("file_date", "")
                filed_dt = datetime.strptime(filed_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                # Extract item numbers for event classification
                items = source.get("items", "")
                event_type = _classify_8k_items(items)
                entity_id = source.get("entity_id", "")
                file_num = source.get("file_num", "")
                accession_no_dashes = file_num.replace("-", "")
                filing_url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{entity_id}/{accession_no_dashes}/{file_num}-index.htm"
                )
                display_name = source.get("display_names", [ticker])[0]
                articles.append(
                    RawArticle(
                        headline=f"8-K: {display_name} — {items or 'Other'}",
                        summary=source.get("display_names", [None])[0],
                        source=self.source_name,
                        source_url=filing_url,
                        ticker=ticker.upper(),
                        published_at=filed_dt,
                        event_type=event_type,
                    )
                )
            except (KeyError, ValueError, TypeError, IndexError):
                logger.warning("Skipping malformed EDGAR filing", exc_info=True)

        await asyncio.sleep(EDGAR_RATE_LIMIT_DELAY)
        return articles

    async def fetch_macro_news(self, since: date) -> list[RawArticle]:
        """EDGAR does not provide macro news — returns empty."""
        return []


def _classify_8k_items(items_str: str) -> str:
    """Map 8-K item numbers to event types. Returns highest-significance match."""
    if not items_str:
        return "other"
    # Priority order: earnings > m_and_a > management > rest
    priority = ["earnings", "m_and_a", "management", "guidance", "regulatory"]
    found_types: set[str] = set()
    for item_num in items_str.split(","):
        item_num = item_num.strip()
        event = ITEM_EVENT_MAP.get(item_num, "other")
        found_types.add(event)
    for p in priority:
        if p in found_types:
            return p
    return next(iter(found_types), "other")
