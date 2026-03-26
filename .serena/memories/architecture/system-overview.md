---
scope: project
category: architecture
updated_by: session-59
---

# System Architecture Overview

## Services

| Service | Port | Entry Point | Stack |
|---------|------|-------------|-------|
| Backend | 8181 | `backend/main.py` | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Celery |
| Frontend | 3000 | `frontend/src/app/layout.tsx` | Next.js (latest), React, TypeScript, Tailwind CSS, shadcn/ui |
| Postgres | 5433 | Docker | PostgreSQL 16 + TimescaleDB extension |
| Redis | 6380 | Docker | Redis 7 (cache + Celery broker) |
| Celery worker | — | `backend/tasks/__init__.py` | Beat scheduler + worker |
| Docs | 8000 | `mkdocs serve` | MkDocs Material |

**IMPORTANT:** Postgres runs on 5433 (NOT 5432), Redis on 6380 (NOT 6379).

## Agent Architecture (Plan->Execute->Synthesize)

LangGraph StateGraph with 4 nodes (V1 deleted Session 54):
1. **Planner (LLM):** Intent classification, tool plan, pronoun resolution, response_type routing (Phase 7)
2. **Executor (mechanical):** ToolRegistry, $PREV_RESULT, retries, circuit breaker, 45s timeout, param validation (Phase 7)
3. **Synthesizer (LLM):** Confidence scoring, scenarios, evidence tree, output validation (Phase 7)
4. **format_simple:** Bypass synthesis for simple_lookup intents (template output, no LLM)

24 internal tools + 4 MCP adapters = 28 total (36 with adapter sub-tools). See `domain/agent-tools` for full list.

Phase 7 additions: input/output guardrails, PII/injection detection, financial disclaimer, portfolio health scoring, market briefings, stock intelligence, multi-signal recommendations.

## LLM Routing (Phase 6A)

Data-driven cascade from `llm_model_config` DB table (migration 012). TokenBudget tracks per-model limits (in-process only — KAN-186 will move to Redis for multi-worker). Admin API at `/api/v1/admin/llm-models`.

## DB Migrations

Alembic head: migration 015 (portfolio_health_snapshots).
Chain: 012 (LLM config) -> 013 (decline_count) -> 014 (enriched stock data) -> 015 (portfolio_health_snapshots).

## Key Entry Points

- `backend/main.py` — FastAPI app, mounts all routers (including market router added Phase 7)
- `backend/config.py` — Pydantic Settings from `backend/.env`
- `backend/database.py` — async engine + `async_session_factory`
- `backend/dependencies.py` — `get_current_user` JWT dependency
- `backend/tools/registry.py` — ToolRegistry (24 internal + MCP adapters)
- `backend/tools/build_registry.py` — constructs registry with all 24 tools
- `backend/agents/guards.py` — input/output guardrails (Phase 7)
- `backend/mcp_server/server.py` — FastMCP at `/mcp` (Streamable HTTP)
- `backend/mcp_server/tool_server.py` — stdio MCP server (Phase 5.6, for agent use when MCP_TOOLS=True)
- `backend/mcp_server/tool_client.py` — MCPToolClient (wraps params for FastMCP dispatch)
- `backend/services/cache.py` — CacheService (3-tier namespace, 4 TTL tiers)
- `backend/services/redis_pool.py` — shared Redis connection pool
- `backend/services/token_blocklist.py` — Redis JTI blocklist for refresh token rotation

## Routers (13 files, all mounted at /api/v1/)

admin, alerts, auth, chat, forecasts, health, indexes, market, portfolio, preferences, sectors, stocks, tasks

## Models (17 files in backend/models/)

alert, chat, dividend, earnings, forecast, index, llm_config, logs, pipeline, portfolio, portfolio_health, price, recommendation, signal, stock, user + base

## Frontend Pages

- Dashboard (`src/app/(authenticated)/dashboard/`)
- Portfolio (`src/app/(authenticated)/portfolio/`)
- Screener (`src/app/(authenticated)/screener/`)
- Sectors (`src/app/(authenticated)/sectors/`)
- Stock Detail (`src/app/(authenticated)/stocks/[ticker]/`)
- Login + Register (`src/app/login/`, `src/app/register/`)

## Celery Task Modules (8 in backend/tasks/)

alerts, evaluation, forecasting, market_data, pipeline, portfolio, recommendations, warm_data

## Core Architecture Patterns

- **No module-level mutable state** — constants + settings only
- **Async by default** — Celery tasks bridge via `asyncio.run()`
- **Tool boundary for external APIs** — all external calls through `backend/tools/`
- **Pre-computed signals** — nightly Celery Beat; dashboard reads pre-computed data
- **Three-layer MCP** — consume external MCPs -> enrich -> expose at `/mcp`

## Environment Variables

All secrets in `backend/.env` (gitignored). Template: `backend/.env.example`.
CI-only: `CI_DATABASE_URL`, `CI_REDIS_URL`, `CI_JWT_SECRET_KEY`, `CI_JWT_ALGORITHM`, `CI_POSTGRES_PASSWORD`
