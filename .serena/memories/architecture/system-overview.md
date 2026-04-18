---
scope: project
category: architecture
updated_by: session-118
---

# System Architecture Overview

## Services

| Service | Port | Entry Point | Stack |
|---------|------|-------------|----------|
| Backend | 8181 | `backend/main.py` | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Celery |
| Frontend | 3000 | `frontend/src/app/layout.tsx` | Next.js (latest), React, TypeScript, Tailwind CSS, shadcn/ui |
| Postgres | 5433 | Docker | PostgreSQL 16 + TimescaleDB extension |
| Redis | 6380 | Docker | Redis 7 (cache + Celery broker) |
| Langfuse | 3001 | Docker | Observability (LLM traces, cost tracking) |
| Langfuse DB | 5434 | Docker | PostgreSQL for Langfuse |
| Celery worker | — | `backend/tasks/__init__.py` | Beat scheduler + worker |
| Docs | 8000 | `mkdocs serve` | MkDocs Material |

**IMPORTANT:** Postgres 5433 (NOT 5432), Redis 6380 (NOT 6379), Langfuse 3001+5434.

## Key Entry Points

- `backend/main.py` — FastAPI app, mounts all routers
- `backend/config.py` — Pydantic Settings from `backend/.env`
- `backend/database.py` — async engine + `async_session_factory`
- `backend/dependencies.py` — `get_current_user` JWT dependency
- `backend/services/cache.py` — CacheService (3-tier namespace, 4 TTL tiers)
- `backend/services/redis_pool.py` — shared Redis connection pool
- `backend/services/token_blocklist.py` — Redis JTI blocklist for refresh token rotation
- `backend/observability/collector.py` — Langfuse trace collection

## Routers (17 top-level modules + 2 subpackages, all mounted at /api/v1/)

**Top-level (17):** admin, admin_pipelines, alerts, backtesting, chat, convergence, forecasts, health, indexes, market, news, observability, portfolio, preferences, sectors, sentiment, tasks
**Subpackages:**
- `auth/` — core, admin, oauth, oidc, password, email_verification, _helpers
- `stocks/` — data, search, watchlist, recommendations, _helpers

## Models (27+ files in backend/models/)

**Core:** alert, chat, dividend, earnings, forecast, index, llm_config, logs, pipeline, portfolio, portfolio_health, price, recommendation, signal, stock, user, base
**Phase 8.6+ additions (11+):** backtest, convergence, news_sentiment, audit (admin audit log), oauth_account, login_attempt, sentiment_score, cache_entry, forecast_component, rate_limit_event, agent_metadata
**Pipeline Overhaul additions (2):** ticker_ingestion_state (migration 025), dq_check_history (migration 027)
**Observability additions (3):** schema_versions (migration 030), external_api_call_log (migration 031), rate_limiter_event (migration 031) — all in `observability` schema, NOT in backend/models/__init__.py

## Frontend Pages & Components

**Pages:**
- Dashboard (`src/app/(authenticated)/dashboard/`)
- Portfolio (`src/app/(authenticated)/portfolio/`)
- Screener (`src/app/(authenticated)/screener/`)
- Sectors (`src/app/(authenticated)/sectors/`)
- Stock Detail (`src/app/(authenticated)/stocks/[ticker]/`)
- Login + Register (`src/app/login/`, `src/app/register/`)

**New Phase 8.6+ Component Trees:**
- `src/components/convergence/` — TrafficLightRow, DivergenceAlert, ConvergenceSummary, ConvergenceChart
- `src/components/portfolio/` — PortfolioForecastCard, RationaleSection, AccuracyBadge, BLForecastCard, MonteCarloChart, CVaRCard
- **16 custom hooks** across all components (useSignalConvergence, usePortfolioForecast, etc.)

## Services (21+ in backend/services/)

**Core:** cache, redis_pool, token_blocklist
**Phase 8.6+ additions (18+):**
- BacktestEngine — backtesting logic, Monte Carlo, optimization
- CacheInvalidator — event-driven cache warming + expiry
- SignalConvergenceService — cross-signal voting, divergence detection
- PortfolioForecastService — Bayesian forecast aggregation, confidence intervals
- RationaleGenerator — forecast explanation + narrative scoring
- NewsIngestionService — news feed aggregation
- SentimentScorer — NLP sentiment → 0-10 scale
- PipelineRegistry — task orchestration metadata
- GroupRunManager — batch Celery execution coordinator
- EmailService — Resend integration
- GoogleOAuthService — OAuth 2.0 flow + token exchange
- 4 News Providers — NewsAPI, Finnhub, Guardian, Seeking Alpha adapters

