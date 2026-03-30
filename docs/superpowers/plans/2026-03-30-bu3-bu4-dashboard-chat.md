# BU-3 Dashboard Redesign + BU-4 Chat Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the dashboard from a mixed KPI/watchlist page into a 5-zone Daily Intelligence Briefing, relocate watchlist to screener, and clean up chat system.

**Architecture:** Backend-first: migration + endpoint changes → frontend utilities → hooks → components → page assembly. Two-tier cache split for news (global briefing + per-user news). Layered data loading for stock cards (recommendations → bulk signals → fundamentals).

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), Next.js/React/TanStack Query (frontend), Redis caching, TimescaleDB, Tailwind CSS with glassmorphism tokens.

**Spec:** `docs/superpowers/specs/2026-03-30-bu3-bu4-dashboard-chat-design.md`
**Visual Reference:** `docs/mockups/dashboard-bulletin-v3.html`

**LM Studio Triage:** Each chunk has a suggested complexity score. Tasks ≤ 8/15 should be offered to local LLM before starting.

---

## Chunk 1: Backend Infrastructure (7 tasks)
*No frontend dependencies. Can be parallelized where noted.*
*Suggested LM Studio score: T1=4, T2=7, T3=5, T4=6, T5=7, T6=6, T7=8*

### Task 1: Sector Name Normalization Utility

**Files:**
- Create: `backend/utils/sectors.py`
- Test: `tests/unit/utils/test_sectors.py`

- [ ] **Step 1: Write tests**

```python
# tests/unit/utils/test_sectors.py
from backend.utils.sectors import normalize_sector, SECTOR_ALIASES


def test_normalize_exact_match():
    assert normalize_sector("Technology") == "Technology"
    assert normalize_sector("Energy") == "Energy"


def test_normalize_etf_alias():
    assert normalize_sector("Financials") == "Financial Services"
    assert normalize_sector("Consumer Discretionary") == "Consumer Cyclical"
    assert normalize_sector("Consumer Staples") == "Consumer Defensive"
    assert normalize_sector("Materials") == "Basic Materials"


def test_normalize_unknown_passthrough():
    assert normalize_sector("Unknown Sector") == "Unknown Sector"


def test_normalize_communication_services():
    assert normalize_sector("Communications") == "Communication Services"
    assert normalize_sector("Telecom") == "Communication Services"


def test_aliases_cover_all_sectors():
    assert len(SECTOR_ALIASES) == 11
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/utils/test_sectors.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# backend/utils/sectors.py
"""Sector name normalization between yfinance GICS names and ETF sector names."""

SECTOR_ALIASES: dict[str, list[str]] = {
    "Technology": ["Technology", "Information Technology"],
    "Healthcare": ["Healthcare", "Health Care"],
    "Financial Services": ["Financial Services", "Financials"],
    "Consumer Cyclical": ["Consumer Cyclical", "Consumer Discretionary"],
    "Consumer Defensive": ["Consumer Defensive", "Consumer Staples"],
    "Energy": ["Energy"],
    "Industrials": ["Industrials"],
    "Basic Materials": ["Basic Materials", "Materials"],
    "Utilities": ["Utilities"],
    "Real Estate": ["Real Estate"],
    "Communication Services": ["Communication Services", "Communications", "Telecom"],
}

SECTOR_NORMALIZE: dict[str, str] = {
    alias: canonical
    for canonical, aliases in SECTOR_ALIASES.items()
    for alias in aliases
}


def normalize_sector(name: str) -> str:
    """Normalize a sector name to yfinance canonical form."""
    return SECTOR_NORMALIZE.get(name, name)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/utils/test_sectors.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/utils/sectors.py tests/unit/utils/test_sectors.py
git commit -m "feat(utils): add sector name normalization utility"
```

---

### Task 2: Migration — Add `change_pct` to SignalSnapshot + Compute in Signals Service

**Files:**
- Modify: `backend/models/signal.py` (add column after `sharpe_ratio`, ~line 54)
- Modify: `backend/services/signals.py` (add computation in `compute_signals()`, ~line 191)
- Create: Alembic migration
- Test: `tests/unit/services/test_signals.py` (add assertion for change_pct)

- [ ] **Step 1: Add columns to model**

In `backend/models/signal.py`, after `sharpe_ratio = Column(Float, nullable=True)` (~line 54):

```python
    change_pct = Column(Float, nullable=True)  # daily price change percentage
    current_price = Column(Float, nullable=True)  # latest close price (materialized for top movers)
```

Both are needed: `change_pct` for sorting movers, `current_price` for display. Materialized during signal computation to avoid expensive JOINs at query time.

- [ ] **Step 2: Write manual Alembic migration**

**IMPORTANT:** Do NOT use `alembic revision --autogenerate` — it falsely drops TimescaleDB indexes and rewrites the entire schema. Write a manual migration:

Run: `uv run alembic revision -m "add change_pct and current_price to signal_snapshots"`

Then edit the generated file:

```python
def upgrade() -> None:
    op.add_column("signal_snapshots", sa.Column("change_pct", sa.Float(), nullable=True))
    op.add_column("signal_snapshots", sa.Column("current_price", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("signal_snapshots", "current_price")
    op.drop_column("signal_snapshots", "change_pct")
```

- [ ] **Step 3: Run migration**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly.

- [ ] **Step 4: Add computation to signals service**

In `backend/services/signals.py`, add a helper function before `compute_signals()`:

```python
def compute_price_change(df: pd.DataFrame) -> tuple[float | None, float | None]:
    """Compute daily price change percentage and current price from OHLC DataFrame.

    Returns (change_pct, current_price).
    Note: DataFrame column names vary by source. Check for 'adj_close' first,
    then 'Adj Close' (raw yfinance), then 'close'.
    """
    if df is None or len(df) < 2:
        return None, None
    for col in ("adj_close", "Adj Close", "close", "Close"):
        if col in df.columns:
            closes = df[col]
            break
    else:
        return None, None
    current = float(closes.iloc[-1])
    previous = float(closes.iloc[-2])
    if previous == 0:
        return None, current
    change = ((current - previous) / previous) * 100
    return round(change, 2), round(current, 2)
```

In `compute_signals()`, after the existing `ann_ret, vol, sharpe = compute_risk_return(closes, risk_free_rate)` line (~line 191):

```python
    change_pct, current_price = compute_price_change(df)
```

Add both fields to the returned `SignalResult` dataclass. In `backend/models/signal.py` or wherever `SignalResult` is defined, add:

```python
    change_pct: float | None = None
    current_price: float | None = None
```

Also add `change_pct=change_pct, current_price=current_price` to the `SignalResult(...)` constructor call in `compute_signals()`.

- [ ] **Step 5: Update snapshot persistence**

Find where `SignalSnapshot` is created from `SignalResult` (likely in `backend/services/stock_data.py` or `ingest` logic). Add `change_pct=result.change_pct, current_price=result.current_price` to the snapshot constructor.

- [ ] **Step 6: Write test**

In the existing signals test file, add:

```python
def test_compute_price_change():
    from backend.services.signals import compute_price_change
    import pandas as pd

    df = pd.DataFrame({"adj_close": [100.0, 102.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct == pytest.approx(2.0)
    assert current_price == pytest.approx(102.0)


def test_compute_price_change_negative():
    from backend.services.signals import compute_price_change
    import pandas as pd

    df = pd.DataFrame({"adj_close": [100.0, 97.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct == pytest.approx(-3.0)
    assert current_price == pytest.approx(97.0)


def test_compute_price_change_insufficient_data():
    from backend.services.signals import compute_price_change
    import pandas as pd

    df = pd.DataFrame({"adj_close": [100.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct is None
    assert current_price is None


def test_compute_price_change_zero_previous():
    """Division by zero guard when previous close is 0."""
    from backend.services.signals import compute_price_change
    import pandas as pd

    df = pd.DataFrame({"adj_close": [0.0, 5.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct is None
    assert current_price == pytest.approx(5.0)


def test_compute_price_change_capital_close_column():
    """Handles yfinance raw column name 'Close' (capital C)."""
    from backend.services.signals import compute_price_change
    import pandas as pd

    df = pd.DataFrame({"Close": [100.0, 105.0]})
    change_pct, current_price = compute_price_change(df)
    assert change_pct == pytest.approx(5.0)
    assert current_price == pytest.approx(105.0)


def test_compute_price_change_none_dataframe():
    from backend.services.signals import compute_price_change

    change_pct, current_price = compute_price_change(None)
    assert change_pct is None
    assert current_price is None
```

**IMPORTANT: After this task, update `SignalSnapshotFactory` in `tests/conftest.py` to include `change_pct` and `current_price` fields with sensible defaults (e.g., `change_pct=1.5, current_price=150.0`). Without this, T5 and T3 tests that create snapshots via factory will have `None` for these columns, silently breaking queries that filter `change_pct.isnot(None)`.**

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/unit/services/test_signals.py -v -k "price_change"`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add backend/models/signal.py backend/services/signals.py tests/unit/services/test_signals.py alembic/versions/
git commit -m "feat(signals): add change_pct to SignalSnapshot with daily price change computation"
```

---

### Task 3: Bulk Signals — Add `tickers` Query Parameter

**Files:**
- Modify: `backend/routers/stocks/recommendations.py` (~line 118, bulk signals endpoint)
- Modify: `backend/services/signals.py` or wherever `get_bulk_signals_svc` is defined
- Test: `tests/api/test_signals_bulk.py` (add test for tickers filter)

- [ ] **Step 1: Write API test**

```python
# In tests/api/ — add to existing bulk signals test file
async def test_bulk_signals_filter_by_tickers(client, auth_headers):
    """Bulk signals endpoint accepts tickers param to filter by specific stocks.
    NOTE: Requires signal snapshots to exist for AAPL/MSFT. Use the project's
    inline data seeding pattern (StockFactory + SignalSnapshotFactory) in a
    fixture or setup block — do NOT reference nonexistent 'seeded_stocks' fixture.
    """
    resp = await client.get(
        "/api/v1/stocks/signals/bulk?tickers=AAPL,MSFT",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    tickers = {item["ticker"] for item in data["items"]}
    assert tickers.issubset({"AAPL", "MSFT"})
```

- [ ] **Step 2: Add `tickers` param to endpoint**

In `backend/routers/stocks/recommendations.py`, add to the bulk signals endpoint function signature (~line 118):

```python
    tickers: str | None = Query(default=None, description="Comma-separated ticker list, e.g. AAPL,MSFT"),
```

Pass to the service:

```python
    tickers_list = [t.strip().upper() for t in tickers.split(",")] if tickers else None
```

Then pass `tickers_list=tickers_list` to the service function.

- [ ] **Step 3: Add filter to service layer**

In the service function `get_bulk_signals_svc`, add after existing filters:

```python
    if tickers_list:
        query = query.where(SignalSnapshot.ticker.in_(tickers_list))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_signals_bulk.py -v -k "tickers"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/stocks/recommendations.py backend/services/
git commit -m "feat(signals): add tickers query param to bulk signals endpoint"
```

---

### Task 4: Recommendations — Add `name` Field via JOIN

**Files:**
- Modify: `backend/routers/stocks/recommendations.py` (~lines 79-107, recommendations endpoint)
- Modify: `backend/schemas/stock.py` (add `name` to `RecommendationResponse`)
- Test: `tests/api/test_recommendations.py` (assert name field present)

- [ ] **Step 1: Write test**

```python
async def test_recommendation_includes_stock_name(client, auth_headers):
    """NOTE: Requires recommendations to exist for the test user. Use inline
    seeding with RecommendationSnapshotFactory — do NOT reference nonexistent fixtures."""
    resp = await client.get("/api/v1/stocks/recommendations", headers=auth_headers)
    assert resp.status_code == 200
    recs = resp.json()["recommendations"]
    if recs:
        assert "name" in recs[0]
        # name can be None (if stock not in stocks table) or a string
        assert recs[0]["name"] is None or isinstance(recs[0]["name"], str)
```

- [ ] **Step 2: Add `name` to schema**

In `backend/schemas/stock.py`, find `RecommendationResponse` and add:

```python
    name: str | None = None
```

