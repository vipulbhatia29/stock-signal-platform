# Progress Log

Track what was built in each Claude Code session.

---

## Session 1 — Project Scaffolding

**Date:** 2026-03-01
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Python project initialized with `uv init`, all Phase 1 dependencies added
- [x] `backend/config.py` — Pydantic Settings loading from `backend/.env`
- [x] `backend/database.py` — Async SQLAlchemy engine + session factory
- [x] `backend/main.py` — FastAPI app with CORS, rate limiting (slowapi), health check
- [x] Database models created per `docs/data-architecture.md`:
  - `backend/models/user.py` — User + UserPreference (with UserRole enum)
  - `backend/models/stock.py` — Stock + Watchlist
  - `backend/models/price.py` — StockPrice (TimescaleDB hypertable)
  - `backend/models/signal.py` — SignalSnapshot (TimescaleDB hypertable)
  - `backend/models/recommendation.py` — RecommendationSnapshot (TimescaleDB hypertable)
- [x] Alembic configured for async (env.py reads from Settings)
- [x] Initial migration `001_initial_schema.py` with `create_hypertable()` calls
- [x] Auth system:
  - `backend/dependencies.py` — bcrypt hashing, JWT create/decode, `get_current_user`
  - `backend/routers/auth.py` — POST register, login, refresh
  - `backend/schemas/auth.py` — Pydantic v2 request/response models
- [x] Test foundation:
  - `tests/conftest.py` — testcontainers (real Postgres+TimescaleDB), factory-boy factories (User, UserPreference, Stock), authenticated client fixture
  - `tests/unit/test_health.py` — health check tests
  - `tests/unit/test_dependencies.py` — password hashing + JWT round-trip tests
  - `tests/api/test_auth.py` — register, login, refresh endpoint tests (12 tests)
- [x] All 23 tests pass (`uv run pytest tests/ -v`)
- [x] Docker Compose starts on ports 5433/6380 (to avoid conflicts with other projects)
- [x] `uv run alembic upgrade head` creates all tables + hypertables
- [x] `uv run uvicorn backend.main:app --port 8181` starts server, health check returns OK

**Key decisions:**
- Pinned `bcrypt==4.2.1` (passlib incompatible with bcrypt 5.x)
- Docker ports changed to 5433 (Postgres) and 6380 (Redis) to avoid conflicts
- Test approach: per-test engine + truncate tables (avoids asyncpg event loop issues)

**Next:** Signal engine — `backend/tools/market_data.py`, `backend/tools/signals.py`, `backend/tools/recommendations.py` + stock router endpoints + tests (Phase 1 continued)

---

## Session 2 — Signal Engine + Stock API

**Date:** 2026-03-01
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] `backend/tools/market_data.py` — yfinance OHLCV fetcher:
  - Async wrapper around yfinance (runs in thread pool to avoid blocking)
  - Batch upsert into TimescaleDB (ON CONFLICT DO NOTHING for idempotency)
  - `ensure_stock_exists()` — auto-creates Stock records from yfinance metadata
  - `get_latest_price()` — fetch most recent adj_close from database
- [x] `backend/tools/signals.py` — Technical signal computation engine:
  - RSI(14) with Wilder's smoothed method → OVERSOLD/NEUTRAL/OVERBOUGHT labels
  - MACD(12,26,9) with EMA-based computation → BULLISH/BEARISH labels
  - SMA 50/200 crossover detection → GOLDEN_CROSS/DEATH_CROSS/ABOVE_200/BELOW_200
  - Bollinger Bands(20,2) → UPPER/MIDDLE/LOWER position
  - Annualized return, volatility, Sharpe ratio calculation
  - Composite score (0-10) combining all indicators (4 × 2.5 points each)
  - `store_signal_snapshot()` — upsert into signal_snapshots hypertable
- [x] `backend/tools/recommendations.py` — Recommendation decision engine:
  - Score ≥8 → BUY, 5-7 → WATCH, <5 → AVOID (Phase 1 rules)
  - Confidence levels (HIGH/MEDIUM/LOW) based on score strength
  - Detailed JSONB reasoning with per-signal interpretations
  - `store_recommendation()` — upsert into recommendation_snapshots
- [x] `backend/schemas/stock.py` — Pydantic v2 schemas:
  - StockResponse, StockSearchResponse, PricePointResponse, PricePeriod enum
  - Nested signal schemas: RSIResponse, MACDResponse, SMAResponse, BollingerResponse
  - SignalResponse (full nested structure), RecommendationResponse
  - WatchlistAddRequest, WatchlistItemResponse
- [x] `backend/routers/stocks.py` — REST API endpoints:
  - `GET /api/v1/stocks/search?q=...` — case-insensitive stock search
  - `GET /api/v1/stocks/{ticker}/prices?period=1y` — historical OHLCV data
  - `GET /api/v1/stocks/{ticker}/signals` — latest technical signals (with staleness flag)
  - `GET /api/v1/stocks/watchlist` — user's watchlist (with stock details via JOIN)
  - `POST /api/v1/stocks/watchlist` — add ticker (with 100-ticker limit + duplicate check)
  - `DELETE /api/v1/stocks/watchlist/{ticker}` — remove from watchlist
  - `GET /api/v1/stocks/recommendations` — recent recommendations (24h window, filterable)
- [x] Router mounted in `backend/main.py` at `/api/v1/stocks`
- [x] Test factories added to `tests/conftest.py`:
  - StockPriceFactory, SignalSnapshotFactory, RecommendationSnapshotFactory, WatchlistFactory
- [x] `tests/unit/test_signals.py` — 31 unit tests:
  - RSI: uptrend, downtrend, extreme drop/rally, insufficient data, value range
  - MACD: uptrend bullish, accelerating downtrend bearish, insufficient data
  - SMA: uptrend above 200, downtrend below 200, golden cross detection, insufficient data
  - Bollinger: middle, spike to upper, crash to lower, insufficient data
  - Risk/Return: positive/negative return, volatility, Sharpe positive/negative, insufficient data
  - Composite: max score, min score, mixed mid-range, all-None, within 0-10 range
  - End-to-end: all fields populated, insufficient data, Adj Close preference
- [x] `tests/unit/test_recommendations.py` — 23 unit tests:
  - BUY: score 9+ HIGH confidence, score 8 MEDIUM confidence, boundary tests
  - WATCH: score 7, score 5, MEDIUM/LOW confidence levels
  - AVOID: score 4, score 0 HIGH confidence, score 3 MEDIUM confidence
  - Edge cases: None score, price preserved, ticker preserved, boundary values
  - Reasoning: signal breakdown, returns, score breakdown, RSI interpretation
- [x] `tests/api/test_stocks.py` — 27 API endpoint tests:
  - Search: auth required, by ticker, by name, empty result, missing query
  - Prices: auth required, 404 not found, returns data
  - Signals: auth required, stock not found, no snapshot, full response, stale flag
  - Watchlist: auth, add, unknown ticker, duplicate, get, remove, remove not found, empty
  - Recommendations: auth, empty, returns data, filter by action, filter no match, stale excluded
- [x] All **104 tests pass** (`uv run pytest tests/ -v`)

