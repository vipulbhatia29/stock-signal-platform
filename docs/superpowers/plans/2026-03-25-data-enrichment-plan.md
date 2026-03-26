# Spec C: Data Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the Stock model with beta/yield/PE, add news + intelligence API endpoints, sync dividends during ingest, and refresh enriched fields in nightly pipeline.

**Architecture:** 3 new columns on Stock model extracted from yfinance `.info` during ingest. 2 new on-demand API endpoints (`/news`, `/intelligence`) backed by yfinance + Google News RSS with volatile Redis cache. Dividend sync added to ingest tool and nightly pipeline.

**Tech Stack:** yfinance, defusedxml (for Google News RSS XXE protection), FastAPI, redis cache (CacheService from KAN-148)

**Spec:** `docs/superpowers/specs/2026-03-25-data-enrichment-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/models/stock.py` | Add `beta`, `dividend_yield`, `forward_pe` columns |
| Modify | `backend/tools/fundamentals.py` | Extract 3 new fields in `fetch_analyst_data()` |
| Modify | `backend/tools/ingest_stock_tool.py` | Add dividend sync step during ingest |
| Create | `backend/tools/news.py` | yfinance news + Google News RSS fetch functions |
| Create | `backend/tools/intelligence.py` | yfinance upgrades/insider/calendar/EPS fetch functions |
| Create | `backend/schemas/intelligence.py` | News + intelligence response schemas |
| Modify | `backend/routers/stocks.py` | Add `GET /{ticker}/news` and `GET /{ticker}/intelligence` |
| Modify | `backend/tasks/market_data.py` | Refresh beta/yield/PE + sync dividends in nightly pipeline |
| Create | `backend/migrations/versions/XXX_013_enrichment.py` | Add 3 columns to stocks table |
| Create | `tests/unit/tools/test_news.py` | News fetch function tests |
| Create | `tests/unit/tools/test_intelligence.py` | Intelligence fetch function tests |
| Create | `tests/api/test_stock_news.py` | API endpoint tests |

**Note:** Migration 013 may be shared with Spec A (if both add columns). If executing in parallel, whichever runs first creates 013, the other becomes 013b or adjusts. Safest: run Spec A migration first (just `decline_count`), then Spec C adds a separate migration for the 3 stock columns.

---

### Task 1: Stock Model + Migration

**Files:**
- Modify: `backend/models/stock.py`
- Create: migration file

- [ ] **Step 1: Add 3 columns to Stock model**

In `backend/models/stock.py`, after `return_on_equity` (line ~52), add:

```python
    # Market risk & income (populated during ingestion from yfinance)
    beta: Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 2: Generate migration**

```bash
uv run alembic revision --autogenerate -m "add_beta_dividend_yield_forward_pe_to_stocks"
```

Review the generated migration — keep ONLY the 3 `add_column` statements. Alembic autogenerate may detect other changes — remove them.

- [ ] **Step 3: Apply migration**

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/models/stock.py backend/migrations/versions/*beta*
git commit -m "feat(enrichment): add beta, dividend_yield, forward_pe to Stock model"
```

---

### Task 2: Extract New Fields in Ingest

**Files:**
- Modify: `backend/tools/fundamentals.py`
- Modify: `backend/tools/ingest_stock_tool.py`

- [ ] **Step 1: Add field extraction to fetch_analyst_data**

In `backend/tools/fundamentals.py`, in `fetch_analyst_data()`, after the profile data extraction (around line 366), add:

```python
    # Market risk & income (for portfolio health computation)
    for yf_key, field_name in [
        ("beta", "beta"),
        ("dividendYield", "dividend_yield"),
        ("forwardPE", "forward_pe"),
    ]:
        val = _get_float(yf_key)
        if val is not None:
            result[field_name] = val
```

No change needed in `persist_enriched_fundamentals()` — it already iterates all keys in the dict.

- [ ] **Step 2: Add dividend sync to ingest tool**

In `backend/tools/ingest_stock_tool.py`, after `persist_earnings_snapshots` (line ~106), add:

```python
                # 4d. Sync dividend history
                from backend.tools.dividends import fetch_dividends, store_dividends

                dividends = await loop.run_in_executor(None, fetch_dividends, ticker)
                if dividends:
                    await store_dividends(ticker, dividends, session)
```

- [ ] **Step 3: Run existing tests**

```bash
uv run pytest tests/unit/ -q --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add backend/tools/fundamentals.py backend/tools/ingest_stock_tool.py
git commit -m "feat(enrichment): extract beta/yield/PE during ingest + sync dividends"
```

