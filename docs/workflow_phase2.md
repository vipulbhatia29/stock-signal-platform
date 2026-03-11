# Phase 2 Implementation Workflow

**Generated:** 2026-03-07
**Status:** COMPLETED (Sessions 5-7, all tasks implemented on `feat/initial-scaffold`)
**Source:** `docs/phase2-requirements.md`, `project-plan.md`
**Branch:** `feat/initial-scaffold` (originally planned as `feat/dashboard`)
**Estimated tasks:** 11 backend + 11 frontend = 22 implementation tasks

---

## Pre-flight Checklist

- [ ] Commit all uncommitted Session 3-4 work on `feat/initial-scaffold`
- [ ] Create `feat/dashboard` branch from `feat/initial-scaffold`
- [ ] Verify 114 tests still pass
- [ ] Docker Compose up (Postgres 5433, Redis 6380)

---

## STAGE 1: Backend Pre-requisites

### Task 1.1 — httpOnly Cookie Auth
**Priority:** P0 (blocks all frontend work)
**Files to modify:**
- `backend/dependencies.py` — add `get_current_user_from_cookie()`, update `get_current_user` to dual-mode (header OR cookie, header takes precedence)
- `backend/routers/auth.py` — modify `login()` and `refresh_token()` to set httpOnly cookies on `Response`; add `POST /logout` endpoint that clears cookies
- `backend/main.py` — update CORS: `allow_credentials=True`, explicit `allow_origins` (no wildcard with credentials)

**Key decisions:**
- Cookie names: `access_token`, `refresh_token`
- Cookie attrs: `httponly=True`, `secure=True` (relaxed in dev), `samesite="lax"`, `path="/"`
- `refresh_token` cookie: longer `max_age` (7 days vs 30 min for access)
- Keep JSON body response too (backward-compatible for existing tests + non-browser clients)

**Tests to write/update:**
- `tests/api/test_auth.py` — verify cookies set on login, cookies set on refresh, logout clears cookies, cookie-based auth works on protected endpoints, dual-mode (header still works)
- ~8-10 new/modified tests

**Checkpoint:** All existing auth tests still pass + new cookie tests pass

---

### Task 1.2 — Stock Index Model + Migration
**Priority:** P0 (blocks dashboard index cards + screener)
**Files to create:**
- `backend/models/index.py` — `StockIndex` (id, name, slug, description) + `StockIndexMembership` (id, ticker FK, index_id FK, added_at)
- `backend/schemas/index.py` — `IndexResponse`, `IndexWithCountResponse`, `IndexStockResponse`
- `backend/routers/indexes.py` — new router
- Alembic migration `002_stock_indexes.py`

**Files to modify:**
- `backend/models/__init__.py` — export new models
- `backend/main.py` — mount indexes router at `/api/v1/indexes`

**Endpoints:**
- `GET /api/v1/indexes` — list all indexes with stock counts (JOIN + COUNT)
- `GET /api/v1/indexes/{index_id}/stocks` — paginated stocks in index with latest price + signal summary

**Tests to write:**
- `tests/unit/test_index_model.py` — model creation, relationships
- `tests/api/test_indexes.py` — auth required, list indexes, get index stocks, 404 unknown index, pagination
- ~10-12 tests

**Checkpoint:** Migration runs cleanly, new endpoints return data, all tests pass

---

### Task 1.3 — Index Seed Scripts
**Priority:** P1 (needed for demo data, but not blocking other tasks)
**Files to create:**
- `scripts/sync_indexes.py` — seed S&P 500 + NASDAQ-100 + Dow 30 index records + memberships

**Files to modify:**
- `scripts/sync_sp500.py` — refactor to also create index membership (or deprecate in favor of `sync_indexes.py`)

**Logic:**
- Create `StockIndex` rows for each index
- For S&P 500: reuse Wikipedia scraping from `sync_sp500.py`
- For NASDAQ-100: scrape Wikipedia NASDAQ-100 list
- For Dow 30: scrape Wikipedia Dow Jones list
- Create `StockIndexMembership` rows linking tickers to indexes
- Idempotent (upsert pattern)

**Tests to write:**
- `tests/unit/test_sync_indexes.py` — 3-5 tests
- **Dependency:** Task 1.2 (needs index model + migration)