**Key decisions:**
- All code includes inline educational comments explaining technical analysis concepts
- Signal functions are pure (no DB dependency) for easy unit testing; DB persistence is separate
- MACD test required accelerating downtrend (not constant) because EMA convergence behavior
- Sharpe tests require non-zero noise (smooth series has zero volatility → undefined Sharpe)
- Watchlist endpoints nested under `/api/v1/stocks/watchlist` (not separate router)

**Test count:** 23 (Session 1) → 104 (Session 2) = +81 new tests

**Next:** Seed scripts (`scripts/sync_sp500.py`, `scripts/seed_prices.py`) to populate real stock data, then verify end-to-end: fetch AAPL prices → compute signals → get recommendation via API. After that, Phase 2 (Dashboard UI) or remaining Phase 1 items (Celery tasks for nightly computation).

---

## Session 3 — Seed Scripts + End-to-End Verification + Phase 1 Complete

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] `scripts/sync_sp500.py` — S&P 500 universe sync:
  - Scrapes current S&P 500 constituents from Wikipedia via `pandas.read_html()`
  - Upserts into `stocks` table with sector/industry metadata
  - Marks removed stocks as `is_in_universe=False`
  - Supports `--dry-run` flag for preview
  - Handles ticker format conversion (BRK.B → BRK-B for yfinance compatibility)
- [x] `scripts/seed_prices.py` — Price backfill + signal computation:
  - Fetches OHLCV data via yfinance for specified tickers or full universe
  - Stores prices in TimescaleDB (idempotent upsert)
  - Computes technical signals and stores snapshots
  - Generates recommendations (computed but not persisted — recommendations are user-scoped)
  - Supports `--tickers`, `--universe`, `--period`, `--dry-run` flags
  - Rate-limited (0.5s between tickers) to avoid yfinance throttling
  - Default tickers: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, JPM, V, UNH
- [x] Added `lxml` dependency for `pandas.read_html()`
- [x] Bug fix: `UserRole` enum in `backend/models/user.py` — SQLAlchemy was sending
  uppercase enum names (`"USER"`) instead of lowercase values (`"user"`) to Postgres.
  Fixed with `values_callable=lambda e: [m.value for m in e]`
- [x] End-to-end verification with real data:
  - AAPL: 501 price rows, composite score 4.0, AVOID (MEDIUM confidence)
  - MSFT: 501 price rows, composite score 4.0, AVOID (MEDIUM confidence)
  - API verified: register (201), login (200), signals (200), prices (200), search (200)
  - Idempotent upsert confirmed (re-run skipped 501 duplicates per ticker)
- [x] `tests/unit/test_sync_sp500.py` — 5 tests:
  - DataFrame structure, whitespace stripping, dot-to-dash conversion, exchange is None, all tickers present
- [x] `tests/unit/test_seed_prices.py` — 5 tests:
  - Successful seed, error handling, signal computation, recommendation generation, default tickers
- [x] All **114 tests pass** (`uv run pytest tests/ -v`)

**Key decisions:**
- Recommendations are NOT persisted by seed script (they require `user_id` FK — generated per-user via API)
- Seed script computes recommendations in-memory for logging/verification only
- `scripts/` is a proper Python package (has `__init__.py`) for `python -m scripts.xxx` usage

**Test count:** 104 (Session 2) → 114 (Session 3) = +10 new tests

**Phase 1 Status:** COMPLETE — all deliverables from project-plan.md Phase 1 are done.

**Next:** Phase 2 — Dashboard + Screener UI (Next.js, login page, stock cards with sentiment badges, screener table with filters, stock detail page with charts). See `project-plan.md` Phase 2 for full deliverable list.

---

## Session 4 — Phase 2 Requirements & Documentation Enhancement

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Created `docs/phase2-requirements.md` — comprehensive Phase 2 requirements spec:
  - 5 backend pre-requisites (httpOnly cookie auth, index membership, on-demand ingestion,
    bulk signals endpoint, signal history endpoint)
  - 7 frontend page specs with wireframe layouts (login, register, dashboard, screener,
    stock detail, nav, auth guard)
  - Acceptance criteria (functional, non-functional, testing)
  - Implementation order (backend first, then frontend)
- [x] Enhanced `CLAUDE.md` with 9 new sections:
  - Session Start protocol, Anti-Patterns tables (Python/TS/Architecture),
    Error Handling & Logging standards, Security section with critical files list,
    Troubleshooting table (consolidated gotchas), Mock & Patch Guidelines,
    Documentation Triggers table, TypeScript/Frontend rules, Dependency management rules
- [x] Fixed `.claude/rules/python-backend.md` — changed "structlog" to `logging.getLogger(__name__)`
  (matches actual codebase; structlog is in deps but never imported)
- [x] Updated `project-plan.md` — Phase 2 now includes backend pre-requisites
  (cookie auth, index model, on-demand ingestion, bulk signals, signal history)
- [x] Updated `docs/FSD.md` — added FR-1.5 (httpOnly cookies), FR-2.4 (index management),
  FR-2.5 (on-demand ingestion), FR-7.5 (bulk signals), FR-7.6 (signal history);
  updated Feature × Phase Matrix; fixed structlog references
- [x] Updated `docs/TDD.md` — rewrote JWT flow for cookie auth (Section 9.1),
  added Sections 3.7-3.10 (index, ingestion, bulk signals, signal history endpoints);
  fixed structlog references
- [x] Updated `docs/data-architecture.md` — added StockIndex + StockIndexMembership tables
  to Section 3.1, updated Phase Mapping (Phase 2 row), updated query patterns and
  data seeding strategy

**Key decisions:**
- httpOnly cookies over localStorage (security — XSS protection)
- Stock indexes as separate table with membership (not boolean flags) — supports
  multi-index membership (AAPL in S&P 500 + NASDAQ-100 + Dow 30)
- On-demand ingestion with delta fetch (not full re-fetch for existing tickers)
- Server-side pagination for screener (not client-side — 500 stocks too large)
- stdlib `logging` over structlog for now (structlog migration deferred to production)
- Dark/light theme toggle; mobile layouts deferred

**Test count:** 114 (unchanged — no code changes, only documentation)

**Next:** Begin Phase 2 implementation. Start with backend pre-requisites (cookie auth →
index model + migration → ingestion endpoint → bulk signals → signal history), then
scaffold Next.js frontend and build pages. See `docs/phase2-requirements.md` Section 6
for full implementation order.

---

## Session 5 — Phase 2 Backend Pre-Requisites

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] httpOnly cookie authentication (dual-mode: Authorization header + cookie):
  - `backend/dependencies.py` — `_extract_token()` checks header first, then cookie
  - `backend/routers/auth.py` — login/refresh set cookies via `_set_auth_cookies()`
  - `POST /logout` endpoint added — clears auth cookies
  - `backend/config.py` — added `COOKIE_SECURE` setting
- [x] `backend/models/index.py` — StockIndex + StockIndexMembership models:
  - StockIndex: name, slug (indexed), description
  - StockIndexMembership: ticker FK + index_id FK with unique constraint
- [x] `backend/routers/indexes.py` — Index API endpoints:
  - `GET /indexes` — list all indexes with stock counts (LEFT JOIN + COUNT)
  - `GET /indexes/{slug}/stocks` — paginated stocks with latest price + signal via window functions