---

### Task 3: News Fetch Functions

**Files:**
- Create: `backend/tools/news.py`
- Create: `tests/unit/tools/test_news.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/tools/test_news.py
"""Tests for news fetch functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestFetchYfinanceNews:
    """Tests for yfinance news fetching."""

    def test_returns_list_of_articles(self) -> None:
        """Should return a list of news article dicts."""
        from backend.tools.news import fetch_yfinance_news

        mock_ticker = MagicMock()
        mock_ticker.news = [
            {"title": "AAPL Earnings Beat", "link": "https://example.com/1", "publisher": "Reuters", "providerPublishTime": 1711900000},
            {"title": "Apple Event", "link": "https://example.com/2", "publisher": "CNBC", "providerPublishTime": 1711800000},
        ]
        with patch("backend.tools.news.yf.Ticker", return_value=mock_ticker):
            articles = fetch_yfinance_news("AAPL")
        assert len(articles) == 2
        assert articles[0]["title"] == "AAPL Earnings Beat"
        assert articles[0]["source"] == "yfinance"

    def test_empty_news_returns_empty_list(self) -> None:
        """No news should return empty list."""
        from backend.tools.news import fetch_yfinance_news

        mock_ticker = MagicMock()
        mock_ticker.news = []
        with patch("backend.tools.news.yf.Ticker", return_value=mock_ticker):
            articles = fetch_yfinance_news("AAPL")
        assert articles == []

    def test_yfinance_error_returns_empty(self) -> None:
        """yfinance error should return empty list, not raise."""
        from backend.tools.news import fetch_yfinance_news

        with patch("backend.tools.news.yf.Ticker", side_effect=Exception("API down")):
            articles = fetch_yfinance_news("AAPL")
        assert articles == []


class TestFetchGoogleNewsRss:
    """Tests for Google News RSS fetching."""

    @pytest.mark.asyncio
    async def test_parses_rss_xml(self) -> None:
        """Should parse RSS XML into article dicts."""
        from backend.tools.news import fetch_google_news_rss

        mock_xml = """<?xml version="1.0"?>
        <rss><channel>
            <item>
                <title>AAPL surges</title>
                <link>https://news.google.com/1</link>
                <source>Bloomberg</source>
                <pubDate>Mon, 25 Mar 2026 10:00:00 GMT</pubDate>
            </item>
        </channel></rss>"""

        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_xml

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tools.news.httpx.AsyncClient", return_value=mock_client):
            articles = await fetch_google_news_rss("AAPL")
        assert len(articles) == 1
        assert articles[0]["title"] == "AAPL surges"
        assert articles[0]["source"] == "google_news"

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self) -> None:
        """HTTP error should return empty list."""
        from backend.tools.news import fetch_google_news_rss

        mock_resp = AsyncMock()
        mock_resp.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tools.news.httpx.AsyncClient", return_value=mock_client):
            articles = await fetch_google_news_rss("AAPL")
        assert articles == []


class TestMergeAndDeduplicate:
    """Tests for article merge/dedup."""

    def test_deduplicates_by_url(self) -> None:
        """Duplicate URLs should be removed."""
        from backend.tools.news import merge_and_deduplicate

        articles = [
            {"title": "A", "link": "https://example.com/1", "source": "yfinance"},
            {"title": "B", "link": "https://example.com/1", "source": "google_news"},
            {"title": "C", "link": "https://example.com/2", "source": "google_news"},
        ]
        result = merge_and_deduplicate(articles)
        assert len(result) == 2

    def test_caps_at_max(self) -> None:
        """Should return at most max_results articles."""
        from backend.tools.news import merge_and_deduplicate

        articles = [{"title": f"A{i}", "link": f"https://example.com/{i}", "source": "yf"} for i in range(30)]
        result = merge_and_deduplicate(articles, max_results=10)
        assert len(result) == 10
```

- [ ] **Step 2: Implement news.py**

```python
# backend/tools/news.py
"""News fetch functions — yfinance + Google News RSS.

All functions are either synchronous (for yfinance, run in thread pool)
or async (for Google News RSS). Caller is responsible for caching.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import yfinance as yf

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

        articles.append({
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "publisher": item.get("publisher", ""),
            "published": published,
            "source": "yfinance",
        })
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
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []

        root = ET.fromstring(resp.text)
        articles = []
        for item in root.findall(".//item")[:10]:
            articles.append({
                "title": item.findtext("title", ""),
                "link": item.findtext("link", ""),
                "publisher": item.findtext("source", "Google News"),
                "published": item.findtext("pubDate"),
                "source": "google_news",
            })
        return articles
    except Exception:
        logger.warning("Google News RSS fetch failed for %s", ticker)
        return []


def merge_and_deduplicate(
    articles: list[dict], max_results: int = 15
) -> list[dict]:
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
```

