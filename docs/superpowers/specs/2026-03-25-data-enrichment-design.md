# Spec C: Data Enrichment — Design Spec

**Date**: 2026-03-25
**Phase**: 7 (KAN-147)
**Status**: Draft
**Depends on**: None (can parallel with Spec A)
**Blocks**: Spec B (Agent Intelligence — tools need this data)

---

## 1. Problem Statement

yfinance provides 30+ data points per ticker that we're not using. The `fetch_analyst_data()` function already calls `yf.Ticker(ticker).info` but only extracts profile + analyst targets. Key fields like `beta`, `dividendYield`, `forwardPE` are available but never stored.

Additionally, yfinance provides rich per-ticker data via `.news`, `.upgrades_downgrades`, `.insider_transactions`, `.calendar`, `.eps_revisions` — all free, all untapped. These are needed by the new `get_stock_intelligence` and `get_market_briefing` tools (Spec B).

---

## 2. Stock Model Enrichment

### 2.1 New Columns on `stocks` Table

Add 3 columns to `backend/models/stock.py`:

```python
# Market risk
beta: Mapped[float | None] = mapped_column(Float, nullable=True)

# Income
dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)

# Valuation
forward_pe: Mapped[float | None] = mapped_column(Float, nullable=True)
```

These change slowly (updated on each ingest) and are needed by portfolio health computation.

### 2.2 Extract During Ingest

In `backend/tools/fundamentals.py` → `fetch_analyst_data()`, the `info` dict is already fetched. Add extraction:

```python
# After existing analyst target extraction (line ~336):

# Market risk & income (needed for portfolio health)
for yf_key, field_name in [
    ("beta", "beta"),
    ("dividendYield", "dividend_yield"),
    ("forwardPE", "forward_pe"),
]:
    val = _get_float(yf_key)
    if val is not None:
        result[field_name] = val
```

No change needed in `persist_enriched_fundamentals()` — it already iterates over all keys in `analyst_data` dict and calls `setattr(stock, field_name, val)`.

### 2.3 Migration 013

```sql
ALTER TABLE stocks ADD COLUMN beta FLOAT;
ALTER TABLE stocks ADD COLUMN dividend_yield FLOAT;
ALTER TABLE stocks ADD COLUMN forward_pe FLOAT;
```

---

## 3. Dividend Sync in Ingest + Nightly Pipeline

### 3.1 Problem

`fetch_dividends()` + `store_dividends()` exist in `backend/tools/dividends.py` but are only called via the `GET /portfolio/dividends/{ticker}` endpoint. They are NOT called during:
- `POST /stocks/{ticker}/ingest` (ingest_stock_tool.py)
- Nightly price refresh pipeline

This means dividend data is only as fresh as the user's last visit to the dividend page.

### 3.2 Add to Ingest Pipeline

In `backend/tools/ingest_stock_tool.py`, after `persist_earnings_snapshots` (line 106), add:

```python
# 4d. Sync dividend history
from backend.tools.dividends import fetch_dividends, store_dividends

dividends = await loop.run_in_executor(None, fetch_dividends, ticker)
if dividends:
    await store_dividends(ticker, dividends, session)
```

### 3.3 Add to Nightly Pipeline

In `backend/tasks/market_data.py`, the `_refresh_ticker_async()` function currently only fetches prices + computes signals. It should also sync dividends:

```python
async def _refresh_ticker_async(ticker: str) -> dict:
    async with async_session_factory() as db:
        await fetch_prices_delta(ticker, db)
        full_df = await load_prices_df(ticker, db)
        # ... existing signal computation ...

        # Sync dividends (new)
        from backend.tools.dividends import fetch_dividends, store_dividends
        divs = await asyncio.to_thread(fetch_dividends, ticker)
        if divs:
            await store_dividends(ticker, divs, db)

        await db.commit()
```

---

## 4. New API Endpoints

### 4.1 Stock News Endpoint

`GET /api/v1/stocks/{ticker}/news`

Returns recent news from yfinance `ticker.news` + Google News RSS. Cached with volatile TTL (5 min via CacheService).

**Response schema:**

```python
class NewsItem(BaseModel):
    title: str
    link: str
    publisher: str | None = None
    published: str | None = None  # ISO datetime string
    source: str  # "yfinance" or "google_news"

class StockNewsResponse(BaseModel):
    ticker: str
    articles: list[NewsItem]
    fetched_at: str  # ISO datetime
```

**Implementation pattern (on-demand, NOT materialized):**

```python
@router.get("/{ticker}/news", response_model=StockNewsResponse)
async def get_stock_news(ticker: str, request: Request, ...):
    cache = getattr(request.app.state, "cache", None)
    cache_key = f"app:news:{ticker.upper()}"
    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return StockNewsResponse.model_validate_json(cached)

    # Fetch from yfinance (sync → thread pool)
    articles = await asyncio.to_thread(_fetch_yfinance_news, ticker)

    # Optionally merge Google News RSS
    google_articles = await _fetch_google_news_rss(ticker)
    articles.extend(google_articles)

    # Deduplicate by URL, sort by date
    seen_urls = set()
    unique = []
    for a in articles:
        if a["link"] not in seen_urls:
            seen_urls.add(a["link"])
            unique.append(a)
    unique.sort(key=lambda x: x.get("published", ""), reverse=True)

    response = StockNewsResponse(ticker=ticker.upper(), articles=unique[:15], fetched_at=...)
    if cache:
        await cache.set(cache_key, response.model_dump_json(), CacheTier.VOLATILE)
    return response
```

### 4.2 Stock Intelligence Endpoint

`GET /api/v1/stocks/{ticker}/intelligence`

Aggregates: recent upgrades/downgrades, insider transactions, EPS revisions, next earnings date. All from yfinance, cached volatile (5 min).