- [x] `backend/schemas/index.py` — IndexResponse, IndexStockItem, IndexStocksResponse
- [x] `backend/routers/stocks.py` — 3 new endpoints:
  - `POST /{ticker}/ingest` — on-demand ingestion with ticker validation
  - `GET /signals/bulk` — screener with filters (index, RSI, MACD, sector, score range), sorting, pagination
  - `GET /{ticker}/signals/history` — chronological signal snapshots with days + limit params
- [x] `backend/schemas/stock.py` — added IngestResponse, BulkSignalItem, BulkSignalsResponse, SignalHistoryItem
- [x] `backend/tools/market_data.py` — delta fetch functions:
  - `fetch_prices_delta()` — queries MAX(time), fetches from that date forward
  - `update_last_fetched_at()` — updates Stock.last_fetched_at after fetch
  - `_download_ticker_range()` — yfinance download with start date
- [x] `scripts/sync_indexes.py` — seed S&P 500, NASDAQ-100, Dow 30 index memberships from Wikipedia
- [x] Indexes router mounted in `backend/main.py` at `/api/v1/indexes`
- [x] Test factories: StockIndexFactory, StockIndexMembershipFactory added to conftest.py
- [x] `tests/api/test_auth.py` — expanded from 12 to 20 tests (cookie auth, logout)
- [x] `tests/api/test_indexes.py` — 8 tests for index endpoints
- [x] `tests/api/test_ingest.py` — 4 tests for ingestion endpoint
- [x] `tests/api/test_bulk_signals.py` — 7 tests for screener endpoint
- [x] `tests/api/test_signal_history.py` — 6 tests for signal history
- [x] All **147 tests pass** (`uv run pytest tests/ -v`)

**Key decisions:**
- Dual-mode auth preserves backward compatibility (header takes precedence over cookie)
- Window functions (row_number OVER PARTITION BY) for efficient "latest per ticker" queries
- Lazy imports in ingest endpoint to avoid circular dependency between routers and tools
- Ticker validation via regex pattern `^[A-Za-z0-9.\-]{1,10}$`

**Test count:** 114 (Session 4) → 147 (Session 5) = +33 new tests

**Pending:**
- Alembic migration `002_stock_indexes.py` for new tables (needs Docker running)

**Next:** Phase 2 frontend — Next.js project setup, login/register pages, dashboard,
screener, stock detail page. See `docs/workflow_phase2.md` Tasks 2.1-2.7.

---

## Session 6 — Phase 2 Frontend Build (Tasks 2.1–2.6 in progress)

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Alembic migration `311355a05744` applied (stock_indexes + stock_index_memberships)
  - Removed false TimescaleDB index drops from autogenerated migration
- [x] Serena `project_overview` memory updated to Session 5 state
- [x] CLAUDE.md end-of-session checklist updated (item 7: mandatory Serena memory updates)
- [x] Deleted redundant `PROJECT_INDEX.md` (Serena memories + CLAUDE.md already cover it)
- [x] **Task 2.1 — Next.js project scaffold** (COMPLETE):
  - `npx create-next-app@latest` with TypeScript, Tailwind, App Router, src-dir
  - Installed: `@tanstack/react-query`, `next-themes`, `recharts`
  - shadcn/ui initialized + 20 components added (button, input, card, table, select,
    slider, dropdown-menu, badge, sonner, dialog, popover, command, separator, label,
    tabs, skeleton, sheet, avatar, tooltip, textarea)
  - `next.config.ts` — API proxy rewrites `/api/*` → `localhost:8181`
  - `src/lib/api.ts` — centralized fetch wrapper with cookie auth, auto-refresh on 401
  - `src/lib/auth.ts` — AuthContext + `useAuth` hook (login, register, logout)
  - `src/types/api.ts` — all TypeScript types mirroring backend Pydantic schemas
  - `src/app/providers.tsx` — QueryClient + ThemeProvider + TooltipProvider + AuthProvider + Sonner
  - `src/app/layout.tsx` — root layout with Providers wrapper
  - `src/app/page.tsx` — redirects `/` to `/login`
- [x] **Task 2.2 — Login + Register pages** (COMPLETE):
  - `src/app/login/page.tsx` — email/password form, error display, link to register
  - `src/app/register/page.tsx` — with password confirmation + client-side validation
- [x] **Task 2.3 — Auth guard + Nav layout** (COMPLETE):
  - `src/middleware.ts` — redirects unauthenticated users to `/login`
  - `src/components/nav-bar.tsx` — sticky nav, Dashboard/Screener links, theme toggle, logout
  - `src/app/(authenticated)/layout.tsx` — route group with NavBar + max-w-7xl container
- [x] **Tasks 2.4–2.6 — Component architecture** (IN PROGRESS):
  - Foundation layer created:
    - `src/lib/signals.ts` — sentiment classification, color mappings
    - `src/lib/format.ts` — currency, percent, volume, date formatters
    - `src/hooks/use-stocks.ts` — all TanStack Query hooks (12 hooks total)
  - Shared components created:
    - `score-badge.tsx`, `signal-badge.tsx`, `empty-state.tsx`, `pagination-controls.tsx`
  - Dashboard components created:
    - `ticker-search.tsx` (cmdk autocomplete), `index-card.tsx`, `stock-card.tsx`, `sector-filter.tsx`
    - `dashboard/page.tsx` — fully wired with search, index cards, watchlist grid, sector filter
  - Screener components created:
    - `screener-filters.tsx` (5 filter controls + score slider), `screener-table.tsx` (sortable, color-coded)
    - `screener/page.tsx` — fully wired with URL state management
  - Stock detail components created:
    - `stock-header.tsx`, `price-chart.tsx` (Recharts composed chart), `signal-cards.tsx`,
      `signal-history-chart.tsx` (dual-axis), `risk-return-card.tsx`
    - `stock-detail-client.tsx` — fully wired client component

**Key decisions:**
- shadcn/ui v4 uses `@base-ui/react` (not Radix) — Select, Dialog etc. have different API
- `sonner` replaced deprecated `toast` component in shadcn v4
- Middleware still works in Next.js 16 despite deprecation warning (proxy convention is alternative)
- Server component shell → client component pattern for stock detail (params is async in Next 16)
- Optimistic updates on watchlist removal (immediate UI, rollback on error)
- URL state management on screener via `useSearchParams` (filters bookmarkable)

**Test count:** 147 (unchanged — frontend work, no new backend tests)
**Frontend files created:** ~25 new files in `frontend/src/`

---

## Session 7 — Build Verification, Bug Fixes, E2E Testing

**Date:** 2026-03-07
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Wired `stocks/[ticker]/page.tsx` — server shell rendering `StockDetailClient`
- [x] Fixed 3 TypeScript build errors:
  - `Select.onValueChange` type: shadcn/ui v4 passes `string | null` (4 instances in 2 files)
  - `Slider.onValueChange` type: accepts `number | readonly number[]` not `number[]`
  - `useSearchParams()` requires `<Suspense>` boundary for static prerender (screener page)
