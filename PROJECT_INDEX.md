# Project Index: Stock Signal Platform

Stock analysis SaaS for part-time investors — US equities, signal detection, portfolio tracking, AI-powered recommendations. Multi-user cloud deployment target.

**Updated:** 2026-05-02 | **Session:** 148 | **Alembic head:** `0ff65ce55dc5` (migration 045)

---

## Repository Structure (Top 2 Levels)

```
backend/                       FastAPI + SQLAlchemy async + Celery
├── agents/ (20 files)         LangGraph ReAct, guards, intent, providers
├── migrations/versions/ (46)  Alembic migrations (TimescaleDB hypertables)
├── models/ (30+ files)        SQLAlchemy 2.0 ORM models (public + observability schema)
├── observability/ (30+ files) SDK, writers, anomaly engine, MCP tools, admin routers
│   ├── anomaly/               12 anomaly rules + engine + persistence
│   ├── routers/               admin_query.py, admin.py, command_center.py, health.py
│   └── sdk/                   ObservabilityClient, targets, spool, bootstrap
├── routers/ (24 files)        API endpoints under /api/v1/
│   └── stocks/ (4 files)      Data, search, watchlist, recommendations
├── schemas/ (15+ files)       Pydantic v2 request/response models
├── services/ (21 files)       Business logic: signals, portfolio, cache, pipeline
├── tasks/ (19 files)          Celery tasks: market data, alerts, forecasts, retention, anomaly, DQ
└── tools/ (30+ files)         25 internal tools + 4 MCP adapters + registry

frontend/                      Next.js 15 + TypeScript + Tailwind v4 + shadcn/ui
├── src/app/                   8 auth-protected route groups + admin pages
├── src/components/ (80+)      UI components + domain-specific + admin observability
├── src/hooks/ (18 files)      TanStack Query hooks
├── src/lib/                   api.ts (fetch wrapper), auth, format, chart-theme, utils
└── src/__tests__/ (86 files)  Jest + MSW v2 test suites

tests/                         2742 unit + 454 API + 78 integration + 29 E2E
├── unit/ (255 files)          Services, routers, tools, agents, pipeline, guards, obs
├── api/ (51 files)            Endpoint tests with testcontainers
├── integration/ (24 files)    Observability SDK, anomaly lifecycle, MCP tools, retention
├── e2e/ (29 specs)            Playwright: auth, dashboard, portfolio, admin, sectors, obs
├── fixtures/ (8 files)        Factory-boy model fixtures
└── semgrep/ (2 files)         Custom rule validation tests

docs/                          Specifications and plans
├── PRD.md, FSD.md, TDD.md    Product, functional, technical specs
├── superpowers/specs/ (25+)   Design docs per sprint
├── superpowers/plans/ (25+)   Implementation plans per sprint
└── superpowers/archive/       Completed features + full progress log

.github/workflows/             6 CI/CD pipelines
├── ci-pr.yml                  13 checks, path-filter routing, ci-gate
├── ci-merge.yml               Build verification + deploy webhook
├── ci-nightly.yml             Weekdays 04:00 UTC: Lighthouse + perf + heap
├── ci-eval.yml                LLM agent evaluation
├── assessment.yml             Golden dataset + QuantStats validation
└── deploy.yml                 Production deployment

.semgrep/                      2 rule files: stock-signal-rules.yml + observability-rules.yml (21 rules total)
```

---

## Entry Points

| Service | Command | Port | File |
|---------|---------|------|------|
| **Backend API** | `uv run uvicorn backend.main:app --reload --port 8181` | 8181 | `backend/main.py` |
| **Frontend** | `cd frontend && npm run dev` | 3000 | `frontend/` |
| **Celery Worker** | `uv run celery -A backend.tasks worker --loglevel=info` | — | `backend/tasks/__init__.py` |
| **Celery Beat** | Scheduled via celery-beat (nightly pipeline + anomaly scan 5min + retention) | — | `backend/tasks/__init__.py` |
| **MCP Tool Server** | `uv run python -m backend.mcp_server` | stdio | `backend/mcp_server.py` |
| **Migrations** | `uv run alembic upgrade head` | — | `backend/migrations/` |
| **Docs** | `uv run mkdocs serve` | 8000 | `mkdocs.yml` |