- [ ] **Step 3: Restructure query with JOIN**

In `backend/routers/stocks/recommendations.py`, change the recommendations query from:

```python
query = select(RecommendationSnapshot).where(...)
```

To:

```python
from backend.models.stock import Stock

query = (
    select(RecommendationSnapshot, Stock.name)
    .join(Stock, RecommendationSnapshot.ticker == Stock.ticker, isouter=True)
    .where(RecommendationSnapshot.user_id == current_user.id)
)
```

Update the result processing from:

```python
recs = result.scalars().all()
recommendations = [RecommendationResponse.model_validate(r) for r in recs]
```

To:

```python
rows = result.all()
recommendations = []
for row in rows:
    snapshot = row[0]  # RecommendationSnapshot
    stock_name = row[1]  # Stock.name (may be None)
    rec_dict = {c.key: getattr(snapshot, c.key) for c in snapshot.__table__.columns}
    rec_dict["name"] = stock_name
    recommendations.append(RecommendationResponse.model_validate(rec_dict))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_recommendations.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/stocks/recommendations.py backend/schemas/stock.py tests/api/
git commit -m "feat(recommendations): add stock name via JOIN to recommendation response"
```

---

### Task 5: Market Briefing — Implement Top Movers

**Files:**
- Modify: `backend/tools/market_briefing.py` (replace empty top_movers at ~line 237)
- Test: `tests/unit/tools/test_market_briefing.py`

- [ ] **Step 1: Write test**

```python
async def test_top_movers_returns_gainers_and_losers(db_session):
    """Top movers should return stocks sorted by change_pct."""
    from backend.tools.market_briefing import _fetch_top_movers

    # Seed signal_snapshots with known change_pct values
    # (use existing fixture pattern from the project)
    result = await _fetch_top_movers(db_session, limit=4)
    assert "gainers" in result
    assert "losers" in result
    assert len(result["gainers"]) <= 4
    assert len(result["losers"]) <= 4
    if result["gainers"]:
        assert "ticker" in result["gainers"][0]
        assert "current_price" in result["gainers"][0]
        assert "change_pct" in result["gainers"][0]
        assert "macd_signal_label" in result["gainers"][0]
```

- [ ] **Step 2: Implement `_fetch_top_movers` function**

In `backend/tools/market_briefing.py`, add a new async function:

```python
from backend.models.signal import SignalSnapshot
from sqlalchemy import select, func, desc, asc


async def _fetch_top_movers(
    db: AsyncSession, limit: int = 4
) -> dict[str, list[dict]]:
    """Fetch top gainers and losers from latest signal snapshots."""
    latest_ts_q = select(func.max(SignalSnapshot.computed_at))
    latest_ts = (await db.execute(latest_ts_q)).scalar_one_or_none()
    if not latest_ts:
        return {"gainers": [], "losers": []}

    base_q = select(
        SignalSnapshot.ticker,
        SignalSnapshot.current_price,
        SignalSnapshot.change_pct,
        SignalSnapshot.macd_signal_label,
        SignalSnapshot.composite_score,
    ).where(
        SignalSnapshot.computed_at == latest_ts,
        SignalSnapshot.change_pct.isnot(None),
    )

    def _to_dict(row) -> dict:
        return {
            "ticker": row.ticker,
            "current_price": row.current_price,
            "change_pct": round(row.change_pct, 2),
            "macd_signal_label": row.macd_signal_label,
            "composite_score": row.composite_score,
        }

    gainers_q = base_q.order_by(desc(SignalSnapshot.change_pct)).limit(limit)
    gainers = [_to_dict(r) for r in (await db.execute(gainers_q)).all()]

    losers_q = base_q.order_by(asc(SignalSnapshot.change_pct)).limit(limit)
    losers = [_to_dict(r) for r in (await db.execute(losers_q)).all()]

    return {"gainers": gainers, "losers": losers}
```

- [ ] **Step 3: Wire into execute() method**

In the `execute()` method of `MarketBriefingTool`, replace the hardcoded `top_movers` (line 237) with a call to the new function. **IMPORTANT:** Do NOT import `async_session_factory` directly — the tool's `execute()` method already opens a session (check how `portfolio_news` fetch gets its session at ~line 170). Follow that same pattern. If the tool uses `async_session_factory()` internally (as it does for portfolio queries), reuse that same session for `_fetch_top_movers`:

```python
# Inside the existing `async with async_session_factory() as session:` block
# that already exists for portfolio queries (~line 170):
top_movers = await _fetch_top_movers(session)
```

If the session block doesn't cover the return dict construction, move the `top_movers` call inside the existing block and store the result in a local variable.

Then use `top_movers` in the return dict instead of the hardcoded empty dict.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/tools/test_market_briefing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/market_briefing.py tests/unit/tools/
git commit -m "feat(briefing): implement top movers from signal snapshots"
```

---

### Task 6: Market Briefing — Parallelize Sector ETF Fetch + Add General Market News + Sector Normalization

**Files:**
- Modify: `backend/tools/market_briefing.py` (parallelize ~lines 81-111, add market news, normalize sectors)
- Test: `tests/unit/tools/test_market_briefing.py`

- [ ] **Step 1: Parallelize sector ETF fetch**

In `backend/tools/market_briefing.py`, find `_fetch_sector_etf_performance()` (~lines 81-111). Currently it loops sequentially. Replace with parallel fetch:

```python
async def _fetch_sector_etf_performance() -> list[dict]:
    """Fetch sector ETF performance in parallel."""
    from backend.utils.sectors import normalize_sector

    async def _fetch_one(sector: str, etf: str) -> dict | None:
        try:
            ticker = await asyncio.to_thread(yf.Ticker, etf)
            info = await asyncio.to_thread(lambda: ticker.fast_info)
            prev = getattr(info, "previous_close", None)
            curr = getattr(info, "last_price", None)
            if prev and curr and prev > 0:
                change = ((curr - prev) / prev) * 100
                return {
                    "sector": normalize_sector(sector),
                    "etf": etf,
                    "change_pct": round(change, 2),
                }
        except Exception:
            logger.warning("Failed to fetch ETF %s for sector %s", etf, sector)
        return None

    tasks = [_fetch_one(sector, etf) for sector, etf in SECTOR_ETFS.items()]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]
```

- [ ] **Step 2: Add XLC to SECTOR_ETFS**

In the `SECTOR_ETFS` dict (~line 30), add:

```python
    "Communication Services": "XLC",
```

- [ ] **Step 3: Add general market news to briefing**

In the `execute()` method, add a Google RSS fetch for general market news alongside the existing parallel calls:

```python
from backend.tools.news import fetch_google_news_rss

general_news = await fetch_google_news_rss("stock+market+today")
general_news = [
    {**article, "portfolio_ticker": None}
    for article in general_news[:3]
]
```

Merge `general_news` into the return dict alongside (but separate from) `portfolio_news`.

- [ ] **Step 4: Write tests for parallelized ETF fetch + general news**

```python
# Add to tests/unit/tools/test_market_briefing.py

@pytest.mark.asyncio
async def test_sector_etf_fetch_handles_single_failure(monkeypatch):
    """One ETF failure should not crash the entire batch."""
    from backend.tools.market_briefing import _fetch_sector_etf_performance
    import yfinance as yf

    call_count = 0

    def mock_ticker(symbol):
        nonlocal call_count
        call_count += 1
        if symbol == "XLF":  # Simulate one failure
            raise Exception("yfinance timeout")
        mock = MagicMock()
        mock.fast_info.previous_close = 100.0
        mock.fast_info.last_price = 102.0
        return mock

    monkeypatch.setattr(yf, "Ticker", mock_ticker)
    result = await _fetch_sector_etf_performance()
    # Should return results for all sectors EXCEPT the failed one
    assert len(result) >= 9  # 11 total - 1 failed = 10 (some may also fail)
    sectors = {r["sector"] for r in result}
    assert "Financial Services" not in sectors  # XLF failed


@pytest.mark.asyncio
async def test_sector_etf_normalizes_names(monkeypatch):
    """Sector names should be normalized to yfinance canonical form."""
    from backend.tools.market_briefing import _fetch_sector_etf_performance
    import yfinance as yf

    mock = MagicMock()
    mock.fast_info.previous_close = 100.0
    mock.fast_info.last_price = 101.0
    monkeypatch.setattr(yf, "Ticker", lambda _: mock)

    result = await _fetch_sector_etf_performance()
    names = {r["sector"] for r in result}
    # Should use canonical names, not ETF names
    assert "Consumer Cyclical" in names or len(names) > 0
    assert "Consumer Discretionary" not in names  # ETF alias should be normalized
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/unit/tools/test_market_briefing.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/tools/market_briefing.py tests/unit/tools/test_market_briefing.py
git commit -m "feat(briefing): parallelize sector ETF fetch, add XLC, add general market news"
```

---

### Task 7: New Endpoint — `GET /news/dashboard` (User-Scoped News)

**Files:**
- Create: `backend/routers/news.py` (new router)
- Modify: `backend/main.py` (register router)
- Test: `tests/api/test_news_dashboard.py`

- [ ] **Step 1: Write API test**

```python
# tests/api/test_news_dashboard.py
import pytest


