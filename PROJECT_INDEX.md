# Project Index: stock-signal-platform

Generated: 2026-03-21 | Phase: 4C.1 IN PROGRESS | Next: Phase 4F UI Migration

---

## 📁 Project Structure

```
stock-signal-platform/
├── backend/                    Python FastAPI backend (90 .py files)
│   ├── main.py                 App entry point, router mounts, startup (V1+V2 graphs)
│   ├── config.py               Pydantic Settings (reads .env) — incl. AGENT_V2 flag
│   ├── database.py             Async SQLAlchemy engine + async_session_factory
│   ├── dependencies.py         JWT auth: get_current_user, create_access_token
│   ├── request_context.py      ContextVar for request-scoped user ID
│   ├── rate_limit.py           slowapi limiter (shared — never import from main.py)
│   ├── agents/                 LangGraph agents — V1 ReAct + V2 Plan→Execute→Synthesize
│   │   ├── graph.py            V1 ReAct graph (backward compat when AGENT_V2=false)
│   │   ├── graph_v2.py         V2 three-phase StateGraph (plan→execute→synthesize)
│   │   ├── planner.py          Intent classification + tool plan generation (LLM)
│   │   ├── executor.py         Mechanical tool executor ($PREV_RESULT, retries, circuit breaker)
│   │   ├── synthesizer.py      Confidence scoring + scenarios + evidence tree (LLM)
│   │   ├── simple_formatter.py Template-based formatter for simple queries (no LLM)
│   │   ├── user_context.py     Build portfolio/preferences context for planner
│   │   ├── result_validator.py Tool result validation (null, stale, source annotation)
│   │   ├── llm_client.py       Provider-agnostic LLM client with tier routing + fallback
│   │   ├── stream.py           NDJSON stream events (V1 bridge + V2 events)
│   │   ├── base.py             Agent base class + tool filter
│   │   ├── stock_agent.py      V1 stock-focused agent
│   │   ├── general_agent.py    V1 general agent
│   │   ├── providers/          LLM providers (Anthropic, Groq)
│   │   └── prompts/            planner.md, synthesizer.md, stock_agent.md, general_agent.md
│   ├── models/                 SQLAlchemy 2.0 ORM models (15 files)
│   ├── routers/                FastAPI endpoint handlers (7 routers)
│   ├── schemas/                Pydantic v2 request/response schemas
│   ├── tools/                  Business logic + 13 registered tools + 4 MCP adapters
│   ├── tasks/                  Celery background jobs (refresh, snapshots)
│   ├── services/               Service layer (thin — mostly in tools/)
│   ├── mcp_server/             FastMCP server at /mcp (Streamable HTTP, JWT auth)
│   └── migrations/             Alembic versions (head: ac5d765112d6 = 010)
├── frontend/                   Next.js 15, TypeScript, Tailwind v4, shadcn/ui v4
│   └── src/
│       ├── app/                App Router pages + layouts (7 pages)
│       ├── components/         39 UI components + 14 chat components + 21 UI primitives
│       ├── hooks/              TanStack Query hooks + chat state management
│       ├── lib/                Utilities, auth, design tokens, formatters
│       └── types/api.ts        Shared TypeScript API types
├── tests/                      10 domain subdirs (Phase 4G restructured)
│   ├── conftest.py             Shared fixtures: DB, Redis, factories, auth
│   ├── unit/                   ~40 test files — 440 tests, no external deps
│   │   ├── agents/             Agent V2, planner, executor, synthesizer, stream
│   │   ├── auth/               JWT, dependencies
│   │   ├── chat/               Session management, schemas, models
│   │   ├── infra/              MCP, Celery, health, user context
│   │   ├── pipeline/           Sync, seed, warm data
│   │   ├── portfolio/          FIFO, divestment
│   │   ├── recommendations/    Recommendation engine
│   │   ├── signals/            Signal computation
│   │   ├── tools/              Internal tools, registry, hardening
│   │   └── adversarial/        Agent adversarial tests
│   ├── api/                    15 test files — 157 tests, needs Postgres + Redis
│   ├── integration/            1 file — 4 Agent V2 flow tests
│   └── e2e/                    eval/ (rubric, judge, golden set) + 7 live LLM tests
├── docs/
│   ├── PRD.md                  Product requirements (WHAT + WHY)
│   ├── FSD.md                  Functional spec (acceptance criteria)
│   ├── TDD.md                  Technical design (HOW + API contracts)
│   ├── data-architecture.md    DB schema, TimescaleDB, model versioning
│   └── superpowers/
│       ├── specs/              Active design specs (7 files)
│       ├── plans/              Active implementation plans (8 files)
│       └── archive/            Completed specs + plans
├── scripts/                    seed_prices.py, sync_sp500.py, sync_indexes.py
├── .github/workflows/          ci-pr.yml, ci-merge.yml, ci-eval.yml, deploy.yml
├── CLAUDE.md                   Project instructions for Claude
├── PROGRESS.md                 Session log (full detail last 3 sessions)
├── project-plan.md             Phased build plan with ✅ completions
└── PROJECT_INDEX.md            This file
```