- [x] `npm run build` passes (all 8 routes generated)
- [x] `npm run lint` clean
- [x] Backend bug fixes discovered during e2e testing:
  - `compute_signals(df)` → `compute_signals(ticker, df)` — missing ticker arg in ingest endpoint
  - `store_signal_snapshot(ticker, signals, db)` → `store_signal_snapshot(result, db)` — was using wrong signature (dict vs SignalResult)
  - Added `load_prices_df()` to `backend/tools/market_data.py` — loads full price history from DB as DataFrame with `float`/`int` types (not `Decimal`)
  - Ingest endpoint now uses full DB history for signal computation instead of delta-only DataFrame
- [x] Updated `tests/api/test_ingest.py` to match new ingest flow (added `load_prices_df` mock, `SignalResult`-style mock)
- [x] **E2E verification** — all flows tested in browser:
  - Register → Login → Dashboard (empty) → Search AAPL → Ingest + Watchlist → Stock Detail (chart, signals, risk/return) → Screener (table, filters) → Dark mode → Logout → Auth guard redirect
- [x] All **147 tests pass**

**Bugs found during e2e (fixed):**
1. Ingest 500: `compute_signals()` called without `ticker` arg
2. Ingest 500: `store_signal_snapshot()` called with wrong signature
3. Ingest 500: `Decimal` values from DB caused `TypeError` in pandas arithmetic

**Test count:** 147 (unchanged — test mocks updated to match fixed signatures)

**UI polish items for next session:**
- [ ] Screener filter dropdowns show `__all__` as placeholder text instead of proper labels (e.g. "Index: All", "RSI: All")
- [ ] Watchlist stock cards show "N/A" for composite score — watchlist query doesn't JOIN signal data
- [ ] Price chart renders sparse when only ~1 year of data is in DB (chart axis range vs data range mismatch)
- [ ] Stock detail header shows "—" for stock name (not loaded from API)
- [ ] Market Indexes section on dashboard is empty (indexes exist in DB but cards don't render — may be a query or rendering issue)

**Next:** Fix UI polish items above, then commit all Session 6+7 work. After that, proceed to Phase 2 remaining tasks or Phase 3 planning.

---

## Session 8 — Design System Research & Planning (Phase 2.5)

**Date:** 2026-03-08
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Researched financial dashboard UI/UX patterns from TradingView, Robinhood, and Bloomberg Terminal
- [x] Analyzed current frontend codebase (21 shadcn/ui components, 15+ custom components, OKLCH color system)
- [x] Identified critical issues:
  - Chart colors broken: `hsl(var(--chart-1))` references but CSS variables are OKLCH
  - Sentiment colors hardcoded as Tailwind strings in `lib/signals.ts`, not theme-aware
  - Signal cards (grid-cols-2) and risk/return grid (grid-cols-3) have no responsive breakpoints
  - No breadcrumb navigation, no gain/loss indicators, no reusable financial components
  - Section heading pattern repeated 6+ times as raw inline classes
- [x] Created comprehensive design system plan: `.claude/plans/cozy-wandering-backus.md`
  - Color system: financial semantic CSS variables (gain/loss/neutral), chart-specific colors
  - Typography: semantic token constants (PAGE_TITLE, METRIC_PRIMARY, TICKER, etc.)
  - 8 new components: ChangeIndicator, SectionHeading, ChartTooltip, ErrorState, Breadcrumbs, MetricCard, Sparkline, SignalMeter
  - Responsive fixes for signal cards, risk/return, chart heights, sticky table header
  - Dark mode tuning (Bloomberg-inspired), accessibility (WCAG AA, color-blind safe)
  - Screener enhancements (TradingView-inspired column preset tabs — deferred)
- [x] Integrated design system plan into master project documents:
  - Added Phase 2.5 to `project-plan.md` (between Phase 2 and Phase 3)
  - Updated `PROGRESS.md` with Session 8 entry
  - Updated `docs/workflow_phase2.md` with Task 2.8 (design system)
  - Updated `MEMORY.md` with current state

**Key decisions:**
- Design system split into "Phase 2 polish" (do now) and "deferred enhancements" (after Phase 2 sign-off)
- TradingView-inspired screener column presets deferred (enhancement, not Phase 2 requirement)
- Sparkline, MetricCard, SignalMeter deferred (nice-to-have, not Phase 2 scope)
- 5 Session 7 UI bugs must be fixed FIRST before design system work
- All Session 6+7 work must be committed before adding design system changes

**Research sources:** 15 articles analyzed (TradingView docs, Robinhood UX analysis, Bloomberg UX blog, financial dashboard best practices). Full list in `.claude/plans/cozy-wandering-backus.md#sources`

**Test count:** 147 (unchanged — planning session, no code changes)

**Priorities for next session (in order):**
1. Fix 5 UI polish bugs from Session 7
2. Commit all Session 6+7 work (establish baseline)
3. Phase A: Design system foundation (color vars, OKLCH fix, tokens, typography)
4. Phase B: Core components (ChangeIndicator, SectionHeading, ChartTooltip, ErrorState, Breadcrumbs)
5. Phase D: Responsive fixes (signal cards, risk/return, chart heights)
6. Dark mode tuning + accessibility
7. `npm run build` + `npm run lint` verification

→ **ALL COMPLETE in Session 9**

---

## Session 9 — UI Bug Fixes + Phase 2.5 Design System

**Date:** 2026-03-10
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] **Bug #1 — Screener dropdowns showing `__all__`**: @base-ui/react Select doesn't resolve SelectItem labels when popup is closed. Fixed by computing display label explicitly and passing as SelectValue children.
- [x] **Bug #2 — Watchlist score N/A**: Added `row_number()` subquery to watchlist endpoint to join latest composite_score from signal_snapshots. Extended `WatchlistItemResponse` schema + `WatchlistItem` frontend type. Dashboard now passes `score={item.composite_score}` to StockCard.
- [x] **Bug #3 — Price chart sparse**: Added `domain={["auto","auto"]}` to price YAxis — was defaulting to `[0, max]` making all movements look flat.
- [x] **Bug #4 — Stock detail header "—" for name**: Added `useStockMeta()` hook to derive name/sector from watchlist cache. Replaced hardcoded `name={null}` in `stock-detail-client.tsx`.
- [x] **Bug #5 — Market Indexes empty**: Added empty state with seeding instructions instead of silent nothing.
- [x] **Committed bug fixes**: `c0302ac`
- [x] **Phase A — Design System Foundation**:
  - `globals.css`: financial semantic CSS vars (--gain, --loss, --neutral-signal, --chart-price etc.) in both :root and .dark; Bloomberg dark mode (oklch subtle blue undertone)
  - `lib/design-tokens.ts`, `lib/chart-theme.ts` (useChartColors + CHART_STYLE), `lib/typography.ts`
  - `lib/signals.ts`: migrated SENTIMENT_CLASSES from hardcoded Tailwind → CSS variable classes
- [x] **Phase B — Core Components**: ChangeIndicator, SectionHeading, ChartTooltip, ErrorState, Breadcrumbs
- [x] **Phase D — Responsive + Polish**:
  - signal-cards: responsive grid (1/2/4 cols), risk-return: (1/3 cols)
  - Responsive chart heights (250px/400px), sticky screener header, full-row click
  - nav-bar: Sun/Moon icons, score/signal badges with aria-labels
  - price-chart + signal-history-chart: useChartColors + ChartTooltip (fixes OKLCH mismatch)
  - stock-detail: Breadcrumbs added; SectionHeading throughout
