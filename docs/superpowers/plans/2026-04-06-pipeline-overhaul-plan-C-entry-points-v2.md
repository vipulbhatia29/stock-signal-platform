# Pipeline Overhaul — Spec C (Entry Point Unification) — Split Plan v2

> **Supersedes:** `2026-04-06-pipeline-overhaul-plan-C-entry-points.md` (monolithic, ~800 lines, exceeded Hard Rule #12)
>
> **Split rationale:** Original plan was ~800 lines touching ~28 files across backend + frontend. Split into 4 independently-mergeable PRs per Hard Rule #12 (plans ≤ 500 lines, PRs ≤ 10 files / 500 diff lines).

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-C-entry-points.md`

**Depends on:** Spec A (done), Spec B (done), Spec F rate limiters (done)

---

## Gap Analysis (2026-04-12 audit)

Issues found when verifying the original spec/plan against the current codebase:

| # | Gap | Resolution |
|---|---|---|
| 1 | `IngestInProgressError` does not exist in `backend/services/exceptions.py` | Create it in PR1 |
| 2 | `backend/services/ingest_lock.py` does not exist | Create it in PR1 (Redis SETNX helper) |
| 3 | Plan uses `vitest` imports in frontend tests — project uses **Jest** | Fix: use `jest`/`@testing-library` imports |
| 4 | Plan deletes `tests/unit/test_analyze_stock_autoingest.py` — file **does exist** | Confirmed; delete in PR2 and replace |
| 5 | `get_latest_signals` exists at `backend/services/signals.py:723` | Confirmed available |
| 6 | `mark_stage_updated` not imported in `market_data.py` | Not relevant to Spec C (Spec E concern) |
| 7 | Line references in spec may have drifted post-Sessions 99-106 | Implementer must grep before editing, per plan-execution.md |

---

## PR Structure

| PR | JIRA | Scope | Files | Tests |
|---|---|---|---|---|
| **PR1** | KAN-423-A | C1 + C6: Watchlist auto-ingest + Redis dedup infra | ~8 backend + frontend | ~8 |
| **PR2** | KAN-423-B | C2 + C3: Portfolio sync-ingest + Chat canonical ingest | ~6 backend + frontend | ~8 |
| **PR3** | KAN-423-C | C4: Stale auto-refresh + Redis debounce | ~5 backend + frontend | ~6 |
| **PR4** | KAN-423-D | C5: Bulk CSV upload (new endpoint + component) | ~8 backend + frontend | ~13 |

Each PR is independently mergeable with green CI.

---

## PR1: C1 + C6 — Watchlist Auto-Ingest + Redis Dedup

**Branch:** `feat/KAN-423-A-watchlist-auto-ingest`

### Fact Sheet (verify at implementation time)

Before writing code, implementer MUST grep:
```bash
grep -rn "add_to_watchlist" backend/services/watchlist.py
grep -rn "StockNotFoundError\|IngestFailedError" backend/services/exceptions.py
grep -rn "handleAddTicker\|useIngestTicker" frontend/src/app/\(authenticated\)/layout.tsx
grep -rn "useAddToWatchlist" frontend/src/hooks/use-stocks.ts
grep -rn "handleToggleWatchlist" frontend/src/app/\(authenticated\)/stocks/
```

### Task 1.1: Create dedup infrastructure

**Files:**
- Create: `backend/services/ingest_lock.py`
- Modify: `backend/services/exceptions.py`

- [ ] Add `IngestInProgressError` to `backend/services/exceptions.py`:
```python
class IngestInProgressError(ServiceError):
    """Another caller is already ingesting this ticker."""
    def __init__(self, ticker: str) -> None:
        super().__init__(f"Ingestion in progress for {ticker}")
        self.ticker = ticker
```

- [ ] Create `backend/services/ingest_lock.py` — Redis SETNX lock:
```python
"""Redis-backed ingest dedup lock (Spec C.6)."""

import logging
import redis.asyncio as redis_async
from backend.config import settings

logger = logging.getLogger(__name__)

IN_FLIGHT_KEY = "ingest:in_flight:{ticker}"
LOCK_TTL_SECONDS = 60


async def acquire_ingest_lock(ticker: str) -> bool:
    """SETNX with 60s TTL. Returns True if lock acquired."""
    try:
        client = redis_async.from_url(settings.REDIS_URL)
        return bool(await client.set(
            IN_FLIGHT_KEY.format(ticker=ticker.upper()),
            "1", ex=LOCK_TTL_SECONDS, nx=True,
        ))
    except Exception:
        logger.warning("Redis unavailable for ingest lock %s", ticker, exc_info=True)
        return True  # fail-open: allow ingest if Redis is down


async def release_ingest_lock(ticker: str) -> None:
    """Delete the lock key after ingest completes or fails."""
    try:
        client = redis_async.from_url(settings.REDIS_URL)
        await client.delete(IN_FLIGHT_KEY.format(ticker=ticker.upper()))
    except Exception:
        logger.warning("Redis unavailable for lock release %s", ticker, exc_info=True)
```

- [ ] Write unit tests for lock helpers (mock Redis)

### Task 1.2: Watchlist auto-ingest (backend)

**Files:**
- Modify: `backend/services/watchlist.py`
- Modify: `backend/routers/stocks/watchlist.py`
- Modify: `backend/config.py` (add `WATCHLIST_AUTO_INGEST: bool = True`)
- Create: `tests/unit/services/test_watchlist_ingest.py`
- Create: `tests/api/test_watchlist_auto_ingest.py`

- [ ] Add `WATCHLIST_AUTO_INGEST` feature flag to `backend/config.py`
- [ ] Write failing unit tests (4 cases per spec)
- [ ] Rewrite `add_to_watchlist` to call `ingest_ticker` with dedup lock
- [ ] Add `IngestInProgressError` + `IngestFailedError` handlers to watchlist router
- [ ] Write API integration tests (2 cases)
- [ ] Run tests, lint

### Task 1.3: Frontend watchlist simplification

**Files:**
- Modify: `frontend/src/app/(authenticated)/layout.tsx`
- Modify: `frontend/src/app/(authenticated)/stocks/[ticker]/stock-detail-client.tsx`
- Modify: `frontend/src/hooks/use-stocks.ts`
- Create: `frontend/src/__tests__/hooks/use-add-to-watchlist.test.tsx`

- [ ] Collapse `handleAddTicker` two-phase hack → single `addToWatchlist.mutate`
- [ ] Upgrade `useAddToWatchlist` with loading toast + full query invalidation + 404 handling
- [ ] Simplify `handleToggleWatchlist` on stock detail
- [ ] Write Jest tests (NOT Vitest — use `jest`/`@testing-library` imports)
- [ ] Run frontend lint + tests

**Done criteria PR1:** Watchlist add auto-ingests unknown tickers. Concurrent adds to same ticker hit dedup lock. Frontend hack removed. ~8 tests green.

---

## PR2: C2 + C3 — Portfolio Sync-Ingest + Chat Canonical Ingest

**Branch:** `feat/KAN-423-B-portfolio-chat-ingest`
**Depends on:** PR1 merged (uses `ingest_lock`)

### Task 2.1: Portfolio transaction sync-ingest (backend)

**Files:**
- Modify: `backend/routers/portfolio.py`
- Modify: `tests/api/test_portfolio.py`

- [ ] Write failing tests (3 cases: new ticker triggers ingest, existing skips, failure returns 422)
- [ ] Update `create_transaction` to check `stock.last_fetched_at is None` → call `ingest_ticker`
- [ ] Run tests, lint

### Task 2.2: Portfolio frontend (async submit + invalidation)

**Files:**
- Modify: `frontend/src/hooks/use-portfolio.ts` (or wherever `useLogTransaction` lives)
- Modify: `frontend/src/components/log-transaction-dialog.tsx`

- [ ] Upgrade `useLogTransaction` to full query invalidation on success
- [ ] Make dialog `handleSubmit` async; keep dialog open on error; add loading overlay
- [ ] Run frontend lint + tests

### Task 2.3: Chat `analyze_stock` canonical ingest

**Files:**
- Modify: `backend/tools/analyze_stock.py`
- Delete: `tests/unit/test_analyze_stock_autoingest.py`
- Create: `tests/api/test_analyze_stock_tool.py`

- [ ] Rewrite `_run` to use `ingest_ticker` + `get_latest_signals` (reload from DB)
- [ ] Bump `timeout_seconds` to 45.0
- [ ] Delete legacy test, create new test file (3 cases: calls ingest, reloads snapshot, safe error)
- [ ] Run tests, lint

### Task 2.4: Chat frontend invalidation

**Files:**
- Modify: `frontend/src/hooks/use-stream-chat.ts`
- Modify: `frontend/src/components/chat/tool-card.tsx`

- [ ] Invalidate query keys on `analyze_stock` tool_complete event
- [ ] Add running-state label to tool-card for `analyze_stock`
- [ ] Run frontend lint + tests

**Done criteria PR2:** Portfolio transaction for new ticker runs full ingest. Chat `analyze_stock` persists signals. ~8 tests green.

---

## PR3: C4 — Stale Auto-Refresh + Redis Debounce

**Branch:** `feat/KAN-423-C-stale-auto-refresh`
**Depends on:** PR1 merged (uses Redis patterns)

### Task 3.1: Backend debounced refresh dispatch

**Files:**
- Modify: `backend/routers/stocks/data.py`
- Modify: `backend/schemas/stock.py`
- Create: `tests/api/test_signals_auto_refresh.py`

- [ ] Write failing tests (4 cases: stale dispatches, debounce prevents re-dispatch, not stale skips, Redis down still returns data)
- [ ] Add `_try_dispatch_refresh` helper with Redis SETNX debounce (5-min TTL)
- [ ] Wire into `get_signals` after `is_stale` computation
- [ ] Add `is_refreshing: bool` and `last_refresh_attempt: datetime | None` to `SignalResponse` schema
- [ ] Skip cache when `is_stale=True`
- [ ] Run tests, lint

### Task 3.2: Frontend auto-poll + badges

**Files:**
- Modify: `frontend/src/hooks/use-stocks.ts` (`useSignals`)
- Modify: `frontend/src/components/stock-header.tsx`
- Modify: `frontend/src/types/api.ts`

- [ ] Add `is_refreshing` + `last_refresh_attempt` to `SignalResponse` type
- [ ] Add conditional `refetchInterval: 5000` when `is_refreshing` in `useSignals`
- [ ] Add refresh badges to stock-header ("Refreshing data..." / "Data may be outdated")
- [ ] Run frontend lint + tests

**Done criteria PR3:** Stale signals trigger debounced background refresh. Frontend polls until fresh. ~6 tests green.

---

## PR4: C5 — Bulk CSV Upload

**Branch:** `feat/KAN-423-D-bulk-csv-upload`
**Depends on:** PR1 merged (uses `ingest_ticker` + dedup)

### Task 4.1: Backend service + endpoint

**Files:**
- Create: `backend/services/portfolio/bulk_import.py`
- Modify: `backend/routers/portfolio.py` (add endpoint)
- Modify: `backend/schemas/portfolio.py` (add schemas)
- Create: `tests/unit/services/test_bulk_import.py`
- Create: `tests/api/test_bulk_transactions.py`

- [ ] Add `BulkTransactionError` + `BulkTransactionResponse` schemas
- [ ] Write failing unit tests (8 cases: CSV parse, row limit, parallel ingest, skip existing, failure drops rows, validate_only)
- [ ] Implement `parse_csv_to_transactions` + `bulk_create_transactions`
- [ ] Add `POST /portfolio/transactions/bulk` endpoint with rate limit `3/hour`
- [ ] Write API tests (6 cases: auth, verified email, happy path, wrong content type, oversized, dry run)
- [ ] Run tests, lint

### Task 4.2: Frontend bulk upload component

**Files:**
- Modify: `frontend/src/lib/api.ts` (add `postMultipart`)
- Create: `frontend/src/hooks/use-bulk-transactions.ts`
- Create: `frontend/src/components/bulk-transaction-upload.tsx`
- Modify: `frontend/src/app/(authenticated)/portfolio/portfolio-client.tsx`
- Modify: `frontend/src/types/api.ts`
- Create: `frontend/public/portfolio-template.csv`
- Create: `frontend/src/__tests__/components/bulk-transaction-upload.test.tsx`

- [ ] Add `postMultipart` helper to `api.ts`
- [ ] Add `BulkTransactionError` + `BulkTransactionResponse` types
- [ ] Create `useBulkUploadTransactions` hook
- [ ] Create `BulkTransactionUpload` component (drag-drop, preview, per-row errors)
- [ ] Add "Upload CSV" button to portfolio page
- [ ] Create `portfolio-template.csv`
- [ ] Write Jest component tests (3 cases: reject non-CSV, validate-only preview, render errors)
- [ ] Run frontend lint + tests

**Done criteria PR4:** Bulk CSV upload accepts 500 rows, dedupes tickers, returns per-row errors. ~13 tests green.

---

## Execution Order

```
PR1 (C1+C6) ──┬── PR2 (C2+C3)
               ├── PR3 (C4)
               └── PR4 (C5)
```

PR1 lands first (provides dedup infra). PR2/PR3/PR4 can be developed in parallel after PR1 merges.

## Hard Constraints Carried From Spec

1. **Hard Rule #10** — no `str(e)` in user-facing output. Log the real error, return generic messages.
2. **Hard Rule #11** — Sonnet implements, Opus reviews.
3. **Jest for frontend tests** — NOT Vitest. Use `@testing-library/react`, `jest`, `msw`.
4. **Patch at lookup site** — `backend.services.watchlist.ingest_ticker`, not `backend.services.pipelines.ingest_ticker`.
5. **Redis fail-open** — if Redis is unavailable, allow the operation (dedup is optimization, not correctness).
6. **Feature flag** — `WATCHLIST_AUTO_INGEST` for C1 rollback.