- [ ] **Step 3: Install defusedxml**

```bash
uv add defusedxml
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/tools/test_news.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/tools/news.py tests/unit/tools/test_news.py pyproject.toml uv.lock
git commit -m "feat(enrichment): news fetch — yfinance + Google News RSS with defusedxml"
```

---

### Task 4: Intelligence Fetch Functions

**Files:**
- Create: `backend/tools/intelligence.py`
- Create: `tests/unit/tools/test_intelligence.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/tools/test_intelligence.py
"""Tests for stock intelligence fetch functions."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestFetchUpgradesDowngrades:
    """Tests for analyst rating changes."""

    def test_returns_recent_grades(self) -> None:
        """Should return recent upgrade/downgrade entries."""
        from backend.tools.intelligence import fetch_upgrades_downgrades

        mock_ticker = MagicMock()
        mock_ticker.upgrades_downgrades = pd.DataFrame({
            "Firm": ["UBS", "Goldman"],
            "ToGrade": ["Buy", "Neutral"],
            "FromGrade": ["Neutral", "Buy"],
            "Action": ["up", "down"],
        }, index=pd.to_datetime(["2026-03-20", "2026-03-15"]))

        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_upgrades_downgrades("AAPL")
        assert len(result) == 2
        assert result[0]["firm"] == "UBS"
        assert result[0]["action"] == "up"

    def test_no_data_returns_empty(self) -> None:
        """No upgrades data should return empty list."""
        from backend.tools.intelligence import fetch_upgrades_downgrades

        mock_ticker = MagicMock()
        mock_ticker.upgrades_downgrades = None
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_upgrades_downgrades("AAPL")
        assert result == []


class TestFetchInsiderTransactions:
    """Tests for insider transaction data."""

    def test_returns_transactions(self) -> None:
        """Should return formatted insider transactions."""
        from backend.tools.intelligence import fetch_insider_transactions

        mock_ticker = MagicMock()
        mock_ticker.insider_transactions = pd.DataFrame({
            "Insider Trading": ["Tim Cook", "Jeff Williams"],
            "Relationship": ["CEO", "COO"],
            "Transaction": ["Sale", "Purchase"],
            "Shares": [50000, 10000],
            "Value": [8500000, 1700000],
            "Start Date": ["2026-03-01", "2026-02-15"],
        })
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_insider_transactions("AAPL")
        assert len(result) == 2
        assert result[0]["insider_name"] == "Tim Cook"


class TestFetchNextEarningsDate:
    """Tests for earnings calendar."""

    def test_returns_date_string(self) -> None:
        """Should return ISO date string for next earnings."""
        from backend.tools.intelligence import fetch_next_earnings_date

        mock_ticker = MagicMock()
        mock_ticker.calendar = {"Earnings Date": [pd.Timestamp("2026-04-28")]}
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_next_earnings_date("AAPL")
        assert result is not None
        assert "2026-04-28" in result

    def test_no_calendar_returns_none(self) -> None:
        """No calendar data should return None."""
        from backend.tools.intelligence import fetch_next_earnings_date

        mock_ticker = MagicMock()
        mock_ticker.calendar = None
        with patch("backend.tools.intelligence.yf.Ticker", return_value=mock_ticker):
            result = fetch_next_earnings_date("AAPL")
        assert result is None
```

- [ ] **Step 2: Implement intelligence.py**