- [x] **Build + lint clean**: `npm run build` ✓, `npm run lint` ✓, 75 unit tests ✓
- [x] **Committed design system**: `2cbe7a8`

**Key decisions:**
- useChartColors() uses MutationObserver on `<html class>` to detect dark/light toggle; lazy useState initializer handles initial value (avoids setState-in-effect lint error)
- Bloomberg dark bg: oklch(0.145 0.005 250) — subtle blue undertone reduces eye strain vs pure black
- Semantic color classes (text-gain, text-loss) registered via @theme inline — Tailwind generates utilities from CSS vars

**Test count:** 75 unit (unchanged — frontend-only changes)
**Files created:** 8 new (design-tokens, chart-theme, typography, 5 components)
**Files changed:** 12 existing

**Next:** Session 10 deferred items completed (see below).

---

## Session 10 — Phase 2.5 Deferred Components

**Date:** 2026-03-10
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] `components/sparkline.tsx` — tiny inline Recharts line chart (no axes/grid/tooltip). Props: `data`, `width`, `height`, `sentiment`. Color driven by CSS vars via `useSparklineColor` hook with MutationObserver for dark/light reactivity. Used by chart grid view (next session).
- [x] `components/signal-meter.tsx` — 10-segment horizontal score bar. Segments color-coded: red (1-4), amber (5-6), green (7-10). `role="meter"` with aria attributes. Size sm/default.
- [x] `components/metric-card.tsx` — standardized KPI block (label + value + optional ChangeIndicator). `MetricCardSkeleton` included. Used by RiskReturnCard + IndexCard.
- [x] Refactored `components/risk-return-card.tsx` — 3 ad-hoc metric divs → `MetricCard` with `valueClassName` for color logic.
- [x] Refactored `components/index-card.tsx` — stock count display → `MetricCard`.
- [x] `price-chart.tsx` — sentiment-tinted gradient: computes `trendColor` from first/last price, fills gradient with `colors.gain`/`colors.loss`/`colors.price`. Stroke unchanged.
- [x] `lib/chart-theme.ts` — added `gain` + `loss` to `ChartColors` interface + `resolveChartColors()`.
- [x] `components/screener-table.tsx` — full rewrite with TradingView-style column preset tabs (Overview | Signals | Performance), each backed by a different column set. Signals tab includes `SignalMeter`. Density-aware row padding/text via `useDensity()`.
- [x] `lib/density-context.tsx` — `DensityProvider` + `useDensity()`. Toggles comfortable/compact row density. Persisted to `localStorage`. Lazy initializer avoids setState-in-effect lint error.
- [x] `app/(authenticated)/screener/page.tsx` — added `DensityProvider` wrapper, `DensityToggle` button (AlignJustify/LayoutList icons), `activeTab` state passed to `ScreenerTable`.
- [x] `npm run build` ✓, `npm run lint` ✓

**Key decisions:**
- Lazy `useState(() => ...)` initializer for localStorage reads (avoids `setState` in effect — ESLint `react-hooks/set-state-in-effect` rule)
- `MutationObserver` on `<html class>` attribute for dark/light color reactivity in Sparkline (same pattern as `useChartColors`)
- Column definitions extracted to `COL` record + `TAB_COLUMNS` presets — clean separation between column rendering and tab layout
- `activeTab` state lives in `screener/page.tsx` (not URL) — tab preference is ephemeral UI state, not a bookmark-worthy filter

**Test count:** 147 backend / 75 frontend unit (unchanged — frontend-only changes)
**Files created:** 3 new (`sparkline.tsx`, `signal-meter.tsx`, `metric-card.tsx`, `density-context.tsx`)
**Files changed:** 6 existing

---

## Chart Grid View — Next Session Integration Contract

The chart grid view (deferred) requires these specific changes to pick up cleanly:

**Backend change needed:**
- Add `price_history: list[float]` (30 data points, daily closes) to `BulkSignalItem` Pydantic schema
- Update `GET /api/v1/stocks/signals/bulk` query to include last 30 `adj_close` values per ticker (window function or subquery)
- Update `tests/api/test_bulk_signals.py` mocks

**Frontend changes needed:**
1. Add `price_history: number[] | null` to `BulkSignalItem` in `types/api.ts`
2. Create `components/screener-grid.tsx` — CSS grid of stock cards, each with:
   - Ticker + name header
   - `<Sparkline data={item.price_history} sentiment={scoreToSentiment(item.composite_score)} width={120} height={40} />`
   - Score badge + signal badges
   - Click → navigate to stock detail
3. Add `viewMode: "table" | "grid"` state to `screener/page.tsx`
4. Add `LayoutGrid` / `LayoutList` toggle button beside `DensityToggle`
5. Conditionally render `ScreenerTable` or `ScreenerGrid` based on `viewMode`

**Next:** Phase 3 planning (Agent/chat interface, portfolio tracking, LangChain/LangGraph integration) or chart grid view.

---

## Session 11 — Screener Grid View

**Date:** 2026-03-10
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] **Backend:** Added `price_history: list[float] | None = None` to `BulkSignalItem` Pydantic schema
- [x] **Backend:** Added correlated subquery to `GET /api/v1/stocks/signals/bulk` — returns last 30 `adj_close` values per ticker in chronological order using `aggregate_order_by` (PostgreSQL-specific). Uses two-level pattern: `_last_30_times` inner subquery (DESC LIMIT 30) + `price_sub` scalar subquery (`array_agg` with ORDER BY ASC)
- [x] **Test:** `test_bulk_signals_includes_price_history` — asserts exactly 30 values, all floats, ascending order. All 148 backend tests pass.
- [x] **Frontend:** `frontend/src/hooks/use-container-width.ts` — `useContainerWidth(ref)` hook using `ResizeObserver` for responsive card widths (starts at 160px, corrects on first observe)
- [x] **Frontend:** `frontend/src/components/screener-grid.tsx` — `ScreenerGrid` component: responsive CSS grid (2→3→4→5 cols), C2-style cards (full-width Sparkline top, ticker + signal badges + score below), loading skeleton, keyboard accessibility (Enter + Space)
- [x] **Frontend:** `frontend/src/app/(authenticated)/screener/page.tsx` — `viewMode: "table" | "grid"` state + `ViewModeToggle` button; `DensityToggle` hidden in grid mode; `PaginationControls` rendered on both views
- [x] `npm run lint` ✓, `npm run build` ✓

**Key decisions:**
- `aggregate_order_by` from `sqlalchemy.dialects.postgresql` is required for `array_agg(col ORDER BY ...)` — standard SQLAlchemy `func.array_agg` doesn't support inline ORDER BY
- `useContainerWidth` uses `useState(160)` not lazy initializer — reading `ref.current` during render violates `react-hooks/refs` ESLint rule; ResizeObserver fires synchronously on first observe, so width is correct after mount
- Pagination rendered outside view-mode conditionals (both views), guarded only by `data && data.total > 0`

**Test count:** 148 backend / 75 frontend unit
**Files created:** `use-container-width.ts`, `screener-grid.tsx`
**Files changed:** `schemas/stock.py`, `routers/stocks.py`, `test_bulk_signals.py`, `types/api.ts`, `screener/page.tsx`