**Response schema:**

```python
class UpgradeDowngrade(BaseModel):
    firm: str
    to_grade: str
    from_grade: str | None = None
    action: str  # "up", "down", "main", "init"
    date: str

class InsiderTransaction(BaseModel):
    insider_name: str
    relation: str | None = None
    transaction_type: str  # "Buy", "Sell"
    shares: int
    value: float | None = None
    date: str

class StockIntelligenceResponse(BaseModel):
    ticker: str
    upgrades_downgrades: list[UpgradeDowngrade]
    insider_transactions: list[InsiderTransaction]
    next_earnings_date: str | None = None
    eps_revisions: dict | None = None  # current/7d/30d/90d revision data
    fetched_at: str
```

**Data sources (all yfinance, all free):**

```python
def _fetch_intelligence(ticker: str) -> dict:
    t = yf.Ticker(ticker)

    # Upgrades/downgrades (last 90 days)
    upgrades = t.upgrades_downgrades
    # → DataFrame: date, firm, toGrade, fromGrade, action

    # Insider transactions (recent)
    insider = t.insider_transactions
    # → DataFrame: name, relation, transaction, shares, value, date

    # Calendar (next earnings)
    calendar = t.calendar
    # → dict with earnings date

    # EPS revisions
    eps_rev = t.eps_revisions
    # → DataFrame with current, 7d, 30d, 90d ago estimates

    return {...}
```

---

## 5. Google News RSS Integration

Free, no API key, no rate limit. Simple HTTP GET to RSS feed.

```python
import xml.etree.ElementTree as ET

async def _fetch_google_news_rss(ticker: str) -> list[dict]:
    """Fetch financial news from Google News RSS for a ticker."""
    url = f"https://news.google.com/rss/search?q={ticker}+stock&hl=en-US&gl=US&ceid=US:en"
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
```

**Security note:** Use `defusedxml.ElementTree` instead of `xml.etree.ElementTree` to prevent XXE attacks on RSS parsing.

---

## 6. Nightly Pipeline Enhancement

### 6.1 Beta/Yield Refresh

During nightly price refresh (`_refresh_ticker_async`), after fetching prices and computing signals, also refresh `beta`, `dividend_yield`, `forward_pe` from yfinance `.info`:

```python
# After signal computation in _refresh_ticker_async:
try:
    info = await asyncio.to_thread(lambda: yf.Ticker(ticker).info)
    if info:
        stock = await db.execute(select(Stock).where(Stock.ticker == ticker))
        stock_obj = stock.scalar_one_or_none()
        if stock_obj:
            for yf_key, field in [("beta", "beta"), ("dividendYield", "dividend_yield"), ("forwardPE", "forward_pe")]:
                val = info.get(yf_key)
                if val is not None:
                    setattr(stock_obj, field, float(val))
            db.add(stock_obj)
except Exception:
    logger.warning("Failed to refresh beta/yield for %s", ticker)
```

**Performance note:** This adds one extra `yf.Ticker(ticker).info` call per ticker per night. Since the nightly pipeline already takes 5-10 min for 500 tickers, this adds ~2-3 min. Acceptable.

### 6.2 Dividend Sync

Already covered in §3.3 — `fetch_dividends()` + `store_dividends()` added to nightly refresh.

---

## 7. Files Changed

| Action | File | Change |
|--------|------|--------|
| **Modify** | `backend/models/stock.py` | Add `beta`, `dividend_yield`, `forward_pe` columns |
| **Modify** | `backend/tools/fundamentals.py` | Extract 3 new fields in `fetch_analyst_data()` |
| **Modify** | `backend/tools/ingest_stock_tool.py` | Add dividend sync step |
| **Modify** | `backend/tasks/market_data.py` | Add beta/yield refresh + dividend sync to nightly |
| **Modify** | `backend/routers/stocks.py` | Add `GET /{ticker}/news` and `GET /{ticker}/intelligence` endpoints |
| **Create** | `backend/schemas/intelligence.py` | News + intelligence response schemas |
| **Create** | `backend/tools/news.py` | yfinance news + Google News RSS fetch functions |
| **Create** | `backend/tools/intelligence.py` | yfinance upgrades/insider/calendar/EPS fetch functions |
| **Create** | `backend/migrations/versions/XXX_013_enrichment.py` | Add 3 columns to stocks |
| **Create** | `tests/unit/tools/test_news.py` | News fetch tests |
| **Create** | `tests/unit/tools/test_intelligence.py` | Intelligence fetch tests |
| **Create** | `tests/api/test_stock_news.py` | API endpoint tests |

---

## 8. Success Criteria

- [ ] `beta`, `dividend_yield`, `forward_pe` populated on Stock model after ingest
- [ ] Dividends synced during ingest (not just on-demand)
- [ ] `GET /stocks/{ticker}/news` returns merged yfinance + Google News articles
- [ ] `GET /stocks/{ticker}/intelligence` returns upgrades, insider, earnings, EPS revisions
- [ ] News endpoint cached with volatile TTL (5 min)
- [ ] Intelligence endpoint cached with volatile TTL (5 min)
- [ ] Nightly pipeline refreshes beta/yield/forward_pe for all watchlist tickers
- [ ] Nightly pipeline syncs dividends for all watchlist tickers
- [ ] Google News RSS parsed with `defusedxml` (XXE protection)
- [ ] All existing tests pass

---

## 9. Out of Scope

- Materializing news in DB → fetched on-demand, cached in Redis
- Sentiment scoring on news articles → future (could use Alpha Vantage or local model)
- Historical insider transaction tracking → yfinance provides recent only
- Alpha Vantage / Finnhub news integration → can be added later as additional sources
- EPS revisions as a signal in composite score → Spec B may use for momentum scoring
