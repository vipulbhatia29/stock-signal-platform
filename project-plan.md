# Stock Signal Platform — Project Plan

## Phase 1: Signal Engine + Database + API (Weeks 1-2)

### Goal
Fetch stock data, compute technical signals, store in database, expose via API.

### Deliverables
1. **Docker Compose** running Postgres+TimescaleDB and Redis
2. **Database models:** User, UserPreference, Stock, Watchlist, StockPrice (hypertable), SignalSnapshot (hypertable)
3. **Alembic migrations** with TimescaleDB hypertable creation
4. **`backend/tools/market_data.py`** — fetch OHLCV via yfinance, store to TimescaleDB
5. **`backend/tools/signals.py`** — compute RSI(14), MACD(12,26,9), SMA 50/200, Bollinger Bands
   - Label each signal: bullish / bearish / neutral
   - Compute composite score (0-10) — Phase 1 uses 100% technical weights
     (Phase 3 rebalances to 50% technical + 50% fundamental, see FSD FR-3.2)
   - Compute annualized return, volatility, Sharpe ratio
6. **`backend/tools/recommendations.py`** — basic recommendation engine:
   - Score ≥8 → BUY, 5-7 → WATCH, <5 → AVOID (no portfolio context yet)
   - Store as RecommendationSnapshot rows
7. **`backend/routers/stocks.py`** — REST endpoints:
   - `GET /api/v1/stocks/{ticker}/signals` — current signals
   - `GET /api/v1/stocks/{ticker}/prices` — historical prices
   - `POST /api/v1/stocks/watchlist` — add ticker to watchlist
   - `GET /api/v1/recommendations` — today's actionable items
8. **Auth:** JWT login/register + refresh endpoint, password hashing, rate limiting (slowapi)
9. **Seed scripts:** `scripts/sync_sp500.py` (stock universe), `scripts/seed_prices.py` (backfill)
10. **Tests:** unit tests for all signal computations, API tests for all endpoints
11. **Verification:** can call API and get computed signals + recommendations for AAPL and MSFT

### Success Criteria
- `uv run pytest` passes with >80% coverage on backend/tools/signals.py
  and backend/tools/recommendations.py
- Can call `GET /api/v1/recommendations` and see actionable BUY/SELL/HOLD items
- JWT refresh flow works end-to-end

---

## Phase 2: Dashboard + Screener UI (Weeks 3-4)

### Goal
Visual dashboard showing watchlist, signals, and a stock screener.
Includes backend pre-requisites (cookie auth, index model, new endpoints).

### Deliverables — Backend Pre-requisites
1. **httpOnly cookie auth** — login/refresh set Secure httpOnly cookies; dual-mode
   auth dependency (cookie + header); `POST /auth/logout` clears cookies
2. **Stock index membership model** — `StockIndex` + `StockIndexMembership` tables;
   Alembic migration; `GET /api/v1/indexes`, `GET /api/v1/indexes/{id}/stocks` endpoints;
   seed scripts for S&P 500, NASDAQ-100, Dow 30
3. **On-demand data ingestion** — `POST /api/v1/stocks/{ticker}/ingest` endpoint;
   delta fetch (only new data since `last_fetched_at`); signal computation after fetch
4. **Bulk signals endpoint** — `GET /api/v1/stocks/signals/bulk` with index filter,
   pagination, RSI/MACD/sector/score filters, sorting; `DISTINCT ON (ticker)` query
5. **Signal history endpoint** — `GET /api/v1/stocks/{ticker}/signals/history`
   returning chronological snapshots (default 90 days, max 365)

### Deliverables — Frontend
6. **Next.js app** with App Router, Tailwind, shadcn/ui, dark/light theme toggle
7. **Login + Register pages** with cookie-based JWT auth flow
8. **Dashboard page** showing:
   - Major index cards (S&P 500, NASDAQ-100, Dow 30) — click navigates to screener
   - User's watchlist as stock cards (ticker, price, sentiment badge, return, last updated)
   - Inline search bar to add tickers to watchlist (triggers ingestion if needed)
   - Sector filter toggle
9. **Screener page** with filterable, sortable table:
   - Columns: Ticker, RSI Signal, MACD, vs SMA 200, Ann. Return, Volatility, Sharpe, Score
   - Filters: Index, RSI state, MACD state, Sector, Composite Score range
   - Row color-coding: green (≥8), yellow (5-7), red (<5)
   - Server-side pagination, URL state for shareable filters
10. **Stock detail page** with:
    - Price chart (Recharts) with 1M/3M/6M/1Y/5Y timeframe selector
    - Signal breakdown cards (RSI, MACD, SMA, Bollinger)
    - Signal history chart (composite score + RSI over time)
    - Risk & return section (annualized return, volatility, Sharpe)
11. **Auth guard** — redirect to login if no valid cookie; auto-refresh on 401
12. **API integration** via TanStack Query + centralized fetch wrapper (cookie auth)

### Success Criteria
- Can register, log in (httpOnly cookies), and be redirected to dashboard
- Dashboard shows index cards and watchlist with live signal data
- Can search and add a new ticker — data is ingested on-demand
- Screener loads 500 stocks in <3 seconds with working filters and sorting
- Stock detail shows price chart + signal breakdown + signal history chart
- Dark/light theme toggle works and persists

---

## Phase 2.5: Design System + UI Polish (Week 4)

### Goal
Establish a cohesive design system informed by TradingView, Robinhood, and
Bloomberg Terminal UI patterns. Fix responsive layout issues, standardize
color/typography tokens, and add financial-specific components.

**Detailed plan:** `docs/superpowers/archive/cozy-wandering-backus.md` (COMPLETED)

### Deliverables — Phase 2 Polish (do now)
1. **Color system overhaul** — financial semantic CSS variables (gain/loss/neutral),
   fix OKLCH/HSL chart color mismatch, migrate hardcoded sentiment classes to CSS vars
2. **Typography tokens** — `lib/typography.ts` with semantic constants (PAGE_TITLE,
   SECTION_HEADING, METRIC_PRIMARY, TICKER, TABLE_NUM)
3. **Chart design system** — `lib/chart-theme.ts` with `useChartColors()` hook,
   standardized `ChartTooltip` component, crosshair cursor
4. **New components:** `ChangeIndicator` (gain/loss with icon+sign+color),
   `SectionHeading`, `ChartTooltip`, `ErrorState`, `Breadcrumbs`
5. **Responsive fixes** — signal cards grid (1/2/4 cols), risk/return grid (1/3 cols),
   responsive chart heights, sticky screener table header
6. **Dark mode tuning** — Bloomberg-inspired warm backgrounds, chart color brightness,
   Sun/Moon toggle icons
7. **Accessibility** — aria-labels on badges, color+icon+sign for all gain/loss
   indicators (WCAG AA compliance)
8. **Fix Session 7 UI bugs** — screener filter placeholders, watchlist score N/A,
   stock detail name, market indexes rendering

### Deliverables — Deferred Enhancements (Phase 2.5+)
9. Screener column preset tabs (TradingView-inspired: Overview | Signals | Performance)
10. `MetricCard`, `Sparkline`, `SignalMeter` components
11. Sentiment-tinted chart gradient (Robinhood-style)
12. Entry animations + `prefers-reduced-motion`
13. DensityProvider (compact/comfortable toggle)
14. Chart grid view toggle for screener

### Success Criteria
- All colors defined as CSS variables, no hardcoded Tailwind sentiment classes
- Charts render correctly in both light and dark mode (OKLCH fix verified)
- Signal cards and risk/return grids responsive at 375px, 768px, 1280px
- All gain/loss indicators use color + icon + sign (accessibility)
- `npm run build` and `npm run lint` pass with zero errors
- Session 7 UI bugs all resolved

---

## Phase 3: Portfolio Tracker + Fundamentals (Weeks 5-6)

### Goal
Track actual positions and add fundamental analysis signals.

### Deliverables — Phase 3 Core (portfolio tracker COMPLETE ✅)

**Spec:** `docs/superpowers/specs/2026-03-13-portfolio-tracker-design.md`
**Plan:** `docs/superpowers/plans/2026-03-13-portfolio-tracker.md` ✅ IMPLEMENTED

