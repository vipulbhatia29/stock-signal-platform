# Progress Log

Track what was built in each Claude Code session.
Full verbose history for sessions 1-22: `docs/superpowers/archive/progress-full-log.md`

---

## Project Timeline (compact)

### Phase 1 — Signal Engine + Database + API (Sessions 1-3)
**Branch:** `feat/initial-scaffold` | **Tests:** 0 → 114 | **Dates:** 2026-03-01 to 2026-03-07

- **Session 1:** Project scaffold — FastAPI + SQLAlchemy async + Alembic + TimescaleDB hypertables + JWT auth + testcontainers fixtures. Pinned `bcrypt==4.2.1` (passlib compat). Docker ports 5433/6380.
- **Session 2:** Signal engine (`tools/signals.py`: RSI, MACD, SMA, Bollinger, composite score 0-10), recommendation engine (`tools/recommendations.py`: BUY/WATCH/AVOID), stock router (7 endpoints), Pydantic schemas. Signal functions are pure (no DB) for testability.
- **Session 3:** Seed scripts (`sync_sp500.py`, `seed_prices.py`), end-to-end verification with real AAPL/MSFT data. Fixed `UserRole` enum `values_callable`. Phase 1 complete.

### Phase 2 — Dashboard + Screener UI (Sessions 4-7)
**Branch:** `feat/initial-scaffold` | **Tests:** 114 → 147 | **Dates:** 2026-03-07

- **Session 4:** Phase 2 requirements spec + CLAUDE.md enhancement (anti-patterns, error handling, security, mock guidelines). Documentation only.
- **Session 5:** Backend pre-reqs — httpOnly cookie auth (dual-mode), StockIndex + membership models, on-demand ingest with delta fetch, bulk signals screener endpoint, signal history endpoint. Migration 002.
- **Session 6:** Full Next.js frontend — login/register, dashboard (index cards, watchlist, search), screener (filters, sortable table), stock detail (price chart, signal cards, signal history). ~25 files.
- **Session 7:** Build verification + 3 ingest bugs fixed (missing ticker arg, wrong signature, Decimal types). E2E browser testing. 5 UI polish items identified.

### Phase 2.5 — Design System + UI Polish (Sessions 8-13)
**Branch:** `feat/initial-scaffold` | **Tests:** 147 → 148 | **Dates:** 2026-03-08 to 2026-03-10 | **PR #1 merged**

- **Session 8:** Design system research (TradingView, Robinhood, Bloomberg patterns). Plan created, no code.
- **Session 9:** Fixed 5 UI bugs + design system foundation — financial CSS vars (gain/loss/neutral), OKLCH fix, `useChartColors()` hook, typography tokens, 5 new components (ChangeIndicator, SectionHeading, ChartTooltip, ErrorState, Breadcrumbs), responsive grids, Bloomberg dark mode.
- **Session 10:** Deferred components — Sparkline, SignalMeter, MetricCard, DensityProvider, sentiment-tinted chart gradients, TradingView column preset tabs on screener.
- **Session 11:** Screener grid view — `price_history` on bulk signals (array_agg), ScreenerGrid component with responsive CSS grid, `useContainerWidth` hook.
- **Session 12:** Entry animations + `prefers-reduced-motion`. CSS keyframes, staggered delays on cards/rows (first 12 only).
- **Session 13:** Verification, deleted 13 stale files, doc sync (PRD/FSD/TDD/project-plan), design principles extracted to global reference. PR #1 merged.

### Phase 3 — Security + B-Sprint + Portfolio (Sessions 14-20)
**Branch:** `feat/phase-3` → `feat/phase-3-portfolio` | **Tests:** 148 → 188 | **Dates:** 2026-03-11 to 2026-03-14 | **PR #2 + PR #3 merged**

- **Session 14:** Security hardening — JWT startup validation, rate limiting on auth (slowapi), CORS restriction, sort column whitelist. Performance indexes (migration 002). Accessibility (ChangeIndicator). 13 Playwright screenshots.
- **Session 15:** B-sprint planning — scoped B2/B3/B4/B5/B7 (B1 deferred, B6/B8 added). Spec + plan docs.
- **Session 16:** B-sprint implementation — Migration 003 (removed_date, last_synced_at, dropped is_in_universe). Sharpe filter. Watchlist price freshness (current_price, RelativeTime, Celery refresh tasks, per-card polling). `sync_sp500.py` rewritten for index membership.
- **Session 17:** B6 Celery Beat auto-refresh (30-min fan-out). B8 acknowledge stale price. PR #2 merged.
- **Session 18:** Portfolio tracker design + plan — FIFO positions, P&L, sector allocation. Scoped to manual entry, single account.
- **Session 19:** Portfolio tracker implementation — models + migration 005, `_run_fifo()` pure FIFO engine, 5 endpoints, frontend portfolio page with KPI/positions/allocation pie/transaction dialog. +25 tests.
- **Session 20:** Portfolio wrap-up — verification, lint fixes, doc sync, PR #3 merged. New branch `feat/phase-3-fundamentals`.