**Next:** Phase 3 planning (agent/chat interface, LangChain/LangGraph integration, portfolio tracking)

---

## Session 12 — Entry Animations + prefers-reduced-motion

**Date:** 2026-03-10
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] **CSS foundation** (`globals.css`): Added `@keyframes fade-in` + `@keyframes fade-slide-up`, two Tailwind utility classes (`animate-fade-in`, `animate-fade-slide-up`), and a global `@media (prefers-reduced-motion: reduce)` rule collapsing all animation to `0.01ms`
- [x] **Page transitions** (`layout.tsx`): Added `animate-fade-in` to `<main>` — CSS replays on every route change naturally, no client component or `usePathname` needed
- [x] **IndexCard** (`index-card.tsx`): Added `animationDelay?: number` prop; animation applied to `<Card>` (block) not `<Link>` (inline)
- [x] **StockCard** (`stock-card.tsx`): Added `animationDelay?: number` prop; animation on root `<Card>`
- [x] **Dashboard** (`dashboard/page.tsx`): Index cards stagger at 0/80/160ms; watchlist cards at `Math.min(i,7)*60ms`
- [x] **Screener table** (`screener-table.tsx`): First 12 rows stagger at 30ms each; rows 13+ no animation
- [x] **Screener grid** (`screener-grid.tsx`): First 12 cards stagger at 40ms each; cards 13+ no animation
- [x] **Signal cards** (`signal-cards.tsx`): RSI/MACD/SMA/Bollinger stagger at 0/80/160/240ms
- [x] `npm run lint` ✓, `npm run build` ✓, 75 backend unit tests ✓

**Key decisions:**
- `animate-fade-in` on `<main>` (not a keyed client component) — prevents flash-of-empty-content on App Router navigation
- Animation on `<Card>` not `<Link>` — `transform` ignored on inline `<a>` elements
- `--stagger-delay` CSS custom property set as inline `style` — pure CSS stagger, no JS animation library
- First-12 cap on table rows and grid cards — rows/cards beyond visible fold don't need animation

**Test count:** 148 backend / 75 frontend unit (unchanged)
**Files changed:** `globals.css`, `layout.tsx`, `index-card.tsx`, `stock-card.tsx`, `dashboard/page.tsx`, `screener-table.tsx`, `screener-grid.tsx`, `signal-cards.tsx`

**Next:** Session 13 — Verification, cleanup & doc sync

---

## Session 13 — Verification, Cleanup & Doc Sync

**Date:** 2026-03-10
**Branch:** `feat/initial-scaffold`
**What was done:**

### Stack Verification
- [x] All 75 backend unit tests pass (4.4s)
- [x] Ruff lint: 8 E501 line-too-long errors fixed (wrapped f-strings in `recommendations.py`, wrapped `create_index` in migration)
- [x] Ruff format: 2 files reformatted (`stocks.py`, migration file)
- [x] Frontend ESLint: zero errors
- [x] Frontend build (Turbopack): all 8 routes compiled
- [x] TypeScript `tsc --noEmit`: zero type errors
- [x] FastAPI app import: loads cleanly

### Markdown File Audit & Cleanup
- [x] **Deleted 13 files + 2 directories:**
  - `initial-prompt.md` (one-time bootstrap prompt)
  - `frontend/README.md` (generic create-next-app boilerplate)
  - `.claude/worktrees/` (stale worktree snapshots)
  - `docs/superpowers/` (3 shipped plan/spec files)
  - 7 MkDocs stub pages (all contained only "TODO: Write this page")
  - `docs/dev/` (empty directory after stub deletion)
- [x] **Marked COMPLETED:** `docs/phase2-requirements.md`, `docs/workflow_phase2.md`, `.claude/plans/cozy-wandering-backus.md`
- [x] **Fixed:** `global-claude-md-for-home-dir/CLAUDE.md` (structlog → logging.getLogger), `.serena/memories/project_overview.md` (removed "(not yet built)")
- [x] **Updated `mkdocs.yml`:** removed deleted pages from nav, added TODO comments for future guide creation

### Design Principles Extraction
- [x] **Created `global-claude-md-for-home-dir/design-principles.md`** — cross-project reference for financial UI patterns

### PRD / FSD / TDD / Project Plan Sync
- [x] **PRD.md** (9 edits): status, phase labels, composite score, recommendation status, screener, 3 new sections
- [x] **FSD.md** (15 edits): corrected FRs, added 5 new FRs, updated Feature × Phase Matrix
- [x] **TDD.md** (16 edits): fixed all API contracts, marked Sections 4/5/6 as aspirational, updated frontend structure, added Section 12a
- [x] **project-plan.md**: added 8-item implementation backlog (B1-B8) to Phase 3
- [x] **CLAUDE.md**: added doc triggers for plan cleanup and mkdocs updates

**Key decisions:**
- Unimplemented TDD sections kept as specs for future phases
- Implementation gaps formalized as backlog items B1-B8 in project-plan.md
- Design principles extracted to global reference file for cross-project reuse

**Test count:** 75 unit (unchanged — lint fixes and doc updates only)
**Files deleted:** 13 files + 2 directories
**Files created:** 1 (`design-principles.md`)
**Files changed:** 12 existing

**Next:** Merge PR #1 (`feat/initial-scaffold` → `main`), then Phase 3 planning

---

## Session 14 — Security Hardening, Accessibility & Visual Testing

**Date:** 2026-03-11
**Branch:** `feat/phase-3`
**What was done:**

### Code Analysis & Improvements
- [x] `/sc:analyze` — comprehensive code quality, security, performance, and architecture audit
- [x] **Security: JWT startup validation** (`config.py`) — `validate_production_settings()` warns in dev, raises `RuntimeError` in prod/staging for insecure JWT default or disabled `COOKIE_SECURE`
- [x] **Security: Rate limiting on auth** (`routers/auth.py`) — register 3/min, login 5/min, refresh 5/min via slowapi `@limiter.limit()` decorators
- [x] **Security: Shared rate_limit.py** — extracted `limiter` instance to avoid circular imports (main.py ↔ auth.py)
- [x] **Security: CORS restriction** (`main.py`) — replaced `allow_methods=["*"]` / `allow_headers=["*"]` with explicit allowlists
- [x] **Security: Sort column whitelist** (`routers/stocks.py`) — `_ALLOWED_SORT` set prevents column enumeration via `getattr()`
- [x] **Performance: Alembic migration 002** — 5 indexes on `watchlist.user_id`, `recommendation_snapshots.user_id`, `recommendation_snapshots.generated_at`, `signal_snapshots.computed_at`, `stocks.sector`
- [x] **Accessibility: ChangeIndicator** (`screener-grid.tsx`, `screener-table.tsx`) — replaced color-only annual return text with `ChangeIndicator` component (icon + sign + color for color-blind safety)
- [x] **Test fix:** disabled rate limiter in `conftest.py` test client fixture to prevent flaky auth tests

### Full Visual Testing (Playwright MCP)
- [x] 13 screenshots captured across all pages and modes:
  - Login (dark), Register (light), Dashboard (empty/with-data/light), Stock Detail (AAPL)
  - Screener: Table (Overview), Grid (sparklines), Signals tab, Performance tab
  - Light mode: screener, dashboard, register, login
