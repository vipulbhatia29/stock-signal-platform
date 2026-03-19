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
| B1 | **Refresh token rotation** — invalidate old tokens via Redis/DB blacklist | FSD FR-1.3 | Deferred — security improvement, not blocking Phase 3 |
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
- [x] **7 Internal tools** — analyze_stock, portfolio_exposure, screen_stocks, recommendations, compute_signals, geopolitical (GDELT), web_search (SerpAPI) (Session 35)
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

#### Phase 4C.1 — Chat UI Polish + Code Analysis Fixes

Gaps from spec audit + code analysis (Session 37). Grouped by priority.

**Functional fixes (should fix before 4D):**
- [ ] **CSV not wired to in-chat tool cards** — `MessageBubble` renders `MessageActions` with only `content`, never passes `csvData`. Dead code. Fix: extract tabular data from `ToolCall.result` and pass as `csvData` prop.
- [ ] **Session expiry prompt** — clicking an expired session silently loads it. Spec requires a warning prompt with "Start New Chat" button when `is_active === false`.
- [ ] **localStorage session restore** — `CHAT_ACTIVE_SESSION` is saved on switch but never read on mount. Active session lost on page reload.
- [ ] **`tool_calls` type hint** — `save_message()` parameter typed as `dict | None` but receives `list[dict]` at runtime. Fix: `list[dict] | None`.

**Code quality fixes (should fix before 4D):**
- [ ] **Mutable module state** — `let nextId = 0` in `chat-reducer.ts` violates CLAUDE.md rule #7. Fix: use `crypto.randomUUID()`.
- [ ] **Missing type annotations** — `user=Depends(get_current_user)` on all 4 chat endpoints lacks type hint. Fix: `user: User = Depends(...)`.
- [ ] **No OpenAPI metadata** — chat router endpoints have no `summary`/`description` in decorators.
- [ ] **Missing graph guard** — `app.state.stock_graph` access will `AttributeError` if startup failed. Fix: `getattr()` + 503 fallback.
- [ ] **`data: Any` on StreamEvent** — leaks `Any` type across streaming pipeline. Fix: `dict[str, Any] | None`.
- [ ] **`clearError` semantics** — dispatches `STREAM_ERROR("")` to clear. Fix: add `CLEAR_ERROR` action type.
- [ ] **Lazy imports in chat router** — 7 inline imports with no circular dep justification. Move to top-of-file.
- [ ] **Session lookup in router** — inline SQLAlchemy query for session should be a `get_session()` function in `chat_session.py`.

**Performance fixes:**
- [ ] **ReactMarkdown plugin arrays** (HIGH) — `[remarkGfm]` and `[rehypeHighlight]` recreated every render → plugin pipeline reinitializes on each token flush. Fix: hoist to module-level constants.
- [ ] **Artifact dispatch on every flush** — `useEffect` for artifact dispatch fires on every token update. Fix: gate with `!isStreaming` or track dispatched artifacts.
- [ ] **Stale `activeSessionId` in closure** — `queryClient.invalidateQueries` in `sendMessage` captures stale session ID for new-session flows. Fix: use ref.
- [ ] **MessageBubble not memoized** — all bubbles re-render on every token flush. Fix: `React.memo()`.
- [ ] **`dispatch` exposed publicly** — `useStreamChat` exposes raw dispatch, breaking encapsulation. Fix: remove from return, add named callbacks.

**UI polish (can defer to post-4D):**
- [ ] **Artifact bar enhancements** — add Copy button + summary line; persist across page navigation (React context)
- [ ] **Tool card expanded state** — add Copy + CSV buttons in expanded JSON view
- [ ] **Missing tool summaries** — add `portfolio_exposure`, `get_economic_series`, `get_news_sentiment` to `getToolSummary()`
- [ ] **"New messages" scroll pill** — show "↓ New messages" when user scrolled up during streaming
- [ ] **Agent type badge in header** — show "Stock"/"General" badge next to "AI Analyst"
- [ ] **Auto-retry on reconnect** — `navigator.onLine` event listener
- [ ] **Bubble styling alignment** — user: cyan left border; assistant: `bg-card2 border-border`
- [ ] **Duplicated API_BASE + auth retry** — `use-stream-chat.ts` duplicates `API_BASE` and 401 refresh logic from `lib/api.ts`. Extract shared `authenticatedFetch`.

**Dependencies:** None — can be done independently. Functional + code quality + performance fixes should precede Phase 4D.

#### Phase 4D — Query Routing + Tiered Intelligence (after 4C)