### Phase 3 Fundamentals + Phase 3.5 Start (Sessions 21-22)
**Branch:** `feat/phase-3-fundamentals` → `feat/phase-3.5-portfolio-advanced` | **Tests:** 188 → 218 | **Date:** 2026-03-14 | **PR #4 merged**

- **Session 21:** Fundamentals tool — P/E, PEG, FCF yield, D/E, Piotroski F-Score (9 criteria). Composite score rebalanced to 50% technical + 50% fundamental. FundamentalsCard on stock detail. `fetch_fundamentals` is sync (yfinance) — uses `run_in_executor`.
- **Session 22:** Wired Piotroski into ingest endpoint for 50/50 blending at ingestion time. PR #4 merged. Phase 3.5 item 7: PortfolioSnapshot hypertable + migration 006, Celery Beat daily task, `GET /portfolio/history`, PortfolioValueChart. Item 8 WIP (dividends model + tool started). Gotcha: TimescaleDB hypertable upsert needs `constraint="tablename_pkey"`.

---

## Session 23 — Dividend Tracking + Divestment Rules Design

**Date:** 2026-03-14
**Branch:** `feat/phase-3.5-portfolio-advanced`

**What was done:**

### Phase 3.5 Item 8: Dividend Tracking (COMPLETED)
- [x] `backend/migrations/versions/821eb511d146_007_dividend_payments.py` — TimescaleDB hypertable, composite PK (ticker, ex_date), FK to stocks.ticker, ON CONFLICT DO NOTHING for idempotent upserts
- [x] `backend/schemas/portfolio.py` — `DividendResponse` + `DividendSummaryResponse` schemas
- [x] `backend/tools/dividends.py` — `get_dividend_summary()` async function (total received, trailing-12-month, yield calculation)
- [x] `backend/routers/portfolio.py` — `GET /api/v1/portfolio/dividends/{ticker}` endpoint
- [x] `tests/unit/test_dividends.py` — 9 tests (fetch, normalization, empty/None, exceptions, summary)
- [x] `tests/api/test_dividends.py` — 4 tests (auth, happy path, empty, case-insensitive)
- [x] `frontend/src/types/api.ts` — `DividendPayment` + `DividendSummary` interfaces
- [x] `frontend/src/hooks/use-stocks.ts` — `useDividends()` hook (30-min stale time)
- [x] `frontend/src/components/dividend-card.tsx` — KPI row (Yield, Annual, Total, Payments) + collapsible payment history table
- [x] Stock detail page wired up with `DividendCard` section

### Phase 3.5 Item 9: Divestment Rules Engine (DESIGN COMPLETE)
- [x] Brainstorming: 6 clarifying questions resolved with user
  - On-demand computation (not Celery pre-computed)
  - Alerts bundled into positions endpoint (3 queries total)
  - Inline badges on positions table (no separate alert panel)
  - `composite_score < 3` only (Piotroski not persisted in DB)
  - All thresholds from `UserPreference` model (not hardcoded)
  - Cash reserve deferred to Phase 4
- [x] Design spec: `docs/superpowers/specs/2026-03-14-divestment-rules-engine-design.md`
- [x] Spec review: 2 critical + 6 important issues found and resolved:
  - Piotroski score not in DB → use `composite_score` only
  - Missing `sector` on `PositionResponse` → must add + update `get_positions_with_pnl()`
  - Preferences moved to dedicated `backend/routers/preferences.py`
  - `Field(gt=0, le=100)` validation added
  - `Literal` types for `rule`/`severity`
  - Null safety documented + edge case tests added
- [x] Implementation plan: `docs/superpowers/plans/divestment-rules-implementation.md` (10 steps)