**Checkpoint:** Script runs, indexes populated, `GET /api/v1/indexes` returns 3 indexes with correct counts

---

### Task 1.4 — On-Demand Data Ingestion Endpoint
**Priority:** P0 (blocks "add ticker" flow on dashboard)
**Files to modify:**
- `backend/tools/market_data.py` — add `fetch_prices_delta()` that queries `MAX(time)` and fetches only newer data; add `update_last_fetched_at()`
- `backend/routers/stocks.py` — add `POST /api/v1/stocks/{ticker}/ingest` endpoint

**Endpoint behavior:**
1. Validate ticker format (alphanumeric + `.` + `-`)
2. Call `ensure_stock_exists()` to create Stock record if missing
3. Query `MAX(time)` from `stock_prices` for this ticker
4. If no data: fetch 10Y; if has data: fetch from `MAX(time)` to today (delta)
5. Store prices (existing upsert handles overlaps)
6. Compute signals via `compute_signals()` + `store_signal_snapshot()`
7. Update `Stock.last_fetched_at`
8. Return 201 (new) or 200 (existing, delta applied)
9. Rate limit: 5/minute (more aggressive than default)

**Tests to write:**
- `tests/api/test_ingest.py` — auth required, valid ticker ingested (mock yfinance), invalid ticker 400, delta fetch for existing ticker, rate limit
- ~6-8 tests
- **Dependency:** None (uses existing models)

**Checkpoint:** Can call ingest endpoint, see prices + signals created, delta fetch works

---

### Task 1.5 — Bulk Signals Endpoint (Screener)
**Priority:** P0 (blocks screener page)
**Files to modify:**
- `backend/routers/stocks.py` — add `GET /api/v1/stocks/signals/bulk`
- `backend/schemas/stock.py` — add `BulkSignalResponse`, `BulkSignalItem`, pagination schemas

**Query pattern:**
```sql
SELECT DISTINCT ON (ss.ticker) ss.*, s.name, s.sector
FROM signal_snapshots ss
JOIN stocks s ON ss.ticker = s.ticker
JOIN stock_index_memberships sim ON s.ticker = sim.ticker
WHERE sim.index_id = :index_id
  AND (:rsi_state IS NULL OR ss.rsi_signal = :rsi_state)
  AND (:macd_state IS NULL OR ss.macd_signal = :macd_state)
  AND (:sector IS NULL OR s.sector = :sector)
  AND (:score_min IS NULL OR ss.composite_score >= :score_min)
  AND (:score_max IS NULL OR ss.composite_score <= :score_max)
ORDER BY ss.ticker, ss.computed_at DESC
```
- Then apply sort + pagination in Python or subquery

**Query params:** `index_id`, `rsi_state`, `macd_state`, `sector`, `score_min`, `score_max`, `sort_by`, `sort_order`, `limit` (default 50, max 200), `offset`

**Tests to write:**
- `tests/api/test_bulk_signals.py` — auth required, returns paginated data, filters work (RSI, MACD, sector, score range), sorting works, empty result, invalid params
- ~10-12 tests
- **Dependency:** Task 1.2 (needs index membership for filtering)

**Checkpoint:** Screener query returns correct filtered/sorted/paginated data

---

### Task 1.6 — Signal History Endpoint
**Priority:** P1 (blocks stock detail signal chart, but detail page can be built without it initially)
**Files to modify:**
- `backend/routers/stocks.py` — add `GET /api/v1/stocks/{ticker}/signals/history`
- `backend/schemas/stock.py` — add `SignalHistoryItem` schema

**Query:** Simple chronological query on `signal_snapshots` for a ticker, ordered by `computed_at ASC`, with `days` and `limit` params

**Tests to write:**
- `tests/api/test_signal_history.py` — auth required, returns chronological data, respects days param, respects limit, 404 unknown ticker, empty result
- ~6-8 tests
- **Dependency:** None

**Checkpoint:** History endpoint returns time-series signal data

---

## STAGE 2: Frontend Scaffold + Auth