```python
# backend/tools/intelligence.py
"""Stock intelligence fetch functions — upgrades, insider, earnings, EPS revisions.

All functions are synchronous (yfinance). Run in thread pool via asyncio.to_thread().
Caller is responsible for caching.
"""

from __future__ import annotations

import logging

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_upgrades_downgrades(ticker: str, max_results: int = 20) -> list[dict]:
    """Fetch recent analyst rating changes from yfinance.

    Returns:
        List of dicts with firm, to_grade, from_grade, action, date.
    """
    try:
        t = yf.Ticker(ticker.upper())
        df = t.upgrades_downgrades
        if df is None or df.empty:
            return []
        results = []
        for date, row in df.head(max_results).iterrows():
            results.append({
                "firm": row.get("Firm", ""),
                "to_grade": row.get("ToGrade", ""),
                "from_grade": row.get("FromGrade", ""),
                "action": row.get("Action", ""),
                "date": str(date.date()) if hasattr(date, "date") else str(date),
            })
        return results
    except Exception:
        logger.warning("Failed to fetch upgrades for %s", ticker)
        return []


def fetch_insider_transactions(ticker: str, max_results: int = 10) -> list[dict]:
    """Fetch recent insider transactions from yfinance.

    Returns:
        List of dicts with insider_name, relation, transaction_type, shares, value, date.
    """
    try:
        t = yf.Ticker(ticker.upper())
        df = t.insider_transactions
        if df is None or df.empty:
            return []
        results = []
        for _, row in df.head(max_results).iterrows():
            results.append({
                "insider_name": row.get("Insider Trading", row.get("Name", "")),
                "relation": row.get("Relationship", row.get("Relation", "")),
                "transaction_type": row.get("Transaction", ""),
                "shares": int(row.get("Shares", 0)),
                "value": float(row.get("Value", 0)) if row.get("Value") else None,
                "date": str(row.get("Start Date", row.get("Date", ""))),
            })
        return results
    except Exception:
        logger.warning("Failed to fetch insider transactions for %s", ticker)
        return []


def fetch_next_earnings_date(ticker: str) -> str | None:
    """Fetch next earnings date from yfinance calendar.

    Returns:
        ISO date string or None.
    """
    try:
        t = yf.Ticker(ticker.upper())
        cal = t.calendar
        if cal is None:
            return None
        # calendar can be a dict or DataFrame
        if isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if dates:
                return str(dates[0].date()) if hasattr(dates[0], "date") else str(dates[0])
        return None
    except Exception:
        logger.warning("Failed to fetch calendar for %s", ticker)
        return None


def fetch_eps_revisions(ticker: str) -> dict | None:
    """Fetch EPS revision data from yfinance.

    Returns:
        Dict with revision data or None.
    """
    try:
        t = yf.Ticker(ticker.upper())
        rev = t.eps_revisions
        if rev is None or (hasattr(rev, "empty") and rev.empty):
            return None
        if hasattr(rev, "to_dict"):
            return rev.to_dict()
        return None
    except Exception:
        logger.warning("Failed to fetch EPS revisions for %s", ticker)
        return None
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/tools/test_intelligence.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/tools/intelligence.py tests/unit/tools/test_intelligence.py
git commit -m "feat(enrichment): intelligence fetch — upgrades, insider, earnings, EPS revisions"
```

---

### Task 5: Schemas + API Endpoints

**Files:**
- Create: `backend/schemas/intelligence.py`
- Modify: `backend/routers/stocks.py`
- Create: `tests/api/test_stock_news.py`

- [ ] **Step 1: Create schemas**

```python
# backend/schemas/intelligence.py
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
```

- [ ] **Step 2: Add endpoints to stocks router**

In `backend/routers/stocks.py`, add two new endpoints:

```python
@router.get("/{ticker}/news", response_model=StockNewsResponse)
async def get_stock_news(
    ticker: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> StockNewsResponse:
    """Get recent news articles for a stock from multiple sources."""
    import asyncio
    from datetime import datetime, timezone

    from backend.schemas.intelligence import StockNewsResponse
    from backend.services.cache import CacheTier
    from backend.tools.news import fetch_google_news_rss, fetch_yfinance_news, merge_and_deduplicate

    await _require_stock(ticker, db)
    t = ticker.upper()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:news:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockNewsResponse.model_validate_json(cached)

    yf_articles = await asyncio.to_thread(fetch_yfinance_news, t)
    google_articles = await fetch_google_news_rss(t)
    merged = merge_and_deduplicate(yf_articles + google_articles)

    response = StockNewsResponse(
        ticker=t,
        articles=merged,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response


@router.get("/{ticker}/intelligence", response_model=StockIntelligenceResponse)
async def get_stock_intelligence(
    ticker: str,
    request: Request,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> StockIntelligenceResponse:
    """Get analyst upgrades, insider transactions, earnings calendar, EPS revisions."""
    import asyncio
    from datetime import datetime, timezone

    from backend.schemas.intelligence import StockIntelligenceResponse
    from backend.services.cache import CacheTier
    from backend.tools.intelligence import (
        fetch_eps_revisions,
        fetch_insider_transactions,
        fetch_next_earnings_date,
        fetch_upgrades_downgrades,
    )

    await _require_stock(ticker, db)
    t = ticker.upper()

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:intelligence:{t}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockIntelligenceResponse.model_validate_json(cached)

    upgrades, insider, earnings, eps = await asyncio.gather(
        asyncio.to_thread(fetch_upgrades_downgrades, t),
        asyncio.to_thread(fetch_insider_transactions, t),
        asyncio.to_thread(fetch_next_earnings_date, t),
        asyncio.to_thread(fetch_eps_revisions, t),
    )

    response = StockIntelligenceResponse(
        ticker=t,
        upgrades_downgrades=upgrades,
        insider_transactions=insider,
        next_earnings_date=earnings,
        eps_revisions=eps,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response
```