**Key decisions:**
- User thresholds stored in `UserPreference` model (already exists with default values: stop-loss 20%, position 5%, sector 30%)
- Settings accessible via gear icon → shadcn Sheet on portfolio page (not a separate settings page)
- Preferences endpoints at `/api/v1/preferences` in dedicated router (not auth router)
- `_group_sectors()` hardcoded `over_limit: pct > 30` to be updated to use user's `max_sector_pct`

**Test count:** 122 unit + 113 API = 235 total (was 218 → +13 dividend tests + 4 dividend API tests)
**Alembic head:** `821eb511d146` (migration 007 — dividend_payments)
**Current branch:** `feat/phase-3.5-portfolio-advanced`

**Next session — Implement divestment rules engine:**
- Follow `docs/superpowers/plans/divestment-rules-implementation.md` (10 steps)
- Pure rule checker → schemas → sector on positions → preferences router → wire alerts → frontend
- Then: Phase 3.5 items 10-11 (portfolio-aware recommendations, rebalancing)

---

## Session 24 — Divestment Rules Engine Implementation

**Date:** 2026-03-14
**Branch:** `feat/phase-3.5-portfolio-advanced`

**What was done:**

### Phase 3.5 Item 9: Divestment Rules Engine (IMPLEMENTED)
All 10 steps from `docs/superpowers/plans/divestment-rules-implementation.md` completed:

- [x] **Step 1:** `backend/tools/divestment.py` — pure `check_divestment_rules()` function
  - 4 rules: stop_loss (critical), position_concentration (warning), sector_concentration (warning), weak_fundamentals (warning)
  - Null safety: skips rule when dependent value is None
  - Returns `list[dict]` with rule, severity, message, value, threshold
- [x] **Step 2:** `backend/schemas/portfolio.py` — `DivestmentAlert`, `PositionWithAlerts`, `UserPreferenceResponse`, `UserPreferenceUpdate` (with `Field(gt=0, le=100)` validation)
  - Added `sector: str | None` to `PositionResponse`
  - `AlertRule` and `AlertSeverity` as `Literal` types
- [x] **Step 3:** `backend/tools/portfolio.py` — bulk sector fetch in `get_positions_with_pnl()`, parameterized `_group_sectors(max_sector_pct)`, `get_portfolio_summary(max_sector_pct)` uses user pref
- [x] **Step 4:** `backend/routers/preferences.py` — GET/PATCH `/api/v1/preferences` with `_get_or_create_preference()` helper
- [x] **Step 5:** `backend/routers/portfolio.py` — positions endpoint returns `PositionWithAlerts`, 3-query pattern (positions, prefs, signals), summary uses user's `max_sector_pct`
- [x] **Step 6:** `frontend/src/types/api.ts` — `DivestmentAlert`, `UserPreferences`, `UserPreferencesUpdate` interfaces; `sector` + `alerts` on `Position`
  - `frontend/src/lib/api.ts` — `patch<T>()` helper
  - `frontend/src/hooks/use-stocks.ts` — `usePreferences()` + `useUpdatePreferences()` hooks
- [x] **Step 7:** `frontend/src/components/portfolio-settings-sheet.tsx` — inner/outer component pattern (avoids setState-in-useEffect), base-ui `render` prop pattern
- [x] **Step 8:** Portfolio page: `AlertBadges` component, "Alerts" column, gear icon with settings sheet
- [x] **Step 9:** Tests all passing — 129 unit + 121 API = 250 total
  - `tests/unit/test_divestment.py` — 11 tests (all rules, boundaries, null safety, custom thresholds, stacking)
  - `tests/api/test_preferences.py` — 6 tests (auth, defaults, existing, partial update, validation)
  - `tests/api/test_portfolio.py` — 2 new tests (alerts field, alerts respect user prefs)
- [x] **Step 10:** `backend/main.py` — PATCH in CORS, preferences router mounted; lint clean

**Key decisions:**
- Inner/outer component pattern in settings sheet to avoid `setState` in `useEffect` anti-pattern (ESLint rule)
- base-ui v4 uses `render` prop instead of `asChild` on triggers
- `_get_or_create_preference()` shared between preferences and portfolio routers
- TimescaleDB signal subquery: `func.max(computed_at)` grouped by ticker joined back for latest composite_score

**Bugs fixed:**
- FK violation in test: `SignalSnapshotFactory` needs stock flushed before signal insert
- `SheetTrigger asChild` → `render` prop (base-ui v4 API change)
- ruff auto-formatted dividend migration + model (whitespace only)

