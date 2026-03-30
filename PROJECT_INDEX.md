# Project Index: Stock Signal Platform

> Stock analysis SaaS for part-time investors — US equities, signal detection, portfolio tracking, AI-powered recommendations.

Generated: 2026-03-30 | Session: 75

## Project Structure

```
stock-signal-platform/
├── backend/                    # FastAPI async app, 37 tools, LangGraph agents
│   ├── main.py                 # Entry point
│   ├── routers/                # 15 main routes + 6 stock sub-routers
│   ├── models/                 # 19 SQLAlchemy ORM models
│   ├── agents/                 # 22 agent components (ReAct, guards, LLM)
│   ├── tools/                  # 37 internal tools + 6 MCP adapters
│   ├── services/               # 14 service modules
│   ├── tasks/                  # Celery background jobs
│   ├── migrations/             # 20 Alembic versions
│   └── database.py             # AsyncPG, SQLAlchemy 2.0
├── frontend/                   # Next.js 15, React 19, TypeScript
│   ├── src/app/                # App Router (dashboard, portfolio, screener, sectors)
│   ├── src/components/         # 102 .tsx component files
│   ├── src/hooks/              # 10 custom React hooks
│   ├── src/lib/                # 16 utility modules
│   └── package.json
├── tests/                      # 121 unit, 30 api, 5 integration, 45 frontend
├── docs/                       # 8 markdown files
├── pyproject.toml              # Python deps (uv)
└── docker-compose.yml          # Postgres + Redis + Langfuse
```

## Entry Points

| Entry | Path | Command |
|-------|------|---------|
| Backend API | backend/main.py | `uv run uvicorn backend.main:app --reload --port 8181` |
| Frontend | frontend/ | `cd frontend && npm run dev` (port 3000) |
| Celery Worker | backend/tasks/ | `uv run celery -A backend.tasks worker --loglevel=info` |
| Celery Beat | backend/tasks/ | `uv run celery -A backend.tasks beat` |
| Docs | docs/ | `uv run mkdocs serve` (port 8000) |

## Backend Architecture

### Routers (15 main + 6 stock sub-routers)
- `admin.py` — Admin operations
- `alerts.py` — Alert management
- `auth.py` — JWT authentication
- `chat.py` — Chat sessions & agent inference
- `forecasts.py` — Price predictions
- `health.py` — Health check
- `indexes.py` — Market index data
- `market.py` — Market overview
- `news.py` — News feed
- `observability.py` — Langfuse metrics
- `portfolio.py` — Portfolio management
- `preferences.py` — User settings
- `sectors.py` — Sector performance
- `tasks.py` — Celery task status
- **Stock sub-routers:**
  - `stocks/data.py` — OHLC, metrics
  - `stocks/recommendations.py` — AI recommendations
  - `stocks/search.py` — Stock search
  - `stocks/watchlist.py` — Watchlist
  - `stocks/_helpers.py` — Shared utilities

### Models (19 files)
- `user.py`, `stock.py`, `price.py`, `dividend.py`, `earnings.py`
- `forecast.py`, `signal.py`, `recommendation.py`, `alert.py`
- `portfolio.py`, `portfolio_health.py`, `assessment.py`
- `chat.py`, `index.py`, `logs.py`, `llm_config.py`
- `base.py`, `pipeline.py` (mixins)

### Tools (37 files + 6 MCP adapters)
**Core tools:** market_data, fundamentals, dividends, earnings_history, news, web_search, signals, forecast_tools, recommendations, portfolio, risk analysis, market briefing, stock intelligence, ingest/search operations
**MCP adapters:** Alpha Vantage, Edgar, Finnhub, FRED (economic data), base adapter

### Services (14 files)
- `langfuse_service.py` — Observability telemetry
- `cache.py` — Redis caching
- `portfolio.py` — Portfolio calculations
- `signals.py` — Signal computation
- `stock_data.py` — Market data service
- `redis_pool.py`, `token_blocklist.py`, `watchlist.py`
- `exceptions.py`, `oidc_provider.py`, `pipelines.py`, `recommendations.py`, `observability_queries.py`

### Agents (22 files)
- `react_loop.py` — ReAct agent executor
- `model_config.py` — LLM model selection (Claude, Groq)
- `guards.py` — PII, injection, disclaimer guardrails
- `llm_client.py` — LLM client wrapper
- `intent_classifier.py` — User intent detection
- `planner.py`, `executor.py` — Plan/Execute pipeline (legacy)
- `stock_agent.py` — Stock-specific agent
- `general_agent.py` — Chat agent
- `observability.py`, `observability_writer.py` — Langfuse integration
- `entity_registry.py`, `tool_groups.py`, `user_context.py`
- `result_validator.py`, `simple_formatter.py`, `synthesizer.py`
- `stream.py`, `token_budget.py`, `base.py`, `graph.py`

## Frontend Architecture

