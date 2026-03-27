# Project Index: stock-signal-platform

Generated: 2026-03-27 | Service Layer + Router Split COMPLETE | Next: KAN-190 (Observability Gaps)

---

## Project Structure

```
stock-signal-platform/
├── backend/                    Python FastAPI backend (~130 .py files)
│   ├── main.py                 App entry + router mounts + startup validation + MCP lifespan
│   ├── config.py               Pydantic Settings (.env) — MCP_TOOLS, MAX_TOOL_RESULT_CHARS
│   ├── database.py             Async SQLAlchemy engine + async_session_factory
│   ├── dependencies.py         JWT auth: get_current_user, create_access_token
│   ├── request_context.py      ContextVar for request-scoped user ID
│   ├── rate_limit.py           slowapi limiter (shared — never import from main.py)
│   ├── agents/                 LangGraph agents — Plan→Execute→Synthesize
│   │   ├── graph.py            Three-phase StateGraph (plan→execute→synthesize)
│   │   ├── planner.py          Intent classification + tool plan generation (LLM)
│   │   ├── executor.py         Mechanical tool executor ($PREV_RESULT, retries, circuit breaker)
│   │   ├── synthesizer.py      Confidence scoring + scenarios + evidence tree (LLM)
│   │   ├── simple_formatter.py Template-based formatter for simple queries (no LLM)
│   │   ├── user_context.py     Build portfolio/preferences context for planner
│   │   ├── result_validator.py Tool result validation (null, stale, source annotation)
│   │   ├── llm_client.py       Provider-agnostic LLM client with tier routing + fallback
│   │   ├── entity_registry.py  EntityRegistry for tool→entity mapping
│   │   ├── token_budget.py     Async sliding-window rate tracker (TPM/RPM/TPD/RPD)
│   │   ├── model_config.py     ModelConfig dataclass + ModelConfigLoader (DB cache)
│   │   ├── guards.py           Input sanitizer, PII redactor, injection detector, output validator
│   │   ├── observability.py    ObservabilityCollector (ContextVars tracing)
│   │   ├── observability_writer.py  Fire-and-forget DB writer for LLM/tool logs
│   │   ├── stream.py           NDJSON stream events
│   │   ├── base.py             Agent base class + tool filter
│   │   ├── stock_agent.py      V1 stock-focused agent
│   │   ├── general_agent.py    V1 general agent
│   │   ├── providers/          LLM providers (Anthropic, Groq, OpenAI)
│   │   └── prompts/            planner.md, synthesizer.md, stock_agent.md, general_agent.md
│   ├── models/                 SQLAlchemy 2.0 ORM models (19 files)
│   ├── routers/                FastAPI endpoint handlers (14 routers, stocks/ is a package)
│   ├── schemas/                Pydantic v2 request/response schemas (15 files)
│   ├── tools/                  24 registered tools + 5 MCP adapters (thin wrappers → services)
│   ├── tasks/                  Celery background jobs (pipeline, forecasting, alerts, evaluation)
│   ├── services/               Service layer (10 modules — business logic lives here)
│   ├── mcp_server/             FastMCP server — stdio tool server + HTTP /mcp endpoint
│   │   ├── server.py           FastMCP server definition (registers all internal tools)
│   │   ├── tool_server.py      Stdio tool server subprocess entry point
│   │   ├── tool_client.py      MCPToolClient — stdio transport with param wrapping
│   │   ├── lifecycle.py        Lifespan manager (start/stop tool server subprocess)
│   │   └── auth.py             MCP JWT auth middleware
│   └── migrations/             Alembic versions (head: 1a001d6d3535 = 015)
├── frontend/                   Next.js 16, React 19, TypeScript, Tailwind v4, shadcn/ui v4
│   └── src/
│       ├── app/                App Router pages + layouts (8 pages)
│       ├── components/         ~45 UI components + 14 chat components + 21 UI primitives
│       ├── contexts/           ChatContext provider
│       ├── hooks/              TanStack Query hooks + chat state management (10 files)
│       ├── lib/                Utilities, auth, design tokens, formatters (13 files)
│       └── types/api.ts        Shared TypeScript API types
├── tests/                      131 test files across 12 domain subdirs
│   ├── unit/                   ~70 files — agents, auth, chat, infra, pipeline, portfolio, etc.
│   ├── api/                    ~20 files — endpoint tests (needs Postgres + Redis)
│   ├── integration/            Agent V2 flow + MCP stdio integration (24 tests)
│   └── e2e/                    eval/ + playwright/ (POM scaffolding + 17 E2E specs)
├── docs/
│   ├── PRD.md                  Product requirements (WHAT + WHY)
│   ├── FSD.md                  Functional spec (acceptance criteria)
│   ├── TDD.md                  Technical design (HOW + API contracts)
│   ├── data-architecture.md    DB schema, TimescaleDB, model versioning
│   └── superpowers/            specs/ (10), plans/ (10), archive/
├── scripts/                    seed_prices.py, sync_sp500.py, sync_indexes.py
├── .github/workflows/          ci-pr.yml, ci-merge.yml, ci-eval.yml, deploy.yml
├── CLAUDE.md                   Project instructions for Claude
├── PROGRESS.md                 Session log (full detail last 3 sessions)
├── project-plan.md             Phased build plan with completions
└── PROJECT_INDEX.md            This file
```