- [ ] **Step 3: Write API tests**

```python
# tests/api/test_stock_news.py
"""API tests for stock news and intelligence endpoints."""

import pytest
from httpx import AsyncClient


class TestStockNews:
    """Tests for GET /api/v1/stocks/{ticker}/news."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/stocks/AAPL/news")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_ticker_returns_404(self, authenticated_client: AsyncClient) -> None:
        """Unknown ticker should return 404."""
        response = await authenticated_client.get("/api/v1/stocks/ZZZZZ/news")
        assert response.status_code == 404


class TestStockIntelligence:
    """Tests for GET /api/v1/stocks/{ticker}/intelligence."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/stocks/AAPL/intelligence")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_ticker_returns_404(self, authenticated_client: AsyncClient) -> None:
        """Unknown ticker should return 404."""
        response = await authenticated_client.get("/api/v1/stocks/ZZZZZ/intelligence")
        assert response.status_code == 404
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/api/test_stock_news.py tests/unit/tools/test_news.py tests/unit/tools/test_intelligence.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/intelligence.py backend/routers/stocks.py tests/api/test_stock_news.py
git commit -m "feat(enrichment): news + intelligence API endpoints with volatile cache"
```

---

### Task 6: Nightly Pipeline Enhancement

**Files:**
- Modify: `backend/tasks/market_data.py`

- [ ] **Step 1: Add beta/yield refresh + dividend sync to nightly**

In `backend/tasks/market_data.py`, in `_refresh_ticker_async()`, after signal computation and before `await db.commit()`, add:

```python
        # Refresh beta/yield/forward_pe from yfinance info
        try:
            info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info or {})
            stock_result = await db.execute(
                select(Stock).where(Stock.ticker == ticker)
            )
            stock_obj = stock_result.scalar_one_or_none()
            if stock_obj and info:
                for yf_key, field in [("beta", "beta"), ("dividendYield", "dividend_yield"), ("forwardPE", "forward_pe")]:
                    val = info.get(yf_key)
                    if val is not None:
                        try:
                            setattr(stock_obj, field, float(val))
                        except (TypeError, ValueError):
                            pass
                db.add(stock_obj)
        except Exception:
            logger.warning("Failed to refresh beta/yield for %s", ticker, exc_info=True)

        # Sync dividends
        try:
            from backend.tools.dividends import fetch_dividends, store_dividends
            divs = await asyncio.to_thread(fetch_dividends, ticker)
            if divs:
                await store_dividends(ticker, divs, db)
        except Exception:
            logger.warning("Failed to sync dividends for %s", ticker, exc_info=True)
```

Add imports at the top:
```python
from backend.models.stock import Stock
```

And `select` import if not already present.

- [ ] **Step 2: Run pipeline tests**

```bash
uv run pytest tests/unit/pipeline/ -v --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/market_data.py
git commit -m "feat(enrichment): nightly pipeline refreshes beta/yield/PE + syncs dividends"
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest tests/unit/ -q --tb=short
uv run ruff check backend/ tests/
```

- [ ] **Step 2: Commit any remaining fixes**

---

## Execution Summary

| Task | Description | New Tests | Files |
|------|-------------|-----------|-------|
| 1 | Stock model + migration | 0 | 2 |
| 2 | Extract new fields + dividend sync in ingest | 0 | 2 |
| 3 | News fetch functions | 7 | 2 |
| 4 | Intelligence fetch functions | 5 | 2 |
| 5 | Schemas + API endpoints + tests | 4 | 3 |
| 6 | Nightly pipeline enhancement | 0 | 1 |
| 7 | Final verification | 0 | 0 |
| **Total** | | **~16** | **12** |