### Task 2.1 — Next.js Project Setup
**Priority:** P0 (blocks all frontend work)
**Actions:**
- `npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir=false`
- Install deps: `npm install @tanstack/react-query next-themes recharts`
- Install shadcn/ui: `npx shadcn@latest init` + add components (button, input, card, table, select, slider, dropdown-menu, badge, toast, dialog, popover, command)
- Configure `tailwind.config.ts` for dark mode (`class` strategy)
- Set up `next-themes` provider in root layout
- TypeScript strict mode in `tsconfig.json`
- Configure proxy/rewrites in `next.config.ts` to proxy `/api` to backend (port 8181)

**Files to create:**
- `frontend/lib/api.ts` — centralized fetch wrapper with `credentials: "include"`, auto-refresh on 401, typed responses
- `frontend/lib/auth.ts` — auth context/hook (`useAuth`) with login/logout/register functions
- `frontend/types/api.ts` — TypeScript types mirroring backend Pydantic schemas
- `frontend/app/providers.tsx` — QueryClientProvider + ThemeProvider wrapper

**Checkpoint:** `npm run dev` starts, blank page loads, API proxy works

---

### Task 2.2 — Login + Register Pages
**Priority:** P0 (entry point for all authenticated flows)
**Files to create:**
- `frontend/app/login/page.tsx` — email + password form, calls `POST /api/v1/auth/login`, redirect to `/dashboard`
- `frontend/app/register/page.tsx` — email + password + confirm, client-side validation, calls `POST /api/v1/auth/register`, redirect to `/login`
- `frontend/components/auth-form.tsx` — shared form wrapper (centered card layout)

**Dependency:** Task 1.1 (cookie auth must work), Task 2.1 (Next.js setup)

**Checkpoint:** Can register new user, log in, see cookies set in browser DevTools

---

### Task 2.3 — Auth Guard + Nav Layout
**Priority:** P0 (protects all dashboard/screener/detail routes)
**Files to create:**
- `frontend/app/(authenticated)/layout.tsx` — route group layout with auth check + nav bar
- `frontend/components/nav-bar.tsx` — Dashboard + Screener links, theme toggle, logout button
- `frontend/middleware.ts` — Next.js middleware to redirect unauthenticated users to `/login`

**Logic:**
- Middleware checks for `access_token` cookie presence (not validation — backend validates)
- If missing: redirect to `/login`
- `lib/api.ts` handles 401 → attempt refresh → if fail, redirect to `/login`

**Dependency:** Task 2.2 (login must work first)

**Checkpoint:** Unauthenticated user redirected to login, authenticated user sees nav

---

### Task 2.4 — Dashboard Page (Index Cards + Watchlist)
**Priority:** P0 (primary landing page)
**Files to create:**
- `frontend/app/(authenticated)/dashboard/page.tsx` — main dashboard
- `frontend/components/index-card.tsx` — clickable index summary card
- `frontend/components/stock-card.tsx` — watchlist stock card (ticker, price, sentiment badge, return)
- `frontend/components/watchlist-search.tsx` — autocomplete search to add tickers
- `frontend/components/sector-filter.tsx` — dropdown filter for watchlist

**API calls (TanStack Query):**
- `GET /api/v1/indexes` → index cards
- `GET /api/v1/stocks/watchlist` → watchlist data
- `POST /api/v1/stocks/watchlist` → add ticker
- `POST /api/v1/stocks/{ticker}/ingest` → trigger ingestion for new tickers
- `GET /api/v1/stocks/search?q=...` → autocomplete

**Dependency:** Tasks 1.1-1.4, 2.1-2.3

**Checkpoint:** Dashboard shows 3 index cards + watchlist cards, can search and add tickers

---

### Task 2.5 — Screener Page
**Priority:** P0 (core feature)
**Files to create:**
- `frontend/app/(authenticated)/screener/page.tsx` — screener with filters + table
- `frontend/components/screener-filters.tsx` — filter bar (index, RSI, MACD, sector, score slider)
- `frontend/components/screener-table.tsx` — sortable data table with row coloring
- `frontend/components/pagination.tsx` — page navigation

**URL state management:** Sync filters/sort/page to URL search params using `useSearchParams`

**API calls:**
- `GET /api/v1/stocks/signals/bulk?index={id}&...` → table data
- `GET /api/v1/indexes` → index dropdown options

**Dependency:** Tasks 1.2, 1.5, 2.1-2.3