---

## Entry Points

| Entry | Path | Command |
|-------|------|---------|
| Backend API | `backend/main.py` | `uv run uvicorn backend.main:app --reload --port 8181` |
| Frontend | `frontend/` | `cd frontend && npm run dev` (port 3000) |
| Celery worker | `backend/tasks/` | `uv run celery -A backend.tasks worker` |
| Celery beat | `backend/tasks/` | `uv run celery -A backend.tasks beat` |
| DB migrations | `backend/migrations/` | `uv run alembic upgrade head` |
| Tests (unit) | `tests/unit/` | `uv run pytest tests/unit/ -v` |
| Tests (api) | `tests/api/` | `uv run pytest tests/api/ -v` |
| Tests (integration) | `tests/integration/` | `uv run pytest tests/integration/ -v` |
| Tests (e2e/eval) | `tests/e2e/` | `uv run pytest tests/e2e/ -v` (needs GROQ_API_KEY) |
| Tests (frontend) | `frontend/` | `cd frontend && npx jest` |
| Lint (backend) | -- | `uv run ruff check --fix && uv run ruff format` |
| Lint (frontend) | `frontend/` | `cd frontend && npx tsc --noEmit` |

---

## Backend Modules

### `backend/tools/` -- 24 Registered Tools + 5 MCP Adapters

**Internal Tools (24):**