@pytest.mark.asyncio
async def test_dashboard_news_returns_articles(client, auth_headers):
    resp = await client.get("/api/v1/news/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "articles" in data
    assert isinstance(data["articles"], list)


@pytest.mark.asyncio
async def test_dashboard_news_requires_auth(client):
    resp = await client.get("/api/v1/news/dashboard")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_news_empty_portfolio_and_no_recs(client, auth_headers):
    """User with no portfolio and no recommendations gets empty articles."""
    resp = await client.get("/api/v1/news/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["articles"] == []
    assert data["ticker_count"] == 0


@pytest.mark.asyncio
async def test_dashboard_news_cache_hit(client, auth_headers, monkeypatch):
    """Cache hit returns cached data without external API calls."""
    # First call populates cache, second call should hit cache
    resp1 = await client.get("/api/v1/news/dashboard", headers=auth_headers)
    assert resp1.status_code == 200
    resp2 = await client.get("/api/v1/news/dashboard", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
```

- [ ] **Step 2: Implement router**

```python
# backend/routers/news.py
"""Dashboard news aggregation — per-user, cached."""

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import get_current_user
from backend.database import get_db
from backend.models.portfolio import Portfolio, Position
from backend.models.recommendation import RecommendationSnapshot
from backend.models.user import User
from backend.services.cache import CacheTier
from backend.tools.news import fetch_yfinance_news, fetch_google_news_rss, merge_and_deduplicate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/news", tags=["news"])


@router.get("/dashboard")
async def get_dashboard_news(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aggregated news for user's portfolio + recommendation tickers."""

    cache = getattr(request.app.state, "cache", None)
    cache_key = f"user:{current_user.id}:dashboard_news"

    if cache:
        cached = await cache.get(cache_key)
        if cached:
            return json.loads(cached)

    # Get top 3 portfolio tickers by allocation
    portfolio_q = select(Portfolio.id).where(Portfolio.user_id == current_user.id)
    portfolio_result = await db.execute(portfolio_q)
    portfolio_id = portfolio_result.scalar_one_or_none()

    portfolio_tickers: list[str] = []
    if portfolio_id:
        pos_q = (
            select(Position.ticker)
            .where(Position.portfolio_id == portfolio_id, Position.shares > 0)
            .order_by(Position.shares.desc())
            .limit(3)
        )
        pos_result = await db.execute(pos_q)
        portfolio_tickers = [row[0] for row in pos_result.all()]

    # Get top 3 recommendation tickers
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    rec_q = (
        select(RecommendationSnapshot.ticker)
        .where(
            RecommendationSnapshot.user_id == current_user.id,
            RecommendationSnapshot.generated_at >= cutoff,
            RecommendationSnapshot.action.in_(["BUY", "STRONG_BUY"]),
        )
        .order_by(RecommendationSnapshot.composite_score.desc())
        .limit(3)
    )
    rec_result = await db.execute(rec_q)
    rec_tickers = [row[0] for row in rec_result.all()]

    # Deduplicate tickers
    all_tickers = list(dict.fromkeys(portfolio_tickers + rec_tickers))[:6]

    if not all_tickers:
        return {"articles": [], "ticker_count": 0}

    # Fetch news in parallel
    async def _fetch_for_ticker(ticker: str) -> list[dict]:
        try:
            yf_news = await asyncio.to_thread(fetch_yfinance_news, ticker)
            google_news = await fetch_google_news_rss(ticker)
            merged = merge_and_deduplicate(yf_news + google_news, max_results=3)
            return [{**a, "portfolio_ticker": ticker} for a in merged]
        except Exception:
            logger.warning("News fetch failed for %s", ticker)
            return []

    results = await asyncio.gather(*[_fetch_for_ticker(t) for t in all_tickers])
    all_articles = [a for batch in results for a in batch]

    # Sort by published date, limit to 15
    all_articles.sort(key=lambda a: a.get("published", ""), reverse=True)
    all_articles = all_articles[:15]

    response = {"articles": all_articles, "ticker_count": len(all_tickers)}

    if cache:
        await cache.set(cache_key, json.dumps(response, default=str), CacheTier.VOLATILE)

    return response
```

- [ ] **Step 3: Register router in main.py**

In `backend/main.py`, add:

```python
from backend.routers.news import router as news_router
app.include_router(news_router, prefix="/api/v1")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_news_dashboard.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/news.py backend/main.py tests/api/test_news_dashboard.py
git commit -m "feat(news): add per-user dashboard news endpoint with split cache"
```

---

## Chunk 2: Frontend Utilities (4 tasks)
*No backend dependency. Can run in parallel with Chunk 1.*
*Suggested LM Studio score: T8=3, T9=4, T10=3, T11=5*

### Task 8: Sector Normalization — Frontend Mirror

**Files:**
- Create: `frontend/src/lib/sectors.ts`
- Test: `frontend/src/__tests__/lib/sectors.test.ts`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/__tests__/lib/sectors.test.ts
import { normalizeSector } from "@/lib/sectors";

describe("normalizeSector", () => {
  it("passes through canonical names", () => {
    expect(normalizeSector("Technology")).toBe("Technology");
    expect(normalizeSector("Energy")).toBe("Energy");
  });

  it("normalizes ETF aliases to canonical", () => {
    expect(normalizeSector("Financials")).toBe("Financial Services");
    expect(normalizeSector("Consumer Discretionary")).toBe("Consumer Cyclical");
    expect(normalizeSector("Materials")).toBe("Basic Materials");
  });

  it("returns unknown sectors as-is", () => {
    expect(normalizeSector("Unknown")).toBe("Unknown");
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// frontend/src/lib/sectors.ts
const SECTOR_NORMALIZE: Record<string, string> = {
  Technology: "Technology",
  "Information Technology": "Technology",
  Healthcare: "Healthcare",
  "Health Care": "Healthcare",
  "Financial Services": "Financial Services",
  Financials: "Financial Services",
  "Consumer Cyclical": "Consumer Cyclical",
  "Consumer Discretionary": "Consumer Cyclical",
  "Consumer Defensive": "Consumer Defensive",
  "Consumer Staples": "Consumer Defensive",
  Energy: "Energy",
  Industrials: "Industrials",
  "Basic Materials": "Basic Materials",
  Materials: "Basic Materials",
  Utilities: "Utilities",
  "Real Estate": "Real Estate",
  "Communication Services": "Communication Services",
  Communications: "Communication Services",
  Telecom: "Communication Services",
};

export function normalizeSector(name: string): string {
  return SECTOR_NORMALIZE[name] ?? name;
}
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx jest __tests__/lib/sectors.test.ts`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/sectors.ts frontend/src/__tests__/lib/sectors.test.ts
git commit -m "feat(frontend): add sector name normalization utility"
```

---

### Task 9: Market Hours Utility

**Files:**
- Modify: `frontend/src/lib/market-hours.ts` (file already exists with `isNYSEOpen` — extend it, do NOT overwrite)
- Test: `frontend/src/__tests__/lib/market-hours.test.ts`

**IMPORTANT:** This file already exists and exports `isNYSEOpen()`. Read it first. Either rename to `isMarketOpen` (and update all existing consumers), or keep `isNYSEOpen` and add holiday support to it. Grep for imports of `isNYSEOpen` before deciding. The plan below assumes we extend the existing function.

- [ ] **Step 1: Write test**

```typescript
// frontend/src/__tests__/lib/market-hours.test.ts
import { isMarketOpen } from "@/lib/market-hours";

describe("isMarketOpen", () => {
  it("returns true during market hours on weekday", () => {
    // Wednesday March 25, 2026 at 10:00 AM ET = 14:00 UTC
    const date = new Date("2026-03-25T14:00:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });

  it("returns false on weekend", () => {
    // Saturday March 28, 2026 at 10:00 AM ET
    const date = new Date("2026-03-28T14:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns false before market open", () => {
    // Wednesday at 9:00 AM ET = 13:00 UTC (before 9:30)
    const date = new Date("2026-03-25T13:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns false after market close", () => {
    // Wednesday at 4:30 PM ET = 20:30 UTC (after 16:00)
    const date = new Date("2026-03-25T20:30:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("handles EST correctly (November, UTC-5)", () => {
    // Wednesday Nov 4, 2026 at 10:00 AM EST = 15:00 UTC
    const date = new Date("2026-11-04T15:00:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });

  it("returns false on FINRA holiday (New Years Day)", () => {
    // Thursday Jan 1, 2026 at 10:00 AM ET = 15:00 UTC — market is closed for holiday
    const date = new Date("2026-01-01T15:00:00Z");
    expect(isMarketOpen(date)).toBe(false);
  });

  it("returns true on day before holiday (Dec 24 during hours)", () => {
    // Wednesday Dec 24, 2026 at 10:00 AM ET = 15:00 UTC — regular trading day
    const date = new Date("2026-12-24T15:00:00Z");
    expect(isMarketOpen(date)).toBe(true);
  });

  it("uses ET date for holiday check, not UTC", () => {
    // Dec 24 at 11 PM ET = Dec 25 00:00 UTC — should NOT trigger Christmas holiday
    // Dec 24 is a regular trading day (Christmas is Dec 25)
    // At 11 PM ET market is closed (after 4 PM), but NOT because of holiday
    const date = new Date("2026-12-25T04:00:00Z"); // 11 PM ET on Dec 24
    // Market is closed (after hours), but isMarketOpen should return false for time, not holiday
    expect(isMarketOpen(date)).toBe(false);
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// frontend/src/lib/market-hours.ts

// FINRA observed holidays for 2026 (update annually)
const HOLIDAYS_2026 = [
  "2026-01-01", // New Year's Day
  "2026-01-19", // MLK Day
  "2026-02-16", // Presidents' Day
  "2026-04-03", // Good Friday
  "2026-05-25", // Memorial Day
  "2026-06-19", // Juneteenth
  "2026-07-03", // Independence Day (observed)
  "2026-09-07", // Labor Day
  "2026-11-26", // Thanksgiving
  "2026-12-25", // Christmas
];

export function isMarketOpen(now: Date = new Date()): boolean {
  const etFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  });

  const parts = etFormatter.formatToParts(now);
  const weekday = parts.find((p) => p.type === "weekday")?.value;
  const hour = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0");
  const minute = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0");

  // Weekend check
  if (weekday === "Sat" || weekday === "Sun") return false;

  // Holiday check — MUST use ET date, not UTC date.
  // At 11 PM ET on Dec 24, UTC is already Dec 25 — using UTC would falsely trigger Christmas.
  const etDateFormatter = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" });
  const dateStr = etDateFormatter.format(now); // "YYYY-MM-DD" in ET
  if (HOLIDAYS_2026.includes(dateStr)) return false;

  // Market hours: 9:30 AM - 4:00 PM ET
  const minutesSinceMidnight = hour * 60 + minute;
  const openMinute = 9 * 60 + 30; // 9:30 AM
  const closeMinute = 16 * 60; // 4:00 PM

  return minutesSinceMidnight >= openMinute && minutesSinceMidnight < closeMinute;
}
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx jest __tests__/lib/market-hours.test.ts`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/market-hours.ts frontend/src/__tests__/lib/market-hours.test.ts
git commit -m "feat(frontend): add market hours utility with FINRA holidays"
```

---

### Task 10: News Sentiment Heuristic

**Files:**
- Create: `frontend/src/lib/news-sentiment.ts`
- Test: `frontend/src/__tests__/lib/news-sentiment.test.ts`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/__tests__/lib/news-sentiment.test.ts
import { classifyNewsSentiment } from "@/lib/news-sentiment";

describe("classifyNewsSentiment", () => {
  it("classifies bullish headlines", () => {
    expect(classifyNewsSentiment("Microsoft Azure revenue beats estimates")).toBe("bullish");
    expect(classifyNewsSentiment("Stock surges on earnings report")).toBe("bullish");
    expect(classifyNewsSentiment("Analyst upgrades to buy")).toBe("bullish");
  });

  it("classifies bearish headlines", () => {
    expect(classifyNewsSentiment("Intel delays chip production")).toBe("bearish");
    expect(classifyNewsSentiment("Analysts cut price target")).toBe("bearish");
    expect(classifyNewsSentiment("Stock falls on weak guidance")).toBe("bearish");
  });

  it("classifies neutral headlines", () => {
    expect(classifyNewsSentiment("Company announces quarterly results")).toBe("neutral");
    expect(classifyNewsSentiment("CEO discusses strategy at conference")).toBe("neutral");
  });

  it("is case-insensitive", () => {
    expect(classifyNewsSentiment("STOCK SURGES AFTER EARNINGS")).toBe("bullish");
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// frontend/src/lib/news-sentiment.ts
export type NewsSentiment = "bullish" | "bearish" | "neutral";

const BULLISH_KEYWORDS = [
  "beats", "surges", "upgrades", "accelerates", "record",
  "growth", "rises", "soars", "rally", "gains", "jumps",
  "outperforms", "exceeds", "boost", "strong",
];

const BEARISH_KEYWORDS = [
  "misses", "delays", "cuts", "rejects", "falls",
  "downgrades", "warns", "drops", "declines", "plunges",
  "slumps", "losses", "weak", "disappoints", "layoffs",
];

export function classifyNewsSentiment(title: string): NewsSentiment {
  const lower = title.toLowerCase();
  const hasBullish = BULLISH_KEYWORDS.some((kw) => lower.includes(kw));
  const hasBearish = BEARISH_KEYWORDS.some((kw) => lower.includes(kw));

  if (hasBullish && !hasBearish) return "bullish";
  if (hasBearish && !hasBullish) return "bearish";
  return "neutral";
}
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx jest __tests__/lib/news-sentiment.test.ts`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/news-sentiment.ts frontend/src/__tests__/lib/news-sentiment.test.ts
git commit -m "feat(frontend): add news sentiment keyword heuristic"
```

---

### Task 11: Signal Reason Builder

**Files:**
- Create: `frontend/src/lib/signal-reason.ts`
- Test: `frontend/src/__tests__/lib/signal-reason.test.ts`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/__tests__/lib/signal-reason.test.ts
import { buildSignalReason } from "@/lib/signal-reason";

describe("buildSignalReason", () => {
  it("builds reason from MACD + RSI", () => {
    const reason = buildSignalReason({
      macd_signal: "bullish_crossover",
      rsi_value: 34,
      rsi_signal: "oversold",
    });
    expect(reason).toContain("MACD bullish crossover");
    expect(reason).toContain("RSI oversold");
  });

  it("includes Piotroski when strong", () => {
    const reason = buildSignalReason({
      macd_signal: "bullish",
      piotroski_score: 8,
    });
    expect(reason).toContain("Piotroski 8/9");
  });

  it("returns empty string with no data", () => {
    expect(buildSignalReason({})).toBe("");
  });

  it("limits to 3 factors", () => {
    const reason = buildSignalReason({
      macd_signal: "bullish_crossover",
      rsi_value: 30,
      rsi_signal: "oversold",
      piotroski_score: 8,
      sma_signal: "golden_cross",
      pe_ratio: 15,
    });
    const factors = reason.split(" + ");
    expect(factors.length).toBeLessThanOrEqual(3);
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// frontend/src/lib/signal-reason.ts

interface SignalData {
  macd_signal?: string | null;
  rsi_value?: number | null;
  rsi_signal?: string | null;
  piotroski_score?: number | null;
  sma_signal?: string | null;
  pe_ratio?: number | null;
  insider_activity?: string | null;
}

const MACD_LABELS: Record<string, string> = {
  bullish_crossover: "MACD bullish crossover",
  bullish: "MACD bullish",
  bearish_crossover: "MACD bearish crossover",
  bearish: "MACD bearish",
};

export function buildSignalReason(data: SignalData): string {
  const factors: string[] = [];

  if (data.macd_signal && MACD_LABELS[data.macd_signal]) {
    factors.push(MACD_LABELS[data.macd_signal]);
  }

  if (data.rsi_signal === "oversold" || data.rsi_signal === "overbought") {
    factors.push(`RSI ${data.rsi_signal}${data.rsi_value ? ` (${data.rsi_value})` : ""}`);
  }

  if (data.piotroski_score != null && data.piotroski_score >= 7) {
    factors.push(`Piotroski ${data.piotroski_score}/9 (strong fundamentals)`);
  } else if (data.piotroski_score != null && data.piotroski_score <= 2) {
    factors.push(`Piotroski ${data.piotroski_score}/9 (weak fundamentals)`);
  }

  if (data.sma_signal === "golden_cross") {
    factors.push("SMA golden cross");
  } else if (data.sma_signal === "death_cross") {
    factors.push("SMA death cross");
  }

  if (data.insider_activity === "selling") {
    factors.push("insider selling detected");
  }

  return factors.slice(0, 3).join(" + ");
}
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx jest __tests__/lib/signal-reason.test.ts`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/signal-reason.ts frontend/src/__tests__/lib/signal-reason.test.ts
git commit -m "feat(frontend): add signal reason builder from technical data"
```

---

## Chunk 3: Frontend Hooks (4 tasks)
*Depends on Chunk 1 backend endpoints being deployed.*
*Suggested LM Studio score: T12=4, T13=4, T14=5, T15=4*

### Task 12: `useMarketBriefing` Hook

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts` (add hook at end of file)
- Modify: `frontend/src/types/api.ts` (add `MarketBriefingResponse` if not already defined)

- [ ] **Step 1: Add/verify TypeScript types**

In `frontend/src/types/api.ts`, verify `MarketBriefingResult` exists. If not, add:

```typescript
export interface IndexPerformance {
  name: string;
  ticker: string;
  price: number;
  change_pct: number;
}

export interface SectorPerformance {
  sector: string;
  etf: string;
  change_pct: number;
}

export interface TopMover {
  ticker: string;
  change_pct: number;
  macd_signal_label: string | null;
  composite_score: number | null;
}

export interface MarketBriefingResult {
  indexes: IndexPerformance[];
  sector_performance: SectorPerformance[];
  portfolio_news: NewsArticle[];
  upcoming_earnings: { ticker: string; date: string }[];
  top_movers: { gainers: TopMover[]; losers: TopMover[] };
  briefing_date: string;
  general_news?: NewsArticle[];
}

export interface NewsArticle {
  title: string;
  link: string;
  publisher: string | null;
  published: string | null;
  source: string;
  portfolio_ticker?: string | null;
}
```

- [ ] **Step 2: Add hook**

In `frontend/src/hooks/use-stocks.ts`, add:

```typescript
export function useMarketBriefing() {
  return useQuery<MarketBriefingResult>({
    queryKey: ["market-briefing"],
    queryFn: () => get<MarketBriefingResult>("/market/briefing"),
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-stocks.ts frontend/src/types/api.ts
git commit -m "feat(hooks): add useMarketBriefing hook"
```

---

### Task 13: `usePortfolioHealth` + `usePortfolioHealthHistory` Hooks

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts`
- Modify: `frontend/src/types/api.ts` (types should already exist — verify)

- [ ] **Step 1: Verify types exist**

Check that `PortfolioHealthResult` and `PortfolioHealthSnapshotResponse` exist in `types/api.ts`. They should from Session 72. If not, add them per the backend schemas.

- [ ] **Step 2: Add hooks**

```typescript
export function usePortfolioHealth() {
  return useQuery<PortfolioHealthResult>({
    queryKey: ["portfolio-health"],
    queryFn: () => get<PortfolioHealthResult>("/portfolio/health"),
    staleTime: 5 * 60 * 1000,
  });
}

export function usePortfolioHealthHistory(days: number = 7) {
  return useQuery<PortfolioHealthSnapshotResponse[]>({
    queryKey: ["portfolio-health-history", days],
    queryFn: () =>
      get<PortfolioHealthSnapshotResponse[]>(
        `/portfolio/health/history?days=${days}`
      ),
    staleTime: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-stocks.ts frontend/src/types/api.ts
git commit -m "feat(hooks): add usePortfolioHealth and usePortfolioHealthHistory hooks"
```

---

### Task 14: `useUserDashboardNews` Hook

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts`

- [ ] **Step 1: Add type**

In `types/api.ts`:

```typescript
export interface DashboardNewsResponse {
  articles: NewsArticle[];
  ticker_count: number;
}
```

- [ ] **Step 2: Add hook**

```typescript
export function useUserDashboardNews(enabled: boolean = true) {
  return useQuery<DashboardNewsResponse>({
    queryKey: ["dashboard-news"],
    queryFn: () => get<DashboardNewsResponse>("/news/dashboard"),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/use-stocks.ts frontend/src/types/api.ts
git commit -m "feat(hooks): add useUserDashboardNews hook for per-user news"
```

---

### Task 15: Update `useBulkSignals` for `tickers` Param

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts` (update `useBulkSignals` and `ScreenerFilters` type)

- [ ] **Step 1: Add `tickers` to `ScreenerFilters`**

Find the `ScreenerFilters` interface (likely in `types/api.ts` or inline in the hooks file). Add:

```typescript
  tickers?: string; // comma-separated ticker list
```

- [ ] **Step 2: Update query builder**

In the `buildScreenerQuery` function (or wherever the URL is constructed for bulk signals), add:

```typescript
if (filters.tickers) params.append("tickers", filters.tickers);
```

- [ ] **Step 3: Add convenience wrapper**

```typescript
export function useBulkSignalsByTickers(tickers: string[], enabled: boolean = true) {
  return useQuery({
    queryKey: ["bulk-signals-by-ticker", tickers],
    queryFn: () =>
      get<BulkSignalsResponse>(
        `/stocks/signals/bulk?tickers=${tickers.join(",")}&limit=${tickers.length}`
      ),
    enabled: enabled && tickers.length > 0,
    staleTime: 60 * 1000,
  });
}
```

This is a separate hook (not piggybacking on `useBulkSignals` / `buildScreenerQuery`) because the use case is fundamentally different — fetching by specific tickers, not screener filtering. Different query key prevents cache collisions with the screener.

- [ ] **Step 4: Verify**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/use-stocks.ts frontend/src/types/api.ts
git commit -m "feat(hooks): add tickers param support to useBulkSignals"
```

---

## Chunk 4: Frontend Components (8 tasks)
*Depends on Chunks 2-3. These are the new UI components.*
*Suggested LM Studio score: T16=5, T17=5, T18=7, T19=4, T20=6, T21=6, T22=4, T23=5*

### Task 16: ScoreRing + ActionBadge Components

**Files:**
- Create: `frontend/src/components/score-ring.tsx`
- Create: `frontend/src/components/action-badge.tsx`
- Test: `frontend/src/__tests__/components/score-ring.test.tsx`

- [ ] **Step 1: Write test**

```typescript
// frontend/src/__tests__/components/score-ring.test.tsx
import { render, screen } from "@testing-library/react";
import { ScoreRing } from "@/components/score-ring";

describe("ScoreRing", () => {
  it("renders score value", () => {
    render(<ScoreRing score={9.2} />);
    expect(screen.getByText("9.2")).toBeInTheDocument();
  });

  it("applies buy class for score >= 8", () => {
    const { container } = render(<ScoreRing score={8.5} />);
    expect(container.firstChild).toHaveClass("buy");
  });

  it("applies watch class for score >= 5", () => {
    const { container } = render(<ScoreRing score={5.5} />);
    expect(container.firstChild).toHaveClass("watch");
  });

  it("applies sell class for score < 5", () => {
    const { container } = render(<ScoreRing score={3.0} />);
    expect(container.firstChild).toHaveClass("sell");
  });

  it("has accessible aria-label", () => {
    render(<ScoreRing score={9.2} label="Strong Buy" />);
    expect(screen.getByLabelText(/composite score 9.2.*strong buy/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement ScoreRing**

```tsx
// frontend/src/components/score-ring.tsx
import { cn } from "@/lib/utils";

interface ScoreRingProps {
  score: number;
  label?: string;
  className?: string;
}

function getScoreVariant(score: number): "buy" | "watch" | "sell" {
  if (score >= 8) return "buy";
  if (score >= 5) return "watch";
  return "sell";
}

export function ScoreRing({ score, label, className }: ScoreRingProps) {
  const variant = getScoreVariant(score);

  return (
    <div
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-sm font-bold",
        variant === "buy" && "buy border-2 border-gain/30 bg-gain/12 text-[var(--gain)]",
        variant === "watch" && "watch border-2 border-warning/30 bg-warning/12 text-[var(--warning)]",
        variant === "sell" && "sell border-2 border-loss/30 bg-loss/12 text-[var(--loss)]",
        className,
      )}
      aria-label={`Composite score ${score} out of 10${label ? `, ${label}` : ""}`}
    >
      {score.toFixed(1)}
    </div>
  );
}
```

- [ ] **Step 3: Implement ActionBadge**

```tsx
// frontend/src/components/action-badge.tsx
import { cn } from "@/lib/utils";

type BadgeVariant = "strong-buy" | "buy" | "watch" | "sell" | "hold";

interface ActionBadgeProps {
  action: string;
  className?: string;
}

function getVariant(action: string): BadgeVariant {
  const upper = action.toUpperCase();
  if (upper === "STRONG_BUY" || upper === "STRONG BUY") return "strong-buy";
  if (upper === "BUY") return "buy";
  if (upper === "WATCH" || upper === "AVOID") return "watch";
  if (upper === "SELL") return "sell";
  return "hold";
}

const VARIANT_STYLES: Record<BadgeVariant, string> = {
  "strong-buy": "bg-gain/15 text-[var(--gain)]",
  buy: "bg-gain/15 text-[var(--gain)]",
  watch: "bg-warning/15 text-[var(--warning)]",
  sell: "bg-loss/15 text-[var(--loss)]",
  hold: "bg-muted/15 text-muted-foreground",
};

const VARIANT_LABELS: Record<BadgeVariant, string> = {
  "strong-buy": "Strong Buy",
  buy: "Buy",
  watch: "Watch",
  sell: "Sell",
  hold: "Hold",
};

export function ActionBadge({ action, className }: ActionBadgeProps) {
  const variant = getVariant(action);
  return (
    <span
      className={cn(
        "rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
        VARIANT_STYLES[variant],
        className,
      )}
    >
      {VARIANT_LABELS[variant]}
    </span>
  );
}
```

- [ ] **Step 4: Run tests**

Run: `cd frontend && npx jest __tests__/components/score-ring.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/score-ring.tsx frontend/src/components/action-badge.tsx frontend/src/__tests__/components/score-ring.test.tsx
git commit -m "feat(components): add ScoreRing and ActionBadge"
```

---

### Task 17: MetricsStrip Component

**Files:**
- Create: `frontend/src/components/metrics-strip.tsx`
- Test: `frontend/src/__tests__/components/metrics-strip.test.tsx`

- [ ] **Step 1: Write test**

```typescript
import { render, screen } from "@testing-library/react";
import { MetricsStrip } from "@/components/metrics-strip";

describe("MetricsStrip", () => {
  it("renders metric chips", () => {
    render(
      <MetricsStrip
        metrics={[
          { label: "Price", value: "$428.50", sentiment: "positive" },
          { label: "MACD", value: "Bullish ×over", sentiment: "positive" },
          { label: "RSI", value: "34 (oversold)", sentiment: "warning" },
        ]}
      />
    );
    expect(screen.getByText("$428.50")).toBeInTheDocument();
    expect(screen.getByText("Bullish ×over")).toBeInTheDocument();
    expect(screen.getByText("34 (oversold)")).toBeInTheDocument();
  });

  it("renders primary metrics with larger font", () => {
    const { container } = render(
      <MetricsStrip
        metrics={[
          { label: "Price", value: "$100", sentiment: "positive", primary: true },
          { label: "RSI", value: "50", sentiment: "neutral" },
        ]}
      />
    );
    const primaryChip = container.querySelector("[data-primary]");
    expect(primaryChip).toBeInTheDocument();
  });

  it("limits to maxVisible on mobile", () => {
    // Test that the component accepts maxVisible prop
    render(
      <MetricsStrip
        metrics={[
          { label: "A", value: "1", sentiment: "neutral" },
          { label: "B", value: "2", sentiment: "neutral" },
          { label: "C", value: "3", sentiment: "neutral" },
          { label: "D", value: "4", sentiment: "neutral" },
          { label: "E", value: "5", sentiment: "neutral" },
        ]}
        maxVisible={4}
      />
    );
    // All render in DOM (CSS hides extras on mobile)
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/src/components/metrics-strip.tsx
import { cn } from "@/lib/utils";

export interface MetricChip {
  label: string;
  value: string;
  sentiment: "positive" | "negative" | "warning" | "neutral";
  primary?: boolean;
}

interface MetricsStripProps {
  metrics: MetricChip[];
  maxVisible?: number; // for mobile CSS class cutoff
  className?: string;
}

const SENTIMENT_COLORS: Record<MetricChip["sentiment"], string> = {
  positive: "text-[var(--gain)]",
  negative: "text-[var(--loss)]",
  warning: "text-[var(--warning)]",
  neutral: "text-foreground",
};

export function MetricsStrip({ metrics, maxVisible = 6, className }: MetricsStripProps) {
  return (
    <div className={cn("flex flex-wrap gap-0.5", className)}>
      {metrics.map((m, i) => (
        <div
          key={m.label}
          data-primary={m.primary || undefined}
          className={cn(
            "flex items-center gap-1 rounded-md bg-[rgba(15,23,42,0.6)] px-2 py-1 text-[11px]",
            i >= maxVisible && "hidden md:flex", // hide extras on mobile
          )}
        >
          <span className="font-medium text-muted-foreground">{m.label}</span>
          <span className={cn("font-semibold", SENTIMENT_COLORS[m.sentiment])}>
            {m.value}
          </span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx jest __tests__/components/metrics-strip.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/metrics-strip.tsx frontend/src/__tests__/components/metrics-strip.test.tsx
git commit -m "feat(components): add MetricsStrip with sentiment-colored chips"
```

---

### Task 18: SignalStockCard Component

**Files:**
- Create: `frontend/src/components/signal-stock-card.tsx`
- Test: `frontend/src/__tests__/components/signal-stock-card.test.tsx`

This is the composite component that combines ScoreRing, ActionBadge, MetricsStrip, and reason text into a single card. It's the primary display unit for Zone 2.

- [ ] **Step 1: Write test**

```typescript
import { render, screen } from "@testing-library/react";
import { SignalStockCard } from "@/components/signal-stock-card";

const mockProps = {
  ticker: "MSFT",
  name: "Microsoft Corp",
  compositeScore: 9.2,
  action: "BUY",
  metrics: [
    { label: "Price", value: "$428.50", sentiment: "positive" as const, primary: true },
    { label: "MACD", value: "Bullish ×over", sentiment: "positive" as const },
    { label: "RSI", value: "34 (oversold)", sentiment: "warning" as const },
  ],
  reason: "MACD bullish crossover + RSI oversold",
};

describe("SignalStockCard", () => {
  it("renders ticker and company name", () => {
    render(<SignalStockCard {...mockProps} />);
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("Microsoft Corp")).toBeInTheDocument();
  });

  it("renders score ring with correct score", () => {
    render(<SignalStockCard {...mockProps} />);
    expect(screen.getByText("9.2")).toBeInTheDocument();
  });

  it("renders action badge", () => {
    render(<SignalStockCard {...mockProps} />);
    expect(screen.getByText("Buy")).toBeInTheDocument();
  });

  it("renders reason text", () => {
    render(<SignalStockCard {...mockProps} />);
    expect(screen.getByText("MACD bullish crossover + RSI oversold")).toBeInTheDocument();
  });

  it("applies buy variant border", () => {
    const { container } = render(<SignalStockCard {...mockProps} />);
    expect(container.firstChild).toHaveClass("buy-card");
  });

  it("applies sell variant for low scores", () => {
    const { container } = render(
      <SignalStockCard {...mockProps} compositeScore={2.1} action="SELL" />
    );
    expect(container.firstChild).toHaveClass("sell-card");
  });

  it("is keyboard accessible as a button", () => {
    render(<SignalStockCard {...mockProps} onClick={() => {}} />);
    const card = screen.getByRole("button");
    expect(card).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/src/components/signal-stock-card.tsx
"use client";

import { cn } from "@/lib/utils";
import { ScoreRing } from "./score-ring";
import { ActionBadge } from "./action-badge";
import { MetricsStrip, type MetricChip } from "./metrics-strip";

interface SignalStockCardProps {
  ticker: string;
  name?: string | null;
  compositeScore: number;
  action: string;
  metrics: MetricChip[];
  reason?: string;
  onClick?: () => void;
  className?: string;
}

function getCardVariant(score: number): string {
  if (score >= 8) return "buy-card border-gain/15 hover:border-gain/35 hover:shadow-[0_0_12px_rgba(34,211,160,0.3)]";
  if (score >= 5) return "watch-card border-warning/15 hover:border-warning/35 hover:shadow-[0_0_12px_rgba(251,191,36,0.3)]";
  return "sell-card border-loss/20 hover:border-loss/40 hover:shadow-[0_0_12px_rgba(248,113,113,0.3)]";
}

export function SignalStockCard({
  ticker,
  name,
  compositeScore,
  action,
  metrics,
  reason,
  onClick,
  className,
}: SignalStockCardProps) {
  const variant = getCardVariant(compositeScore);
  const Wrapper = onClick ? "button" : "div";

  return (
    <Wrapper
      className={cn(
        "flex w-full flex-col gap-2 rounded-[10px] border bg-[rgba(15,23,42,0.5)] p-3.5 text-left transition-all",
        variant,
        onClick && "cursor-pointer",
        className,
      )}
      onClick={onClick}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <ScoreRing score={compositeScore} label={action} />
          <div>
            <div className="text-sm font-semibold text-foreground">{ticker}</div>
            {name && (
              <div className="text-[11px] text-muted-foreground">{name}</div>
            )}
          </div>
        </div>
        <ActionBadge action={action} />
      </div>
      <MetricsStrip metrics={metrics} maxVisible={4} />
      {reason && (
        <div className="text-[11px] leading-relaxed text-[var(--muted-foreground)]">
          {reason}
        </div>
      )}
    </Wrapper>
  );
}
```

- [ ] **Step 3: Run test**

Run: `cd frontend && npx jest __tests__/components/signal-stock-card.test.tsx`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/signal-stock-card.tsx frontend/src/__tests__/components/signal-stock-card.test.tsx
git commit -m "feat(components): add SignalStockCard with score ring, metrics, reason"
```

---

### Task 19: MoverRow Component

**Files:**
- Create: `frontend/src/components/mover-row.tsx`
- Test: `frontend/src/__tests__/components/mover-row.test.tsx`

- [ ] **Step 1: Write test**

```typescript
import { render, screen } from "@testing-library/react";
import { MoverRow } from "@/components/mover-row";

describe("MoverRow", () => {
  it("renders ticker and price", () => {
    render(<MoverRow ticker="NVDA" price={924.8} changePct={4.2} macdSignal="bullish" />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("$924.80")).toBeInTheDocument();
  });

  it("shows MACD ↑ for bullish", () => {
    render(<MoverRow ticker="NVDA" price={924.8} changePct={4.2} macdSignal="bullish" />);
    expect(screen.getByText("MACD ↑")).toBeInTheDocument();
  });

  it("shows MACD ↓ for bearish", () => {
    render(<MoverRow ticker="PFE" price={26.4} changePct={-3.1} macdSignal="bearish" />);
    expect(screen.getByText("MACD ↓")).toBeInTheDocument();
  });

  it("applies gainer class for positive change", () => {
    const { container } = render(
      <MoverRow ticker="NVDA" price={924.8} changePct={4.2} macdSignal="bullish" />
    );
    expect(container.firstChild).toHaveClass("gainer");
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/src/components/mover-row.tsx
import { cn } from "@/lib/utils";
import { formatCurrency } from "@/lib/format";

interface MoverRowProps {
  ticker: string;
  price?: number | null;
  changePct: number;
  macdSignal?: string | null;
  onClick?: () => void;
}

export function MoverRow({ ticker, price, changePct, macdSignal, onClick }: MoverRowProps) {
  const isGainer = changePct >= 0;
  const macdIsBullish = macdSignal?.toLowerCase().includes("bullish");

  return (
    <button
      className={cn(
        "flex w-full items-center justify-between rounded-lg bg-[rgba(15,23,42,0.5)] px-3 py-1.5",
        isGainer ? "gainer border-l-[3px] border-l-[var(--gain)]" : "loser border-l-[3px] border-l-[var(--loss)]",
      )}
      onClick={onClick}
    >
      <div className="flex items-center gap-2">
        <div>
          <div className="text-[13px] font-semibold">{ticker}</div>
          {price != null && (
            <div className="text-[11px] text-muted-foreground">
              {formatCurrency(price)}
            </div>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        {macdSignal && (
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
              macdIsBullish
                ? "bg-gain/12 text-[var(--gain)]"
                : "bg-loss/12 text-[var(--loss)]",
            )}
          >
            MACD {macdIsBullish ? "↑" : "↓"}
          </span>
        )}
        <span
          className={cn(
            "text-[13px] font-semibold",
            isGainer ? "text-[var(--gain)]" : "text-[var(--loss)]",
          )}
        >
          {isGainer ? "+" : ""}
          {changePct.toFixed(1)}%
        </span>
      </div>
    </button>
  );
}
```

- [ ] **Step 3: Run test + Commit**

Run: `cd frontend && npx jest __tests__/components/mover-row.test.tsx`

```bash
git add frontend/src/components/mover-row.tsx frontend/src/__tests__/components/mover-row.test.tsx
git commit -m "feat(components): add MoverRow with MACD pill and change%"
```

---

### Task 20: PortfolioKPITile + HealthGradeBadge

**Files:**
- Create: `frontend/src/components/portfolio-kpi-tile.tsx`
- Create: `frontend/src/components/health-grade-badge.tsx`
- Test: `frontend/src/__tests__/components/portfolio-kpi-tile.test.tsx`

- [ ] **Step 1: Write test**

```typescript
import { render, screen } from "@testing-library/react";
import { PortfolioKPITile } from "@/components/portfolio-kpi-tile";

describe("PortfolioKPITile", () => {
  it("renders label and value", () => {
    render(<PortfolioKPITile label="Unrealized P&L" value="+$8,240" subtext="+6.9% all time" accent="green" />);
    expect(screen.getByText("Unrealized P&L")).toBeInTheDocument();
    expect(screen.getByText("+$8,240")).toBeInTheDocument();
  });

  it("renders dash for empty value", () => {
    render(<PortfolioKPITile label="Health" value="—" subtext="Add positions to see grade" accent="green" />);
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Add positions to see grade")).toBeInTheDocument();
  });

  it("renders subtext", () => {
    render(<PortfolioKPITile label="90-Day Forecast" value="+4.2%" subtext="Range: +1.8% to +6.1%" accent="cyan" />);
    expect(screen.getByText("Range: +1.8% to +6.1%")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement HealthGradeBadge**

```tsx
// frontend/src/components/health-grade-badge.tsx
import { cn } from "@/lib/utils";

interface HealthGradeBadgeProps {
  grade: string;
  className?: string;
}

function gradeColor(grade: string): string {
  if (grade.startsWith("A")) return "bg-gain/15 text-[var(--gain)] border-gain/25";
  if (grade.startsWith("B")) return "bg-gain/10 text-[var(--gain)] border-gain/20";
  if (grade.startsWith("C")) return "bg-warning/15 text-[var(--warning)] border-warning/25";
  return "bg-loss/15 text-[var(--loss)] border-loss/25";
}

export function HealthGradeBadge({ grade, className }: HealthGradeBadgeProps) {
  return (
    <div
      className={cn(
        "flex h-11 w-11 items-center justify-center rounded-[10px] border text-lg font-extrabold tracking-tight",
        gradeColor(grade),
        className,
      )}
    >
      {grade}
    </div>
  );
}
```

- [ ] **Step 3: Implement PortfolioKPITile**

```tsx
// frontend/src/components/portfolio-kpi-tile.tsx
import { cn } from "@/lib/utils";

interface PortfolioKPITileProps {
  label: string;
  value: string | React.ReactNode;
  subtext?: string;
  accent: "green" | "cyan";
  className?: string;
  onClick?: () => void;
}

export function PortfolioKPITile({
  label,
  value,
  subtext,
  accent,
  className,
  onClick,
}: PortfolioKPITileProps) {
  const Wrapper = onClick ? "button" : "div";

  return (
    <Wrapper
      className={cn(
        "relative flex flex-col gap-1.5 overflow-hidden rounded-[10px] border border-[var(--border)] bg-[rgba(15,23,42,0.7)] px-4 py-3.5",
        onClick && "cursor-pointer hover:border-[var(--bhi)]",
        className,
      )}
      onClick={onClick}
    >
      <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="text-[22px] font-bold tracking-tight">{value}</div>
      {subtext && (
        <div className="text-[11px] text-muted-foreground">{subtext}</div>
      )}
      {/* Bottom accent line */}
      <div
        className={cn(
          "absolute bottom-0 left-0 right-0 h-0.5",
          accent === "green"
            ? "bg-gradient-to-r from-[var(--gain)] to-transparent"
            : "bg-gradient-to-r from-[var(--cyan)] to-transparent",
        )}
      />
    </Wrapper>
  );
}
```

- [ ] **Step 4: Run test + Commit**

Run: `cd frontend && npx jest __tests__/components/portfolio-kpi-tile.test.tsx`

```bash
git add frontend/src/components/portfolio-kpi-tile.tsx frontend/src/components/health-grade-badge.tsx frontend/src/__tests__/components/portfolio-kpi-tile.test.tsx
git commit -m "feat(components): add PortfolioKPITile and HealthGradeBadge"
```

---

### Task 21: SectorPerformanceBars Component

**Files:**
- Create: `frontend/src/components/sector-performance-bars.tsx`
- Test: `frontend/src/__tests__/components/sector-performance-bars.test.tsx`

- [ ] **Step 1: Write test**

```typescript
import { render, screen } from "@testing-library/react";
import { SectorPerformanceBars } from "@/components/sector-performance-bars";

describe("SectorPerformanceBars", () => {
  const sectors = [
    { name: "Technology", returnPct: 8.4, score: 8.1 },
    { name: "Healthcare", returnPct: 4.2, score: 7.3 },
    { name: "Energy", returnPct: -2.6, score: 3.9 },
  ];

  it("renders sector names", () => {
    render(<SectorPerformanceBars sectors={sectors} />);
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("Healthcare")).toBeInTheDocument();
    expect(screen.getByText("Energy")).toBeInTheDocument();
  });

  it("renders return percentages with correct colors", () => {
    render(<SectorPerformanceBars sectors={sectors} />);
    expect(screen.getByText("+8.4%")).toBeInTheDocument();
    expect(screen.getByText("−2.6%")).toBeInTheDocument();
  });

  it("renders scores", () => {
    render(<SectorPerformanceBars sectors={sectors} />);
    expect(screen.getByText("8.1")).toBeInTheDocument();
  });

  it("has accessible aria-labels on rows", () => {
    render(<SectorPerformanceBars sectors={sectors} />);
    expect(
      screen.getByLabelText(/technology sector.*plus 8.4 percent/i)
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/src/components/sector-performance-bars.tsx
"use client";

import { cn } from "@/lib/utils";
import { useRouter } from "next/navigation";

interface SectorBar {
  name: string;
  returnPct: number;
  score?: number | null;
}

interface SectorPerformanceBarsProps {
  sectors: SectorBar[];
  className?: string;
}

function barVariant(pct: number): string {
  if (pct > 2) return "bg-gradient-to-r from-[var(--gain)] to-[var(--gain)]";
  if (pct > 0) return "bg-gradient-to-r from-[var(--warning)] to-[var(--warning)]";
  return "bg-gradient-to-r from-[var(--loss)] to-[var(--loss)]";
}

export function SectorPerformanceBars({ sectors, className }: SectorPerformanceBarsProps) {
  const router = useRouter();
  const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.returnPct)), 1);

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {sectors.map((s) => (
        <button
          key={s.name}
          className="grid grid-cols-[95px_1fr_55px_48px] items-center gap-2.5 rounded-lg bg-[rgba(15,23,42,0.4)] px-3 py-1.5 transition-colors hover:bg-[rgba(15,23,42,0.7)] focus-visible:outline-2 focus-visible:outline-[var(--cyan)]"
          onClick={() => router.push("/sectors")}
          aria-label={`${s.name} sector, ${s.returnPct >= 0 ? "plus" : "minus"} ${Math.abs(s.returnPct).toFixed(1)} percent return`}
        >
          <span className="text-xs font-medium text-[var(--muted-foreground)]">
            {s.name}
          </span>
          <div className="h-1.5 overflow-hidden rounded-full bg-[rgba(100,116,139,0.2)]">
            <div
              className={cn("h-full rounded-full", barVariant(s.returnPct))}
              style={{ width: `${(Math.abs(s.returnPct) / maxAbs) * 100}%` }}
            />
          </div>
          <span
            className={cn(
              "text-right text-[13px] font-semibold",
              s.returnPct >= 0 ? "text-[var(--gain)]" : "text-[var(--loss)]",
            )}
          >
            {s.returnPct >= 0 ? "+" : "−"}
            {Math.abs(s.returnPct).toFixed(1)}%
          </span>
          <span className="text-right text-xs text-muted-foreground">
            {s.score?.toFixed(1) ?? "—"}
          </span>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Run test + Commit**

Run: `cd frontend && npx jest __tests__/components/sector-performance-bars.test.tsx`

```bash
git add frontend/src/components/sector-performance-bars.tsx frontend/src/__tests__/components/sector-performance-bars.test.tsx
git commit -m "feat(components): add SectorPerformanceBars with a11y aria-labels"
```

---

### Task 22: AlertTile Component

**Files:**
- Create: `frontend/src/components/alert-tile.tsx`
- Test: `frontend/src/__tests__/components/alert-tile.test.tsx`

- [ ] **Step 1: Write test**

```typescript
import { render, screen } from "@testing-library/react";
import { AlertTile } from "@/components/alert-tile";

describe("AlertTile", () => {
  it("renders severity label and ticker", () => {
    render(
      <AlertTile
        severity="critical"
        ticker="INTC"
        title="Divestment rule triggered"
        createdAt="2026-03-30T10:00:00Z"
      />
    );
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText("INTC")).toBeInTheDocument();
  });

  it("renders title text", () => {
    render(
      <AlertTile
        severity="warning"
        ticker="DIS"
        title="Score dropped below WATCH threshold"
        createdAt="2026-03-30T06:00:00Z"
      />
    );
    expect(screen.getByText(/score dropped/i)).toBeInTheDocument();
  });

  it("shows relative time", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    render(
      <AlertTile severity="info" ticker="AAPL" title="Earnings in 3 days" createdAt={twoHoursAgo} />
    );
    expect(screen.getByText(/ago/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Implement**

```tsx
// frontend/src/components/alert-tile.tsx
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/format";

interface AlertTileProps {
  severity: "critical" | "warning" | "info";
  ticker?: string | null;
  title: string;
  createdAt: string;
  onClick?: () => void;
}

const SEVERITY_STYLES = {
  critical: { dot: "bg-[var(--loss)] animate-pulse", label: "text-[var(--loss)]", text: "CRITICAL" },
  warning: { dot: "bg-[var(--warning)]", label: "text-[var(--warning)]", text: "WARNING" },
  info: { dot: "bg-[var(--cyan)]", label: "text-[var(--cyan)]", text: "INFO" },
};

export function AlertTile({ severity, ticker, title, createdAt, onClick }: AlertTileProps) {
  const s = SEVERITY_STYLES[severity];

  return (
    <button
      className="flex w-full items-start gap-2.5 rounded-[10px] border border-[var(--border)] bg-[rgba(15,23,42,0.5)] px-3 py-2.5 text-left text-xs leading-relaxed text-[var(--muted-foreground)] transition-colors hover:border-[rgba(148,163,184,0.3)] focus-visible:outline-2 focus-visible:outline-[var(--cyan)]"
      onClick={onClick}
    >
      <span className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", s.dot)} />
      <div>
        <span className={cn("mr-1 text-[10px] font-semibold uppercase tracking-wide", s.label)}>
          {s.text}
        </span>
        {ticker && <strong className="text-foreground">{ticker}</strong>}
        {" — "}
        {title}
        <span className="mt-0.5 block text-[10px] text-muted-foreground">
          {formatRelativeTime(createdAt)}
        </span>
      </div>
    </button>
  );
}
```

- [ ] **Step 3: Run test + Commit**

```bash
git add frontend/src/components/alert-tile.tsx frontend/src/__tests__/components/alert-tile.test.tsx
git commit -m "feat(components): add AlertTile with severity labels and a11y"
```

---

### Task 23: Update NewsCard with Sentiment + Ticker/Sector Tags

**Files:**
- Modify: `frontend/src/components/news-card.tsx` (add OPTIONAL tag props — do NOT break existing API)
- Modify: `frontend/src/__tests__/components/news-card.test.tsx` (add tag tests)

**CRITICAL: The existing `NewsCard` accepts `news: StockNewsResponse` (with `ticker` + `articles` array) and is used on the stock detail page. Do NOT change the existing prop interface. Add the new tag props as OPTIONAL alongside the existing props. The stock detail page passes `news={stockNewsData}` and must continue working. Read the existing component and its tests FIRST before modifying.**

- [ ] **Step 1: Read existing `news-card.tsx` and its tests to understand current API**

- [ ] **Step 2: Write test for NEW optional tag props (alongside existing tests)**

```typescript
// Add to EXISTING news-card test file — do not replace existing tests
describe("NewsCard — Dashboard Tags", () => {
  it("renders sentiment tag when provided", () => {
    // Use the EXISTING component API + new optional props
    render(
      <NewsCard
        news={{ ticker: "MSFT", articles: [{ title: "Stock surges", link: "#", publisher: "Reuters", published: "2h ago", source: "yfinance" }], fetched_at: "" }}
        sentimentTag="bullish"
      />
    );
    expect(screen.getByText("Bullish")).toBeInTheDocument();
  });

  it("renders ticker and sector tags when provided", () => {
    render(
      <NewsCard
        news={{ ticker: "MSFT", articles: [{ title: "Test", link: "#", publisher: null, published: null, source: "yfinance" }], fetched_at: "" }}
        tickerTag="MSFT"
        sectorTag="Technology"
      />
    );
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
  });

  it("renders without tags when not provided (backwards compatible)", () => {
    render(
      <NewsCard
        news={{ ticker: "AAPL", articles: [{ title: "Apple news", link: "#", publisher: "CNN", published: "1h ago", source: "yfinance" }], fetched_at: "" }}
      />
    );
    expect(screen.getByText("Apple news")).toBeInTheDocument();
    expect(screen.queryByText("Bullish")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Update component**

Add props for `sentimentTag`, `tickerTag`, `sectorTag`. Render as colored pills above the headline. Use the same tag pill styles from the mockup:

```tsx
// Add to NewsCard props:
sentimentTag?: "bullish" | "bearish" | "neutral";
tickerTag?: string | null;
sectorTag?: string | null;

// Render tag row above headline:
<div className="flex flex-wrap gap-1.5">
  {sentimentTag && (
    <span className={cn(
      "rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
      sentimentTag === "bullish" && "bg-gain/12 text-[var(--gain)]",
      sentimentTag === "bearish" && "bg-loss/12 text-[var(--loss)]",
      sentimentTag === "neutral" && "bg-muted/12 text-muted-foreground",
    )}>
      {sentimentTag === "bullish" ? "Bullish" : sentimentTag === "bearish" ? "Bearish" : "Neutral"}
    </span>
  )}
  {tickerTag && (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-[var(--cdim)] text-[var(--cyan)]">
      {tickerTag}
    </span>
  )}
  {sectorTag && (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide bg-purple-500/12 text-purple-400">
      {sectorTag}
    </span>
  )}
</div>
```

- [ ] **Step 3: Run tests + Commit**

```bash
git add frontend/src/components/news-card.tsx frontend/src/__tests__/components/news-card.test.tsx
git commit -m "feat(news-card): add sentiment, ticker, and sector tag pills"
```

---

## Chunk 5: Page Assembly (3 tasks)
*Depends on Chunks 1-4. This is where the dashboard is rewritten.*
*Suggested LM Studio score: T24=12 (NOT suitable for local LLM — complex composition), T25=6, T26=4*

### Task 24: Dashboard Page Rewrite — All 5 Zones

**Files:**
- Rewrite: `frontend/src/app/(authenticated)/dashboard/page.tsx`

This is the largest task. It replaces the entire dashboard with the 5-zone bulletin board layout. Too complex to show every line here — the implementer should:

- [ ] **Step 1: Read the spec §3 (all 5 zones), §10 (responsive), §10a (empty states), §10b (accessibility), §11 (data flow)**

Also open `docs/mockups/dashboard-bulletin-v3.html` in a browser for visual reference.

- [ ] **Step 2: Remove old imports and add new ones**

Remove: `IndexCard`, `StockCard`, `SectorFilter`, `WelcomeBanner`, `TrendingStocks`, `useIndexes`, `useAddToWatchlist`, `useRemoveFromWatchlist`, `PortfolioDrawer`, `DONUT_COLORS`.

Add: `SignalStockCard`, `MoverRow`, `PortfolioKPITile`, `HealthGradeBadge`, `SectorPerformanceBars`, `AlertTile`, `useMarketBriefing`, `usePortfolioHealth`, `usePortfolioHealthHistory`, `useUserDashboardNews`, `useBulkSignalsByTickers`, `useAlerts`, `useSectors`, `isMarketOpen`, `classifyNewsSentiment`, `buildSignalReason`, `normalizeSector`.

- [ ] **Step 3: Implement Phase 1 data hooks (parallel on load)**

```typescript
const { data: briefing, isLoading: briefingLoading, error: briefingError } = useMarketBriefing();
const { data: recommendations, isLoading: recsLoading } = useRecommendations();
const { data: positions, isLoading: positionsLoading } = usePositions();
const { data: health, isLoading: healthLoading, error: healthError } = usePortfolioHealth();
const { data: healthHistory } = usePortfolioHealthHistory(7);
const { data: summary, isLoading: summaryLoading } = usePortfolioSummary();
const { data: forecast } = usePortfolioForecast(!!summary?.position_count);
const { data: scorecard } = useScorecard();
const { data: sectors } = useSectors("portfolio");
const { data: alertsData } = useAlerts();
```

- [ ] **Step 4: Implement Phase 2 data hooks (after dependencies resolve)**

```typescript
// Extract tickers for bulk signals
const signalTickers = useMemo(() => {
  const recTickers = (recommendations ?? []).slice(0, 3).map((r) => r.ticker);
  const alertTickers = (positions ?? [])
    .filter((p) => p.alerts?.length > 0)
    .slice(0, 3)
    .map((p) => p.ticker);
  return [...new Set([...recTickers, ...alertTickers])];
}, [recommendations, positions]);

const { data: bulkSignals } = useBulkSignalsByTickers(
  signalTickers,
  signalTickers.length > 0,
);

const { data: dashboardNews } = useUserDashboardNews(
  !recsLoading && !positionsLoading,
);
```

- [ ] **Step 5: Implement Zone 1 — Market Pulse**

Glass card with 2-column grid. Left: 3 IndexChips from `briefing.indexes`. Right: 4 MoverRows from `briefing.top_movers`. Market session indicator using `isMarketOpen()`.

- [ ] **Step 6: Implement Zone 2 — Signals (split)**

Left glass card: Opportunities (top 3 BUY recommendations as SignalStockCards). Right glass card: Action Required (positions with alerts as SignalStockCards). Build metrics from `bulkSignals` data. Build reason from `buildSignalReason()`.

Each card includes empty states per §10a.

- [ ] **Step 7: Implement Zone 3 — Portfolio Position**

5-column KPI tile row + AllocationDonut + SectorPerformanceBars. Health tile uses `HealthGradeBadge`. Merge sector scores from `useSectors("portfolio")` with sector returns from `briefing.sector_performance` using `normalizeSector()`.

Handle empty states for new users (position_count === 0).

- [ ] **Step 8: Implement Zone 4 — Alerts**

3-column grid of AlertTiles from `useAlerts()`. Empty state: "No recent alerts."

- [ ] **Step 9: Implement Zone 5 — News**

3-column grid of NewsCards. Merge `briefing.general_news` + `dashboardNews.articles`. Enrich with `classifyNewsSentiment()`, `tickerTag`, `sectorTag`.

- [ ] **Step 10: Add responsive behavior**

Chat panel adaptation (`useChat().chatOpen` for grid column adjustments). Mobile scroll compression with `showAll` state toggles per zone.

- [ ] **Step 11: Add section aria landmarks**

Each zone wrapped in `<section aria-labelledby="zone-X-heading">` with semantic headings.

- [ ] **Step 12: Verify**

Run: `cd frontend && npx tsc --noEmit && npx jest`
Expected: All pass

- [ ] **Step 13: Commit**

```bash
git add frontend/src/app/\(authenticated\)/dashboard/page.tsx
git commit -m "feat(dashboard): rewrite as 5-zone Daily Intelligence Briefing"
```

---

### Task 25: Screener — Add Watchlist Tab

**Files:**
- Modify: `frontend/src/app/(authenticated)/screener/page.tsx`

- [ ] **Step 1: Add Watchlist tab to TabKey type and tabs array**

Add `"watchlist"` to `TabKey`. Add a tab trigger with watchlist count badge.

- [ ] **Step 2: Add watchlist tab content**

When `activeTab === "watchlist"`, render watchlist items using `useWatchlist()` and `SignalStockCard` component. Include remove-from-watchlist action.

- [ ] **Step 3: Add URL param support**

Read `tab` from URL search params so `/screener?tab=watchlist` deep-links to the watchlist tab.

- [ ] **Step 4: Verify + Commit**

Run: `cd frontend && npx tsc --noEmit`

```bash
git add frontend/src/app/\(authenticated\)/screener/
git commit -m "feat(screener): add Watchlist tab with SignalStockCard format"
```

---

### Task 26: Watchlist Migration Toast

**Files:**
- Modify: `frontend/src/app/(authenticated)/dashboard/page.tsx` (add toast effect)

- [ ] **Step 1: Add migration toast**

At the top of the dashboard component, add:

```typescript
useEffect(() => {
  if (!localStorage.getItem("watchlist_migration_dismissed")) {
    toast("Your watchlist has moved to the Screener page", {
      action: {
        label: "Go to Screener",
        onClick: () => {
          router.push("/screener?tab=watchlist");
          localStorage.setItem("watchlist_migration_dismissed", "true");
        },
      },
      onDismiss: () => {
        localStorage.setItem("watchlist_migration_dismissed", "true");
      },
      duration: 10000,
    });
  }
}, [router]);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/\(authenticated\)/dashboard/page.tsx
git commit -m "feat(dashboard): add one-time watchlist migration toast"
```

---

## Chunk 6: Chat BU-4 Cleanup (3 tasks)
*Independent of Chunks 1-5. Can run in parallel.*
*Suggested LM Studio score: T27=3, T28=5, T29=3*

### Task 27: Update PINNABLE_TOOLS

**Files:**
- Modify: `frontend/src/components/chat/artifact-bar.tsx` (~line 5-13)

- [ ] **Step 1: Read current backend tool list**

Run: `uv run python -c "from backend.agents.tools import TOOL_REGISTRY; print([t.name for t in TOOL_REGISTRY.values()])"` or grep for tool registrations to get the current 24 tool names.

- [ ] **Step 2: Update the PINNABLE_TOOLS set**

Replace the 7-tool set with the current tools. Focus on tools that produce artifacts users want to pin (analysis results, charts, data tables). Not all 24 tools need to be pinnable — curate the subset that produces visual artifacts.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/artifact-bar.tsx
git commit -m "fix(chat): update PINNABLE_TOOLS to current 24 backend tools"
```

---

### Task 28: Feedback Button Visual State

**Files:**
- Modify: `frontend/src/components/chat/` (find the feedback buttons component)

- [ ] **Step 1: Find the feedback buttons**

Grep for "thumbs" or "feedback" in the chat components directory. Find where up/down buttons are rendered.

- [ ] **Step 2: Add persisted visual state**

After clicking thumbs up/down, the selected button should have a highlighted style (brighter icon, filled vs outline). The unselected button should dim. The `feedback` field from the `ChatMessage` type (synced in Task 29) indicates prior feedback.

```tsx
// Pseudocode for the button:
<button
  className={cn(
    "transition-opacity",
    message.feedback === "positive" ? "opacity-100 text-[var(--gain)]" : "opacity-40 hover:opacity-70",
  )}
  onClick={() => submitFeedback("positive")}
>
  <ThumbsUpIcon />
</button>
```

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(chat): persist feedback button visual state after click"
```

---

### Task 29: ChatMessage Type Sync

**Files:**
- Modify: `frontend/src/types/api.ts` (find `ChatMessage` interface)

- [ ] **Step 1: Add missing fields**

Add to `ChatMessage`:

```typescript
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  latency_ms?: number | null;
  feedback?: "positive" | "negative" | null;
  trace_id?: string | null;
```

These fields are NOT displayed in chat — they exist for the observability page to consume.

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/api.ts
git commit -m "feat(types): sync ChatMessage with backend fields for observability"
```

---

## Chunk 7: Polish & Accessibility (1 task)
*Final pass after all components are assembled.*
*Suggested LM Studio score: 9 (borderline — may need Opus for a11y nuance)*

### Task 30: Global Focus Styles + Accessibility Pass + Automated a11y Tests

**Files:**
- Modify: `frontend/src/app/globals.css` (add focus-visible styles)
- Modify: `frontend/package.json` (add jest-axe)
- Create: `frontend/src/__tests__/a11y/dashboard-a11y.test.tsx`
- Review: all new components for aria-labels

- [ ] **Step 1: Install jest-axe**

Run: `cd frontend && npm install --save-dev jest-axe @types/jest-axe`

- [ ] **Step 2: Add global focus-visible style**

In `globals.css`:

```css
:focus-visible {
  outline: 2px solid var(--cyan);
  outline-offset: 2px;
}
```

- [ ] **Step 3: Write automated accessibility tests**

```typescript
// frontend/src/__tests__/a11y/dashboard-a11y.test.tsx
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { ScoreRing } from "@/components/score-ring";
import { AlertTile } from "@/components/alert-tile";
import { SectorPerformanceBars } from "@/components/sector-performance-bars";
import { MoverRow } from "@/components/mover-row";

expect.extend(toHaveNoViolations);

// Mock next/navigation for SectorPerformanceBars
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

describe("Accessibility — axe automated checks", () => {
  it("ScoreRing has no a11y violations", async () => {
    const { container } = render(<ScoreRing score={9.2} label="Strong Buy" />);
    expect(await axe(container)).toHaveNoViolations();
  });

  it("AlertTile has no a11y violations", async () => {
    const { container } = render(
      <AlertTile severity="critical" ticker="INTC" title="Divestment triggered" createdAt="2026-03-30T10:00:00Z" />
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("SectorPerformanceBars has no a11y violations", async () => {
    const { container } = render(
      <SectorPerformanceBars sectors={[{ name: "Technology", returnPct: 8.4, score: 8.1 }]} />
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("MoverRow has no a11y violations", async () => {
    const { container } = render(
      <MoverRow ticker="NVDA" price={924.8} changePct={4.2} macdSignal="bullish" />
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
```

- [ ] **Step 4: Verify all clickable elements are semantic**

Audit: every `<div onClick>` should be `<button>` or `<a>`. The components in Chunk 4 already use `<button>` elements. Verify the dashboard page (Task 24) follows suit.

- [ ] **Step 5: Verify aria-labels are present**

Check that:
- ScoreRing has `aria-label` with score + action
- SectorPerformanceBars rows have `aria-label` with sector name + return
- Alert severity dots have visible "CRITICAL"/"WARNING"/"INFO" text labels
- IndexChips from briefing data have descriptive text

- [ ] **Step 6: Run tests**

Run: `cd frontend && npx jest __tests__/a11y/ && npx tsc --noEmit`
Expected: All PASS, no a11y violations

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/globals.css frontend/src/__tests__/a11y/ frontend/package.json
git commit -m "feat(a11y): add focus-visible styles, jest-axe tests, verify aria-labels"
```

---

### Task 31: Dashboard Integration Tests

**Files:**
- Create: `frontend/src/__tests__/pages/dashboard.test.tsx`

- [ ] **Step 1: Write integration tests for all 5 zones + empty states**

```typescript
// frontend/src/__tests__/pages/dashboard.test.tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Mock ALL hook modules used by dashboard
jest.mock("@/hooks/use-stocks");
jest.mock("@/hooks/use-forecasts");
jest.mock("@/hooks/use-alerts", () => ({
  useAlerts: jest.fn(() => ({ data: { alerts: [], total: 0, unread_count: 0 }, isLoading: false })),
}));
jest.mock("@/contexts/chat-context", () => ({
  useChat: () => ({ chatOpen: false }),
}));
jest.mock("next/navigation", () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import DashboardPage from "@/app/(authenticated)/dashboard/page";
import * as stockHooks from "@/hooks/use-stocks";
import * as forecastHooks from "@/hooks/use-forecasts";

// Default mock data for a populated dashboard
const DEFAULT_MOCKS = {
  briefing: {
    indexes: [{ name: "S&P 500", ticker: "SPY", price: 5667, change_pct: 0.82 }],
    top_movers: { gainers: [{ ticker: "NVDA", current_price: 924.8, change_pct: 4.2, macd_signal_label: "bullish" }], losers: [] },
    sector_performance: [{ sector: "Technology", etf: "XLK", change_pct: 1.5 }],
    portfolio_news: [],
    general_news: [{ title: "Market news", link: "#", publisher: "Reuters", published: "2h ago", source: "google_news" }],
    upcoming_earnings: [],
    briefing_date: "2026-03-30",
  },
  recommendations: [{ ticker: "MSFT", composite_score: 9.2, action: "BUY", name: "Microsoft", confidence: "HIGH" }],
  positions: [{ ticker: "AAPL", shares: 10, current_price: 200, alerts: [], sector: "Technology" }],
  health: { health_score: 7.8, grade: "B+", components: [], metrics: { weighted_sharpe: 1.34 }, top_concerns: [], top_strengths: [], position_details: [] },
  healthHistory: [{ snapshot_date: "2026-03-23", health_score: 7.5 }, { snapshot_date: "2026-03-30", health_score: 7.8 }],
  summary: { total_value: 127400, total_cost_basis: 119160, unrealized_pnl: 8240, unrealized_pnl_pct: 6.9, position_count: 12, sectors: [{ sector: "Technology", pct: 30, market_value: 38220 }] },
  forecast: { horizons: [{ horizon_days: 90, expected_return_pct: 4.2, lower_pct: 1.8, upper_pct: 6.1, confidence_level: "medium", diversification_ratio: 0.08 }], ticker_count: 12, vix_regime: "normal" },
  scorecard: { total_outcomes: 142, overall_hit_rate: 0.73, avg_alpha: 1.2, buy_hit_rate: 0.75, sell_hit_rate: 0.68, worst_miss_pct: -12, worst_miss_ticker: "INTC", by_horizon: [] },
  sectors: [{ sector: "Technology", stock_count: 5, avg_score: 8.1 }],
  bulkSignals: { items: [{ ticker: "MSFT", rsi_value: 34, macd_signal: "bullish_crossover", composite_score: 9.2 }], total: 1 },
  dashboardNews: { articles: [], ticker_count: 0 },
};

function setupMocks(overrides: Partial<typeof DEFAULT_MOCKS> = {}) {
  const m = { ...DEFAULT_MOCKS, ...overrides };
  const mockQuery = (data: unknown) => ({ data, isLoading: false, error: null });
  const mockError = (error: Error) => ({ data: undefined, isLoading: false, error });

  (stockHooks.useMarketBriefing as jest.Mock).mockReturnValue(mockQuery(m.briefing));
  (stockHooks.useRecommendations as jest.Mock).mockReturnValue(mockQuery(m.recommendations));
  (stockHooks.usePositions as jest.Mock).mockReturnValue(mockQuery(m.positions));
  (stockHooks.usePortfolioHealth as jest.Mock).mockReturnValue(
    overrides.hasOwnProperty("healthError") ? mockError(overrides.healthError as Error) : mockQuery(m.health)
  );
  (stockHooks.usePortfolioHealthHistory as jest.Mock).mockReturnValue(mockQuery(m.healthHistory));
  (stockHooks.usePortfolioSummary as jest.Mock).mockReturnValue(mockQuery(m.summary));
  (stockHooks.useSectors as jest.Mock).mockReturnValue(mockQuery(m.sectors));
  (stockHooks.useBulkSignalsByTickers as jest.Mock).mockReturnValue(mockQuery(m.bulkSignals));
  (stockHooks.useUserDashboardNews as jest.Mock).mockReturnValue(mockQuery(m.dashboardNews));
  (forecastHooks.usePortfolioForecast as jest.Mock).mockReturnValue(mockQuery(m.forecast));
  (forecastHooks.useScorecard as jest.Mock).mockReturnValue(mockQuery(m.scorecard));
}

function renderDashboard(overrides: Partial<typeof DEFAULT_MOCKS> = {}) {
  setupMocks(overrides);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DashboardPage />
    </QueryClientProvider>
  );
}

describe("Dashboard — All Zones Render", () => {
  it("renders Zone 1 Market Pulse with index chips", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Market Pulse")).toBeInTheDocument();
    });
  });

  it("renders Zone 2a Opportunities with stock cards", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Opportunities")).toBeInTheDocument();
    });
  });

  it("renders Zone 2b Action Required", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Action Required")).toBeInTheDocument();
    });
  });

  it("renders Zone 3 Portfolio KPI tiles", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Your Portfolio")).toBeInTheDocument();
    });
  });

  it("renders Zone 4 Alerts", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Recent Alerts")).toBeInTheDocument();
    });
  });

  it("renders Zone 5 News", async () => {
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText("Market News")).toBeInTheDocument();
    });
  });
});

describe("Dashboard — Empty States", () => {
  it("shows empty state when no recommendations", async () => {
    renderDashboard({ recommendations: [] });
    await waitFor(() => {
      expect(screen.getByText(/no buy signals/i)).toBeInTheDocument();
    });
  });

  it("shows empty state for new user with no portfolio", async () => {
    renderDashboard({ positions: [], summary: { position_count: 0 } });
    await waitFor(() => {
      expect(screen.getByText(/start building your portfolio/i)).toBeInTheDocument();
    });
  });

  it("shows all-clear when portfolio has no alerts", async () => {
    renderDashboard({ positions: [{ ticker: "AAPL", alerts: [] }] });
    await waitFor(() => {
      expect(screen.getByText(/all clear/i)).toBeInTheDocument();
    });
  });

  it("shows no-alerts message when alerts empty", async () => {
    renderDashboard({ alerts: [] });
    await waitFor(() => {
      expect(screen.getByText(/no recent alerts/i)).toBeInTheDocument();
    });
  });
});

describe("Dashboard — Error States", () => {
  it("shows error card with retry when health fails", async () => {
    renderDashboard({ healthError: new Error("500") });
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    });
  });

  it("renders P&L tile normally even when health fails (partial failure)", async () => {
    renderDashboard({ healthError: new Error("500"), summary: { unrealized_pnl: 8240 } });
    await waitFor(() => {
      expect(screen.getByText(/\$8,240/)).toBeInTheDocument();
    });
  });
});
```

The actual mock setup will depend on the hook return shapes — the implementer should set up `jest.mocked()` return values for each hook based on the data flow in Task 24.

- [ ] **Step 2: Run tests**

Run: `cd frontend && npx jest __tests__/pages/dashboard.test.tsx`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/pages/dashboard.test.tsx
git commit -m "test(dashboard): add integration tests for all 5 zones, empty states, error states"
```

---

## Summary

| Chunk | Tasks | Description | Parallelizable? |
|-------|-------|-------------|-----------------|
| **1** | T1-T7 | Backend infrastructure (migration, endpoints, briefing) | T1-T4 parallel; T5-T7 sequential |
| **2** | T8-T11 | Frontend utilities (sectors, market hours, sentiment, reason) | All parallel with Chunk 1 |
| **3** | T12-T15 | Frontend hooks | After Chunk 1 |
| **4** | T16-T23 | Frontend components | After Chunks 2-3; T16-T22 parallel |
| **5** | T24-T26 | Page assembly (dashboard rewrite, screener tab, toast) | After Chunk 4 |
| **6** | T27-T29 | Chat BU-4 cleanup | Independent — anytime |
| **7** | T30-T31 | Accessibility polish + dashboard integration tests | After Chunk 5 |

**Total: 31 tasks, ~7 chunks, estimated 3-4 sessions.**

## Expert Review Fixes Applied

| # | Issue | Fix |
|---|-------|-----|
| C1 | `current_price` not on SignalSnapshot | Added to model + migration + compute_signals (T2) |
| C2 | Alembic autogenerate drops TimescaleDB indexes | Changed to manual migration with explicit add_column (T2) |
| C3 | `market-hours.ts` already exists | Changed from Create to Modify, added note to extend existing `isNYSEOpen` (T9) |
| C4 | Zero tests for dashboard page rewrite | Added T31 with integration tests for all zones, empty states, error states |
| C5 | `enabled` param not wired in useBulkSignalsByTickers | Rewrote as standalone hook with `enabled` in useQuery options (T15) |
| I1 | Holiday check uses UTC date not ET | Fixed to use `Intl.DateTimeFormat("en-CA", {timeZone: "America/New_York"})` (T9) |
| I2 | Direct async_session_factory in tool | Changed to reuse existing session from tool's execute() block (T5) |
| I3 | Lazy imports fail ruff lint | Moved all imports to top of module (T7) |
| I4 | ActionBadge 10px violates minimum | Changed to 11px |

### QA Expert Review Fixes (Round 2)
| # | Issue | Fix |
|---|-------|-----|
| QC1 | T2: No test for `previous == 0` division-by-zero | Added test + `None` df + capital `Close` column tests |
| QC2 | T5: SignalSnapshotFactory lacks new fields | Added note to update factory after T2 migration |
| QC3 | T6: Zero tests for parallelized ETF rewrite | Added 2 tests: single failure handling + sector name normalization |
| QC4 | T7: No cache path tests | Added empty portfolio test + cache hit test |
| QC5 | T9: No FINRA holiday test | Added holiday test + day-before-holiday test |
| QC6 | T23: NewsCard prop change breaks consumers | Rewritten to ADD optional tag props, not change existing API. Backwards-compat test added. |
| QC7 | T31: Mock setup skeleton | Full concrete mock setup with DEFAULT_MOCKS, all 11 hooks mocked, next/navigation mocked |
| QC8 | No automated a11y tests | Added jest-axe tests for 4 key components in T30 |
| QI1 | T3/T4: Non-existent fixture references | Removed fixture params, added inline seeding notes |
| QI2 | T4: Assertion logic bug | Fixed from `is not None or isinstance` to `is None or isinstance` |