**Checkpoint:** Table loads 500 stocks, filters work, sorting works, pagination works, rows color-coded

---

### Task 2.6 — Stock Detail Page
**Priority:** P0 (core feature)
**Files to create:**
- `frontend/app/(authenticated)/stocks/[ticker]/page.tsx` — stock detail
- `frontend/components/price-chart.tsx` — Recharts line chart with volume bars + timeframe selector
- `frontend/components/signal-cards.tsx` — RSI, MACD, SMA, Bollinger breakdown cards
- `frontend/components/signal-history-chart.tsx` — composite score + RSI over time
- `frontend/components/risk-return.tsx` — annualized return, volatility, Sharpe display

**API calls:**
- `GET /api/v1/stocks/{ticker}/prices?period=1y` → price chart
- `GET /api/v1/stocks/{ticker}/signals` → signal breakdown
- `GET /api/v1/stocks/{ticker}/signals/history?days=90` → signal history chart
- `POST /api/v1/stocks/{ticker}/ingest` → ingest button if no data

**Dependency:** Tasks 1.4, 1.6, 2.1-2.3

**Checkpoint:** Price chart renders with timeframe switching, signal cards show current values, signal history chart shows trends

---

### Task 2.7 — Theme Toggle + Polish
**Priority:** P1 (enhances UX, not blocking)
**Actions:**
- Wire up `next-themes` toggle in nav bar
- Ensure all components respect dark/light mode (Tailwind `dark:` variants)
- Add loading skeletons for all data-fetching components
- Add empty states ("No stocks in watchlist", "No signals available")
- Add error boundaries with retry buttons
- Toast notifications for actions (added to watchlist, ingestion complete, errors)

**Dependency:** Tasks 2.4-2.6 (all pages must exist)

**Checkpoint:** Theme toggles cleanly, loading/empty/error states all look good

---

### Task 2.8 — Design System + UI Polish (Phase 2.5)
**Priority:** P1 (enhances UX, builds on Task 2.7)
**Detailed plan:** `.claude/plans/cozy-wandering-backus.md`
**Research:** TradingView, Robinhood, Bloomberg Terminal UI patterns analyzed

**Pre-requisites (do first):**
- Fix 5 Session 7 UI bugs (screener filter placeholders, watchlist score N/A, stock name, market indexes)
- Commit all Session 6+7 work (establish baseline)

**Phase A — Foundation:**
- Add financial semantic CSS variables to `globals.css` (gain/loss/neutral, chart colors)
- Register in `@theme inline` for Tailwind class generation
- Fix OKLCH/HSL chart color mismatch (charts use `hsl()` but vars are OKLCH)
- Create `lib/design-tokens.ts`, `lib/chart-theme.ts`, `lib/typography.ts`
- Migrate `lib/signals.ts` hardcoded Tailwind classes to CSS variable classes
- Build `useChartColors()` hook for theme-aware Recharts colors

**Phase B — Core Components:**
- `ChangeIndicator` — gain/loss with icon + sign + color (accessible)
- `SectionHeading` — replaces 6+ inline heading patterns
- `ChartTooltip` — reusable Recharts tooltip, refactor both charts
- `ErrorState` — error display with retry button
- `Breadcrumbs` — back navigation for stock detail page

**Phase C — Responsive & Polish:**
- Fix signal cards grid: `grid-cols-1 sm:grid-cols-2 xl:grid-cols-4`
- Fix risk/return grid: `grid-cols-1 sm:grid-cols-3`
- Responsive chart heights: `h-[250px] sm:h-[400px]`
- Sticky screener table header with backdrop blur
- aria-labels on ScoreBadge, SignalBadge

**Phase D — Dark Mode & Theme:**
- Bloomberg-inspired warm dark backgrounds (subtle blue undertone)
- Chart color brightness increase for dark mode (L >= 0.70)
- Sun/Moon toggle icons (replace text toggle)

**Deferred (post-Phase 2):**
- Screener column preset tabs (TradingView-inspired)
- MetricCard, Sparkline, SignalMeter components
- Entry animations, DensityProvider, chart grid view