| Tool | Module | Purpose |
|------|--------|---------|
| `analyze_stock` | `analyze_stock.py` | Detailed stock analysis (signals + fundamentals) |
| `compute_signals` | `compute_signals_tool.py` | Signal computation on demand |
| `get_recommendations` | `recommendations_tool.py` | Portfolio-aware BUY/HOLD/SELL |
| `get_portfolio_exposure` | `portfolio_exposure.py` | Position analysis + sector allocation |
| `screen_stocks` | `screen_stocks.py` | Screener filtering by criteria |
| `search_stocks` | `search_stocks_tool.py` | Ticker lookup (DB + Yahoo Finance) |
| `ingest_stock` | `ingest_stock_tool.py` | Full ingest: prices + signals + fundamentals + earnings |
| `web_search` | `web_search.py` | General web search (SerpAPI) |
| `get_geopolitical_events` | `geopolitical.py` | Geopolitical + macro data |
| `get_fundamentals` | `fundamentals_tool.py` | Growth, margins, ROE, market cap (from DB) |
| `get_analyst_targets` | `analyst_targets_tool.py` | Analyst price targets + buy/hold/sell (from DB) |
| `get_earnings_history` | `earnings_history_tool.py` | Quarterly EPS + beat/miss summary (from DB) |
| `get_company_profile` | `company_profile_tool.py` | Business summary, sector, employees (from DB) |
| `get_forecast` | `forecast_tools.py` | Prophet price forecast (30/60/90 day) |
| `get_forecast_accuracy` | `forecast_tools.py` | Forecast accuracy metrics |
| `get_drift_alerts` | `forecast_tools.py` | Price drift detection alerts |
| `get_portfolio_forecasts` | `forecast_tools.py` | Portfolio-wide forecast summary |
| `get_scorecard` | `scorecard_tool.py` | Comprehensive stock scorecard |
| `get_dividend_sustainability` | `dividend_sustainability.py` | Dividend payout + sustainability analysis |
| `get_risk_narrative` | `risk_narrative.py` | Risk assessment narrative |
| `get_portfolio_health` | `portfolio_health.py` | HHI diversification, signal quality, Sharpe, dividend, sector balance → 0-10 score |
| `get_market_briefing` | `market_briefing.py` | S&P 500/NASDAQ/Dow/VIX + sector ETFs + portfolio news + earnings |
| `get_stock_intelligence` | `stock_intelligence.py` | Analyst upgrades, insider transactions, earnings calendar, EPS revisions |
| `recommend_stocks` | `recommend_stocks.py` | Multi-signal consensus (signals 35%, fundamentals 25%, momentum 20%, fit 20%) |

**MCP Adapters (5):** EdgarAdapter (SEC), AlphaVantageAdapter, FredAdapter, FinnhubAdapter, base adapter

**Core Business Logic:** Moved to `backend/services/` (Session 61). Tool files are thin re-export shims for backward compatibility.

| Module | Key Exports | Purpose |
|--------|------------|---------|
| `chat_session.py` | `create_session()`, `save_message()`, `build_context_window()` | Session CRUD, message persistence, token windowing |
| `forecasting.py` | `run_prophet_forecast()` | Prophet time-series forecasting |
| `scorecard.py` | `build_scorecard()` | Multi-factor stock scorecard |

### `backend/agents/` -- V1 ReAct + V2 Plan->Execute->Synthesize

| Module | Purpose |
|--------|---------|
| `graph.py` | StateGraph -- plan->execute->synthesize->done with conditional edges |
| `planner.py` | Intent classification, scope enforcement, tool plan generation (LLM tier=planner) |
| `executor.py` | Mechanical tool execution: $PREV_RESULT resolution, retries, circuit breaker, 45s timeout |
| `synthesizer.py` | Confidence scoring, bull/base/bear scenarios, evidence tree (LLM tier=synthesizer) |
| `simple_formatter.py` | Template-based responses for simple queries (no LLM) |
| `user_context.py` | Build portfolio + preferences + watchlist context for planner |
| `result_validator.py` | Annotate tool results with status/source/staleness |
| `llm_client.py` | Provider-agnostic LLM client with tier_config routing + fallback chain |
| `entity_registry.py` | EntityRegistry for tool->entity mapping (Phase 4D) |
| `token_budget.py` | Async sliding-window rate tracker (TPM/RPM/TPD/RPD per model) |
| `model_config.py` | ModelConfig dataclass + ModelConfigLoader (DB read + cache) |
| `stream.py` | NDJSON events: thinking, plan, tool_start/result/error, evidence, decline, token, done |

### `backend/routers/` -- API Endpoints