## Celery Task Files (15 in backend/tasks/)

**Original (8):** alerts, evaluation, forecasting, market_data, pipeline, portfolio, recommendations, warm_data
**Phase 8.6+ additions (7):** convergence, news_sentiment, audit, warm_data (extended), assessment_runner, scoring_engine, golden_dataset, seed_tasks
**Pipeline Overhaul additions (2):** dq_scan, retention

## Observability Package (backend/observability/, 30+ Python files)

**Top-level (9):** `__init__.py`, `collector.py`, `writer.py`, `langfuse.py`, `context.py`, `token_budget.py`, `queries.py`, `client.py`, `bootstrap.py`, `buffer.py`, `spool.py`
- `metrics/` subpackage (5): `__init__.py`, `db_pool.py`, `health_checks.py`, `http_middleware.py`, `pipeline_stats.py` — Prometheus-style metric recording
- `routers/` subpackage (6): `__init__.py`, `admin.py`, `health.py`, `user_observability.py`, `command_center.py`, `ingest.py`
- `models/` subpackage (4): `__init__.py`, `schema_versions.py`, `external_api_call.py`, `rate_limiter_event.py`
- `schema/` subpackage (4): `__init__.py`, `v1.py`, `external_api_events.py`, `rate_limiter_events.py`
- `targets/` subpackage (5): `__init__.py`, `base.py`, `direct.py`, `internal_http.py`, `memory.py`
- `service/` subpackage (4): `__init__.py`, `event_writer.py`, `external_api_writer.py`, `rate_limiter_writer.py`
- `instrumentation/` subpackage (4): `__init__.py`, `external_api.py`, `providers.py`, `yfinance_session.py`
- `mcp/describe_schema.py` (skeleton)

## Agent Architecture — ReAct Loop (Phase 8B, Session 63)

Single-LLM reasoning loop (old Plan->Execute->Synthesize behind REACT_AGENT=false flag):
1. **Reason:** LLM observes scratchpad -> outputs thought + next_action OR finish
2. **Act:** Runs ONE tool, appends result to scratchpad
3. **Loop:** Repeats until LLM emits finish or circuit breaker (max iterations)
4. **Fast path:** Rule-based intent classifier filters tool set (zero LLM cost for out_of_scope/simple_lookup)

25 internal tools + 4 MCP adapters = 29 total.

## LLM Routing (Phase 6A)

Data-driven cascade from `llm_model_config` DB table (migration 012). TokenBudget tracks per-model limits via Redis sorted sets (KAN-186, Session 67 — multi-worker safe, fail-open). Admin API at `/api/v1/admin/llm-models`.

## DB Migrations

Alembic head: migration 031 (`d5e6f7a8b9c0` — external_api + rate_limiter hypertables).
Recent migrations: 025 (ticker_ingestion_state), 026 (celery_task_id on pipeline_runs), 027 (dq_check_history), 028 (timescaledb_compression), 029 (backtest_unique_constraint), 030 (observability schema + schema_versions), 031 (external_api_call_log + rate_limiter_event hypertables).
No gaps in revision chain.

## Core Architecture Patterns

- **No module-level mutable state** — constants + settings only
- **Async by default** — Celery tasks bridge via `asyncio.run()`
- **Tool boundary for external APIs** — all external calls through `backend/tools/`
- **Pre-computed signals** — nightly Celery Beat; dashboard reads pre-computed data
- **Three-layer MCP** — consume external MCPs -> enrich -> expose at `/mcp`
- **Cache invalidation via events** — Celery tasks emit cache-buster payloads on signal change
- **Langfuse tracing on all LLM calls** — cost + latency visibility for token budget enforcement

## Environment Variables

All secrets in `backend/.env` (gitignored). Template: `backend/.env.example`.
CI-only: `CI_DATABASE_URL`, `CI_REDIS_URL`, `CI_JWT_SECRET_KEY`, `CI_JWT_ALGORITHM`, `CI_POSTGRES_PASSWORD`
Phase 8.6+ additions: `LANGFUSE_*`, `RESEND_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID/SECRET`, news provider API keys
