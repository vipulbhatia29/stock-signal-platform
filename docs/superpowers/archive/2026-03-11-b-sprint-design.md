# B-Sprint Design Spec
**Date:** 2026-03-11
**Branch:** `feat/phase-3`
**Status:** Approved — ready for implementation planning

## Overview

Pre-Phase 3 backlog cleanup sprint. 4 items scoped, delivered feature-by-feature (vertical slices). Each item is independently shippable and testable.

**Deferred / promoted:**
- B1 (refresh token rotation) → deferred to a future security sprint
- B6 (staleness enforcement + auto-refresh) → promoted to Phase 3 proper
- B8 (acknowledge endpoint) → promoted to Phase 3 (no UI consumer yet)

---

## Sprint Order

1. **Migration 003** — B3 + B4 + B5 (backend only, foundation)
2. **B7** — Sharpe ratio filter (backend only, one query param)
3. **B2** — Watchlist current price + freshness UI (full stack, most visual)

---

## Item 1: Migration 003 (B3 + B4 + B5)

### B3 — StockIndexMembership: add `removed_date`

**Problem:** When a stock leaves an index, the membership row is currently deleted. History is lost.

**Change:** Add `removed_date: DateTime(timezone=True) | None` (nullable) to `StockIndexMembership`.

**Behaviour:**
- Sync scripts set `removed_date = now()` instead of deleting the row when a stock leaves an index
- Query for current members: `WHERE removed_date IS NULL`
- Query for historical membership: full table scan (no filter)

**Files changed:**
- `backend/models/stock.py` — add `removed_date` to `StockIndexMembership`
- `backend/migrations/versions/003_*.py` — `ADD COLUMN removed_date TIMESTAMPTZ`
- `scripts/sync_sp500.py` — update stale-stock logic to set `removed_date` instead of DELETE

### B4 — StockIndex: add `last_synced_at`

**Problem:** No way to know when index data was last refreshed.

**Change:** Add `last_synced_at: DateTime(timezone=True) | None` (nullable) to `StockIndex`.

**Behaviour:**
- Sync scripts set `last_synced_at = now()` at the end of a successful sync run
- Exposed via `GET /api/v1/indexes` response (already exists)

**Files changed:**
- `backend/models/stock.py` — add `last_synced_at` to `StockIndex`
- `backend/migrations/versions/003_*.py` — `ADD COLUMN last_synced_at TIMESTAMPTZ`
- `backend/schemas/stock.py` — add `last_synced_at` to index response schema
- `scripts/sync_sp500.py` — set `last_synced_at` after successful sync

### B5 — Remove `is_in_universe` from Stock

**Problem:** `Stock.is_in_universe` boolean is made redundant by the `StockIndexMembership` table (Phase 2). The field coexists with the new system and sends conflicting signals.

**Change:** Full clean break — drop column from DB, sweep all references.

**Reference sweep:**

| File | Change |
|---|---|
| `backend/models/stock.py` | Remove `is_in_universe` mapped column |
| `backend/schemas/stock.py` | Remove `is_in_universe` from `StockResponse` |
| `backend/tools/market_data.py` | Remove `is_in_universe=False` from `ensure_stock_exists()` |
| `frontend/src/types/api.ts` | Remove `is_in_universe: boolean` from `Stock` type |
| `scripts/sync_sp500.py` | Remove all `is_in_universe` reads/writes; use index membership exclusively |
| `scripts/seed_prices.py` | Replace `Stock.is_in_universe.is_(True)` filter with index membership join |
| `tests/conftest.py` | Remove `is_in_universe = True` from `StockFactory` |
| `docs/data-architecture.md` | Remove from entity diagram and index table |
| `backend/migrations/versions/003_*.py` | `DROP COLUMN is_in_universe` |

**Migration safety:** Column has a `server_default=false` — dropping is safe, no data needed.

---

## Item 2: B7 — Sharpe Ratio Filter

### Problem
`GET /api/v1/stocks/signals/bulk` supports sorting by `sharpe_ratio` but has no filter — users can't screen for stocks above a minimum Sharpe threshold.

### Change
Add `sharpe_min: float | None = None` query parameter to the bulk signals endpoint.

### Behaviour
- Applied as `WHERE sharpe_ratio >= :sharpe_min` before pagination
- `sharpe_min=None` (omitted) → no filter applied (backwards compatible)
- Works in combination with all existing filters (`sector`, `sort`, `order`, `limit`, `offset`)
- Screener UI already passes query params through — no frontend changes needed