**Problem:** All queries currently hit the same model with all tools bound. A simple "What's the S&P at?" burns the same tokens as "Analyze my portfolio's sector concentration vs macro headwinds." This is unsustainable at scale and blocks monetization.

**Core Architecture: Query Router + Model Tiers**

- [ ] **Query Classifier** — lightweight classification (heuristic first, cheap LLM fallback) that determines:
  - Complexity tier: simple (lookup/news) vs analytical (multi-tool reasoning) vs deep (cross-source synthesis)
  - Required tool categories: which data sources the query actually needs
  - Estimated token budget: how much context this query needs
- [ ] **Model Tier System** — map complexity to model:
  - Tier 1 (Simple): Groq Llama / cheap fast model — lookups, news, simple Q&A
  - Tier 2 (Analytical): Claude Haiku or Sonnet — tool-calling, signal analysis
  - Tier 3 (Deep): Claude Sonnet/Opus — multi-step reasoning, portfolio synthesis, SEC filing analysis
- [ ] **Pre-compiled Graph Pool** — N graphs (tier x agent type) compiled at startup, router picks per request
- [ ] **Cost Tracking + Budgets** — per-user token/cost tracking via LLMCallLog, daily/monthly budget caps
- [ ] **Escalation Logic** — if cheap model fails or returns low-confidence, auto-escalate to next tier
- [ ] **Fallback Guarantees** — every tier has a fallback; no query goes unanswered

**Monetization Foundation (product decisions needed in brainstorm):**

- [ ] **User Tier Model** — Free / Pro / Premium with different:
  - Model access (free = Tier 1 only, Pro = Tier 1+2, Premium = all tiers)
  - Daily query limits (free = 20/day, Pro = 100/day, Premium = unlimited)
  - Tool access (free = basic tools, Pro = all internal, Premium = all + MCP adapters)
  - Context window budget (free = 4K, Pro = 16K, Premium = 32K)
- [ ] **Usage Metering** — track tokens, tool calls, model tier per user per day
- [ ] **Paywall UI** — upgrade prompts when hitting limits, tier comparison page
- [ ] **API key management** — users bring their own keys (BYOK) as an alternative to paid tiers

**Why this is separate from 4C:** Routing is a backend optimization + product decision. 4C needs to ship a working chat UI first. Once real conversations generate LLMCallLog data, we'll have actual cost data to set routing thresholds — not guesses.

**Report Generation + Export (brainstorm with routing):**
- [ ] **"Generate Report" agent tool** — agent calls multiple tools, synthesizes into structured document
- [ ] **PDF generation** — `react-pdf` (client) or server-side (Puppeteer/wkhtmltopdf)
- [ ] **Excel export** — SheetJS (`xlsx`) for formatted spreadsheets
- [ ] **Report templates** — "Portfolio Summary", "Stock Analysis", "Screener Results"
- [ ] **Monetization tie-in** — Free: CSV only. Pro: PDF. Premium: branded reports + Excel

**Dependencies:** Phase 4C complete (chat working end-to-end), LLMCallLog data accumulating.

#### Phase 4E — Quick Security Fixes (after 4C/4D, before Phase 5)

HIGH-severity findings from security + code analysis audits. Trivial fixes (~20 min total).

- [ ] **MCP auth bypass** (`backend/main.py:94`) — Apply `MCPAuthMiddleware` to `/mcp` mount. Currently all 22+ tools callable without auth. Fix: 3 lines. Test: verify 401 without JWT.
- [ ] **Chat session IDOR** (`backend/routers/chat.py`) — Add `user_id` ownership check when resuming sessions (`chat_stream`) and loading messages (`get_session_messages`). Fix: ~10 lines. Test: User B cannot access User A's sessions.
- [ ] **Exception info leak** (`backend/agents/stream.py`) — Replace `str(exc)` in error StreamEvent with generic message. Raw exceptions from LangGraph/SQLAlchemy/LLM providers can leak internal hostnames, DB connection strings, file paths. Fix: 1 line. The full exception is already logged server-side via `logger.exception`.
- [ ] **UUID leak in delete 403** (`backend/routers/chat.py:164`) — `str(exc)` in HTTPException detail exposes user UUID + session UUID. Fix: generic "Not authorized to delete this session" message.

**Dependencies:** None — can be done anytime. Placed here to not interrupt 4C/4D feature flow.

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

## Phase 5: Background Jobs + Alerts (Weeks 9-10)

### Goal
Pre-compute signals and send notifications.