---

## 🚀 Entry Points

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
| Lint (backend) | — | `uv run ruff check --fix && uv run ruff format` |
| Lint (frontend) | `frontend/` | `cd frontend && npx tsc --noEmit` |

---

## 📦 Backend Modules

### `backend/tools/` — 13 Registered Tools + 4 MCP Adapters

**Internal Tools (13):**
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

**MCP Adapters (4):** EdgarAdapter (SEC), AlphaVantageAdapter, FredAdapter, FinnhubAdapter

**Core Business Logic:**
| Module | Key Exports | Purpose |
|--------|------------|---------|
| `signals.py` | `compute_signals()`, `SignalResult` | RSI, MACD, SMA, Bollinger, composite 0-10 |
| `recommendations.py` | `generate_recommendation()` | BUY/HOLD/SELL + portfolio-aware sizing |
| `market_data.py` | `fetch_prices()`, `ensure_stock_exists()` | yfinance OHLCV → TimescaleDB |
| `fundamentals.py` | `fetch_fundamentals()`, `fetch_analyst_data()`, `fetch_earnings_history()`, `persist_*()` | All yfinance data materialized to DB during ingestion |
| `portfolio.py` | `get_positions_with_pnl()`, `_run_fifo()` | FIFO positions, P&L, sector allocation |
| `chat_session.py` | `create_session()`, `save_message()`, `build_context_window()` | Session CRUD, message persistence, token windowing |

### `backend/agents/` — V1 ReAct + V2 Plan→Execute→Synthesize

| Module | Purpose |
|--------|---------|
| `graph_v2.py` | **V2 StateGraph** — plan→execute→synthesize→done with conditional edges |
| `planner.py` | Intent classification, scope enforcement, tool plan generation (LLM tier=planner) |
| `executor.py` | Mechanical tool execution: $PREV_RESULT resolution, retries, circuit breaker, 45s timeout |
| `synthesizer.py` | Confidence scoring, bull/base/bear scenarios, evidence tree (LLM tier=synthesizer) |
| `simple_formatter.py` | Template-based responses for simple queries (no LLM) |
| `user_context.py` | Build portfolio + preferences + watchlist context for planner |
| `result_validator.py` | Annotate tool results with status/source/staleness |
| `llm_client.py` | Provider-agnostic LLM client with tier_config routing + fallback chain |
| `stream.py` | NDJSON events: thinking, plan, tool_start/result/error, evidence, decline, token, done |
| `graph.py` | V1 ReAct graph (kept for backward compat when AGENT_V2=false) |

### `backend/routers/` — API Endpoints

| Router | Prefix | Key Endpoints |
|--------|--------|--------------|
| `auth.py` | `/api/v1/auth` | POST /register, /login, /logout, /refresh |
| `stocks.py` | `/api/v1/stocks` | GET /watchlist, POST /{ticker}/ingest, GET /{ticker}/signals, /fundamentals, /history |
| `chat.py` | `/api/v1/chat` | POST /stream (V1 or V2 via feature flag), PATCH /feedback, GET /sessions |
| `portfolio.py` | `/api/v1/portfolio` | CRUD transactions, GET positions/summary/history/rebalancing/dividends |
| `preferences.py` | `/api/v1/preferences` | GET/PUT user thresholds |
| `indexes.py` | `/api/v1/indexes` | S&P 500, NASDAQ, Dow index cards |
| `tasks.py` | `/api/v1/tasks` | POST /refresh-watchlist (Celery trigger) |

### `backend/models/` — ORM Models (15 files)

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

---

## 🖥️ Frontend Modules

### Shell (Phase 4A — navy dark command-center)

| File | Purpose |
|------|---------|
| `app/(authenticated)/layout.tsx` | Root shell: SidebarNav + Topbar + content + ChatPanel |
| `components/sidebar-nav.tsx` | 54px icon nav, CSS tooltips, PopoverTrigger logout |
| `components/topbar.tsx` | Market status, signal count, AI toggle |
| `components/chat-panel.tsx` | Drag-resize panel with V2 event handling |

### Chat Components (14 files — Phase 4C + 4D)

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
| `chat/session-list.tsx` | Session history with expired session warning prompt |
| `chat/artifact-bar.tsx` | Pinned artifact display |
| `chat/error-bubble.tsx` | Error state display |
| `chat/message-actions.tsx` | Copy/CSV export actions |

### Hooks

**Data fetching (26 from `hooks/use-stocks.ts`):**
`useWatchlist`, `useAddToWatchlist`, `useRemoveFromWatchlist`, `useStockSearch`,
`useIngestTicker`, `useBulkSignals`, `useTrendingStocks`, `usePrices`, `useSignals`,
`useSignalHistory`, `useIsInWatchlist`, `useStockMeta`, `useFundamentals`,
`useDividends`, `usePreferences`, `useUpdatePreferences`, `useRebalancing`,
`usePositions`, `usePortfolioSummary`, `usePortfolioHistory`, `useIndexes`