---

## Backend Routers

| Prefix | File | Purpose |
|--------|------|---------|
| `/auth` | `auth.py` | Login, register, refresh, logout, OAuth, email verification, password reset, account deletion |
| `/stocks` | `stocks/` | Signals, prices, OHLC, search, watchlist, fundamentals, news, intelligence, benchmark, ingest |
| `/portfolio` | `portfolio.py` | Transactions, positions, summary, history, dividends, rebalancing, analytics, health, forecast, bulk upload |
| `/recommendations` | `recommendations.py` | List, history, scorecard |
| `/forecasts` | `forecasts.py` | Ticker, portfolio, sectors, scorecard |
| `/indexes` | `indexes.py` | List, membership |
| `/chat` | `chat.py` | NDJSON streaming, sessions, feedback (ReAct agent) |
| `/alerts` | `alerts.py` | List, dismiss, severity |
| `/sectors` | `sectors.py` | Summary, stocks, correlation |
| `/news` | `news.py` | Dashboard news (per-user cache) |
| `/preferences` | `preferences.py` | User preferences |
| `/convergence` | `convergence.py` | Per-ticker convergence, portfolio convergence, history, sector convergence |
| `/backtesting` | `backtesting.py` | Backtest execution, per-ticker results, summary |
| `/sentiment` | `sentiment.py` | Per-ticker sentiment, bulk, macro, articles |
| `/observability` | `user_observability.py` | User KPIs, queries, assessments |
| `/observability/admin` | `admin_query.py` | Admin KPIs, errors, findings, trace explorer, externals, costs, pipelines, DQ |
| `/admin` | `admin.py` | LLM config, tier health, usage, chat sessions, model reload |
| `/admin/pipelines` | `admin_pipelines.py` | Pipeline groups, runs, triggers, cache, audit log, ingestion health |
| `/admin/command-center` | `command_center.py` | 4-zone command center + drill-down |
| `/health` | `health.py` | Readiness, liveness (k8s probes) |
| `/tasks` | `tasks.py` | Celery task status |
| `/search` | `search.py` | Aggregated search |
| `/observability/frontend-error` | `admin_query.py` | Frontend error beacon (CSRF-exempt) |
| `/observability/deploy-event` | `admin_query.py` | Deploy event webhook |

---

## Observability Infrastructure (shipped Sessions 113-134)

| Layer | Coverage |
|-------|----------|
| **SDK** | `ObservabilityClient` + `EventBuffer` + JSONL spool + `DirectTarget` + `MemoryTarget` |
| **HTTP** | `ObsHttpMiddleware` (request/error logging), PII redaction |
| **Auth** | Auth/OAuth/email event logging, JWT recursion guard |
| **DB** | Slow query detection (>500ms), `_in_obs_write` guard, cache instrumentation |
| **Celery** | Worker heartbeat, queue depth, `@tracked_task` lifecycle events |
| **Agent** | Intent logging, ReAct reasoning events, provider health snapshots |
| **External API** | `ObservedHttpClient` wrapping 10 providers, rate limiter events |
| **Frontend** | Error beacon (sendBeacon), ErrorBoundary, window error listeners |
| **Deploy** | GitHub Actions webhook → deploy_events table |
| **Anomaly** | 12 rules, 5-min scan, auto-close after 3 negative checks, finding dedup |
| **Admin UI** | 8-zone dashboard (health strip, errors, findings, APIs, costs, pipelines, DQ, trace explorer) |
| **MCP Tools** | 13 tools (platform health, trace spans, anomalies, error search, obs self-report) |
| **Retention** | 18 table-specific policies (drop_chunks for hypertables, DELETE for regular) |
| **Semgrep** | 8 observability rules (ban bare httpx, ban utcnow, require tracked_task, etc.) |

---

## Database

