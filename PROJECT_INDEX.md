# Project Index: Stock Signal Platform

Stock analysis SaaS for part-time investors — US equities, signal detection, portfolio tracking, AI-powered recommendations. Multi-user cloud deployment target.

**Generated:** 2026-04-03 | **Alembic head:** `b2351fa2d293` (migration 024)

---

## Repository Structure (Top 2 Levels)

```
backend/                       FastAPI + SQLAlchemy async + Celery
├── agents/ (20 files)         LangGraph ReAct, guards, intent, providers
├── migrations/versions/ (24)   Alembic migrations (TimescaleDB hypertables)
├── models/ (27 files)          SQLAlchemy 2.0 ORM models
├── observability/ (18 files)   Collector, writer, langfuse, token budget
├── routers/ (19 files)         API endpoints under /api/v1/
│   └── stocks/ (4 files)       Data, search, watchlist, recommendations
├── schemas/ (13 files)         Pydantic v2 request/response models
├── services/ (21 files)        Business logic: signals, portfolio, cache, pipeline
├── tasks/ (12 files)           Celery tasks: market data, alerts, forecasts
└── tools/ (30+ files)          25 internal tools + 4 MCP adapters + registry

frontend/                        Next.js 15 + TypeScript + Tailwind v4 + shadcn/ui
├── src/app/                    8 auth-protected route groups
├── src/components/ (68+)       UI components + domain-specific
├── src/hooks/ (16 files)       TanStack Query hooks
├── src/lib/                    api.ts (fetch wrapper), auth, format, utils
└── src/__tests__/ (540 files)  Jest + MSW v2 test suites

tests/                           1768 backend tests (unit, api, integration, e2e, semgrep)
├── unit/ (163 files)           Services, routers, tools, agents, pipeline, guards
├── api/ (40 files)             Endpoint tests with testcontainers
├── integration/ (7 files)       MCP stdio, regression, migration validation
├── e2e/ (6 files)              Playwright tests (dashboard, auth, portfolio)
├── fixtures/ (8 files)          Factory-boy model fixtures
└── semgrep/ (2 files)          Custom rule validation tests

docs/                            Specifications and plans
├── PRD.md, FSD.md, TDD.md      Product, functional, technical specs
├── superpowers/specs/ (20)     Design docs per sprint
├── superpowers/plans/ (20)     Implementation plans per sprint
└── superpowers/archive/        Completed features

.github/workflows/              6 CI/CD pipelines
├── ci-pr.yml                   13 checks, path-filter routing, ci-gate
├── ci-merge.yml                Build verification
├── ci-nightly.yml              Weekdays 04:00 UTC: Lighthouse + perf + heap
├── ci-eval.yml                 LLM agent evaluation
├── assessment.yml              Golden dataset + QuantStats validation
└── deploy.yml                  Production deployment

.semgrep/                        13 custom Semgrep rules (Hard Rules + JWT + OAuth)
```

---

## Entry Points

| Service | Command | Port | File |
|---------|---------|------|------|
| **Backend API** | `uv run uvicorn backend.main:app --reload --port 8181` | 8181 | `backend/main.py` |
| **Frontend** | `cd frontend && npm run dev` | 3000 | `frontend/` |
| **Celery Worker** | `uv run celery -A backend.tasks worker --loglevel=info` | — | `backend/tasks/__init__.py` |
| **Celery Beat** | Scheduled via celery-beat (nightly pipeline at 04:00 UTC) | — | `backend/tasks/market_data.py` |
| **MCP Tool Server** | `uv run python -m backend.mcp_server` | stdio | `backend/mcp_server.py` |
| **Migrations** | `uv run alembic upgrade head` | — | `backend/migrations/` |
| **Docs** | `uv run mkdocs serve` | 8000 | `mkdocs.yml` |

---

## Backend Routers (19)