- [x] Theme toggle (dark ↔ light) verified working
- [x] All screener tab presets (Overview, Signals, Performance) render correctly
- [x] ChangeIndicator accessibility fix confirmed (trending icon + signed value + color)
- [x] No console errors (only cosmetic Recharts width warnings)

**Key decisions:**
- Extracted `rate_limit.py` to break circular import chain (main.py creates app, auth.py imports limiter → both import from shared module)
- Rate limiter disabled during tests via `app.state.limiter.enabled = False` (simpler than per-test override)
- Sort whitelist falls back to `composite_score` for invalid sort columns (graceful degradation, not 400 error)

**Test count:** 148 backend (all passing)
**Files created:** `backend/rate_limit.py`, `backend/migrations/versions/002_add_performance_indexes.py`
**Files changed:** `config.py`, `main.py`, `auth.py`, `stocks.py`, `screener-grid.tsx`, `screener-table.tsx`, `conftest.py`

**Next:** Phase 3 planning (portfolio tracker, fundamentals, agent/chat, backlog B1-B8)

---

## Session 15 — B-Sprint Planning (Brainstorming + Spec + Plan)

**Date:** 2026-03-11
**Branch:** `feat/phase-3`
**What was done:**

### Brainstorming + Design (no code changes)
- [x] Reviewed B1-B8 backlog items collaboratively with user
- [x] **Scoped B-sprint to 4 items** — B1 deferred, B6+B8 promoted to Phase 3
- [x] **B3** — Add `removed_date` to `StockIndexMembership` (soft-delete instead of hard-delete)
- [x] **B4** — Add `last_synced_at` to `StockIndex`, expose in API response
- [x] **B5** — Clean break: drop `is_in_universe` column + sweep all references
- [x] **B7** — Add `sharpe_min` filter to `GET /api/v1/stocks/signals/bulk`
- [x] **B2** — Watchlist current price + freshness UI: `current_price` + `price_updated_at` in response, `RelativeTime` component, per-card refresh icon (amber when >1h stale), "Refresh All" button in watchlist section header with Celery async tasks + per-card spinner polling

### Artifacts created
- [x] Spec: `docs/superpowers/specs/2026-03-11-b-sprint-design.md` (committed `ec0e534`)
- [x] Plan: `docs/superpowers/plans/2026-03-11-b-sprint.md` (committed `667c7f8`) — 4 chunks, 12 tasks, TDD throughout

### Key decisions
- Single Migration 003 covers B3+B4+B5 (atomic DB change)
- Celery task `refresh_ticker_task` uses exponential backoff (5s→10s→20s→40s, max 4 retries)
- `refresh_ticker_task` uses `asyncio.run()` bridge since Celery workers are sync
- "Refresh All" uses live per-task polling (TanStack Query `refetchInterval: 2000`) rather than optimistic UI
- `RelativeTime` format: <1h → "just now", 1-23h → "X hours ago", 1-6d → "X days ago", ≥7d → "Mar 4"
- Task status router lives in `backend/routers/tasks.py` (not `stocks.py`)
- `sync_sp500.py` is a significant rewrite — it currently doesn't touch `StockIndexMembership` at all

**Test count:** 148 (unchanged — planning session only)
**Files created:** spec + plan docs, `.gitignore` updated (added `.superpowers/`, `.serena/`)
**Files changed:** none (planning session)

**Next:** Execute B-sprint implementation plan (Session 16+)

---

## Session 16 — B-Sprint Implementation (B3/B4/B5/B7/B2)

**Date:** 2026-03-11
**Branch:** `feat/phase-3`
**What was done:**

### Chunk 1: Migration 003 (B3 + B4 + B5)
- [x] **B3** — Added `removed_date: Mapped[datetime | None]` to `StockIndexMembership` (soft-delete instead of hard-delete when stock leaves index)
- [x] **B4** — Added `last_synced_at: Mapped[datetime | None]` to `StockIndex`, exposed in `IndexResponse` schema
- [x] **B5** — Removed `is_in_universe` from `Stock` model, `StockResponse` schema, `ensure_stock_exists()`, `frontend/src/types/api.ts`, `StockFactory`, `sync_sp500.py`, `seed_prices.py`
- [x] Alembic migration `003_index_cleanup` (rev `9e985ae6a70f`) — 3 ops: ADD removed_date, ADD last_synced_at, DROP is_in_universe
- [x] `sync_sp500.py` rewritten: now manages `StockIndexMembership` upsert + `removed_date` soft-delete + `last_synced_at` update
- [x] `seed_prices.py` updated: uses index membership subquery instead of `is_in_universe` filter (distinct subquery pattern to avoid duplicates from multi-index membership)

### Chunk 2: B7 — Sharpe Ratio Filter
- [x] Added `sharpe_min: float | None = Query(...)` to `get_bulk_signals()` endpoint
- [x] Filter applied as `WHERE sharpe_ratio >= sharpe_min` when provided
- [x] `test_bulk_signals_sharpe_filter` added inside `TestBulkSignals` class

### Chunk 3: B2 — Watchlist Price + Freshness (Backend)
- [x] `WatchlistItemResponse` schema: added `current_price: float | None` + `price_updated_at: datetime | None`
- [x] Watchlist endpoint: added `latest_price` window function subquery (mirrors `latest_signal` pattern)
- [x] `StockPriceFactory` added to `tests/conftest.py`
- [x] `test_watchlist_returns_price` added to `tests/api/test_watchlist.py`
- [x] `backend/tasks/__init__.py`: bootstrapped Celery app with Redis broker/backend, JSON serializers
- [x] `backend/tasks/market_data.py`: `refresh_ticker_task` with `bind=True`, exponential backoff (4 retries, max 60s), `asyncio.run()` bridge pattern
- [x] `backend/routers/tasks.py`: `GET /api/v1/tasks/{task_id}/status` using `celery.result.AsyncResult`
- [x] `backend/routers/stocks.py`: `POST /api/v1/stocks/watchlist/refresh-all` with `@limiter.limit("2/minute")`
- [x] `backend/main.py`: tasks router mounted at `/api/v1`
- [x] `tests/unit/test_tasks.py` + `tests/api/test_tasks.py` added (4 + 2 = 6 new tests)

### Chunk 4: B2 — Frontend
- [x] `frontend/src/components/relative-time.tsx` — pure `RelativeTime` component: <1h→"just now", 1-23h→"X hours ago", 1-6d→"X days ago", ≥7d→"Mar 4"
- [x] `frontend/src/components/stock-card.tsx` — new props: `currentPrice`, `priceUpdatedAt`, `onRefresh`, `isRefreshing`; price + refresh icon row; amber icon when >1h stale
- [x] `frontend/src/types/api.ts` — added `TaskStatus`, `RefreshTask` types; `WatchlistItem` updated
- [x] Dashboard — "Refresh All" button in watchlist header; `useMutation` + `useEffect` (TanStack Query v5 pattern); per-task polling with `refetchInterval: 2000`; SUCCESS → invalidate watchlist, FAILURE → sonner toast