| Attribute | Value |
|-----------|-------|
| Engine | PostgreSQL 16 + TimescaleDB |
| Schemas | `public` (app tables) + `observability` (18 obs tables) |
| Tables | 50+ (public) + 18 (observability) |
| Migrations | 46 (Alembic) — head: `0ff65ce55dc5` (migration 045) |
| Hypertables | stock_prices, signal_snapshots, news_articles, forecast_results, portfolio_health_snapshots, recommendation_snapshots, external_api_call_log, rate_limiter_event, request_log, api_error_log, slow_query_log, cache_operation_log, celery_worker_heartbeat, celery_queue_depth, provider_health_snapshot |
| Compression | stock_prices (180d), signal_snapshots (180d), news_articles (60d), external_api_call_log (7d) |
| Retention | 18 policies ranging from 7d (compressed API logs) to 365d (deploy events) |

---

## Tests

| Category | Location | Count |
|----------|----------|-------|
| **Unit** | `tests/unit/` | 2742 tests (255+ files) |
| **API** | `tests/api/` | 454 tests (51 files) |
| **Integration** | `tests/integration/` | 78 tests (24 files) — obs SDK, anomaly lifecycle, MCP tools, retention |
| **E2E** | `tests/e2e/` | 29 Playwright specs — auth, dashboard, portfolio, admin, sectors, obs, Lighthouse |
| **Frontend** | `frontend/src/__tests__/` | 86 test files (Jest + jsdom) |
| **Semgrep** | `tests/semgrep/` | 2 files (custom rule validation) |

---

## Frontend Hooks (18)

| File | Purpose |
|-------|---------|
| `use-stocks.ts` | Signals, prices, OHLC, search, watchlist, fundamentals, news, intelligence, benchmark, analytics, rebalancing, positions, portfolio summary/health/history |
| `use-forecasts.ts` | Ticker forecast, portfolio forecast (full BL+MC), scorecard |
| `use-alerts.ts` | Alert list + mark read |
| `use-sectors.ts` | Sector summary, stocks, correlation |
| `use-sentiment.ts` | Per-ticker sentiment, bulk, macro |
| `use-convergence.ts` | Per-ticker, portfolio, history, sector convergence |
| `use-chat.ts` | Chat sessions, messages, delete |
| `use-stream-chat.ts` | NDJSON chat streaming + state machine |
| `use-observability.ts` | User KPIs, queries, assessments |
| `use-admin-observability.ts` | Admin KPIs, errors, findings, ack/suppress, JIRA draft, externals, costs, pipelines, DQ, trace |
| `use-admin-pipelines.ts` | Pipeline groups, runs, triggers, cache controls |
| `use-command-center.ts` | Command center data + drill-down |
| `use-bulk-transactions.ts` | CSV bulk upload |
| `use-ingest-progress.ts` | Polling ingest state per ticker |
| `use-current-user.ts` | Cached user auth state |
| `use-mounted.ts` | Hydration safety |
| `use-container-width.ts` | Dynamic chart sizing |

---

## Quick Reference

| Attribute | Value |
|-----------|-------|
| **Package Manager** | `uv` (Python), `npm` (Frontend) |
| **Python Version** | 3.12+ |
| **Node Version** | 18+ |
| **Backend Port** | 8181 |
| **Frontend Port** | 3000 |
| **Database Port** | 5433 (Postgres), 5434 (Langfuse DB) |
| **Cache Port** | 6380 (Redis) |
| **Langfuse Port** | 3001 |
| **Testing** | pytest (backend), Jest (frontend), Playwright (E2E) |
| **Linter** | Ruff (Python), ESLint (TypeScript) |
| **Type Checker** | Pyright (Python), TypeScript strict (frontend) |
| **CI Gate** | 13 checks, Semgrep custom rules, path-filter routing |
| **Git Strategy** | Branch from `develop`, PR to `develop`, `main` is production-ready |
| **Tests** | 2742 unit + 454 API + 78 integration + 29 E2E + 551 frontend |
| **Auth** | JWT (httpOnly cookie), OAuth 2.0 (Google), email verification, Resend |

---

**Last updated:** 2026-05-02 | **Session:** 148