| Prefix | File | Purpose |
|--------|------|---------|
| `/auth` | `auth.py` | Login, register, refresh, logout, OAuth, email verification, password reset, account settings, deletion |
| `/stocks` | `stocks/` | Signals, prices, OHLC, search, watchlist, fundamentals, news, intelligence, benchmark |
| `/portfolio` | `portfolio.py` | Transactions, positions, summary, history, dividends, rebalancing, analytics, health |
| `/recommendations` | `recommendations.py` | List, history |
| `/forecasts` | `forecasts.py` | Ticker, portfolio, sectors |
| `/indexes` | `indexes.py` | List, membership |
| `/chat` | `chat.py` | NDJSON streaming, sessions, feedback (ReAct agent) |
| `/alerts` | `alerts.py` | List, dismiss, severity |
| `/sectors` | `sectors.py` | Summary, stocks, correlation |
| `/news` | `news.py` | Dashboard news (per-user cache) |
| `/preferences` | `preferences.py` | User preferences (theme, rebalancing_strategy, etc.) |
| `/observability` | `observability.py` | KPIs, queries, assessments, performance metrics |
| `/admin` | `admin.py` | System health, LLM config, command center, pipelines |
| `/health` | `health.py` | Readiness, liveness (k8s probes) |
| `/tasks` | `tasks.py` | Pipeline control, status (admin only) |
| `/convergence` | `convergence.py` | Signal rationale, correlation, historical analysis |
| `/backtesting` | `backtesting.py` | Backtest execution, results |
| `/sentiment` | `sentiment.py` | News sentiment (per ticker, aggregate) |
| `/search` | `search.py` | Aggregated search (stocks, news, intelligence) |

---

## Backend Services (21)

| File | Purpose |
|------|---------|
| `email.py` | Resend API integration (verification, reset, deletion emails) |
| `google_oauth.py` | OAuth 2.0 auth code flow, JWKS validation |
| `signals.py` | Signal computation (RSI, MACD, Bollinger, momentum, trend) |
| `portfolio.py` | Position tracking, P&L, asset allocation |
| `stock_data.py` | Price ingest, OHLC, fundamentals, earnings |
| `recommendations.py` | Signal-based buy/sell recommendations |
| `cache.py` | Redis caching layer (TTL, invalidation) |
| `cache_invalidator.py` | Cache invalidation triggers (price, signals, portfolio) |
| `news/` | News ingestion (GDELT, Edgar earnings) |
| `pipeline_registry.py` | Task pipeline orchestration + dependency graph |
| `pipelines.py` | 9-step nightly pipeline (cache, price, forecast, alerts, health, drift) |
| `observability_queries.py` | SQL queries for observability KPIs |
| `langfuse_service.py` | LLM tracing integration |
| `oidc_provider.py` | OIDC identity provider (for SSO) |
| `rationale.py` | Signal convergence rationale generation |
| `signal_convergence.py` | Multi-signal consensus + alerts |
| `portfolio_forecast.py` | Portfolio-level forecasting + optimization |
| `redis_pool.py` | Redis connection pooling (graceful degradation) |
| `token_blocklist.py` | JWT revocation tracking (user-level logout) |
| `watchlist.py` | Watchlist persistence + sync |
| `backtesting.py` | Historical signal backtesting + metrics |

---

## Backend Models (27)

