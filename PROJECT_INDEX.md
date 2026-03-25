# Project Index: stock-signal-platform

Generated: 2026-03-25 | Phase 6A COMPLETE | Next: Phase 6B (Agent Observability)

---

## Project Structure

```
stock-signal-platform/
├── backend/                    Python FastAPI backend (118 .py files)
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
│   │   ├── stream.py           NDJSON stream events
│   │   ├── base.py             Agent base class + tool filter
│   │   ├── stock_agent.py      V1 stock-focused agent
│   │   ├── general_agent.py    V1 general agent
│   │   ├── providers/          LLM providers (Anthropic, Groq, OpenAI)
│   │   └── prompts/            planner.md, synthesizer.md, stock_agent.md, general_agent.md
│   ├── models/                 SQLAlchemy 2.0 ORM models (17 files)
│   ├── routers/                FastAPI endpoint handlers (12 routers)
│   ├── schemas/                Pydantic v2 request/response schemas (11 files)
│   ├── tools/                  Business logic + 20 registered tools + 5 MCP adapters
│   ├── tasks/                  Celery background jobs (pipeline, forecasting, alerts, evaluation)
│   ├── services/               Service layer (token_blocklist)
│   ├── mcp_server/             FastMCP server — stdio tool server + HTTP /mcp endpoint
│   │   ├── server.py           FastMCP server definition (registers all internal tools)
│   │   ├── tool_server.py      Stdio tool server subprocess entry point
│   │   ├── tool_client.py      MCPToolClient — stdio transport with param wrapping
│   │   ├── lifecycle.py        Lifespan manager (start/stop tool server subprocess)
│   │   └── auth.py             MCP JWT auth middleware
│   └── migrations/             Alembic versions (head: c965b4058c70 = 012)
├── frontend/                   Next.js 16, React 19, TypeScript, Tailwind v4, shadcn/ui v4
│   └── src/
│       ├── app/                App Router pages + layouts (8 pages)
│       ├── components/         ~45 UI components + 14 chat components + 21 UI primitives
│       ├── contexts/           ChatContext provider
│       ├── hooks/              TanStack Query hooks + chat state management (10 files)
│       ├── lib/                Utilities, auth, design tokens, formatters (13 files)
│       └── types/api.ts        Shared TypeScript API types
├── tests/                      96 test files across 10 domain subdirs
│   ├── unit/                   ~50 files — agents, auth, chat, infra, pipeline, portfolio, etc.
│   ├── api/                    15 files — endpoint tests (needs Postgres + Redis)
│   ├── integration/            Agent V2 flow + MCP stdio integration (20 tests)
│   └── e2e/                    eval/ (rubric, judge, golden set) + live LLM tests
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

### `backend/tools/` -- 20 Registered Tools + 5 MCP Adapters

**Internal Tools (20):**

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

**MCP Adapters (5):** EdgarAdapter (SEC), AlphaVantageAdapter, FredAdapter, FinnhubAdapter, base adapter

**Core Business Logic:**

| Module | Key Exports | Purpose |
|--------|------------|---------|
| `signals.py` | `compute_signals()`, `SignalResult` | RSI, MACD, SMA, Bollinger, composite 0-10 |
| `recommendations.py` | `generate_recommendation()` | BUY/HOLD/SELL + portfolio-aware sizing |
| `market_data.py` | `fetch_prices()`, `ensure_stock_exists()` | yfinance OHLCV -> TimescaleDB |
| `fundamentals.py` | `fetch_fundamentals()`, `fetch_analyst_data()`, `fetch_earnings_history()`, `persist_*()` | All yfinance data materialized to DB during ingestion |
| `portfolio.py` | `get_positions_with_pnl()`, `_run_fifo()` | FIFO positions, P&L, sector allocation |
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
| `stocks.py` | `/api/v1/stocks` | GET /watchlist, POST /{ticker}/ingest, GET /{ticker}/signals, /fundamentals, /history |
| `chat.py` | `/api/v1/chat` | POST /stream (V1 or V2 via feature flag), PATCH /feedback, GET /sessions |
| `portfolio.py` | `/api/v1/portfolio` | CRUD transactions, GET positions/summary/history/rebalancing/dividends |
| `preferences.py` | `/api/v1/preferences` | GET/PUT user thresholds |
| `indexes.py` | `/api/v1/indexes` | S&P 500, NASDAQ, Dow index cards |
| `tasks.py` | `/api/v1/tasks` | POST /refresh-watchlist (Celery trigger) |
| `alerts.py` | `/api/v1/alerts` | GET alerts, PATCH acknowledge |
| `forecasts.py` | `/api/v1/forecasts` | GET /{ticker}, /portfolio, /accuracy |
| `sectors.py` | `/api/v1/sectors` | GET /summary, /{sector}/stocks, /correlation |
| `health.py` | `/api/v1/health` | GET /health, /mcp (MCP server status) |
| `admin.py` | `/api/v1/admin` | GET/PATCH/POST /llm-models (superuser-only) |

### `backend/models/` -- ORM Models (16 files)

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
| Backend unit | ~54 | ~766 | `uv run pytest tests/unit/ -v` |
| Backend API | 15 | ~180 | `uv run pytest tests/api/ -v` |
| Backend integration | 2 | ~24 | `uv run pytest tests/integration/ -v` |
| Backend e2e/eval | 1 | 7 | `uv run pytest tests/e2e/ -v` (needs API key) |
| Frontend | 27 | ~107 | `cd frontend && npx jest` |
| **Total** | **~100** | **~1000** | |

---

## Database

- **PostgreSQL 16 + TimescaleDB** -- Docker port 5433
- **Redis 7** -- Docker port 6380 (session cache + refresh token blocklist)
- **Alembic head:** `c965b4058c70` (migration 012 -- Phase 6A llm_model_config)
- **Migrations:** 13 total (001-012 + stock index memberships)
- **Hypertables:** `stock_prices`, `signal_snapshots`, `portfolio_snapshots`, `dividend_payments`
- **Enriched tables:** `earnings_snapshots` (ticker+quarter PK), `stocks` (+15 columns)

---

## Key Dependencies

**Python:** fastapi, sqlalchemy[asyncio], asyncpg, alembic, pydantic[v2], celery, redis, yfinance, pandas-ta, langchain (anthropic/groq/openai), langgraph, prophet, fastmcp, mcp, python-jose, passlib, bcrypt==4.2.1, slowapi, httpx, tiktoken, structlog, edgartools, gdeltdoc

**Node:** next 16, react 19, typescript 5, tailwindcss v4, @base-ui/react (shadcn v4), @tanstack/react-query, recharts 3, framer-motion, react-markdown, remark-gfm, rehype-highlight, cmdk, sonner, next-themes, jest 29, @testing-library/react

---

## Active Docs

| Doc | Topic |
|-----|-------|
| `docs/PRD.md` | Product requirements |
| `docs/FSD.md` | Functional spec + acceptance criteria |
| `docs/TDD.md` | API contracts + technical architecture |
| `docs/data-architecture.md` | DB schema + TimescaleDB patterns |
| `docs/superpowers/specs/2026-03-25-llm-factory-cascade-design.md` | Phase 6A LLM Factory spec |
| `docs/superpowers/plans/2026-03-25-llm-factory-cascade-plan.md` | Phase 6A implementation plan |
| `docs/superpowers/specs/2026-03-25-agent-observability-design.md` | Observability spec |
| `docs/superpowers/specs/2026-03-25-testing-infrastructure-design.md` | Testing infra spec |
| `docs/superpowers/specs/2026-03-25-architecture-gaps-backlog.md` | Backlog of architecture gaps |
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
uv run pytest tests/unit/ -v          # ~745 green
cd frontend && npx jest                # ~107 green

# 5. Enable Agent V2 + MCP (optional)
echo "AGENT_V2=true" >> backend/.env
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
| **6A -- LLM Factory & Cascade** | **Done** | Session 54, PR pending |
| 7 -- Architecture Backlog | Planned | |
| 8 -- Subscriptions | Planned | |
| 9 -- Cloud Deployment | Planned | |