### Files changed
- `backend/routers/stocks.py` — add `sharpe_min` param, apply filter in query
- `backend/schemas/stock.py` — add `sharpe_min` to bulk signals query params if extracted
- `tests/api/test_bulk_signals.py` — add `test_bulk_signals_sharpe_filter`

### Test
```python
# test_bulk_signals_sharpe_filter
# - seed 3 stocks with sharpe_ratio: 1.5, 0.3, 0.8
# - GET /api/v1/stocks/signals/bulk?sharpe_min=0.7
# - assert only tickers with sharpe >= 0.7 returned
```

---

## Item 3: B2 — Watchlist Current Price + Freshness UI

### Problem
`GET /api/v1/stocks/watchlist` returns no price data. The dashboard shows stock cards with no price — a separate API call is required. There is also no indication of data freshness.

### Backend Changes

#### Schema
Add to `WatchlistItemResponse`:
```python
current_price: float | None = None       # latest adj_close from stock_prices
price_updated_at: datetime | None = None  # timestamp of that price row
```

Source: correlated subquery on `stock_prices` ordered by `timestamp DESC LIMIT 1` — same pattern as existing `composite_score` subquery.

#### New Endpoints

**`POST /api/v1/stocks/watchlist/refresh-all`**
- Auth required
- Enqueues one `refresh_ticker_task` Celery task per ticker in user's watchlist
- Returns: `list[{"ticker": str, "task_id": str}]`
- Rate: slowapi limit (suggest 2/minute — expensive operation)

**`GET /api/v1/tasks/{task_id}/status`**
- Auth required
- Returns task state from Redis via `AsyncResult(task_id).state`
- Response: `{"task_id": str, "state": "PENDING" | "STARTED" | "SUCCESS" | "FAILURE"}`
- No DB access — reads directly from Celery result backend (Redis)
- Lives in a new `backend/routers/tasks.py` (not `stocks.py` — semantically unrelated to stocks)
- Mounted at `/api/v1/tasks` in `backend/main.py`

#### Celery App Bootstrap (prerequisite)
`backend/tasks/__init__.py` is currently empty. Before the task can be defined, the Celery application instance must be created.

Add to `backend/tasks/__init__.py`:
```python
from celery import Celery
from backend.config import settings

celery_app = Celery(
    "stock_signal_platform",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["backend.tasks.market_data"],
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
```

#### Celery Task
New file: `backend/tasks/market_data.py`

```python
@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=4,
    retry_backoff=True,        # exponential: 5s → 10s → 20s → 40s
    retry_backoff_max=60,
)
def refresh_ticker_task(self, ticker: str) -> dict:
    # 1. fetch_and_store_prices(ticker)
    # 2. compute_signals(ticker)
    # 3. store_signal_snapshot(result, db)
    # returns {"ticker": ticker, "status": "ok"}
```

On final failure: `logger.error("refresh_ticker_task failed for %s after %d retries", ticker, max_retries)`

**Note:** This task is the same primitive B6 (nightly auto-refresh) will use in Phase 3 — building it now with retry logic means the scheduler work in Phase 3 is wiring, not new logic.

### Frontend Changes

#### `components/relative-time.tsx` (new)
Pure presentational component. No hooks, no side effects — pure date math.

```typescript
interface RelativeTimeProps {
  date: string | Date;
  prefix?: string; // default: "Refreshed"
}
```

Display rules:
| Age | Output |
|---|---|
| < 1 hour | "Refreshed just now" |
| 1–23 hours | "Refreshed 3 hours ago" |
| 1–6 days | "Refreshed 2 days ago" |
| ≥ 7 days | "Refreshed Mar 4" (absolute, `MMM D` format) |

**Reuse:** Phase 3 B6 will use this for signal freshness indicators on stock detail pages.

#### `components/stock-card.tsx` (updated)
Add props:
```typescript
current_price?: number | null;
price_updated_at?: string | null;
onRefresh?: (ticker: string) => void;  // triggers single-ticker ingest
isRefreshing?: boolean;                // shows spinner on card
```