**Test count:** 129 unit + 121 API = 250 total (was 235 → +7 unit, +8 API)
**Alembic head:** `821eb511d146` (migration 007 — unchanged)
**Current branch:** `feat/phase-3.5-portfolio-advanced`

**Next session — Phase 3.5 continued:**
- Phase 3.5 item 10: Portfolio-aware recommendations upgrade
- Phase 3.5 item 11: Rebalancing suggestions with specific dollar amounts
- Move completed divestment spec + plan to `docs/superpowers/archive/`

---

## Session 25 — Portfolio-Aware Recommendations + Rebalancing

**Date:** 2026-03-15
**Branch:** `feat/phase-3.5-portfolio-advanced`

**What was done:**

### Phase 3.5 Item 10: Portfolio-Aware Recommendations (COMPLETED)
- [x] `backend/tools/recommendations.py` — `PortfolioState` TypedDict; `Action.HOLD` + `Action.SELL` added; `generate_recommendation()` upgraded with `portfolio_state: PortfolioState | None` + `max_position_pct: float = 5.0` params
  - held + score ≥ 8 + at cap → HOLD (HIGH); held + score ≥ 5 → HOLD (MEDIUM); held + score < 5 → SELL (MEDIUM/HIGH)
  - held but under cap still returns BUY (correct fall-through)
- [x] `suggested_amount: float | None = None` added to `RecommendationResult` dataclass and `RecommendationResponse` schema
- [x] `backend/routers/stocks.py` — `ingest_ticker` now does best-effort portfolio context lookup (lazy imports inside try/except to avoid circular deps) and passes `portfolio_state` + `max_position_pct` to `generate_recommendation()`
- [x] 7 new unit tests covering all HOLD/SELL branches + boundary cases

### Phase 3.5 Item 11: Rebalancing Suggestions (COMPLETED)
- [x] `calculate_position_size()` pure function in `backend/tools/recommendations.py`
  - Equal-weight targeting: `target = min(max_position_pct, 100/num_positions)`
  - Returns 0 if sector at cap, position at target, or amount < $100 (MIN_TRADE_SIZE)
  - `available_cash = 0.0` (Phase 3.5: no cash account — conservative default)
- [x] `RebalancingSuggestion` + `RebalancingResponse` Pydantic schemas in `backend/schemas/portfolio.py`
- [x] `GET /api/v1/portfolio/rebalancing` endpoint — per-position BUY_MORE/HOLD/AT_CAP suggestions, sorted BUY_MORE first
- [x] `frontend/src/types/api.ts` — `RebalancingSuggestion` + `RebalancingResponse` interfaces (action typed as union literal)
- [x] `frontend/src/hooks/use-stocks.ts` — `useRebalancing()` hook (5-min stale time)
- [x] `frontend/src/components/rebalancing-panel.tsx` — table showing current/target %, action badge, suggested dollar amount; BUY_MORE rows get green left border + green amount; AT_CAP rows amber badge
- [x] Portfolio page wired up with `RebalancingPanel`
- [x] 6 unit tests for `calculate_position_size()` + 3 API tests for rebalancing endpoint

### Housekeeping
- [x] Divestment spec + plan archived to `docs/superpowers/archive/`
- [x] Plan archived: `docs/superpowers/plans/2026-03-15-portfolio-recommendations-rebalancing.md`

**Key decisions:**
- Double `/api/v1/` prefix bug caught in review: `API_BASE` in `api.ts` already includes `/api/v1/`, so hooks must use `/portfolio/...` relative paths
- `available_cash = 0.0` is explicit in the endpoint docstring — Phase 4 can add a cash balance model without changing `calculate_position_size()` function signature
- Lazy imports (`from backend.routers.portfolio import ...` inside try block) used in `ingest_ticker` to avoid circular imports between stocks and portfolio routers
- AT_CAP badge uses `text-amber-500` (no `--color-warning` CSS var defined in design system yet)

**Test count:** 143 unit + 124 API = 267 total (was 250 → +11 unit, +6 API)
**Alembic head:** `821eb511d146` (migration 007 — unchanged)
**Current branch:** `feat/phase-3.5-portfolio-advanced`

**Next session — Phase 3.5 wrap-up / Phase 4 start:**
- Phase 3.5 items 10-11 complete — remaining: item 12 (Schwab OAuth, Phase 4) + item 13 (multi-account, Phase 4)
- Consider: PR for Phase 3.5 branch, then start Phase 4 (AI Chatbot)
- Or: add `--color-warning` CSS var to design system (minor polish)

---