### Deliverables
1. **Database models:** ModelVersion, ForecastResult (hypertable), MacroSnapshot (hypertable)
2. **Model versioning:**
   - ModelVersion table tracks training data range, hyperparameters, metrics, artifact path
   - Every ForecastResult links to model_version_id
   - `data/models/` directory for serialized model artifacts
   - Auto-increment version on retrain, only one active per (model_type, ticker)
3. **Celery worker + beat scheduler**
4. **`backend/tasks/refresh_data.py`** — nightly fetch for all watchlist tickers
5. **`backend/tasks/compute_signals.py`** — nightly signal computation + store snapshots
6. **`backend/tasks/run_forecasts.py`** — weekly Prophet forecast with model versioning:
   - Train Prophet per ticker → create ModelVersion row → save artifact → store ForecastResult
   - 3 horizons per ticker: 90d, 180d, 270d
7. **`backend/tasks/evaluate_forecasts.py`** — nightly forecast evaluation loop:
   - Find ForecastResult where target_date ≤ today AND actual_price IS NULL
   - Fill in actual_price and error_pct from StockPrice
   - Aggregate metrics per model_version_id → update ModelVersion.metrics
   - Trigger retrain if accuracy degrades below threshold
8. **`backend/tasks/check_alerts.py`** — check trailing stops, concentration, fundamentals
9. **`backend/tasks/generate_recommendations.py`** — daily recommendation generation:
   - Run after signal computation
   - Apply decision rules from recommendation engine
   - Factor in portfolio state + macro regime
   - Store RecommendationSnapshot rows with price_at_recommendation
10. **`backend/tasks/evaluate_recommendations.py`** — nightly recommendation evaluation:
    - Find recommendations where generated_at + horizon ≤ today AND no outcome exists
    - Evaluate at 3 horizons: 30d, 90d, 180d
    - Compute return vs SPY benchmark, alpha, action_was_correct
    - Store RecommendationOutcome rows
    - Requires SPY in stock universe with daily price data
11. **Notification system:**
    - Telegram bot integration (python-telegram-bot)
    - Daily morning briefing: "3 stocks hit buy signals, portfolio up 1.2%"
    - Real-time alerts for stop-loss triggers
12. **Macro overlay:**
    - FRED API integration for yield curve, VIX proxy, unemployment claims
    - Market regime indicator (risk-on / risk-off / neutral)
13. **Dashboard updates:** pre-computed data loads instantly, last-updated timestamps

### Success Criteria
Signals pre-computed nightly, Telegram alerts firing for configured triggers,
recommendation outcomes evaluated at 30/90/180d horizons with SPY benchmark.

---

## Phase 5.5: Security Hardening (Pre-Launch Gate)

### Goal
Fix remaining MEDIUM-severity security findings before deployment. (HIGH items already fixed in Phase 4E.)

### Deliverables

1. **Refresh token never invalidated** (`backend/routers/auth.py`)
   Old refresh tokens valid for 7 days after refresh/logout. No server-side revocation.
   Fix: Redis blocklist for revoked token JTI claims. (Was backlog item B1, deferred from Phase 3.)

2. **Task status lacks ownership** (`backend/routers/tasks.py`)
   Any authenticated user can poll any task ID.
   Fix: Store task_id to user_id in Redis, check on GET.

### Success Criteria
Both fixed, tests added, security re-audit clean. Dependencies: Phase 4E complete.

---

## Phase 6: Deployment + LLMOps (Weeks 11-12)

### Goal
Deploy to cloud and add LLM observability/gateway.

### Deliverables
1. **Docker Compose** updated with all services containerized
2. **Terraform** for cloud deployment:
   - Container Apps (API, workers, frontend)
   - Managed PostgreSQL + TimescaleDB
   - Managed Redis
   - Container Registry
3. **`deploy.yml`** — wire actual deployment (currently a stub)
4. **LLMOps / Gateway:**
   - LiteLLM or custom gateway for centralized LLM routing
   - Observability dashboard (token usage, cost, latency per provider)
   - Prompt versioning
   - A/B testing between providers
   - Auto-routing based on query complexity
5. **Observability:**
   - structlog JSON logging throughout
   - OpenTelemetry instrumentation on FastAPI + Celery
   - Cloud monitoring integration
6. **Tier 2 MCP integrations:**
   - Unusual Whales MCP (options flow, dark pool, congressional trading)
   - Polygon.io MCP (broader market data)

### Success Criteria
App running in cloud, LLM gateway with cost tracking, Tier 2 data integrations live.

**Note:** MCP server (`/mcp`) and CI/CD pipeline already implemented in Phase 4B/4.5.
