---
scope: project
category: architecture
updated_by: session-133
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

## Observability Package (backend/observability/, 120+ Python files across 11 subdirectories)

**Top-level (11):** `__init__.py`, `client.py`, `bootstrap.py`, `buffer.py`, `spool.py`, `collector.py`, `writer.py`, `langfuse.py`, `context.py`, `token_budget.py`, `span.py`, `queries.py`
- `models/` (21 ORM models): All in `observability` schema. 17 hypertables + 4 regular tables. NOT in `backend/models/__init__.py`.
- `schema/` (11): `v1.py` (ObsEventBase, EventType 24 types, AttributionLayer 10, Severity 4) + per-layer event schemas
- `targets/` (5): `base.py` (protocol), `direct.py`, `internal_http.py`, `memory.py`
- `service/` (11 event writers): `event_writer.py` (dispatcher) + 10 specialized writers routing events to DB
- `instrumentation/` (10): HTTP middleware, DB hooks, cache, auth, celery, agent, external_api, yfinance, providers, pii_redact
- `mcp/` (13 MCP tools): platform_health, trace, anomalies, search_errors, obs_health, cost_breakdown, external_api_stats, deploys, describe_schema, diagnose_pipeline, dq_findings, recent_errors, slow_queries
- `anomaly/` (14): engine.py, persist.py, base.py + 12 anomaly rules
- `routers/` (8): health, ingest, user_observability, admin, admin_query, command_center, deploy_events, frontend_errors
- `metrics/` (5): db_pool, health_checks, http_middleware, pipeline_stats

## DB Migrations

Alembic head: migration 040 (`e0f1a2b3c4d5` — negative_check_count on finding_log).
Recent obs migrations: 030 (schema + schema_versions), 031 (external_api + rate_limiter), 032 (request_log + api_error_log), 033 (auth + oauth + email), 034 (slow_query + cache + db_pool + schema_migration), 035 (celery + beat + queue_depth), 036 (agent + provider_health), 037 (frontend_error + deploy_events), 038 (audit indexes), 039 (finding_log), 040 (negative_check_count).