1. ✅ **Database models:** Portfolio, Transaction, Position — `backend/models/portfolio.py` + migration 005 (`2c45d28eade6`)
2. ✅ **`backend/tools/portfolio.py`** — `_run_fifo()` pure FIFO engine, position recompute, P&L, sector allocation
3. ✅ **Portfolio API endpoints (5):**
   - `POST /api/v1/portfolio/transactions` — log a BUY/SELL (validates SELL ≤ held shares, ticker FK → 422)
   - `GET /api/v1/portfolio/transactions` — history with optional `?ticker=` filter
   - `DELETE /api/v1/portfolio/transactions/{id}` — pre-validates FIFO integrity before deleting
   - `GET /api/v1/portfolio/positions` — current holdings with live P&L
   - `GET /api/v1/portfolio/summary` — KPI totals + sector allocation breakdown
4. ✅ **Portfolio page** (`/portfolio`): KPI row + positions table (3fr) + allocation pie (2fr), "Log Transaction" dialog
5. ✅ **`backend/tools/fundamentals.py`** — P/E, PEG, FCF yield, debt-to-equity, Piotroski F-Score (Session 21)
6. ✅ **Updated composite score** merging technical (50%) + fundamental (50%) (Session 21)
   - `GET /api/v1/stocks/{ticker}/fundamentals` endpoint added
   - `FundamentalsCard` on stock detail page (P/E, PEG, FCF yield, D/E, Piotroski bar)
   - ✅ Piotroski wired into ingest endpoint for 50/50 blending at ingest time (Session 22)

### Deliverables — Phase 3.5 (deferred — next sprint after core)

7. ✅ **Portfolio value history** — PortfolioSnapshot hypertable, Celery Beat daily task, `GET /portfolio/history`, PortfolioValueChart (Session 22)
8. ✅ **Dividend tracking** — DividendPayment model, migration 007, summary tool, GET endpoint, unit+API tests, DividendCard UI (Session 23)
9. ✅ **Divestment rules engine** (Session 24):
   - Pure `check_divestment_rules()` function with 4 rules (stop-loss, position/sector concentration, weak fundamentals)
   - GET/PATCH `/api/v1/preferences` with configurable thresholds
   - Settings sheet UI on portfolio page (gear icon)
   - Alert badges on positions table (critical=red, warning=amber)
   - 19 new tests (11 unit + 6 preferences API + 2 portfolio alert API)
10. ✅ **`backend/tools/recommendations.py`** — UPGRADE to portfolio-aware (Session 25):
    - `PortfolioState` TypedDict; `Action.HOLD` + `Action.SELL`; portfolio context in `ingest_ticker`
    - held + at cap → HOLD; held + weak → SELL; not held → existing BUY/WATCH/AVOID
11. ✅ **Rebalancing suggestions with specific dollar amounts** (Session 25):
    - `calculate_position_size()` pure function; `GET /api/v1/portfolio/rebalancing`
    - `RebalancingPanel` component on portfolio page (BUY_MORE/HOLD/AT_CAP per position)
12. **Schwab OAuth sync** — Phase 4 dedicated feature
13. **Multi-account support** (Fidelity/IRA) — Phase 4

### Phase 1-2 Implementation Backlog (pre-requisites for Phase 3)

These are specified features that were intentionally deferred or partially implemented
during Phases 1-2. They should be addressed early in Phase 3 since several are
prerequisites for portfolio-aware recommendations.