| File | Model | Purpose |
|------|-------|---------|
| `user.py` | User | Identity, email, password hash, email_verified, deleted_at |
| `oauth_account.py` | OAuthAccount | OAuth provider linking (Google, Microsoft) |
| `stock.py` | Stock | Ticker, company name, sector, beta, dividend yield, forward P/E |
| `price.py` | StockPrice | ⏱️ Hypertable — OHLC, volume, timestamp |
| `signal.py` | SignalSnapshot | ⏱️ Hypertable — signal values per indicator + composite score |
| `portfolio.py` | Portfolio | User's collection of positions |
| `portfolio.py` | Position | Holding (ticker, avg_cost_basis, quantity, portfolio_id) |
| `portfolio.py` | Transaction | Buy/sell + dividend reinvestment |
| `portfolio_health.py` | PortfolioHealthSnapshot | ⏱️ Hypertable — health metrics (Sortino, drawdown, VaR) |
| `forecast.py` | ForecastResult | Prophet price forecast (mean, CI 25/75/5/95) |
| `forecast.py` | ModelVersion | Forecast model metadata (Prophet params, train date) |
| `recommendation.py` | RecommendationSnapshot | ⏱️ Hypertable — BUY/WATCH/AVOID + rationale |
| `recommendation.py` | RecommendationOutcome | Feedback (user_id, recommendation_id, outcome) |
| `alert.py` | InAppAlert | User alerts (severity, dismissal) |
| `earnings.py` | EarningsSnapshot | Announced earnings dates + historical results |
| `dividend.py` | DividendPayment | Dividend history (payment_date, amount_per_share) |
| `news_sentiment.py` | NewsSentimentSnapshot | ⏱️ Hypertable — ticker sentiment + source counts |
| `convergence.py` | ConvergenceSignal | Signal agreement matrix + rationale |
| `assessment.py` | AssessmentResult | Backtest outcome (signal, buy_date, sell_date, return %) |
| `assessment.py` | AssessmentRun | Backtest campaign metadata |
| `chat.py` | ChatSession | Conversation history container |
| `chat.py` | ChatMessage | Message (role, content, tool_calls, created_at) |
| `logs.py` | LLMCallLog | LLM API call (model, tokens, latency, cost) |
| `logs.py` | ToolExecutionLog | Tool invocation (tool_name, input, output, latency) |
| `index.py` | Index | Market index (S&P 500, Nasdaq, Russell 2000) |
| `index.py` | IndexMembership | Stock in index (ticker, weight, added_date) |
| `llm_config.py` | LLMModelConfig | Model params (temperature, max_tokens, cost/1M tokens) |
| `login_attempt.py` | LoginAttempt | Failed login tracking (brute-force detection) |
| `audit.py` | AuditLog | User actions (portfolio, preferences, orders) |
| `pipeline.py` | PipelineRun | Task execution log (status, start, end, error) |
| `pipeline.py` | PipelineWatermark | Incremental ingest watermark (last_processed_date) |

**Hypertables (⏱️):** StockPrice, SignalSnapshot, PortfolioHealthSnapshot, RecommendationSnapshot, NewsSentimentSnapshot — compress older chunks, drop data > 2 years.

---

## Backend Tasks (12)

| File | Purpose |
|------|---------|
| `market_data.py` | 9-phase nightly pipeline (cache, SPY, price, forecast, alerts, health, drift, rebalancing, cleanup) |
| `alerts.py` | Alert generation (price thresholds, signal divergence, portfolio risk) |
| `forecasting.py` | Prophet model training + price forecasts |
| `news_sentiment.py` | GDELT ingest + sentiment scoring |
| `convergence.py` | Multi-signal agreement + rationale generation |
| `portfolio.py` | Portfolio snapshot, P&L, rebalancing suggestions |
| `assessment_runner.py` | Backtest suite runner (10-year rolling windows) |
| `scoring_engine.py` | Composite signal scoring (weighting, calibration) |
| `recommendations.py` | Buy/watch/avoid recommendations (+ outcome tracking) |
| `evaluation.py` | Recommendation accuracy metrics (precision, recall, AUROC) |
| `seed_tasks.py` | Golden dataset seeding (pre-computed baselines) |
| `warm_data.py` | Cache warming on startup |

---

## Frontend Hooks (16)

| File | Purpose |
|-------|---------|
| `use-stocks.ts` | Stock search, watchlist, signal snapshot |
| `use-portfolio.ts` | Positions, transactions, summary |
| `use-forecasts.ts` | Price forecasts (ticker + portfolio level) |
| `use-recommendations.ts` | Buy/watch/avoid + historical outcomes |
| `use-alerts.ts` | Alert list + dismiss |
| `use-sectors.ts` | Sector summary, correlation heatmap |
| `use-sentiment.ts` | News sentiment (per ticker, aggregate) |
| `use-convergence.ts` | Signal rationale + agreement matrix |
| `use-chat.ts` | Chat sessions + streaming messages |
| `use-observability.ts` | KPI queries, performance charts |
| `use-admin-pipelines.ts` | Pipeline control, status monitoring |
| `use-command-center.ts` | Command center state + execution |
| `use-current-user.ts` | Cached user (email, preferences, auth status) |
| `use-mounted.ts` | Hydration safety helper |
| `use-container-width.ts` | Dynamic chart sizing |
| `use-stream-chat.ts` | NDJSON chat streaming |