UI additions:
- Price display: `$182.40` in card header (right side)
- Below price: `<RelativeTime date={price_updated_at} />` + refresh icon (↻)
- Refresh icon color: amber (`text-amber-500`) when age > 1 hour, muted when fresh
- Click refresh icon → calls `POST /api/v1/stocks/{ticker}/ingest` → TanStack mutation → refetch watchlist item
- **Note:** Single-ticker refresh is synchronous (calls existing ingest endpoint directly). "Refresh All" is async (Celery tasks + polling). Intentional asymmetry — a single ticker is fast enough to be synchronous; refreshing all in parallel would exhaust the yfinance rate limit.
- `isRefreshing=true` → spinner replaces refresh icon

#### `app/(authenticated)/dashboard/page.tsx` (updated)
- Add "Refresh All" button in watchlist section header: `Watchlist (12)  [↻ Refresh All]`
- Click → `POST /watchlist/refresh-all` → receive `[{ticker, task_id}]`
- Per-ticker TanStack Query poll on `GET /tasks/{task_id}/status` with `refetchInterval: 2000`
- Poll stops when state is `SUCCESS` or `FAILURE` (`refetchInterval: false` at terminal state)
- On `SUCCESS`: invalidate watchlist query for that ticker → card updates
- On `FAILURE`: `sonner` toast — "Couldn't refresh {ticker} — Yahoo Finance may be rate limited. Try again in a few minutes."
- Button disabled + spinner while any tasks are in-flight

### Test Coverage

| Test | File | What it covers |
|---|---|---|
| `test_watchlist_returns_price` | `tests/api/test_watchlist.py` | `current_price` + `price_updated_at` present in response |
| `test_watchlist_refresh_all_enqueues_tasks` | `tests/api/test_watchlist.py` | Endpoint returns task_ids, Celery task enqueued (mock) |
| `test_task_status_endpoint` | `tests/api/test_tasks.py` | Returns correct state string for known task_id |
| `test_refresh_ticker_task_retries` | `tests/unit/test_tasks.py` | Task retries on exception, logs on final failure |
| `test_bulk_signals_sharpe_filter` | `tests/api/test_bulk_signals.py` | Filter applied correctly, unfiltered still works |

---

## Component + File Summary

### New files
| File | Purpose |
|---|---|
| `backend/tasks/__init__.py` | Already exists (empty) |
| `backend/tasks/market_data.py` | `refresh_ticker_task` Celery task |
| `backend/migrations/versions/003_index_cleanup.py` | B3 + B4 + B5 schema changes |
| `frontend/src/components/relative-time.tsx` | Relative time display component |
| `tests/api/test_tasks.py` | Task status endpoint tests |
| `tests/unit/test_tasks.py` | Celery task unit tests |

### Modified files
| File | Change |
|---|---|
| `backend/models/stock.py` | Add B3/B4 fields, remove B5 field |
| `backend/schemas/stock.py` | Add price fields to watchlist schema, add sharpe_min param |
| `backend/routers/stocks.py` | Add sharpe_min filter, refresh-all endpoint |
| `backend/routers/tasks.py` | New router — task status endpoint |
| `backend/main.py` | Mount `tasks` router at `/api/v1/tasks` |
| `backend/tools/market_data.py` | Remove is_in_universe |
| `frontend/src/types/api.ts` | Add price fields, remove is_in_universe, add task status type |
| `frontend/src/components/stock-card.tsx` | Add price + refresh icon |
| `frontend/src/app/(authenticated)/dashboard/page.tsx` | Add Refresh All button + polling logic |
| `scripts/sync_sp500.py` | **Significant rewrite:** add StockIndexMembership upsert logic (currently only writes to Stock table), use removed_date instead of deleting stale rows, set last_synced_at after successful run, remove is_in_universe |
| `scripts/seed_prices.py` | Replace is_in_universe filter with index membership join |
| `tests/conftest.py` | Remove is_in_universe from StockFactory |

---

## Success Criteria

- [ ] Migration 003 applies cleanly on top of 002
- [ ] `is_in_universe` removed from all files — `grep -r is_in_universe .` returns zero results
- [ ] `GET /watchlist` returns `current_price` + `price_updated_at` for all items
- [ ] `GET /signals/bulk?sharpe_min=0.5` returns only stocks with sharpe ≥ 0.5
- [ ] Refresh icon on stock card turns amber when price > 1 hour old
- [ ] "Refresh All" shows per-card spinners, updates prices on SUCCESS, toasts on FAILURE
- [ ] All 6 new tests pass
- [ ] `uv run pytest tests/ -v` — full suite green
- [ ] `npm run lint && npm run build` — zero errors