**Chat state:**
- `hooks/use-stream-chat.ts` — NDJSON streaming, RAF token batching, abort, auth retry, session restore
- `hooks/chat-reducer.ts` — Pure state machine (16 action types incl. CLEAR_ERROR)
- `hooks/use-chat.ts` — TanStack Query hooks for session CRUD

---

## 🧪 Test Coverage

| Suite | Files | Tests | Command |
|-------|-------|-------|---------|
| Backend unit | ~40 | 440 | `uv run pytest tests/unit/ -v` |
| Backend API | 15 | 157 | `uv run pytest tests/api/ -v` |
| Backend integration | 1 | 4 | `uv run pytest tests/integration/ -v` |
| Backend e2e/eval | 1 | 7 | `uv run pytest tests/e2e/ -v` (needs API key) |
| Frontend | 20 | 70 | `cd frontend && npx jest` |
| **Total** | **~77** | **~678** | |

---

## 🗄️ Database

- **PostgreSQL 16 + TimescaleDB** — Docker port 5433
- **Redis 7** — Docker port 6380
- **Alembic head:** `ac5d765112d6` (migration 010 — agent v2 fields)
- **Migrations:** 11 total (001–010 + stock index memberships)
- **Hypertables:** `stock_prices`, `signal_snapshots`, `portfolio_snapshots`, `dividend_payments`
- **Enriched tables:** `earnings_snapshots` (ticker+quarter PK), `stocks` (+15 columns)

---

## 🔗 Key Dependencies

**Python:** fastapi, sqlalchemy[asyncio], asyncpg, alembic, pydantic[v2], celery, redis, yfinance, pandas-ta, langchain, langgraph, python-jose, passlib, bcrypt==4.2.1, slowapi, httpx, tiktoken, pytest, testcontainers, factory-boy

**Node:** next 15, react 19, typescript, tailwindcss v4, @base-ui/react (shadcn v4), @tanstack/react-query, recharts, react-markdown, remark-gfm, rehype-highlight, sonner, next-themes, jest, @testing-library/react

---

## 📚 Active Docs

| Doc | Topic |
|-----|-------|
| `docs/PRD.md` | Product requirements |
| `docs/FSD.md` | Functional spec + acceptance criteria |
| `docs/TDD.md` | API contracts + technical architecture |
| `docs/data-architecture.md` | DB schema + TimescaleDB patterns |
| `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md` | Phase 4D spec |
| `docs/superpowers/specs/2026-03-21-backend-hardening-design.md` | Phase 4G spec |
| `docs/superpowers/plans/2026-03-19-ui-migration-workflow.md` | Phase 4F UI migration workflow |
| `docs/lovable/migration-gap-analysis.md` | Phase 4F gap analysis |
| `PROGRESS.md` | Session log — read first each session |
| `project-plan.md` | Phase roadmap with ✅ completions |

---

## 📝 Quick Start

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
uv run pytest tests/unit/ -v          # 440 green
cd frontend && npx jest                # 70 green

# 5. Enable Agent V2 (optional)
echo "AGENT_V2=true" >> backend/.env
```

---

## 🗺️ Phase Roadmap

| Phase | Status | PRs |
|-------|--------|-----|
| 1 — Signal Engine + API | ✅ Complete | PR #1 |
| 2 — Dashboard + Screener UI | ✅ Complete | PR #1 |
| 2.5 — Design System + Polish | ✅ Complete | PR #1 |
| 3 — Security + Portfolio | ✅ Complete | PRs #2-4 |
| 3.5 — Advanced Portfolio | ✅ Complete | PR #5 |
| 4A — UI Redesign | ✅ Complete | PR #5 |
| 4B — AI Chatbot Backend | ✅ Complete | PRs #12-13 |
| 4C — Frontend Chat UI | ✅ Complete | PRs #15-16 |
| 4.5 — CI/CD + Branching | ✅ Complete | PRs #7-9 |
| Bug Sprint | ✅ Complete | PRs #18-21 |
| 4D — Agent Intelligence | ✅ Complete | PRs #26-32 |
| KAN-57 — Onboarding | ✅ Complete | PR #33 |
| 4E — Security Hardening | ✅ Complete | PR #35 |
| 4G — Backend Hardening | ✅ Complete | PR #38 |
| **4C.1 — Chat UI Polish** | 🟡 **In Progress** | KAN-87 |
| 4D.2 — Stock Detail Enrichment | ⬜ Planned (5 items) | — |
| 4F — UI Migration | ⬜ Planned (9 stories, ~26h) | — |
| 5 — Background Jobs + Alerts | ⬜ Planned | — |
| 5.5 — Security (refresh token revocation) | ⬜ Planned | — |
| 6 — Deployment (Docker + Terraform) | ⬜ Planned | — |