**Files to create:** `lib/design-tokens.ts`, `lib/chart-theme.ts`, `lib/typography.ts`, `components/change-indicator.tsx`, `components/section-heading.tsx`, `components/chart-tooltip.tsx`, `components/error-state.tsx`, `components/breadcrumbs.tsx`

**Files to modify:** `globals.css`, `lib/signals.ts`, `price-chart.tsx`, `signal-history-chart.tsx`, `signal-cards.tsx`, `risk-return-card.tsx`, `screener-table.tsx`, `stock-header.tsx`, `score-badge.tsx`, `signal-badge.tsx`, `nav-bar.tsx`

**Checkpoint:** `npm run build` + `npm run lint` pass, charts render in both themes, responsive at 375/768/1280px

---

## STAGE 3: Testing + Integration

### Task 3.1 — Backend Test Completion
**Priority:** P0
**Actions:**
- Verify all new endpoints have auth + happy path + error path tests
- Run full test suite: `uv run pytest tests/ -v --cov=backend --cov-fail-under=80`
- Fix any coverage gaps

**Target:** All backend tests pass, coverage >= 80%

---

### Task 3.2 — Frontend Tests
**Priority:** P1
**Actions:**
- Set up vitest + React Testing Library in frontend
- Unit tests for key components: auth form, stock card, screener table, price chart
- Integration test: login → dashboard → screener → stock detail flow

**Target:** Key component tests pass

---

### Task 3.3 — End-to-End Verification
**Priority:** P0
**Actions:**
1. Start backend: `uv run uvicorn backend.main:app --reload --port 8181`
2. Start frontend: `cd frontend && npm run dev`
3. Run seed scripts to populate data
4. Manual flow: register → login → see dashboard → search + add AAPL → screener → stock detail
5. Verify dark/light theme
6. Verify cookie auth (check DevTools)

**Target:** Full flow works end-to-end

---

## Dependency Graph

```
Task 1.1 (Cookie Auth) ─────────────────────────┐
Task 1.2 (Index Model) ──┬── Task 1.3 (Seed)    │
                          ├── Task 1.5 (Bulk)    │
Task 1.4 (Ingestion) ────┤                      │
Task 1.6 (History) ──────┤                      │
                          │                      │
                    Task 2.1 (Next.js Setup) ◄───┘
                          │
                    Task 2.2 (Login/Register)
                          │
                    Task 2.3 (Auth Guard + Nav)
                          │
              ┌───────────┼───────────┐
              │           │           │
        Task 2.4      Task 2.5    Task 2.6
       (Dashboard)   (Screener)  (Detail)
              │           │           │
              └───────────┼───────────┘
                          │
                    Task 2.7 (Polish)
                          │
                    Task 2.8 (Design System)
                          │
              ┌───────────┼───────────┐
              │           │           │
        Task 3.1      Task 3.2    Task 3.3
      (Backend Tests) (FE Tests) (E2E)
```

## Parallelization Opportunities

**Can run in parallel:**
- Tasks 1.1, 1.2, 1.4, 1.6 (independent backend tasks)
- Task 1.3 starts after 1.2 completes
- Task 1.5 starts after 1.2 completes
- Tasks 2.4, 2.5, 2.6 (independent pages, after 2.3)
- Tasks 3.1, 3.2 (backend vs frontend tests)

**Must be sequential:**
- 1.1 → 2.1 → 2.2 → 2.3 → (2.4, 2.5, 2.6) → 2.7 → 3.3
- 1.2 → 1.3
- 1.2 → 1.5

## Recommended Session Breakdown

| Session | Tasks | Focus |
|---------|-------|-------|
| Session 5 | 1.1-1.6 | All backend pre-reqs (DONE) |
| Session 6 | 2.1-2.6 | Next.js setup + all pages (DONE) |
| Session 7 | 2.7 (partial) | Build verification + bug fixes (DONE) |
| Session 8 | — | Design system research + planning (DONE) |
| Session 9 | 2.7 + 2.8 | UI bug fixes + design system implementation |
| Session 10 | 3.1, 3.2, 3.3 | Testing + E2E verification |

---

## Quality Gates (per task)

1. Ruff lint + format passes (zero errors)
2. All existing tests still pass (no regressions)
3. New tests written and passing
4. PROGRESS.md updated
5. Relevant docs updated (TDD, FSD, data-architecture) if schema/API changed