### Success Checklist Verification
- [x] `grep is_in_universe` → zero results (outside migrations)
- [x] `alembic current` → `9e985ae6a70f (head)`
- [x] `uv run pytest tests/` → 156 passed, 1 warning
- [x] `ruff check` → all checks passed
- [x] `npm run lint` → zero errors
- [x] `npm run build` → zero errors

**Key decisions:**
- `asyncio.run()` bridge in Celery task (Celery workers are sync, tool functions are async)
- Separate `backend/routers/tasks.py` router (task status is not semantically related to stocks)
- No `onSuccess` in TanStack Query v5 — all post-mutation effects via `useEffect` watching `.data`
- Ticker VARCHAR(10) constraint: test tickers kept to ≤10 chars (e.g. "RFRSH" not "REFRESHTEST")

**Test count:** 156 backend (was 148 → +8 new tests)
**Commits:** 6 feature commits on `feat/phase-3`

**Next:** Phase 3 main features (portfolio tracker, fundamentals, agent/chat, B6 auto-refresh, B8 acknowledge endpoint) — or PR for B-sprint if desired

---

## Session 17 — B6 Auto-refresh + B8 Acknowledge + PR #2

**Date:** 2026-03-11
**Branch:** `feat/phase-3`
**What was done:**

### PR #2 — B-sprint merge
- [x] Pushed `feat/phase-3` to remote (11 commits ahead of origin)
- [x] Opened PR #2: "feat: B-sprint — data model cleanup, Sharpe filter, watchlist price freshness"
  - Covers B2/B3/B4/B5/B7 (Sessions 15-16 work)

### B8 — Acknowledge Stale Price
- [x] `price_acknowledged_at: Mapped[datetime | None]` added to `Watchlist` model
- [x] Alembic migration `004_watchlist_acknowledge` (rev `9c7b7e9860b1`) — single ADD column op
- [x] `POST /api/v1/stocks/watchlist/{ticker}/acknowledge` — sets `price_acknowledged_at = now()`
- [x] `WatchlistItemResponse` + `GET /watchlist` now include `price_acknowledged_at`
- [x] Frontend `isStale()` updated: amber shows only when `price_updated_at > price_acknowledged_at`
- [x] `StockCard`: new `priceAcknowledgedAt` + `onAcknowledge` props; dismiss ✕ button when stale
- [x] Dashboard `acknowledgeMutation` wired; invalidates watchlist query on success
- [x] 4 new API tests: happy path, 404, 401, field presence

### B6 — Celery Beat Auto-refresh
- [x] `refresh_all_watchlist_tickers_task`: fan-out coordinator — queries all distinct tickers
  across all user watchlists, dispatches `refresh_ticker_task.delay(ticker)` per ticker
- [x] `beat_schedule` added to `tasks/__init__.py`: fires every 30 minutes
- [x] 3 new unit tests: dispatch count, empty watchlist, beat_schedule config assertion

### Verification
- [x] `alembic current` → `9c7b7e9860b1 (head)`
- [x] `uv run pytest tests/` → 163 passed (was 156 → +7 new tests)
- [x] `ruff check` → zero errors
- [x] `npm run lint` → zero errors
- [x] `npm run build` → clean

**Key decisions:**
- B8: `price_acknowledged_at` stored on `Watchlist` row (no separate table) — single UPDATE, no join
- B8: Amber indicator logic: stale if `price_updated_at > price_acknowledged_at` (re-appears when new price arrives)
- B6: Coordinator-then-workers pattern (single Beat task fans out N Celery tasks) — idiomatic Celery
- B6: 30-minute interval (configurable via beat_schedule if needed)

**Test count:** 163 backend (was 156 → +7)
**Alembic head:** `9c7b7e9860b1`
**Commits:** 1 feature commit on `feat/phase-3`, PR #2 open

**Next:** Merge PR #2 (B-sprint) → Phase 3 main features: portfolio tracker, fundamentals, agent/chat

---

## Session 18 — Portfolio Tracker Design + Plan

**Date:** 2026-03-13
**Branch:** `feat/phase-3-portfolio`
**What was done:**

### Brainstorming + Design
- [x] Reviewed project context: Phase 3 deliverables, existing models, patterns
- [x] Scoped Phase 3 portfolio tracker sprint collaboratively:
  - **In scope:** Transaction log, FIFO positions + P&L, Allocation view (sector pie)
  - **Deferred to Phase 3.5:** Value history chart, dividends, alerts, portfolio-aware recs, rebalancing
  - **Deferred to Phase 4:** Schwab OAuth sync, multi-account (Fidelity/IRA)
- [x] Data source decision: manual entry (B), Schwab OAuth sync deferred
- [x] Single portfolio model (one Schwab taxable account)
- [x] Layout A selected: KPI row + positions table (3fr) + allocation pie (2fr) side-by-side

### Spec + Review
- [x] Wrote design spec: `docs/superpowers/specs/2026-03-13-portfolio-tracker-design.md`
- [x] Spec review: 3 blocking issues fixed:
  - `positions` model clarified to use `TimestampMixin`; `transactions` intentionally omits `updated_at`
  - DELETE transaction pre-validation logic specified (simulate FIFO, reject 422 if strands SELL)
  - Ticker FK error → 422 with helpful message (not 500)
  - Plus: `opened_at` upsert safety, NULL sector → "Unknown", full schema fields enumerated, extra unit test cases

### Implementation Plan
- [x] Wrote 5-chunk implementation plan: `docs/superpowers/plans/2026-03-13-portfolio-tracker.md`
- [x] Plan reviewed by subagent — all issues fixed:
  - Removed spurious `TransactionType` non-enum class
  - `user.py` `TYPE_CHECKING` block guidance clarified (no duplicate blocks)
  - `__init__.py` `__all__` update specified
  - `TransactionCreate` uses `@field_validator` not `model_post_init`
  - `_get_transactions_for_ticker` now returns `"id"` key; delete simulation uses ID-based exclusion
  - `auth_client` fixture uses correct `create_access_token(user.id)` signature
  - Unused `client` params removed from all authenticated test methods
  - Fixed broken `uv run grep` → bare `grep` in verification checklist

**Key decisions:**
- `_run_fifo()` is a pure function (no DB) — testable without async/SQLAlchemy
- `positions` is a DB table not a SQL view — queryable, indexable
- `opened_at` preserved on upsert via explicit SELECT + UPDATE (never ON CONFLICT overwrite)
- FIFO recomputed from scratch on every transaction write/delete (personal portfolio is small)
- Ticker FK error caught in router, returned as 422 not 500

**Test count:** 163 backend (no new tests this session — implementation in next session)
**Alembic head:** `9c7b7e9860b1` (unchanged — migration 005 to be created in next session)
**Commits:** 3 doc commits on `feat/phase-3-portfolio`

**Deferred items logged for Phase 3.5:**
- Portfolio value history chart (Celery daily snapshots)
- Dividend tracking
- Divestment alerts (stop-loss, concentration warnings)
- Portfolio-aware recommendations upgrade
- Rebalancing suggestions

**Next:** Execute implementation plan (`docs/superpowers/plans/2026-03-13-portfolio-tracker.md`) — Chunk 1 (models + migration) → Chunk 2 (FIFO tool) → Chunk 3 (router + tests) → Chunk 4 (frontend) → Chunk 5 (doc sync)

---
