# Project Index: stock-signal-platform

Generated: 2026-03-15 | Phase: 4A Complete, 4B Next

---

## 📁 Project Structure

```
stock-signal-platform/
├── backend/                    Python FastAPI backend
│   ├── main.py                 App entry point, router mounts, startup events
│   ├── config.py               Pydantic Settings (reads .env)
│   ├── database.py             Async SQLAlchemy engine + async_session_factory
│   ├── dependencies.py         JWT auth: get_current_user, create_access_token
│   ├── rate_limit.py           slowapi limiter (shared — never import from main.py)
│   ├── agents/                 LangChain/LangGraph agents (Phase 4B — stubs only)
│   ├── models/                 SQLAlchemy 2.0 ORM models
│   ├── routers/                FastAPI endpoint handlers
│   ├── schemas/                Pydantic v2 request/response schemas
│   ├── tools/                  Business logic tools (future MCP servers)
│   ├── tasks/                  Celery background jobs
│   ├── services/               Service layer (thin — mostly in tools/)
│   └── migrations/             Alembic versions (head: 821eb511d146 = 007)
├── frontend/                   Next.js 15, TypeScript, Tailwind v4, shadcn/ui v4
│   └── src/
│       ├── app/                App Router pages + layouts
│       ├── components/         UI components
│       ├── hooks/              TanStack Query hooks (use-stocks.ts = all API hooks)
│       ├── lib/                Utilities, auth, design tokens, formatters
│       └── types/api.ts        Shared TypeScript API types
├── tests/
│   ├── conftest.py             Shared fixtures: DB, Redis, factories, auth
│   ├── unit/                   143 tests — no external deps
│   ├── api/                    124 tests — FastAPI httpx client
│   └── integration/            Stub only (real tests in future phases)
├── docs/
│   ├── PRD.md                  Product requirements (WHAT + WHY)
│   ├── FSD.md                  Functional spec (acceptance criteria)
│   ├── TDD.md                  Technical design (HOW + API contracts)
│   ├── data-architecture.md    DB schema, TimescaleDB, model versioning
│   └── superpowers/
│       ├── specs/              Active design specs
│       ├── plans/              Active implementation plans
│       └── archive/            Completed specs + plans
├── scripts/                    seed_prices.py, sync_sp500.py
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

---

## 📦 Backend Modules

### `backend/tools/` — Business Logic (Core)

| Module | Key Exports | Purpose |
|--------|------------|---------|
| `signals.py` | `compute_signals()`, `SignalResult` | RSI, MACD, SMA, Bollinger, composite score 0-10 |
| `recommendations.py` | `generate_recommendation()`, `calculate_position_size()` | BUY/HOLD/SELL + portfolio-aware sizing |
| `market_data.py` | `fetch_prices()`, `ensure_stock_exists()` | yfinance OHLCV → TimescaleDB |
| `fundamentals.py` | `fetch_fundamentals()` | P/E, PEG, FCF yield, Piotroski F-Score (sync — use run_in_executor) |
| `portfolio.py` | `get_positions_with_pnl()`, `_run_fifo()`, `get_portfolio_summary()` | FIFO positions, P&L, sector allocation |
| `dividends.py` | `get_dividend_summary()` | Dividend history + trailing 12-month yield |
| `divestment.py` | `check_divestment_rules()` | Stop-loss, concentration, fundamental alerts |
| `screener.py` | (screener queries) | Filter + rank stocks by composite criteria |

### `backend/routers/` — API Endpoints

| Router | Prefix | Key Endpoints |
|--------|--------|--------------|
| `auth.py` | `/api/v1/auth` | POST /register, /login, /logout, /refresh |
| `stocks.py` | `/api/v1/stocks` | GET /watchlist, POST /{ticker}/ingest, GET /{ticker}/signals, /recommendation, /history |
| `portfolio.py` | `/api/v1/portfolio` | CRUD transactions, GET positions/summary/history/rebalancing/dividends |
| `preferences.py` | `/api/v1/preferences` | GET/PUT user thresholds (stop-loss, position, sector pcts) |
| `indexes.py` | `/api/v1/indexes` | S&P 500, NASDAQ, Dow index cards |
| `tasks.py` | `/api/v1/tasks` | POST /refresh-watchlist (Celery trigger) |

### `backend/models/` — ORM Models

| Model | Table | Notes |
|-------|-------|-------|
| `User` | `users` | JWT auth, bcrypt pw, UserRole enum |
| `Stock` | `stocks` | ticker PK, sector, last_synced_at |
| `StockPrice` | `stock_prices` | TimescaleDB hypertable (ticker, time) |
| `SignalSnapshot` | `signal_snapshots` | TimescaleDB hypertable |
| `Portfolio` | `portfolios` | One per user |
| `Transaction` | `transactions` | FIFO ledger, immutable |
| `Position` | `positions` | Computed from transactions |
| `PortfolioSnapshot` | `portfolio_snapshots` | TimescaleDB hypertable (daily) |
| `DividendPayment` | `dividend_payments` | TimescaleDB hypertable — migration 007 (HEAD) |
| `UserPreference` | `user_preferences` | max_position_pct, max_sector_pct, stop_loss pct |

### `backend/agents/` — Phase 4B (stubs only)

Directory exists with `__init__.py`. Phase 4B will add:
`base.py`, `general_agent.py`, `stock_agent.py`, `loop.py`, `stream.py`

---

## 🖥️ Frontend Modules

### Shell (Phase 4A — navy dark command-center)

| File | Purpose |
|------|---------|
| `app/(authenticated)/layout.tsx` | Root shell: SidebarNav + Topbar + content + ChatPanel |
| `components/sidebar-nav.tsx` | 54px icon nav, CSS tooltips, PopoverTrigger logout |
| `components/topbar.tsx` | Market status, signal count, AI toggle |
| `components/chat-panel.tsx` | Drag-resize panel stub (Phase 4B wires backend) |

### Key Components

| Component | Purpose |
|-----------|---------|
| `stat-tile.tsx` | Dashboard KPI tile with accent gradient |
| `allocation-donut.tsx` | CSS conic-gradient pie (no chart lib) |
| `portfolio-drawer.tsx` | Bottom slide-up with portfolio chart |
| `sparkline.tsx` | Raw SVG `<polyline>` (jagged financial feel) |
| `stock-card.tsx` | Watchlist card with score + signal badge |
| `screener-table.tsx` | TradingView-style tabs + sortable columns |
| `screener-grid.tsx` | Sparkline card grid view |
| `price-chart.tsx` | Recharts line + sentiment gradient |
| `signal-history-chart.tsx` | Dual-axis composite + RSI over time |
| `rebalancing-panel.tsx` | BUY_MORE/HOLD/AT_CAP table |
| `portfolio-value-chart.tsx` | Portfolio history line chart |
| `dividend-card.tsx` | Yield KPIs + collapsible payment history |

### Hooks (`hooks/use-stocks.ts` — ALL API hooks live here)

`useWatchlist`, `useStockSignals`, `useStockRecommendation`, `useSignalHistory`,
`useIndexes`, `useBulkSignals`, `usePortfolio`, `usePositions`, `usePortfolioSummary`,
`usePortfolioHistory`, `useTransactions`, `useRebalancing`, `useDividends`,
`usePreferences`, `useUpdatePreferences`, `useScreener`

### Lib Utilities

| File | Purpose |
|------|---------|
| `lib/api.ts` | Centralized fetch with httpOnly cookie auth; `get/post/patch/delete` helpers |
| `lib/auth.ts` | AuthContext + useAuth hook |
| `lib/design-tokens.ts` | CSS var name constants (navy tokens) |
| `lib/chart-theme.ts` | `useChartColors()` — resolves CSS vars for Recharts |
| `lib/storage-keys.ts` | Namespaced localStorage keys (`stocksignal:` prefix) |
| `lib/market-hours.ts` | Pure `isNYSEOpen()` — IANA `America/New_York`, DST-correct |
| `lib/signals.ts` | Sentiment classification, CSS var color mappings |
| `lib/format.ts` | Currency, percent, volume, date formatters |
| `lib/density-context.tsx` | DensityProvider for screener compact/comfortable toggle |

---

## 🧪 Test Coverage

- **Backend unit:** 143 tests in `tests/unit/` (no Docker required)
- **Backend API:** 124 tests in `tests/api/` (needs Postgres + Redis)
- **Frontend component:** 20 tests in `frontend/src/__tests__/components/`
- **Frontend lib:** `frontend/src/lib/__tests__/market-hours.test.ts`
- **Total backend:** 267 passing
- **Integration:** `tests/integration/` — stub only (Phase 4.5)

**Run commands:**
```bash
uv run pytest tests/unit/ -v                    # fast, no deps
uv run pytest tests/api/ -v                     # needs Docker
cd frontend && npx jest                          # component tests
```

---

## 🔧 Configuration

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python deps (uv), ruff config, pytest settings |
| `backend/.env` | Secrets — gitignored. Required: DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, ANTHROPIC_API_KEY |
| `backend/.env.example` | Template |
| `alembic.ini` | Alembic migration config |
| `docker-compose.yml` | Postgres (port 5433) + Redis (port 6380) |
| `frontend/package.json` | npm deps, Next.js config |
| `frontend/tailwind.config.ts` | Tailwind v4 config |
| `mkdocs.yml` | MkDocs Material docs site |

---

## 🗄️ Database

- **PostgreSQL 16 + TimescaleDB** — Docker port 5433
- **Redis 7** — Docker port 6380
- **Alembic head:** `821eb511d146` (migration 007 — dividend_payments)
- **Hypertables:** `stock_prices`, `signal_snapshots`, `portfolio_snapshots`, `dividend_payments`
- **Upsert pattern:** TimescaleDB hypertables need `constraint="tablename_pkey"` (named constraint)

---

## 🔗 Key Dependencies

**Python:** fastapi, sqlalchemy[asyncio], asyncpg, alembic, pydantic[v2], celery, redis, yfinance, pandas-ta, prophet, langchain, langgraph, python-jose, passlib, bcrypt==4.2.1 (pinned), slowapi, httpx, pytest, testcontainers, factory-boy, freezegun

**Node:** next 15, react 19, typescript, tailwindcss v4, @base-ui/react (shadcn v4), @tanstack/react-query, recharts, sonner, next-themes, jest, @testing-library/react

---

## 📚 Active Docs

| Doc | Topic |
|-----|-------|
| `docs/FSD.md` | Functional requirements + acceptance criteria |
| `docs/TDD.md` | API contracts + technical architecture |
| `docs/data-architecture.md` | DB schema + TimescaleDB patterns |
| `docs/superpowers/specs/2026-03-15-cicd-branching-design.md` | CI/CD + branching strategy (Phase 4.5) |
| `PROGRESS.md` | Session log — read this first each session |
| `project-plan.md` | Phase roadmap with ✅ completions |
| `CLAUDE.md` | All coding conventions + anti-patterns |

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
uv run pytest tests/unit/ -v          # should be 143/143 green
cd frontend && npx jest                # should be 20/20 green
```

---

## 🗺️ Phase Roadmap

| Phase | Status | Branch |
|-------|--------|--------|
| 1 — Signal Engine + API | ✅ Complete | merged |
| 2 — Dashboard + Screener UI | ✅ Complete | merged |
| 2.5 — Design System + Polish | ✅ Complete | merged |
| 3 — Security + Portfolio | ✅ Complete | merged |
| 3.5 — Advanced Portfolio | ✅ Complete | merged (PR #5) |
| 4A — UI Redesign (navy dark shell) | ✅ Complete | feat/phase-4b-ai-chatbot |
| **4B — AI Chatbot Backend** | 🔄 **NEXT** | feat/phase-4b-ai-chatbot |
| 4.5 — CI/CD + Branching | 📋 Spec ready | post-4B |
| 5 — Background Jobs + Alerts | ⬜ Planned | — |
| 6 — Deployment (Azure + Terraform) | ⬜ Planned | — |