---

## Frontend Components (68+)

**Charts:** candlestick-chart, correlation-heatmap, correlation-table, allocation-donut, benchmark-chart
**Alerts:** alert-bell, alert-tile, action-badge
**Domain:** chat (panel, message, input), command-center (palette, results), convergence (heatmap, rationale)
**Admin:** admin (pipelines, health), email-verification-banner
**Layout:** breadcrumbs, empty-state, chart-tooltip
**Data Tables:** correlation-ticker-chips, dividend-card, recommendation-table

---

## Database

| Attribute | Value |
|-----------|-------|
| Engine | PostgreSQL 16 + TimescaleDB |
| Tables | 30+ (4 hypertables for time-series) |
| Migrations | 24 (Alembic) — head: `b2351fa2d293` |
| Foreign Keys | User → OAuthAccount (users.id), Position → Portfolio, Portfolio → User |
| Indexes | 40+ (TimescaleDB indexes on hypertables, regular B-tree on lookups) |
| Retention | Hypertable chunks compressed after 30 days, purged after 2 years |

---

## Tests

| Category | Location | Count |
|----------|----------|-------|
| **Unit** | `tests/unit/` | 163 files (services, tools, agents, guards, pipeline, signals) |
| **API** | `tests/api/` | 40 files (endpoint tests + testcontainers) |
| **Integration** | `tests/integration/` | 7 files (MCP, regression, migration) |
| **E2E** | `tests/e2e/` | 6 files (Playwright: auth, portfolio, dashboard) |
| **Frontend** | `frontend/src/__tests__/` | 540 files (Jest + MSW v2) |
| **Semgrep** | `tests/semgrep/` | 2 files (custom rule validation) |
| **Nightly** | `.github/workflows/ci-nightly.yml` | Lighthouse, perf, heap, responsive (weekdays 04:00 UTC) |
| **Backend Total** | — | 1768 tests |
| **Frontend Total** | — | 540 tests |
| **Grand Total** | — | ~2308 tests |

**Coverage:** ~66% backend (floor: 60%), enforced in CI. Frontend: Snapshot + integration tests, no strict % floor.

---

## Agent Architecture

| Component | File | Purpose |
|-----------|------|---------|
| **ReAct Loop** | `agents/react_loop.py` | Feature-flagged (`REACT_AGENT=true`) agentic routing |
| **Intent Classifier** | `agents/intent_classifier.py` | 8 intents (analyze, screen, forecast, chat, portfolio, sector, search, market) |
| **Planner** | `agents/planner.py` | Multi-step plan generation + feedback loop |
| **Stock Agent** | `agents/stock_agent.py` | Stock-specific analysis tools |
| **General Agent** | `agents/general_agent.py` | Multi-intent orchestration |
| **Executor** | `agents/executor.py` | Tool execution + retries |
| **Guard Rails** | `agents/guards.py` | Input validation, cost limits, safety checks |
| **Result Validator** | `agents/result_validator.py` | Output validation (schema, feasibility) |
| **Internal Tools** | `backend/tools/` | 25 tools (analyze_stock, screen_stocks, compute_signals, get_recommendations, web_search, geopolitical, earnings_history, dividend_sustainability, risk_narrative, portfolio_health, market_briefing, stock_intelligence) |
| **MCP Adapters** | `backend/tools/` | Edgar (10-K), Alpha Vantage (news), FRED (economic), Finnhub (ratings) |

---

## CI/CD Pipelines

