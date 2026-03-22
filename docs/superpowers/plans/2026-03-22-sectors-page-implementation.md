# KAN-94: Sectors Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a full Sectors page with 3 backend endpoints, frontend accordion UI with correlation heatmap, and dashboard cleanup.

**Architecture:** Backend-first — build endpoints + tests, then frontend components, then integration. Chunks are sequential (backend → types → hooks → components → page → dashboard cleanup).

**Tech Stack:** FastAPI, SQLAlchemy, pandas/numpy (correlation), Next.js, TanStack Query, Tailwind, framer-motion

**Spec:** `docs/superpowers/specs/2026-03-22-sectors-page-design.md`
**Branch:** `feat/KAN-94-sectors-page` (create from develop at implementation time)
**JIRA Story:** KAN-94

---

## Chunk 1: Backend — Sectors Router + Pydantic Schemas (KAN-94-S1)

### Task 1: Create Pydantic response schemas

**File:** Create `backend/schemas/sectors.py`

- [ ] `SectorSummary` — sector, stock_count, avg_composite_score, avg_return_pct, your_stock_count, allocation_pct
- [ ] `SectorSummaryResponse` — sectors: list[SectorSummary]
- [ ] `SectorStock` — ticker, name, composite_score, current_price, return_pct (nullable), is_held, is_watched
- [ ] `SectorStocksResponse` — sector: str, stocks: list[SectorStock]
- [ ] `ExcludedTicker` — ticker, reason
- [ ] `CorrelationResponse` — sector, tickers: list[str], matrix: list[list[float]], period_days, excluded_tickers: list[ExcludedTicker]

### Task 2: Create sectors router with `GET /api/v1/sectors`

**File:** Create `backend/routers/sectors.py`

- [ ] Define `ScopeEnum` — portfolio, watchlist, all
- [ ] Query all `Stock` rows grouped by sector (NULL → "Unknown")
- [ ] Join latest `SignalSnapshot` for avg composite_score and annual_return
- [ ] For portfolio scope: join `Position` → latest `StockPrice` to compute market_value per sector
- [ ] Compute allocation_pct = sector_market_value / total_portfolio_value × 100
- [ ] your_stock_count based on scope (portfolio positions / watchlist / both)
- [ ] Sort by allocation_pct descending
- [ ] Auth: `get_current_user` dependency

### Task 3: Add `GET /api/v1/sectors/{sector}/stocks`

**File:** `backend/routers/sectors.py` (append)

- [ ] URL-decode sector path param (FastAPI handles automatically)
- [ ] Validate sector exists (404 if not)
- [ ] Query top 20 stocks by composite_score in sector
- [ ] Always include user's portfolio + watchlist stocks (even if outside top 20)
- [ ] Deduplicate, mark is_held / is_watched
- [ ] current_price from latest `StockPrice.adj_close` (subquery for max date per ticker)
- [ ] return_pct: use `SignalSnapshot.annual_return` where available. Fallback: compute from latest vs 30-trading-day-ago `StockPrice.adj_close`. If insufficient price data, return null
- [ ] Sort: held first, then watched, then by score descending

### Task 4: Add `GET /api/v1/sectors/{sector}/correlation`

**File:** `backend/routers/sectors.py` (append)

- [ ] Accept `tickers` (comma-separated, optional) and `period_days` (default 90)
- [ ] If no tickers: use user's portfolio+watchlist stocks in sector
- [ ] Validation order: (1) max 15 tickers → 400, (2) all tickers belong to sector → 400, (3) fetch price data, (4) min 2 tickers with sufficient data → 400
- [ ] Fetch adj_close from `StockPrice` for period_days
- [ ] Build pandas DataFrame, compute `pct_change().corr()` (daily returns, not raw prices)
- [ ] Exclude tickers with <30 data points, add to excluded_tickers with reason
- [ ] Return symmetric matrix as list[list[float]]

### Task 5: Register router in main.py

**File:** Modify `backend/main.py`

- [ ] Import and include sectors router with prefix `/api/v1/sectors`

---

## Chunk 2: Backend Tests (KAN-94-S2)

### Task 6: Unit tests for sector logic

**File:** Create `tests/unit/test_sectors.py`

- [ ] **Aggregation tests:** NULL sector grouped as "Unknown", allocation_pct sums to 100%, scope filtering (portfolio vs watchlist vs all)
- [ ] **Correlation tests:** known correlation values (2 perfectly correlated series → 1.0), uncorrelated series → ~0.0, insufficient data exclusion, max ticker cap enforcement
- [ ] **return_pct fallback:** annual_return used when available, price-based fallback when not, null when insufficient data

### Task 7: API tests for all 3 endpoints

**File:** Create `tests/api/test_sectors_api.py`

- [ ] Auth required (401 without token)
- [ ] `GET /sectors` — happy path, scope=portfolio, scope=watchlist
- [ ] `GET /sectors/{sector}/stocks` — happy path, 404 for invalid sector
- [ ] `GET /sectors/{sector}/correlation` — happy path, too many tickers (400), insufficient data
- [ ] URL encoding: test with "Consumer Defensive" (space in sector name)

---

## Chunk 3: Frontend Types + Hooks (KAN-94-S3)

### Task 8: Add TypeScript types

**File:** Modify `frontend/src/types/api.ts`

- [ ] `SectorSummary` interface
- [ ] `SectorStock` interface
- [ ] `ExcludedTicker` interface
- [ ] `CorrelationData` interface
- [ ] `SectorScope` type: "portfolio" | "watchlist" | "all"