| # | Item | Source | Why It Matters |
|---|------|--------|----------------|
| B1 | ✅ **Refresh token rotation** — Redis refresh token blocklist | FSD FR-1.3 | Done (Session 50, PR #79) |
| B2 | ✅ **Watchlist: return `current_price` + freshness** | FSD FR-2.2 | Done (Session 16) |
| B3 | ✅ **StockIndexMembership: add `removed_date`** field | FSD FR-2.4 | Done (Session 16, migration 003) |
| B4 | ✅ **StockIndex: add `last_synced_at`** field | FSD FR-2.4 | Done (Session 16, migration 003) |
| B5 | ✅ **Remove `is_in_universe` from Stock model** | FSD FR-2.4 | Done (Session 16, migration 003) |
| B6 | ✅ **Celery Beat 30-min auto-refresh fan-out** | FSD FR-3.3 | Done (Session 17) |
| B7 | ✅ **Sharpe ratio filter** on bulk signals endpoint | FSD FR-7.2 | Done (Session 16) |
| B8 | ✅ **`POST /watchlist/{ticker}/acknowledge`** stale price dismiss | TDD 3.4 | Done (Session 17) |

### Success Criteria
Can log transactions, see portfolio P&L, get rebalancing suggestions.
Implementation backlog items B1-B8 addressed before portfolio-aware features.

---

## Phase 4: UI Redesign + Chatbot + AI Agent (Weeks 7-8)

### Goal
Command-center dark UI shell + natural language AI interface that orchestrates all tools.

### Deliverables

#### Phase 4A — UI Redesign (Sessions 28–29) ✅ COMPLETE
- ✅ **Spec:** `docs/superpowers/specs/2026-03-15-ui-redesign-phase-4-shell-design.md`
- ✅ **Plan:** `docs/superpowers/plans/2026-03-15-ui-redesign-implementation.md`
- ✅ **Design tokens** — navy dark palette replacing OKLCH shadcn defaults, dark-only (`forcedTheme="dark"`)
- ✅ **Typography** — Sora (UI) + JetBrains Mono (numbers) via `next/font/google`; `--font-sora`, `--font-jetbrains-mono` CSS vars
- ✅ **Shell layout** — 54px icon `SidebarNav` + `Topbar` + resizable `ChatPanel` (stub, drag-resize, persisted width)
- ✅ **New components** — `StatTile`, `AllocationDonut`, `PortfolioDrawer`
- ✅ **Dashboard Overview row** — 5 stat tiles with portfolio/signals/allocation data
- ✅ **All component restyling** — screener, stock detail, portfolio, shared atoms updated to navy tokens
- ✅ **SVG Sparkline** — raw `<polyline>` replacing Recharts (jagged financial chart feel)
- ✅ **Frontend tests** — 20 component tests in `frontend/src/__tests__/components/`; Jest upgraded to jsdom env

#### Phase 4B — Financial Intelligence Platform Backend (Session 34+)

**Spec:** `docs/superpowers/specs/2026-03-17-phase-4b-ai-chatbot-design.md` ✅ COMPLETE
**Plan:** `docs/superpowers/plans/2026-03-17-phase-4b-ai-chatbot-implementation.md` ✅ COMPLETE
**JIRA Epic:** KAN-1 ✅ DONE | **PRs:** #12 (→ develop), #13 (→ main) merged

Three-layer MCP architecture: consume external MCPs → enrich in backend → expose as MCP server.

- [x] **Tool Registry** — `backend/tools/registry.py` with BaseTool, ProxiedTool, MCPAdapter, CachePolicy (Session 35)
- [x] **4 MCPAdapters** — EdgarTools (SEC filings), Alpha Vantage (news/sentiment), FRED (macro), Finnhub (analyst/ESG/social) (Session 36)
- [x] **9 Internal tools** — analyze_stock, portfolio_exposure, screen_stocks, recommendations, compute_signals, geopolitical (GDELT), web_search (SerpAPI), search_stocks (DB+Yahoo), ingest_stock (Session 35+38)
- [x] **LLM Client** — provider-agnostic abstraction, fallback chain (Groq → Anthropic → Local), retry with exponential backoff, provider health tracking (Session 35)
- [x] **LangGraph orchestration** — StateGraph with call_model + execute_tools nodes, MemorySaver checkpointer, max 15 iterations (Session 35)
- [x] **Agents** — BaseAgent ABC, StockAgent (full toolkit), GeneralAgent (data + news only), few-shot prompt templates (Session 35)
- [x] **MCP Server** — FastMCP at `/mcp` (Streamable HTTP), JWT auth middleware, mirrors Tool Registry (Session 36)
- [x] **Database models** — ChatSession, ChatMessage, LLMCallLog (hypertable), ToolExecutionLog (hypertable), migration 008 (Session 35)
- [x] **Chat endpoint** — `POST /api/v1/chat/stream` with NDJSON streaming, `GET/DELETE /sessions` (Session 36)
- [x] **Warm data pipeline** — Celery Beat: daily analyst/FRED, weekly 13F, Redis caching (Session 36)
- [x] **Graceful degradation** — per-tool failure isolation, provider fallback, MCP health checks (Session 35-36)
- [x] **Session management** — create/resume/expire (24h), tiktoken sliding window (16K budget), auto_title (Session 36)
- [x] **Lifespan wiring** — main.py startup: ToolRegistry + adapters + LLMClient + LangGraph graphs + MCP mount (Session 36)

#### Phase 4C — Frontend Chat UI (Session 37) ✅ COMPLETE

**Spec:** `docs/superpowers/specs/2026-03-19-phase-4c-frontend-chat-ui.md` ✅
**Plan:** `docs/superpowers/plans/2026-03-19-phase-4c-frontend-chat-ui.md` ✅
**JIRA Epic:** KAN-30 | **Branch:** `feat/KAN-32-chat-ui` (16 commits)

- [x] Backend: error StreamEvent + save_message + chat router persistence (Session 37)
- [x] Frontend: NDJSON parser, CSV export, chat types, TanStack Query hooks (Session 37)
- [x] chatReducer pure state machine + useStreamChat hook with RAF token batching (Session 37)
- [x] 9 chat components: ThinkingIndicator, ErrorBubble, MessageActions, MarkdownContent, ToolCard, MessageBubble, AgentSelector, SessionList, ChatInput (Session 37)
- [x] ArtifactBar with shouldPin rules + ChatPanel major rewrite + layout wiring (Session 37)
- [x] 40 new tests (3 backend + 37 frontend) — 297 total (Session 37)

#### Phase 4C.1 — Chat UI Polish + Code Analysis Fixes ✅ COMPLETE (Session 42)

**JIRA:** KAN-87 | **Branch:** `feat/KAN-87-chat-ui-polish`

**Functional fixes:** ✅ ALL DONE
- [x] CSV wired to tool cards — `extractCsvData()` in MessageBubble
- [x] Session expiry prompt — warning with "Start New Chat" / "View Anyway"
- [x] localStorage session restore — reads `CHAT_ACTIVE_SESSION` on mount
- [x] `tool_calls` type hint — `list[dict] | None` in save_message + schema

**Code quality fixes:** ✅ ALL DONE
- [x] `crypto.randomUUID()` with jsdom fallback
- [x] `user: User = Depends(...)` on all 5 chat endpoints
- [x] OpenAPI `summary`/`description`/`responses` on all chat decorators
- [x] `getattr()` + 503 fallback for missing graphs
- [x] `data: dict[str, Any] | list | str | None` on StreamEvent
- [x] `CLEAR_ERROR` action type added to chat reducer
- [x] All 7 lazy imports moved to top-of-file in chat router
- [x] `_get_session()` helper extracted from 3 inline lookups

**Performance fixes:** ✅ ALL DONE
- [x] Plugin arrays hoisted to module constants
- [x] Artifact dispatch gated on `!isStreaming`
- [x] `activeSessionIdRef` for stale closure fix
- [x] `React.memo()` on MessageBubble
- [x] `dispatch` removed, `setAgentType` exposed

**UI polish (deferred to Phase 4F):**
- [ ] Artifact bar enhancements, tool card buttons, missing tool summaries, scroll pill, agent badge, auto-retry, bubble styling, duplicated API_BASE extraction

#### Phase 4F — UI Migration: Lovable → Production (~26h, 5-6 sessions)

**Gap Analysis:** `docs/lovable/migration-gap-analysis.md`
**Workflow Plan:** `docs/superpowers/plans/2026-03-19-ui-migration-workflow.md`
**Reference Prototype:** https://stocksignal29.lovable.app
**Reference Code:** `docs/lovable/code/stocksignal-source/`

Full UI/UX redesign based on Lovable prototype. 9 phases (UI-1 through UI-9):

- [x] **UI-1: Shell + Design Tokens** (~3h) — PR #41 merged (Session 43). Sidebar (Sectors nav, shadcn Tooltips, LogOut button), Topbar (Activity icon, Bell stub, pulsing dot, AI glow toggle), ChatContext, framer-motion, pulse-subtle/blink/scrollbar-thin tokens
- [x] **UI-2: Shared Components** (~2h) — PR #42 merged (Session 43). ScoreBar, ScoreBadge xs size, SignalBadge WATCH/AVOID/SMA labels, ChangeIndicator prefix/showIcon, AllocationDonut sector link, IndexCard with value/change/sparkline
- [x] **UI-3: Dashboard Redesign** (~3h) — PR #43 merged (Session 43). KPI 5→3 col grid adapt, Market Indexes grid adapt, Action Required + RecommendationRow, Sector Allocation card, Watchlist 4→3 col adapt, useRecommendations hook
- [x] **UI-4: Screener + Stock Detail** (~3h) — PR #44 (Session 43). ScoreBar inline, Held badge, signal descriptions (RSI/MACD/SMA/Bollinger), StockHeader redesign (Close, breadcrumb, Bookmark toggle, price display). Candlestick + benchmark deferred (backend needed)
- [x] **UI-5: Portfolio Redesign** (~2h) — PR #45 (Session 43). Alert icons (AlertOctagon/AlertTriangle), KPI StatTiles with accent gradients, sector concentration warning banner. framer-motion animations deferred to UI-9.
- [ ] **UI-6: Sectors Page (NEW)** (~4h) — New page + 3 backend endpoints (sectors, stocks-by-sector, correlation). AllocationDonut, sector accordions, comparison table, correlation heatmap + table
- [x] **UI-7: Auth Redesign** (~2h) — PR #46 (Session 43). Split-panel login/register, brand showcase (logo glow, feature bullets, sparkline SVG, glowing orbs), Google OAuth stub (toast), styled inputs with icon prefix + focus glow
- [x] **UI-8: Chat Panel Polish** (~1.5h) — PR #47 (Session 43). Agent selector cards (BarChart3/Globe icons, "Choose an Agent"), suggestion chips fill-not-send, pulsing cyan dots thinking indicator, ChatInput forwardRef
- [ ] **UI-9: Animations + Final Polish** (~1.5h) — framer-motion staggered fade-up on all grids, glow effects on CTAs + inputs, scrollbar styling, chat-open grid adaptation on all pages, Playwright E2E verification

**Dependencies:** Phase 4C.1 (quality fixes) must be done first. UI-1 → UI-2 sequential. UI-3/4/5/7 parallelizable. UI-6 needs backend endpoints.

#### Phase 4D — Agent Intelligence Architecture — SPEC + PLAN APPROVED (Session 38)

**JIRA Epic:** KAN-61 | **Stories:** KAN-62 through KAN-68 (7 chunks, 24 tasks, ~14h)
**Spec:** `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md`
**Plan:** `docs/superpowers/plans/2026-03-20-phase-4d-agent-intelligence.md`

Three-phase Plan→Execute→Synthesize agent replacing current ReAct loop:
- **Planner (Sonnet):** Classifies intent, enforces scope (financial only, data-grounded only), generates ordered tool plan, detects stale data → triggers refresh
- **Executor (mechanical, no LLM):** Calls tools in plan order, validates results, retries, circuit breaker. `ingest_stock` is the universal data pipeline — materializes ALL yfinance data to DB
- **Synthesizer (Sonnet):** Confidence scoring (≥65% actionable), bull/base/bear scenarios, collapsible evidence tree, personalized to portfolio, no claims without tool citations

**Key architectural decisions:**
- [x] All yfinance data materialized to DB during ingestion — tools read from DB, not yfinance at runtime
- [x] `ingest_stock` is the single refresh point — chat, search bar, watchlist, Celery nightly all use it
- [x] Chat detects stale data → "Let me refresh and analyze..." → ingest → analysis. Updates all pages.
- [x] Feature-flagged behind `AGENT_V2=true` with rollback plan
- [x] Model tiering: Sonnet plans+synthesizes (2 LLM calls), executor is mechanical ($0)
- [x] Scope enforcement: financial context + peripherals only, speculative/ungroundable queries declined
- [x] Cross-session memory: Level 1 (portfolio + preferences injected at session start)
- [x] Feedback: thumbs up/down + full trace logging (query_id across LLMCallLog + ToolExecutionLog)
- [x] No RAG — structured data via tools, unstructured (10-K sections) small enough for context
- [x] No paid APIs — yfinance covers financials, targets, earnings, profile, growth

**7 implementation chunks:**
- [x] **KAN-62:** Enriched data layer — DB models, migration, ingest pipeline, 4 new tools ✅ Session 39
- [x] **KAN-63:** DB migration — feedback, tier, query_id columns ✅ Session 39
- [x] **KAN-64:** Agent V2 core — feature flag, context, validator, formatter, planner, executor ✅ Session 39
- [x] **KAN-65:** Synthesizer + Graph V2 — synthesizer node, LLMClient tier, 3-phase StateGraph ✅ Session 39
- [x] **KAN-66:** Stream events + router — NDJSON types, feature flag, context injection, feedback ✅ Session 39
- [x] **KAN-67:** Frontend — plan display, evidence, feedback buttons, decline messages ✅ Session 39
- [x] **KAN-68:** Full regression + docs update ✅ Session 39

**Deferred to Phase 4D.1:**
- Celery nightly pre-computation for watchlist stocks (B+C caching)
- Post-synthesis claim verification (hallucination safety net)
- Per-query cost estimation logging

**Deferred to later phases:**
- Monetization (user tiers, usage metering, paywall, BYOK) — needs real usage data first
- Report generation + PDF/Excel export
- MemorySaver → DB-backed checkpointer
- Cross-session memory Level 2+ (analysis summaries, user facts)

#### Phase 4D.2 — Stock Detail Page Enrichment (after 4D)

KAN-62 (Session 39) materialized all enriched data to DB and extended the `GET /stocks/{ticker}/fundamentals` API + `FundamentalsResponse` schema. Frontend TypeScript types updated. The stock detail page can now display enriched data — remaining work is UI components:
- [ ] **Revenue, net income, margins, growth rates** — new FundamentalsCard section or expanded existing card
- [ ] **Analyst price targets** — current vs target range (bar or gauge visualization)
- [ ] **Earnings history** — EPS estimate vs actual chart, beat/miss streak
- [ ] **Company profile** — business summary, employees, website, market cap
- [ ] **Analyst consensus** — buy/hold/sell bar chart

**Dependencies:** ~~Phase 4D Chunk 1 (KAN-62) must be complete~~ ✅ API + data layer done. Only frontend visualization remains.

#### Phase 4E — Security Hardening ✅ COMPLETE (Session 39, PR #35)

11 findings from comprehensive post-4D security audit. All fixed.

**Critical (fixed):**
- [x] **C1: Chat IDOR — messages endpoint** — ownership check added ✅
- [x] **C2: Chat IDOR — stream resume** — ownership check added ✅
- [x] **C3: MCP server unauthenticated** — MCPAuthMiddleware applied ✅

**High (fixed):**
- [x] **H4: Exception strings in NDJSON errors** — generic messages ✅
- [x] **H5: Raw exceptions in tool errors** — all 6 tools sanitized ✅
- [x] **H6: COOKIE_SECURE default** — documented deployment requirement ✅
- [x] **H7: Task status** — documented low-risk (UUID not enumerable) ✅
- [x] **H8: Refresh token in body** — documented dual-transport risk ✅

**Medium (fixed):**
- [x] **M9: Enum validation** — Literal types on query params ✅
- [x] **M10: ContextVar** — reset token stored ✅
- [x] **M11: UUID leak in delete** — generic error messages ✅

**Positive findings:** AGENT_V2 server-side only ✅, $PREV_RESULT no injection ✅, .env gitignored + JWT validated ✅.

#### Phase 4 Bug Sprint (Session 38) ✅ COMPLETE

- [x] **KAN-60** (Highest): Pydantic `args_schema` on all tools — eliminates kwargs double-wrapping (PR #18)
- [x] **KAN-58** (High): Test DB isolation — `tests/api/` no longer destroys dev database (PR #19)
- [x] **KAN-56** (High): Wikipedia 403 fix — switched to `requests` library for index seeding (PR #20)
- [x] **KAN-59** (High): Search autocomplete — Yahoo Finance external search + `SearchStocksTool` + `IngestStockTool` for agent self-service (PR #21)

### Success Criteria
Can ask natural language questions via API (curl/MCP client) and get tool-backed, synthesized answers with data from SEC filings, news, macro, and fundamentals. MCP server callable from Claude Code.

### Phase 4 Pre-flight Bug & UX Backlog (found in Session 26 QA) — ✅ COMPLETE (Session 27)

**Bugs**
- ✅ `GET /portfolio/dividends/{ticker}` — set `retry: 0` on `useDividends`; 404 for unheld tickers no longer retried/noisy

**UX Improvements**
- ✅ **"Add any ticker" open-world search** — `TickerSearch` now shows "Add [TICKER]" fallback item with `PlusCircleIcon` when query matches no DB results and looks like a valid ticker (`TICKER_RE`)
- ✅ **Search empty-state messaging** — "No stocks found" shown when no DB results; "Add new ticker" group shown simultaneously for valid-looking queries

**Polish**
- ✅ Add `--color-warning` CSS var to design system — OKLCH amber in `:root` + `.dark`; `--color-warning` in `@theme`; AT_CAP badge updated to `text-warning border-warning`
- ✅ Signal History x-axis: dynamic `interval={Math.max(0, Math.floor(history.length / 5) - 1)}` — caps at ~5 ticks regardless of data density
- ✅ Price history chart: `interval="preserveStartEnd"` + `minTickGap={60}` — prevents crowded/stale-looking dates on short periods

#### Phase 4.5 — CI/CD + Branching Strategy ✅ COMPLETE (Session 34)
- ✅ **Spec:** `docs/superpowers/specs/2026-03-16-cicd-jira-integration-design.md`
- ✅ **Plan:** `docs/superpowers/plans/2026-03-16-cicd-jira-integration.md`
- ✅ **JIRA Epic:** KAN-22 (DONE) | **PRs:** #7, #8, #9 merged
- ✅ `ci-pr.yml` — 4 parallel jobs (backend-lint, frontend-lint, backend-test, frontend-test)
- ✅ `ci-merge.yml` — 4 sequential jobs (lint → unit+api → integration → build)
- ✅ `deploy.yml` — no-op stub
- ✅ Testcontainers fixture split — sub-level conftests with `db_url` override
- ✅ `uv.lock` committed, `package.json` test script added
- ✅ 5 GitHub Actions Secrets configured
- ✅ Branch protection on `main` + `develop`
- ✅ JIRA: 5-column board, 2 automation rules, GitHub for Jira app
- ✅ Doc catch-up (KAN-29): FSD, TDD, CLAUDE.md updated

---

## Phase 4G: Backend Hardening — Testing, Eval Pyramid, Pre-commit Hooks

**JIRA Epic:** [KAN-73](https://vipulbhatia29.atlassian.net/browse/KAN-73) | **Stories:** KAN-74 through KAN-84 (11 stories, ~211 tests)
**Spec:** `docs/superpowers/specs/2026-03-21-backend-hardening-design.md`

### Goal
Comprehensive backend hardening: test directory restructure, ~211 new tests across 11 stories, LLM-as-Judge evaluation pyramid, pre-commit hooks with agent-aware gating, auto-triage workflow for bugs and backlog.

### Deliverables
- [x] **S0 (KAN-74):** Test directory restructure — flat → domain-organized (Session 41)
- [x] **S1 (KAN-75):** Auth & security hardening — 15 tests (Session 41)
- [x] **S2 (KAN-76):** Ingest & data pipeline — 10 tests (Session 41)
- [x] **S3 (KAN-77):** Signal & recommendation engine — 29 tests (Session 41)
- [x] **S4 (KAN-78):** Agent V2 mocked regression + adversarial — 42 tests (Session 41)
- [x] **S5 (KAN-79):** Eval infrastructure — rubric, judge, golden set (Session 41). Live LLM tests deferred.
- [x] **S6 (KAN-80):** Stock search → ingest flow — 10 tests (Session 41)
- [x] **S7 (KAN-81):** Celery & background jobs — 13 tests (Session 41)
- [x] **S8 (KAN-82):** Tool & MCP coverage — 18 tests (Session 41)
- [x] **S9 (KAN-83):** API contract hardening — 10 tests (Session 41)
- [x] **S10 (KAN-84):** Pre-commit hooks + ci-eval.yml workflow (Session 41)

### Backlog Items (identified during design, target Phase 5) — ALL COMPLETE
- [x] **Session entity registry** — ✅ Done: Phase 5 S8 (KAN-114, EntityRegistry on AgentStateV2)
- [x] **Stock comparison tool** — ✅ Done: Phase 5 S8 (CompareStocksTool)
- [x] **Context-aware planner prompt** — ✅ Done: Phase 7 KAN-160 (response_type routing + 6 few-shots)
- [x] **Dividend sustainability tool** — ✅ Done: Phase 5 S9 (KAN-115)
- [x] **Risk narrative tool** — ✅ Done: Phase 5 S9 (KAN-115)
- [x] ~~**Red flag scanner**~~ — Superseded: short interest added to StockIntelligenceTool (Session 66, PR #135)

### Deferred Backend Work (from Phase 4F UI-4, Session 43)
- [x] **Candlestick chart toggle (backend)** — ✅ Backend done: KAN-150 (format=ohlc, Session 64). Frontend toggle deferred to UI polish.
- [x] **Benchmark comparison chart (backend)** — ✅ Backend done: KAN-151 (PR #134). Frontend chart deferred to UI polish.
- [x] **KAN-98: Hydration mismatch** — Fixed in Session 44 (PR #50).

### Deferred to Phase 5.1 — CLOSED (Session 66 audit)
- [x] ~~**Red flag scanner**~~ — Superseded (Session 66)
- ~~**Telegram notifications**~~ REMOVED
- [x] ~~**Forecast blending**~~ — CLOSED: ReAct agent synthesizes all signals dynamically. Rigid formula adds less value. If screener sort needs forecast input, revisit as product decision.
- [x] **Live LLM eval tests** — Moved to SaaS Launch Roadmap (rescoped for ReAct loop)

### GitHub Secrets Required
- [ ] **CI_GROQ_API_KEY** (required) — primary LLM for agent eval calls
- [ ] CI_ANTHROPIC_API_KEY (optional) — fallback + Haiku judge for eval scoring

### Success Criteria
- ~211 new tests passing
- Test directory restructured, all existing 546 tests still green
- Pre-commit hooks installed and working
- Eval baseline established (all 8 dimensions above threshold)
- 0 hallucinations in eval suite
- All bugs auto-triaged to JIRA
- All backlog items assigned to Phase 5

---

## Phase 5: Forecasting, Evaluation & Background Automation (~33h, 6-7 sessions)

### Goal
Self-healing nightly pipeline, Prophet forecasting (stocks + sector ETFs + portfolio), recommendation evaluation against actuals, drift detection, in-app alerts, 6 new agent tools.

### Design Docs
- **Spec:** `docs/superpowers/specs/2026-03-22-phase5-forecasting-design.md`
- **Plan:** `docs/superpowers/plans/2026-03-22-phase5-forecasting-implementation.md`
- **JIRA Epic:** KAN-106 (11 Stories: KAN-107–117)

### Stories (11)
- [x] **S1 (KAN-107):** DB Models + Migration + ETF Seeding (~3h) ✓ Session 46, PR #54
- [x] **S2 (KAN-108):** Pipeline Infrastructure — watermark, run logging, gap recovery (~3h) ✓ Session 46, PR #55
- [x] **S3 (KAN-109):** Nightly Pipeline Chain + Beat Schedule (~3h) ✓ Session 46, PR #56
- [x] **S4 (KAN-110):** Prophet Forecasting Engine — training, prediction, model versioning (~4h) ✓ Session 46, PR #57
- [x] **S5 (KAN-111):** Forecast + Recommendation Evaluation + Drift Detection (~3h) ✓ Session 46, PR #58
- [x] **S6 (KAN-112):** In-App Alerts Backend + API (~3h) ✓ Session 46, PR #60
- [x] **S7 (KAN-113):** Forecast + Scorecard API Endpoints (~2h) ✓ Session 46, PR #59
- [x] **S8 (KAN-114):** Agent Tools — Forecast + Comparison + Entity Registry (~4h) ✓ Session 47, PR #62
- [x] **S9 (KAN-115):** Agent Tools — Scorecard + Sustainability + Risk (~3h) ✓ Session 47, PR #63
- [x] **S10 (KAN-116):** Frontend — Forecast Card + Dashboard Tiles (~3h) ✓ Session 47, PR #64
- [x] **S11 (KAN-117):** Frontend — Scorecard Modal + Alert Bell + Sectors ETF (~2h) ✓ Session 47, PR #65

### Key Architecture Decisions (from Session 45 brainstorm)
- Stock-level Prophet forecasts + 11 SPDR sector ETFs; portfolio forecast derived by weighted aggregation with correlation-based confidence bands
- Biweekly retrain (Sunday 2 AM), daily predict-only refresh, drift-triggered retrain on MAPE >20% or volatility spike
- Forecasts as parallel signal (not blended into composite score — deferred to 5.1 pending accuracy validation)
- BUY/SELL recommendations evaluated at 30/90/180d vs SPY benchmark
- In-app alerts only (Telegram deferred to 5.1)
- PipelineWatermark for gap detection, PipelineRun for observability, per-ticker atomicity
- VIX regime flag for forecast confidence overlay
- Sharpe direction enrichment on every forecast

### Success Criteria
- ✅ Nightly pipeline runs end-to-end (price → signal → recommendation → forecast → evaluation → alerts)
- ✅ Self-healing: gap recovery, rate limit retry, partial success
- ✅ ~99 new tests passing (888 total)
- ✅ Agent can answer "forecast for AAPL", "compare AAPL and MSFT", "how accurate are your calls"
- ✅ Scorecard modal + alert bell + forecast card visible in UI
- ✅ (Session 48) Full data bootstrap scripts, nightly chain expanded 3→8 steps, README + diagram documentation

---

## Phase 5.5: Security Hardening (Pre-Launch Gate) ✅ COMPLETE (Session 50)

**JIRA Epic:** KAN-118 (DONE) | **PR:** #79 (squash-merged to develop)

### Deliverables

- [x] **Redis refresh token blocklist** — JTI claim on refresh tokens, `backend/services/token_blocklist.py`
- [x] `decode_token()` returns `TokenPayload(user_id, jti)` dataclass
- [x] `/refresh` checks blocklist before issuing, blocklists old token after rotation
- [x] `/logout` blocklists refresh token from cookie
- [x] 12 new tests (6 unit + 5 API + 1 JTI uniqueness)

### Success Criteria
✅ Fixed, tests added, all CI green.

---

## Phase 5.6: MCP-First Tool Architecture (stdio)

### Goal
Refactor the agent to consume tools via MCP protocol (stdio transport) instead of direct in-process Python calls. This establishes the MCP abstraction now so that any future app (mobile, Telegram bot, Slack integration) can consume the same tools without reimplementing discovery/calling logic. The transport swaps to Streamable HTTP in Phase 6 with zero tool/schema changes.

### Architecture Decision (Session 49)

**Current (monolith):**
```
Chat Agent → ToolRegistry → tool.execute()  [in-process, direct Python calls]
MCP Server (/mcp) → ToolRegistry → tool.execute()  [parallel, unused by agent]
```

**Phase 5.6 (stdio MCP):**
```
Chat Agent → MCP Client → stdio → MCP Tool Server (subprocess, same machine)
Celery tasks → direct calls (no MCP, keep simple)
Claude Code → /mcp endpoint (already works, Streamable HTTP)
```

**Phase 6 (Streamable HTTP MCP):**
```
Chat Agent → MCP Client → HTTP → MCP Tool Server (separate container, :8282)
Celery tasks → MCP Client → HTTP → MCP Tool Server (same endpoint)
Claude Code / Telegram / Mobile → MCP Client → HTTP → MCP Tool Server
```

**Key insight:** stdio and Streamable HTTP are independent transport decisions. The tool definitions, schemas, client calls, and auth stay identical across both. Only the transport config changes.

### Deliverables

1. **MCP Tool Server (stdio mode)** — standalone script that registers all 20 tools from ToolRegistry and serves via stdio transport. Own DB connection pool.
2. **MCP Client in agent** — agent executor calls tools via MCP client instead of `tool.execute()`. Planner/Synthesizer unchanged.
3. **Lifespan management** — FastAPI lifespan spawns stdio subprocess, manages lifecycle.
4. **Celery stays direct** — background tasks (nightly pipeline) continue calling tools in-process. No MCP overhead for batch jobs.
5. **New tools built MCP-first** — any Phase 4D.1 or future tools register in the MCP Tool Server from day one.
6. **Tests** — verify agent works identically via MCP stdio as via direct calls. Integration test for tool server lifecycle.

### Trade-offs

| Aspect | Direct (current) | stdio MCP (Phase 5.6) | HTTP MCP (Phase 6) |
|--------|------------------|----------------------|---------------------|
| Latency | ~0 (in-process) | ~0 (local pipes) | ~1-5ms (network) |
| Process model | Single process | Subprocess | Separate container |
| DB access | Shared session factory | Own connection pool | Own connection pool |
| New client apps | Reimplement tool calls | Connect via MCP | Connect via MCP |
| Scaling | Monolith | Monolith | Independent scaling |

### Design Docs
- **Spec:** `docs/superpowers/specs/2026-03-23-phase-5.6-mcp-stdio-design.md` ✅
- **Plan:** `docs/superpowers/plans/2026-03-23-phase-5.6-mcp-stdio-implementation.md` ✅
- **JIRA Epic:** KAN-119 | **Refinement:** KAN-121 (DONE)

### Implementation Stories (6 + validation)
- [x] **S1 (KAN-132):** MCP Tool Server — entry point, registry builder extract, ToolResult serialization (~2.5h) ✓ PR #81
- [x] **S2 (KAN-133):** MCP Tool Client — MCPToolClient class, user context injection (~2h) ✓ PR #82
- [x] **S3 (KAN-134):** Lifespan Wiring + Feature Flag — subprocess manager, MCP_TOOLS=True, fallback (~2h) ✓ PR #83
- [x] **S4 (KAN-135):** Health Endpoint + Observability (~1.5h) ✓ PR #84
- [x] **S5 (KAN-136):** Integration Tests — real stdio round-trip, lifecycle, regression MCP vs direct (~2.5h) ✓ PR #86, Session 51
- [x] **S6 (KAN-131):** Validation — verify against spec+plan, full test suite, docs ✓ Done

### Key Architectural Decisions (Session 50 brainstorm)
- FastMCP server + `mcp` Python SDK client (both official Anthropic)
- `MCP_TOOLS=True` by default — CI always tests MCP path, flag = emergency kill switch
- 3-restart fallback to direct calls + health endpoint reporting degraded state
- Pass `user_id` as explicit param for portfolio tools (no ContextVar across process boundary)
- Real stdio integration tests (not just mocked)
- No new dependencies needed (`mcp` package already installed)

### Success Criteria
- Agent produces identical responses via stdio MCP as via direct calls
- Tool server subprocess starts/stops cleanly with FastAPI lifespan
- Health endpoint reports MCP status (ok/degraded/disabled)
- Feature flag kill switch works (MCP_TOOLS=false falls back)
- All existing tests pass (no regression) + ~34 new tests
- Integration tests with real stdio subprocess

### Dependencies
Phase 5.5 (security) ✅ DONE. No cloud infrastructure needed.

---

## Phase 6: LLM Factory, Observability & Testing Infrastructure

### Goal
Data-driven multi-model LLM cascade, proactive rate limiting, agent observability, expanded E2E testing. Addresses all architecture gaps identified in the aset-platform comparison brainstorm (Session 53).

### Design Docs
- **Spec 6A:** `docs/superpowers/specs/2026-03-25-llm-factory-cascade-design.md`
- **Spec 6B:** `docs/superpowers/specs/2026-03-25-agent-observability-design.md`
- **Spec 6C:** `docs/superpowers/specs/2026-03-25-testing-infrastructure-design.md`
- **Backlog:** `docs/superpowers/specs/2026-03-25-architecture-gaps-backlog.md`
- **Plan 6A:** `docs/superpowers/plans/2026-03-25-llm-factory-cascade-plan.md`

### Phase 6A — LLM Factory & Cascade ✅ (Session 54)
- [x] V1 deprecation (remove `AGENT_V2` flag, delete V1 graph, rename graph_v2→graph)
- [x] `llm_model_config` table (data-driven cascade, Alembic migration 012)
- [x] Multi-model GroqProvider cascade (budget-aware, error-classified)
- [x] TokenBudget async sliding-window tracker (TPM/RPM/TPD/RPD, 80% threshold)
- [x] Tier config wiring (planner→cheap models, synthesizer→quality models)
- [x] Groq error recovery (APIError/APIStatusError/APIConnectionError → cascade)
- [x] Tool result truncation for synthesizer (configurable per-result cap)
- [x] Admin API (model CRUD, reload, health)
- [x] ProviderHealth.mark_exhausted() bug fix
- [x] Documentation updates (TDD, FSD, Swagger, Serena memories)

### Phase 6B — Agent Observability ✅ (Session 55)
- [x] ObservabilityCollector (async, in-memory real-time metrics)
- [x] LLMCallLog writes (every LLM call: success + cascade failures)
- [x] ToolExecutionLog writes (every tool call from executor)
- [x] Tier health classification (healthy/degraded/down/disabled)
- [x] Admin endpoints (llm-metrics, tier-health, tier-toggle, llm-usage)
- [x] ContextVars for request-scoped session_id/query_id
- [x] Dashboard LLM usage API endpoint (via admin/llm-usage)

### Phase 6C — Testing Infrastructure (Session 55: cleanup + scaffold)
- [x] ~55 new unit/integration tests for 6A/6B components *(done during 6A+6B)*
- [x] Test suite cleanup: deleted 11 duplicate root files, relocated 2 orphans (Session 55)
- [x] Playwright POM scaffolding: config, base page, login page, dashboard page, auth fixture, selectors (Session 55)
- ~~[ ] ~27 new E2E tests~~ STALE — Playwright POM selectors outdated after Phase 4F UI rewrite. Start fresh if needed.
- ~~[ ] CI E2E job~~ DEFERRED — revisit after cloud deploy when E2E adds value
- ~~[ ] data-testid attributes~~ STALE — many components rewritten since scaffold

### Success Criteria
- LLM cascade silently handles all Groq errors — user never sees "internal error" ✅
- Model config changeable via DB + admin API without redeploy ✅
- Escalation rate to Anthropic tracked and queryable ✅
- 716 unit + 226 API + 7 e2e + 24 integration + 107 frontend = ~1,080 total tests
- E2E tests cover all critical user flows *(pending — Playwright POM ready, tests next session)*

---

## Phase 7: Bug Fixes, UX Polish & Feature Backlog

### Goal
Address remaining backlog items, UI gaps, and feature requests identified across all phases.

### Deliverables

#### KAN-148: Redis Cache ✅ (Session 55, PR #100)
- [x] CacheService with 3-tier namespace (app/user/session), TTL tiers, cache-aside
- [x] Cache warmup on startup, agent tool session cache, nightly invalidation

#### KAN-158: Spec A — Agent Guardrails ✅ (Session 56, PR #102)
- [x] Input guard (length, injection, PII, control chars)
- [x] Output guard (evidence check, disclaimer)
- [x] Multi-turn abuse tracking (decline_count on ChatSession, migration 013)
- [x] Tool param validation (ticker format, query sanitization)
- [x] 5 new planner decline examples + 9 adversarial tests

#### KAN-159: Spec C — Data Enrichment ✅ (Session 56, PR #103)
- [x] Stock model: add beta, dividend_yield, forward_pe (migration 014)
- [x] News endpoint (yfinance + Google News RSS with defusedxml)
- [x] Intelligence endpoint (upgrades, insider, earnings, EPS revisions)
- [x] Dividend sync in ingest + nightly pipeline
- [x] Nightly beta/yield/PE refresh

#### KAN-160: Spec B — Agent Intelligence ✅ (Session 56, PR #104)
- [x] 4 new tools: portfolio_health, market_briefing, get_stock_intelligence, recommend_stocks
- [x] 6 new planner few-shots + response_type routing in graph state
- [x] API endpoints: GET /portfolio/health, GET /market/briefing
- [x] Portfolio health schemas split from infra health

#### KAN-161: Spec D — Health Materialization ✅ (Session 56, PR #105)
- [x] PortfolioHealthSnapshot model + migration 015 (TimescaleDB hypertable)
- [x] Celery Beat task at 4:45 PM + nightly chain Step 9
- [x] GET /portfolio/health/history endpoint + 3 API tests
- [x] Extracted compute_portfolio_health() standalone function

#### Remaining Backlog (KAN-149–157 + Schwab Import) — Audit Session 66
- [ ] **Schwab CSV Import** — parse Schwab "Positions" CSV export, create BUY transactions + auto-ingest tickers. Low priority.
- [x] ~~KAN-149: Portfolio aggregation tool~~ — superseded by KAN-160 ✅ Closed
- [x] KAN-150: Candlestick OHLC endpoint ✅ Session 64
- [x] KAN-151: Benchmark comparison endpoint ✅ Session 66 (PR #134)
- [x] KAN-153: Chat audit trail ✅ Session 66 (PR #133)
- [x] KAN-154: Centralized API input validation ✅ Session 64
- [x] KAN-156: ~~Red flag scanner~~ — Superseded ✅ Session 66
- [x] ~~KAN-155: Forecast blending~~ — CLOSED: agent synthesizes dynamically ✅ Session 66
- [ ] KAN-162: Langfuse Self-Hosted — **Reopened Session 67.** Visual trace waterfall + eval framework. ~2 days. Slots after Phase B.
- [ ] KAN-152: Google OAuth — **Moved to SaaS Launch Roadmap**
- [ ] KAN-157: Live LLM eval — **Moved to SaaS Launch Roadmap** (rescoped for ReAct)

#### Deferred (UI) — Low Priority
- [x] ~~UI-6: Sectors Page~~ ✅ Done (Session 45)
- [x] ~~UI-9: Animations~~ — Already done in Phase 4A (Session 29). Entry animations + prefers-reduced-motion. CLOSED.
- [ ] Earnings card on stock detail page — Frontend-only, data exists via StockIntelligenceTool. Low priority.
- [ ] Candlestick toggle (frontend) — Backend done (KAN-150). Needs Line/Candle pill on stock detail.
- [ ] Benchmark chart (frontend) — Backend done (KAN-151). Needs 3-line comparison chart.

### Success Criteria
Guardrails deployed. Portfolio health answerable. Market briefing tool works. 24 agent tools (was 20). All free data from yfinance exploited. ✅ Achieved (KAN-158, 159, 160 shipped in Session 56).

---

## Phase 7.5: Code Analysis Tech Debt (Session 58)

### Goal
Address findings from comprehensive `/sc:analyze` audit. Security, performance, architecture improvements.

### Epic: KAN-163 — Code Analysis Tech Debt

#### Shipped (Session 58, PRs #110-116)
- [x] KAN-175: TDD + FSD + Architecture doc refresh (PR #110)
- [x] KAN-164: Migrate python-jose → PyJWT — unmaintained dep with CVE (PR #111)
- [x] KAN-165: Fix N+1 in portfolio forecast — 40→3 queries (PR #112)
- [x] KAN-166: Fix N+1 in portfolio summary — 20→1 query (PR #113)
- [x] KAN-167: Remove str(e) from HTTPException details (PR #114)
- [x] KAN-169: Parallelize market briefing with asyncio.gather (PR #115)
- [x] KAN-171: Fix 4 ESLint unused variable warnings (PR #116)

#### Remaining
- [x] KAN-168: Add pagination to transactions + recommendations (~1h) ✅ Session 59
- [x] KAN-170: Extend CacheService to uncached endpoints (~2h) ✅ Session 59
- [x] KAN-172: Extract service layer from routers ✅ Session 61 (PR #123) — 6 service modules, 49 tests
- [x] KAN-173: Split stocks.py into domain-specific sub-routers ✅ Session 61 (PR #123) — 4 sub-routers
- [x] KAN-174: Evaluate passlib replacement with direct bcrypt (~1h) ✅ Session 59

### Success Criteria
12/12 stories shipped. Service layer fully extracted (Session 61). Unmaintained security dep replaced. Critical N+1 queries fixed. Docs fully refreshed. Coding conventions added to `.claude/rules/`.

---

## Phase 7.6: Scale Readiness — Multi-Worker & SaaS Hardening

### Goal
Fix single-process assumptions, security regressions, and performance bottlenecks identified in the deep architecture audit (Session 59). Required before multi-user cloud deployment.

### Audit Summary
SaaS readiness scored **6.5/10**. Strong async foundation and user isolation, but agent subsystem (TokenBudget, ObservabilityCollector) is per-process, 20+ tools leak `str(e)`, and a ContextVar IDOR regression from Phase 4E was found.

### Deliverables — Security Fixes (Sprint 1, ~5h) ✅ COMPLETE (Session 60, PR #120)
- [x] KAN-177: [Bug] ContextVar tokens not reset in chat_stream — try/finally reset ✅
- [x] KAN-178: [Bug] str(e) leaked in 8 tool ToolResult error paths — safe generic messages ✅

### Deliverables — Quick Performance Wins (Sprint 1, ~3h) ✅ COMPLETE (Session 60, PR #121)
- [x] KAN-179: Cache planner prompt with lru_cache ✅
- [x] KAN-180: [Bug] Health endpoint — Redis ping + DB SELECT 1 + DependencyStatus schema ✅
- [x] KAN-181: Parallelize build_user_context with asyncio.gather (independent sessions) ✅

### Deliverables — Scalability Hardening (Sprint 1+2) — ✅ COMPLETE
- [x] KAN-182: Cache get_current_user in Redis ✅ Session 66 (PR #132) — VOLATILE TTL
- [x] KAN-183: DB pool configurable via env vars ✅ (Session 60, PR #121)
- [x] KAN-184: [Bug] MCP auth middleware ContextVar ✅ (Session 60, PR #120)
- [x] KAN-185: Nightly pipeline parallelized ✅ (Session 60, PR #121)

### Deliverables — Multi-Worker Architecture — ✅ COMPLETE (SaaS Launch Roadmap Phase A)
- [x] KAN-186: TokenBudget → Redis ✅ Session 67 (PR #138)

### Dependencies
None — all findings are independent of feature backlog.

### Success Criteria
- ContextVar IDOR fixed and tested
- Zero `str(e)` in any ToolResult error path
- Health endpoint checks Redis + MCP + DB
- `build_user_context` uses asyncio.gather
- Auth user lookup cached in Redis
- DB pool configurable via env vars
- MCP HTTP portfolio tools work with JWT auth
- Celery tasks use asyncio.gather with semaphore
- TokenBudget works correctly across 2+ Uvicorn workers
- SaaS readiness re-audit scores ≥8/10

---

## Phase 8: Observability Completeness + Agent Redesign Prep

### Goal
Close observability gaps (cost tracking, cache_hit, agent_id, fallback_rate). These are prerequisites for the ReAct agent redesign and dynamic concurrency controller. Backend must be fully instrumented before frontend work.

**JIRA:** KAN-190 (observability gaps), KAN-189 (agent redesign Epic)
**Serena:** `future_work/AgentArchitectureBrainstorming`

### 8A — Observability Completeness ✅ (KAN-190, Session 62)
- [x] Provider base class observability — `_record_success`, `_record_cascade`, `_compute_cost` on LLMProvider ABC
- [x] Anthropic + OpenAI instrumentation (both had zero observability)
- [x] LLMClient cross-provider cascade recording (Groq→Anthropic now visible)
- [x] Wire `cost_usd` on LLMCallLog via `_compute_cost` + pricing from `llm_model_config`
- [x] Populate `cache_hit` on ToolExecutionLog (cache hits now logged as rows)
- [x] Migration 016: `agent_type`, `agent_instance_id`, `loop_step` on both log tables
- [x] ContextVar propagation for `agent_type` + `agent_instance_id`
- [x] `fallback_rate_last_60s()` on ObservabilityCollector (includes cross-provider cascades)
- [x] `GET /admin/observability/query/{query_id}/cost` — per-model + per-tool breakdown
- [x] `ModelConfigLoader.get_pricing_map()` convenience method
- [x] 12 new unit tests + 4 API tests

### 8B — ReAct Loop (KAN-189 Step 1, Session 63) ✅
- [x] S5: Observability loop_step wiring (KAN-203)
- [x] S6: Anthropic multi-turn scratchpad normalization (KAN-204)
- [x] S7: REACT_AGENT feature flag + reason tier seed (KAN-205)
- [x] S8: ReAct loop core — react_loop() async generator + scratchpad + _execute_tools (KAN-206)
- [x] S9: System prompt template + _render_system_prompt() (KAN-207)
- [x] S10+S11: Chat router + main.py — feature flag, conditional graph (KAN-208/209)
- [x] S12: Integration tests + verification + docs (KAN-210)

### 8C — Tool Filtering (KAN-199–202, Session 63) ✅
- [x] Rule-based intent classifier — 8 intents, ticker extraction, pronoun resolution (27 tests)
- [x] Intent → tool group mapping (stock 8, portfolio 8, market 5, comparison 5, simple_lookup 1, general=all) (7 tests)
- [x] Fast path wiring — out_of_scope + simple_lookup bypass graph (0 LLM calls) (3 tests)

### 8D — Dynamic Concurrency Controller — DEFERRED
~~Originally planned as standalone. loop_step already wired in 8A. Concurrency control only matters with multi-agent fan-out (Phase 9A). Merged into SaaS Launch Roadmap Phase D as a dependency of comparison fan-out.~~

### Dependencies
- 8A: independent, do NOW
- 8B: depends on KAN-172 (service layer)
- 8C: alongside 8B
- 8D: after 8A + 8B

### Success Criteria
- cost_usd on every LLM call, cache_hit on every tool call
- ReAct loop passes validation test (adaptive tool selection)
- Planner sees ≤10 tools for single-domain queries
- ConcurrencyController adjusts semaphore based on live fallback_rate

---

## Phase 9: Comparison Fan-Out + Subscriptions — RESCOPED (Session 66 audit)

### 9A — Comparison Fan-Out (rescoped from Multi-Agent, ~15h)
~~Original scope: 4 specialized agents (Stock Research, Portfolio, Orchestrator, Fan-out). Rescoped because the single ReAct agent with tool groups already handles multi-stock and portfolio queries well. Only comparison fan-out adds genuine value (latency: N×8s serial → ~8s parallel).~~

- [ ] Comparison fan-out: asyncio.gather + semaphore for N-stock comparisons
- [ ] ConcurrencyController: reads fallback_rate, adjusts semaphore (moved from 8D)
- [ ] Stagger fan-out with random jitter for rate limit protection

### 9B — Subscription & Monetization (~30h)
- [ ] User model: `subscription_tier`, `subscription_status`, `stripe_customer_id`
- [ ] 3 tiers: Free / Pro / Premium with usage quotas
- [ ] Stripe integration: checkout, webhooks, subscription lifecycle
- [ ] `SubscriptionGuard` middleware: tier + quota enforcement on tool execution
- [ ] `llm_model_config` user_tier filter: route free users to cheap models
- [ ] Frontend: pricing cards, usage meter, paywall modal, billing page
- [ ] JWT claims: `subscription_tier`, `usage_remaining`

### Dependencies
- 9A: Phase 8 complete ✅ (ReAct loop stable, observability wired)
- 9B: KAN-152 Google OAuth should be done first for signup flow

### Success Criteria
- Comparison queries run parallel in ~8s (not N×8s serial)
- Can subscribe via Stripe, tier enforced on agent tool calls

---

## Phase 10: Cloud Deployment + LLMOps

### Goal
Deploy to cloud, swap MCP transport from stdio to Streamable HTTP, production-grade observability.

### Deliverables
1. **Docker Compose** updated with all services containerized (including MCP Tool Server as separate container)
2. **MCP transport swap** — change agent's MCP client from stdio to Streamable HTTP. Tool Server runs as its own container on :8282. Single config change, no tool/schema changes.
3. **Terraform** for cloud deployment:
   - Container Apps (API, workers, frontend, **MCP Tool Server**)
   - Managed PostgreSQL + TimescaleDB
   - Managed Redis
   - Container Registry
4. **`deploy.yml`** — wire actual deployment (currently a stub)
5. **Production Observability:**
   - structlog JSON logging throughout
   - OpenTelemetry instrumentation on FastAPI + Celery
   - Cloud monitoring integration (Grafana/Datadog)
   - Cost dashboards from LLMCallLog data
6. **Tier 2 MCP integrations** (external MCP servers, always Streamable HTTP):
   - Unusual Whales MCP (options flow, dark pool, congressional trading)
   - Polygon.io MCP (broader market data)
7. **Celery → MCP** — background tasks also call tools via Streamable HTTP MCP (optional, enables independent scaling)

### Success Criteria
App running in cloud, MCP Tool Server as separate container, cost tracking live. Any new client app (Telegram, mobile) can connect to MCP Tool Server and use all 20+ tools.

---

## SaaS Launch Roadmap — Backend First (Session 66 audit)

Consolidated execution order. All prior phases complete. This is the critical path to multi-user SaaS launch.

### Phase A: Multi-Worker Correctness ✅ COMPLETE (Session 67, PR #138)
> **No brainstorm needed** — spec exists (KAN-186 description), clear implementation.

| # | Task | JIRA | Brainstorm? | Effort |
|---|------|------|-------------|--------|
| A1 | TokenBudget sliding windows → Redis sorted sets | KAN-186 ✅ | No | ~2 days |
| A2 | ObservabilityCollector admin metrics → read from llm_call_log DB | KAN-186 ✅ | No | ~1 day |

**Why first:** Without this, 2+ Uvicorn workers = 2× overspend on LLM rate limits. Correctness blocker. **RESOLVED.**

### Phase B: Agent Reliability (~2 days)
> **Technical brainstorm needed** — eval framework, test cases, scoring rubric for ReAct loop.

| # | Task | JIRA | Brainstorm? | Effort |
|---|------|------|-------------|--------|
| B1 | Design ReAct eval rubric (tool selection, grounding, loop termination) | KAN-157 | **Technical** | ~0.5 day |
| B2 | Implement eval harness + golden test set (8-10 queries) | KAN-157 | No | ~1 day |
| B3 | CI eval job (weekly scheduled, not per-PR) | KAN-157 | No | ~0.5 day |

**Why second:** Must validate agent quality before exposing to real users. Needs CI_GROQ_API_KEY secret.

### Phase C: Google OAuth + User Acquisition (~3 days)
> **Business + technical brainstorm needed** — account linking policy, PKCE flow design.

| # | Task | JIRA | Brainstorm? | Effort |
|---|------|------|-------------|--------|
| C1 | Brainstorm: account linking (merge on email match? separate accounts?) | KAN-152 | **Business** | ~0.5 day |
| C2 | Brainstorm: PKCE flow, CachedJWKSClient, dual auth (JWT + Google) | KAN-152 | **Technical** | ~0.5 day |
| C3 | Backend: Google OAuth provider, user linking/creation, token exchange | KAN-152 | No | ~1.5 days |
| C4 | Frontend: "Sign in with Google" button, auth flow integration | KAN-152 | No | ~0.5 day |

**Why third:** Unblocks subscriptions (Phase D) and real user signups.

### Phase D: Subscriptions + Monetization (~5 days)
> **Business + technical brainstorm needed** — tier definitions, pricing, Stripe integration.

| # | Task | JIRA | Brainstorm? | Effort |
|---|------|------|-------------|--------|
| D1 | Brainstorm: tier definitions (Free/Pro/Premium), quotas, pricing | NEW | **Business** | ~0.5 day |
| D2 | Brainstorm: Stripe integration, webhook handling, subscription lifecycle | NEW | **Technical** | ~0.5 day |
| D3 | User model: subscription_tier, stripe_customer_id, migration | NEW | No | ~0.5 day |
| D4 | Stripe checkout + webhook endpoints | NEW | No | ~1.5 days |
| D5 | SubscriptionGuard middleware: tier + quota enforcement | NEW | No | ~1 day |
| D6 | LLM tier routing: free users → cheap models | NEW | No | ~0.5 day |
| D7 | Frontend: pricing cards, usage meter, billing page | NEW | No | ~1 day |

**Depends on:** Phase C (Google OAuth for signup flow).

### Phase E: Cloud Deployment (~4 days)
> **Technical brainstorm needed** — cloud provider, infra choices, MCP transport swap.

| # | Task | JIRA | Brainstorm? | Effort |
|---|------|------|-------------|--------|
| E1 | Brainstorm: cloud provider (Azure/AWS/GCP), managed services | NEW | **Technical** | ~0.5 day |
| E2 | Docker Compose: all services containerized (inc. MCP Tool Server) | NEW | No | ~1 day |
| E3 | MCP transport swap: stdio → Streamable HTTP (config change only) | NEW | No | ~0.5 day |
| E4 | Terraform / IaC for cloud infra | NEW | No | ~1.5 days |
| E5 | deploy.yml: wire actual CI/CD deployment | NEW | No | ~0.5 day |

**Depends on:** Phase A (multi-worker correctness).

### Phase F: Comparison Fan-Out (optional, ~2 days)
> **Technical brainstorm needed** — concurrency strategy, rate limit protection.

| # | Task | JIRA | Brainstorm? | Effort |
|---|------|------|-------------|--------|
| F1 | Brainstorm: fan-out pattern, semaphore sizing, fallback stagger | NEW | **Technical** | ~0.5 day |
| F2 | asyncio.gather fan-out for N-stock comparisons | NEW | No | ~1 day |
| F3 | ConcurrencyController: dynamic semaphore from fallback_rate | NEW | No | ~0.5 day |

**Optional:** Single ReAct agent handles comparisons already (serially). Fan-out is a latency optimization, not a blocker.

### Parking Lot (low priority, pick up when needed)
- Schwab CSV import
- Earnings card on stock detail (frontend, data exists)
- Candlestick toggle (frontend, backend done)
- Benchmark chart (frontend, backend done)
- Admin LLM dashboard (frontend, data exists via admin endpoints)