| Router | Prefix | Key Endpoints |
|--------|--------|--------------|
| `auth.py` | `/api/v1/auth` | POST /register, /login, /logout, /refresh |
| `stocks/` (package) | `/api/v1/stocks` | 4 sub-routers: data (prices, signals, fundamentals), watchlist, search+ingest, recommendations+bulk |
| `chat.py` | `/api/v1/chat` | POST /stream (V1 or V2 via feature flag), PATCH /feedback, GET /sessions |
| `portfolio.py` | `/api/v1/portfolio` | CRUD transactions, GET positions/summary/history/rebalancing/dividends |
| `preferences.py` | `/api/v1/preferences` | GET/PUT user thresholds |
| `indexes.py` | `/api/v1/indexes` | S&P 500, NASDAQ, Dow index cards |
| `tasks.py` | `/api/v1/tasks` | POST /refresh-watchlist (Celery trigger) |
| `alerts.py` | `/api/v1/alerts` | GET alerts, PATCH acknowledge |
| `forecasts.py` | `/api/v1/forecasts` | GET /{ticker}, /portfolio, /accuracy |
| `sectors.py` | `/api/v1/sectors` | GET /summary, /{sector}/stocks, /correlation |
| `health.py` | `/api/v1/health` | GET /health, /mcp (MCP server status) |
| `admin.py` | `/api/v1/admin` | GET/PATCH/POST /llm-models, observability endpoints (superuser-only) |
| `market.py` | `/api/v1/market` | GET /briefing (market overview + portfolio news) |

### `backend/models/` -- ORM Models (19 files)

| Model | Table | Notes |
|-------|-------|-------|
| `User` | `users` | JWT auth, bcrypt pw, UserRole enum |
| `Stock` | `stocks` | ticker, sector + 15 enriched columns (profile, growth, margins, analyst) |
| `EarningsSnapshot` | `earnings_snapshots` | Quarterly EPS: estimate, actual, surprise % (PK: ticker+quarter) |
| `StockPrice` | `stock_prices` | TimescaleDB hypertable (ticker, time) |
| `SignalSnapshot` | `signal_snapshots` | TimescaleDB hypertable |
| `Portfolio` | `portfolios` | One per user |
| `Transaction` | `transactions` | FIFO ledger, immutable |
| `Position` | `positions` | Computed from transactions |
| `PortfolioSnapshot` | `portfolio_snapshots` | TimescaleDB hypertable (daily) |
| `DividendPayment` | `dividend_payments` | TimescaleDB hypertable |
| `ChatSession` | `chat_session` | Agent type, user, last_active |
| `ChatMessage` | `chat_message` | Content, tool_calls (list[dict]), feedback (up/down) |
| `LLMCallLog` | `llm_call_log` | Provider, model, tokens, cost, tier, query_id |
| `ToolExecutionLog` | `tool_execution_log` | Tool name, params, latency, cache_hit, query_id |
| `UserPreference` | `user_preferences` | max_position_pct, max_sector_pct, stop_loss |
| `Forecast` | `forecasts` | Prophet predictions (30/60/90d), confidence intervals |
| `Alert` | `alerts` | Drift, signal-change, forecast alerts + acknowledgement |
| `PipelineRun` | `pipeline_runs` | Nightly pipeline execution tracking |
| `RecommendationEvaluation` | `recommendation_evaluations` | Recommendation accuracy tracking |
| `LLMModelConfig` | `llm_model_config` | Data-driven LLM cascade config (provider, model, tier, limits) |
| `PortfolioHealthSnapshot` | `portfolio_health_snapshots` | TimescaleDB hypertable — materialized portfolio health scores |

### `backend/services/` -- Service Layer (10 modules)