### Task 9: Create TanStack Query hooks

**File:** Create `frontend/src/hooks/use-sectors.ts`

- [ ] `useSectors(scope)` — fetches GET /sectors?scope=X
- [ ] `useSectorStocks(sector)` — fetches GET /sectors/{sector}/stocks, enabled only when sector is expanded
- [ ] `useSectorCorrelation(sector, tickers)` — fetches GET /sectors/{sector}/correlation?tickers=X, enabled only when sector is expanded

---

## Chunk 4: Frontend Components (KAN-94-S4)

### Task 10: SectorAccordion component

**File:** Create `frontend/src/components/sector-accordion.tsx`

- [ ] Collapsed: sector name, stock count, avg score (ScoreBar), avg return (ChangeIndicator), your_stock_count, allocation_pct
- [ ] Expand/collapse with framer-motion AnimatePresence
- [ ] Only one accordion open at a time (controlled by parent)
- [ ] Navy design tokens, border-border, bg-card

### Task 11: SectorStocksTable component

**File:** Create `frontend/src/components/sector-stocks-table.tsx`

- [ ] Table with columns: ticker, name, score (ScoreBar), price, return, badge (Held/Watched/—)
- [ ] Click row → callback to add ticker to correlation
- [ ] Highlight user's stocks vs sector stocks
- [ ] "Your Stocks" section above "Top Sector Stocks" section

### Task 12: CorrelationHeatmap component

**File:** Create `frontend/src/components/correlation-heatmap.tsx`

- [ ] Div-based grid (not Recharts) — n×n cells
- [ ] Color scale: green (<0.3) → yellow (0.3-0.7) → red (>0.7), diagonal gray
- [ ] Ticker labels on axes
- [ ] Cell hover shows exact value
- [ ] Responsive sizing

### Task 13: CorrelationTable component

**File:** Create `frontend/src/components/correlation-table.tsx`

- [ ] Ranked pairs list: "AAPL ↔ MSFT: 0.85"
- [ ] Interpretation text: "Highly correlated" (>0.7), "Moderate" (0.3-0.7), "Low" (<0.3)
- [ ] Color-coded values matching heatmap scheme
- [ ] Sorted by correlation descending

### Task 14: CorrelationTickerChips component

**File:** Create `frontend/src/components/correlation-ticker-chips.tsx`

- [ ] Row of removable ticker chips above heatmap
- [ ] ✕ button to remove ticker
- [ ] Disabled add when at 15 cap
- [ ] Excluded tickers shown with warning style + reason tooltip

---

## Chunk 5: Sectors Page Assembly (KAN-94-S5)

### Task 15: Create sectors page

**Files:**
- Create `frontend/src/app/(authenticated)/sectors/page.tsx` — server component wrapper
- Create `frontend/src/app/(authenticated)/sectors/sectors-client.tsx` — client component

- [ ] Page title + scope toggle (Portfolio | Watchlist | All)
- [ ] AllocationDonut (large, portfolio only — hidden when scope=watchlist)
- [ ] StaggerGroup of SectorAccordion cards
- [ ] Accordion expand: fetch stocks + correlation, render 3 sections
- [ ] Single-accordion-open constraint (state in parent)
- [ ] PageTransition wrapper
- [ ] Loading skeletons for accordion content

---

## Chunk 6: Dashboard Cleanup (KAN-94-S6)

### Task 16: Remove duplicate Sector Allocation section

**File:** Modify `frontend/src/app/(authenticated)/dashboard/page.tsx`

- [ ] Remove the "Action Required + Sector Allocation" grid-cols-3 split
- [ ] Action Required section goes full width
- [ ] Remove the `<Link href="/sectors">` donut card

### Task 17: Bigger Allocation StatTile donut

**File:** Modify `frontend/src/components/allocation-donut.tsx`

- [ ] Add `size` prop: "sm" (default, current) | "lg" (bigger radius + taller)
- [ ] Dashboard StatTile uses "lg" size
- [ ] On click → navigate to `/sectors` (via router.push or Link wrapper)

---

## Chunk 7: Frontend Tests + Polish (KAN-94-S7)

### Task 18: Frontend component tests

**File:** Create `frontend/src/__tests__/sectors/`

- [ ] SectorAccordion: renders collapsed stats, expand/collapse toggle
- [ ] CorrelationHeatmap: correct color mapping for known values
- [ ] CorrelationTable: ranked pairs ordering
- [ ] SectorStocksTable: Held/Watched badges render correctly
- [ ] Sectors page: scope toggle hides/shows donut

### Task 19: TypeScript + ESLint verification

- [ ] `npx tsc --noEmit` — zero errors
- [ ] `npx eslint src/` — zero errors (warnings ok for pre-existing)
- [ ] All existing 88 frontend tests still pass
- [ ] All backend tests pass (`uv run pytest tests/unit/ tests/api/ -v`)

---

## Estimated Effort

| Chunk | Effort | Dependencies |
|-------|--------|-------------|
| C1: Backend router + schemas | ~2h | None |
| C2: Backend tests | ~1h | C1 |
| C3: Frontend types + hooks | ~30m | C1 (API contract) |
| C4: Frontend components | ~3h | C3 |
| C5: Page assembly | ~1.5h | C4 |
| C6: Dashboard cleanup | ~30m | None (independent) |
| C7: Tests + polish | ~1h | C4, C5, C6 |
| **Total** | **~9.5h** | **2-3 sessions** |