| Workflow | Events | Jobs | Gate | Notes |
|----------|--------|------|------|-------|
| `ci-pr.yml` | Push to `feat/*`, `hotfix/*` | 13 checks | path-filter + ci-gate | Lint, type-check, unit, api, semgrep, frontend lint/test |
| `ci-merge.yml` | Merge to `develop` | Build only | — | Final validation before integration |
| `ci-nightly.yml` | Weekdays 04:00 UTC | Lighthouse, perf, heap, responsive | — | E2E against production build |
| `ci-eval.yml` | Manual trigger | LLM agent eval | — | Golden dataset + QuantStats assessment |
| `assessment.yml` | Manual trigger | Golden dataset validation | — | End-to-end signal/recommendation accuracy |
| `deploy.yml` | Tag (vX.Y.Z) | Build + ECR + deploy | — | Production deployment to ECS |

**CI Gate:** 13 checks (12 required green, type-check advisory). Semgrep violations fail the gate.

---

## Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Python 3.12, dependencies, test config, Ruff, Pyright, coverage |
| `docker-compose.yml` | Local services (Postgres 5433, Redis 6380, Langfuse 3001/5434) |
| `alembic.ini` | Alembic configuration (sqlalchemy.url from env) |
| `mkdocs.yml` | Documentation site generator |
| `.pre-commit-config.yaml` | Git hooks (ruff lint/format, Pyright) |
| `.semgrep.yml` | 13 custom rules (Hard Rules, JWT, OAuth, async safety) |
| `tsconfig.json` | TypeScript strict mode, paths, lib |
| `jest.config.js` | Frontend test runner (testEnvironment: jsdom + MSW v2) |
| `next.config.js` | Next.js 15 config (font, image optimization, redirects) |

---

## Documentation

| File | Purpose |
|------|---------|
| `docs/PRD.md` | Product requirements: vision, use cases, market fit |
| `docs/FSD.md` | Functional requirements + acceptance criteria |
| `docs/TDD.md` | Technical design: API contracts, data model, architecture |
| `docs/data-architecture.md` | TimescaleDB hypertable strategy, retention, compression |
| `docs/ADR.md` | Architecture decision records (11 total) |
| `docs/superpowers/specs/` | 20 design specs per sprint (Specs A, B, C, D) |
| `docs/superpowers/plans/` | 20 implementation plans |
| `docs/superpowers/archive/` | Completed specs + progress logs |
| `README.md` | Quick start, architecture, local dev setup |
| `PROGRESS.md` | Session log (last 3 sessions detailed, archive older) |
| `PROJECT_INDEX.md` | **This file** — orientation guide |

---

## Quick Reference

| Attribute | Value |
|-----------|-------|
| **Package Manager** | `uv` (Python), `npm` (Frontend) |
| **Python Version** | 3.12+ |
| **Node Version** | 18+ (for Next.js 15) |
| **Backend Ports** | 8181 (API), 8000 (Docs) |
| **Frontend Ports** | 3000 (dev), 3001 (Langfuse) |
| **Database Ports** | 5433 (Postgres), 5434 (Langfuse DB) |
| **Cache Port** | 6380 (Redis) |
| **Testing Framework** | pytest (backend), Jest (frontend), Playwright (E2E) |
| **Linter** | Ruff (Python), ESLint (TypeScript) |
| **Type Checker** | Pyright (Python), TypeScript strict (frontend) |
| **Coverage Floor** | 60% (backend), none enforced (frontend) |
| **CI Gate** | 13 checks, Semgrep custom rules, path-filter routing |
| **Git Strategy** | Branch from `develop`, PR to `develop`, `main` is production-ready |
| **Alembic Head** | `b2351fa2d293` (migration 024 — forecast intelligence tables) |
| **Tests Total** | ~2308 (1768 backend + 540 frontend) |
| **Observability** | Langfuse (LLM tracing), structlog (logging), Prometheus-ready |
| **Auth** | JWT (httpOnly cookie), OAuth 2.0 (Google), email verification |
| **Email** | Resend API (verification, password reset, notifications) |

---

**Last updated:** 2026-04-03 | **Session:** 91