**Business logic services** (Session 61, PR #123):

| Module | Key Exports | Purpose |
|--------|------------|---------|
| `stock_data.py` | `ensure_stock_exists()`, `fetch_prices_delta()`, `get_latest_price()`, `load_prices_df()`, `fetch_fundamentals()`, `persist_*()` | Price CRUD, fundamentals, yfinance → TimescaleDB |
| `signals.py` | `compute_signals()`, `SignalResult`, `get_latest_signals()`, `get_signal_history()`, `get_bulk_signals()` | RSI, MACD, SMA, Bollinger, composite 0-10, screener queries |
| `recommendations.py` | `generate_recommendation()`, `store_recommendation()`, `calculate_position_size()`, `get_recommendations()` | BUY/HOLD/SELL + portfolio-aware sizing + query |
| `watchlist.py` | `get_watchlist()`, `add_to_watchlist()`, `remove_from_watchlist()`, `acknowledge_price()` | Watchlist CRUD with enriched data joins |
| `portfolio.py` | `get_or_create_portfolio()`, `get_positions_with_pnl()`, `_run_fifo()`, `snapshot_portfolio_value()`, `list_transactions()`, `delete_transaction()` | FIFO positions, P&L, sector allocation, transactions |
| `pipelines.py` | `ingest_ticker()` | Full ingest pipeline orchestrator (fetch → compute → store → recommend) |
| `exceptions.py` | `ServiceError`, `StockNotFoundError`, `PortfolioNotFoundError`, `DuplicateWatchlistError`, `IngestFailedError` | Domain exceptions for service layer |

**Infrastructure services:**

| Module | Purpose |
|--------|---------|
| `cache.py` | CacheService — 3-tier namespace (app/user/session), 4 TTL tiers, agent tool session cache |
| `redis_pool.py` | Shared Redis connection pool |
| `token_blocklist.py` | Refresh token blocklist (Redis-backed) |

### `backend/tasks/` -- Celery Background Jobs

| Module | Purpose |
|--------|---------|
| `pipeline.py` | Nightly pipeline chain (ingest -> signals -> forecast -> evaluate -> alert) |
| `forecasting.py` | Prophet forecast generation per ticker |
| `alerts.py` | Alert generation (drift, signal change, forecast deviation) |
| `evaluation.py` | Recommendation accuracy evaluation |
| `market_data.py` | Sync S&P 500, seed prices |
| `portfolio.py` | Portfolio snapshot generation |
| `recommendations.py` | Recommendation refresh |
| `warm_data.py` | Warm data cache |

---

## Frontend Modules

### Shell (Phase 4A -- navy dark command-center)

| File | Purpose |
|------|---------|
| `app/(authenticated)/layout.tsx` | Root shell: SidebarNav + Topbar + content + ChatPanel |
| `components/sidebar-nav.tsx` | 54px icon nav, CSS tooltips, PopoverTrigger logout |
| `components/topbar.tsx` | Market status, signal count, AI toggle |
| `components/chat-panel.tsx` | Drag-resize panel with V2 event handling |

### Pages (8)

| Page | Path | Purpose |
|------|------|---------|
| Dashboard | `app/(authenticated)/dashboard/page.tsx` | StatTiles, AllocationDonut, trending, portfolio overview |
| Screener | `app/(authenticated)/screener/page.tsx` | Signal-based stock screening with filters |
| Stock Detail | `app/(authenticated)/stocks/[ticker]/` | Price chart, signals, fundamentals, dividends, forecasts |
| Portfolio | `app/(authenticated)/portfolio/` | Positions, P&L, rebalancing, dividends, allocation |
| Sectors | `app/(authenticated)/sectors/` | Sector accordion, stocks drill-down, correlation heatmap |
| Login | `app/login/page.tsx` | JWT login form |
| Register | `app/register/page.tsx` | Registration form |
| Landing | `app/page.tsx` | Redirect to dashboard |

### Chat Components (14 files -- Phase 4C + 4D)

| Component | Purpose |
|-----------|---------|
| `chat/message-bubble.tsx` | Memoized message rendering with plan, evidence, decline, CSV extraction |
| `chat/plan-display.tsx` | Research plan with step checkmarks |
| `chat/evidence-section.tsx` | Collapsible evidence tree with source citations |
| `chat/feedback-buttons.tsx` | Thumbs up/down with PATCH API |
| `chat/decline-message.tsx` | Styled out-of-scope message |
| `chat/tool-card.tsx` | Tool execution card (name, params, result) |
| `chat/markdown-content.tsx` | Markdown rendering (hoisted plugin arrays for perf) |
| `chat/thinking-indicator.tsx` | Pulsing dots during analysis |
| `chat/chat-input.tsx` | Message input with submit |
| `chat/agent-selector.tsx` | Stock/General agent toggle |
| `chat/session-list.tsx` | Session history with expired session warning |
| `chat/artifact-bar.tsx` | Pinned artifact display |
| `chat/error-bubble.tsx` | Error state display |
| `chat/message-actions.tsx` | Copy/CSV export actions |

### Key Components

| Component | Purpose |
|-----------|---------|
| `forecast-card.tsx` | Prophet forecast display with confidence intervals |
| `alert-bell.tsx` | Alert notification bell with dropdown |
| `scorecard-modal.tsx` | Full stock scorecard modal |
| `allocation-donut.tsx` | Portfolio allocation pie chart |
| `sparkline.tsx` | SVG inline sparkline |
| `score-bar.tsx` | Horizontal score bar (0-10) |
| `score-badge.tsx` | Colored score badge |
| `recommendation-row.tsx` | Recommendation display row |
| `correlation-heatmap.tsx` | Sector correlation heatmap |
| `sector-accordion.tsx` | Expandable sector view |
| `trending-stocks.tsx` | Trending stocks carousel |
| `welcome-banner.tsx` | First-visit onboarding banner |
| `motion-primitives.tsx` | Framer Motion animation primitives |

### Hooks

**Data fetching (from `hooks/use-stocks.ts`, `use-sectors.ts`, `use-forecasts.ts`, `use-alerts.ts`):**
`useWatchlist`, `useAddToWatchlist`, `useRemoveFromWatchlist`, `useStockSearch`,
`useIngestTicker`, `useBulkSignals`, `useTrendingStocks`, `usePrices`, `useSignals`,
`useSignalHistory`, `useIsInWatchlist`, `useStockMeta`, `useFundamentals`,
`useDividends`, `usePreferences`, `useUpdatePreferences`, `useRebalancing`,
`usePositions`, `usePortfolioSummary`, `usePortfolioHistory`, `useIndexes`,
`useSectorsSummary`, `useSectorStocks`, `useCorrelationMatrix`,
`useForecast`, `usePortfolioForecasts`, `useForecastAccuracy`,
`useAlerts`, `useAcknowledgeAlert`

**Chat state:**
- `hooks/use-stream-chat.ts` -- NDJSON streaming, RAF token batching, abort, auth retry, session restore
- `hooks/chat-reducer.ts` -- Pure state machine (16 action types incl. CLEAR_ERROR)
- `hooks/use-chat.ts` -- TanStack Query hooks for session CRUD

---

## Test Coverage

| Suite | Files | Approx Tests | Command |
|-------|-------|-------------|---------|
| Backend unit | ~76 | ~891 | `uv run pytest tests/unit/ -v` |
| Backend API | ~20 | ~236 | `uv run pytest tests/api/ -v` |
| Backend integration | 2 | ~24 | `uv run pytest tests/integration/ -v` |
| Backend e2e/eval | 1 | 7 | `uv run pytest tests/e2e/ -v` (needs API key) |
| Playwright E2E | 17 | ~17 | `cd tests/e2e/playwright && npx playwright test` |
| Frontend | 27 | ~107 | `cd frontend && npx jest` |
| **Total** | **~137** | **~1127** | |

---

## Database

- **PostgreSQL 16 + TimescaleDB** -- Docker port 5433
- **Redis 7** -- Docker port 6380 (3-tier cache + refresh token blocklist)
- **Alembic head:** `1a001d6d3535` (migration 015 -- portfolio_health_snapshots)
- **Migrations:** 16 total (001-015 + stock index memberships)
- **Hypertables:** `stock_prices`, `signal_snapshots`, `portfolio_snapshots`, `dividend_payments`, `portfolio_health_snapshots`
- **Enriched tables:** `earnings_snapshots` (ticker+quarter PK), `stocks` (+15 columns)

---

## Key Dependencies

**Python:** fastapi, sqlalchemy[asyncio], asyncpg, alembic, pydantic[v2], celery, redis, yfinance, pandas-ta, langchain (anthropic/groq/openai), langgraph, prophet, fastmcp, mcp, PyJWT, bcrypt==4.2.1, slowapi, httpx, tiktoken, structlog, edgartools, gdeltdoc, defusedxml

**Node:** next 16, react 19, typescript 5, tailwindcss v4, @base-ui/react (shadcn v4), @tanstack/react-query, recharts 3, framer-motion, react-markdown, remark-gfm, rehype-highlight, cmdk, sonner, next-themes, jest 29, @testing-library/react

---

## Active Docs

| Doc | Topic |
|-----|-------|
| `docs/PRD.md` | Product requirements |
| `docs/FSD.md` | Functional spec + acceptance criteria |
| `docs/TDD.md` | API contracts + technical architecture |
| `docs/data-architecture.md` | DB schema + TimescaleDB patterns |
| `docs/superpowers/specs/2026-03-25-*` | Phase 6-7 specs (LLM factory, observability, testing, backlog) |
| `docs/superpowers/plans/2026-03-25-*` | Phase 7 plans (guardrails, enrichment, intelligence, health) |
| `PROGRESS.md` | Session log -- read first each session |
| `project-plan.md` | Phase roadmap with completions |

---

## Quick Start

```bash
# 1. Infrastructure
docker compose up -d postgres redis
uv sync
uv run alembic upgrade head

# 2. Backend
uv run uvicorn backend.main:app --reload --port 8181

# 3. Frontend
cd frontend && npm install && npm run dev

# 4. Verify
uv run pytest tests/unit/ -v          # ~806 green
cd frontend && npx jest                # ~107 green

# 5. Enable MCP tools (optional)
echo "MCP_TOOLS=true" >> backend/.env
```

---

## Phase Roadmap

| Phase | Status | PRs |
|-------|--------|-----|
| 1 -- Signal Engine + API | Done | PR #1 |
| 2 -- Dashboard + Screener UI | Done | PR #1 |
| 2.5 -- Design System + Polish | Done | PR #1 |
| 3 -- Security + Portfolio | Done | PRs #2-4 |
| 3.5 -- Advanced Portfolio | Done | PR #5 |
| 4A -- UI Redesign | Done | PR #5 |
| 4B -- AI Chatbot Backend | Done | PRs #12-13 |
| 4C -- Frontend Chat UI | Done | PRs #15-16 |
| 4C.1 -- Chat UI Polish | Done | KAN-87 |
| 4.5 -- CI/CD + Branching | Done | PRs #7-9 |
| Bug Sprint | Done | PRs #18-21 |
| 4D -- Agent Intelligence | Done | PRs #26-32 |
| KAN-57 -- Onboarding | Done | PR #33 |
| 4E -- Security Hardening | Done | PR #35 |
| 4G -- Backend Hardening | Done | PR #38 |
| 4F -- UI Migration | Done | PRs #41-52 |
| 5 -- Forecasting + Pipeline | Done | PRs #54-65 |
| 5.5 -- Refresh Token Blocklist | Done | PR #79 |
| 5.6 -- MCP Stdio Tool Server | Done | PRs #81-86 |
| Dashboard Bug Sprints | Done | PRs #87-93 |
| 6A -- LLM Factory & Cascade | Done | PR #95 |
| 6B -- Agent Observability | Done | PR #97 |
| 6C -- Testing Infrastructure | Done | PRs #98-99 |
| KAN-148 -- Redis Cache | Done | PR #100 |
| 7A -- Agent Guardrails (KAN-158) | Done | PR #102 |
| 7B -- Agent Intelligence (KAN-160) | Done | PR #104 |
| 7C -- Data Enrichment (KAN-159) | Done | PR #103 |
| 7D -- Health Materialization (KAN-161) | Done | PR #105 |
| 7.5 -- Code Analysis Tech Debt | Done | PRs #110-118 |
| 7.6 -- Scale Readiness Sprint 1 | Done | PRs #120-121 |
| KAN-172/173 -- Service Layer + Router Split | Done | PR #123 |
| **Next: Observability** | **KAN-190, then KAN-189 (ReAct)** | |
| 8 -- Observability + Agent Redesign | Planned | |
| 9 -- Multi-Agent + Subscriptions | Planned | |
| 10 -- Cloud Deployment | Planned | |