### Pages (App Router)
- `(authenticated)/dashboard` — Main dashboard
- `(authenticated)/portfolio` — Portfolio management
- `(authenticated)/screener` — Stock screener
- `(authenticated)/sectors` — Sector performance
- `(authenticated)/stocks/[ticker]` — Stock detail
- `login`, `register` — Auth pages

### Components (102 .tsx files)
**Charts:** `price-chart.tsx`, `candlestick-chart.tsx`, `signal-history-chart.tsx`, `portfolio-value-chart.tsx`, `correlation-heatmap.tsx`, `sector-performance-bars.tsx`
**Cards:** `stock-card.tsx`, `dividend-card.tsx`, `forecast-card.tsx`, `fundamentals-card.tsx`, `news-article-card.tsx`, `metric-card.tsx`, `risk-return-card.tsx`
**Sections:** `stock-header.tsx`, `stock-metrics.tsx`, `scorecard-modal.tsx`, `portfolio-kpi-tile.tsx`, `sector-accordion.tsx`, `screener-grid.tsx`, `screener-table.tsx`
**Chat:** `chat-panel.tsx`, `chat/` subdirectory
**UI:** `topbar.tsx`, `sidebar-nav.tsx`, `portfolio-drawer.tsx`, `pagination-controls.tsx`, `breadcrumbs.tsx`

### Hooks (10 files)
- `use-chat.ts` — Chat sessions
- `use-stocks.ts` — Stock data fetching
- `use-forecasts.ts` — Price forecasts
- `use-alerts.ts` — Alert management
- `use-sectors.ts` — Sector data
- `use-stream-chat.ts` — Streaming chat inference
- `use-mounted.ts`, `use-container-width.ts`

### Utilities (16 lib/*.ts files)
- `api.ts` — Fetch wrapper with JWT auto-refresh
- `auth.ts` — Token storage & refresh logic
- `format.ts` — Number formatting
- `csv-export.ts` — Portfolio CSV export
- `chart-theme.ts`, `lightweight-chart-theme.ts` — Chart styling
- `market-hours.ts` — US market hours
- `signals.ts`, `signal-reason.ts` — Signal utilities
- `sectors.ts` — Sector mapping
- `ndjson-parser.ts` — Streaming JSON
- `design-tokens.ts`, `typography.ts`, `storage-keys.ts`, `news-sentiment.ts`

## Infrastructure

| Service | Port | Notes |
|---------|------|-------|
| PostgreSQL + TimescaleDB | 5433 | `timescale/timescaledb:latest-pg16` |
| Redis 7 | 6380 | Cache + Celery broker |
| Langfuse Server | 3001 | LLM observability UI |
| Langfuse DB | 5434 | Postgres for Langfuse |

## Testing

| Category | Count | Command |
|----------|-------|---------|
| Unit | 121 files | `uv run pytest tests/unit/ -v` |
| API | 30 files | `uv run pytest tests/api/ -v` |
| Integration | 5 files | `uv run pytest tests/integration/ -v` |
| Frontend | 45 files | `cd frontend && npx jest` |

## Migrations

20 Alembic migrations. Latest: `ea8da8624c85` (016 observability columns)

## Key Configuration

| File | Purpose |
|------|---------|
| pyproject.toml | Python deps: FastAPI, SQLAlchemy 2.0, Celery, LangGraph, Prophet |
| frontend/package.json | Node deps: Next.js 15, React 19, TanStack Query, Tailwind v4, shadcn/ui |
| docker-compose.yml | Postgres, Redis, Langfuse (all dev services) |
| alembic.ini | Database migration config |
| .pre-commit-config.yaml | Pre-commit hooks (ruff, eslint) |

## Documentation

- `index.md` — Project overview
- `ADR.md` — Architecture Decision Records
- `FSD.md` — Front-end File Structure
- `PRD.md` — Product Requirements
- `TDD.md` — Test-Driven Development guide
- `data-architecture.md` — Data model design
- `phase2-requirements.md` — Phase 2 roadmap
- `workflow_phase2.md` — Phase 2 workflow

## Key Dependencies

### Backend
- **FastAPI** — Web framework
- **SQLAlchemy 2.0** — ORM (async)
- **Alembic** — Schema migrations
- **Celery** — Background tasks
- **LangGraph** — Agent orchestration
- **Anthropic SDK** — Claude LLM
- **Groq SDK** — Groq LLM
- **Prophet** — Time series forecasting
- **yfinance** — Market data
- **Pydantic v2** — Validation
- **httpx** — HTTP client
- **defusedxml** — XML parsing

### Frontend
- **Next.js 15** — App Router, React Server Components
- **React 19** — UI library
- **TypeScript** — Type safety
- **TanStack Query** — Data fetching & caching
- **Tailwind CSS v4** — Styling
- **shadcn/ui** — UI components
- **Recharts** — Interactive charts
- **lightweight-charts** — TradingView charts
- **Framer Motion** — Animations
- **@base-ui/react** — Headless UI (Popover/Trigger)
