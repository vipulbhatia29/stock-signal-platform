---
scope: project
category: architecture
updated_by: session-56
---

# System Architecture Overview

## Services

| Service | Port | Entry Point | Stack |
|---------|------|-------------|-------|
| Backend | 8181 | `backend/main.py` | Python 3.12, FastAPI, SQLAlchemy 2.0 async, Celery |
| Frontend | 3000 | `frontend/app/layout.tsx` | Next.js (latest), React, TypeScript, Tailwind CSS, shadcn/ui |
| Postgres | 5433 | Docker | PostgreSQL 16 + TimescaleDB extension |
| Redis | 6380 | Docker | Redis 7 (cache + Celery broker) |
| Celery worker | — | `backend/tasks/__init__.py` | Beat scheduler + worker |
| Docs | 8000 | `mkdocs serve` | MkDocs Material |

**IMPORTANT:** Postgres runs on 5433 (NOT 5432), Redis on 6380 (NOT 6379).

## Agent Architecture (Plan->Execute->Synthesize)

Three-phase LangGraph StateGraph (V1 deleted Session 54):
1. **Planner (LLM):** Intent classification, tool plan, pronoun resolution, response_type routing (Phase 7)
2. **Executor (mechanical):** ToolRegistry, $PREV_RESULT, retries, circuit breaker, 45s timeout, param validation (Phase 7)
3. **Synthesizer (LLM):** Confidence scoring, scenarios, evidence tree, output validation (Phase 7)

24 internal tools + 4 MCP adapters = 28 total (36 with adapter sub-tools). See `domain/agent-tools` for full list.

Phase 7 additions: input/output guardrails, PII/injection detection, financial disclaimer, portfolio health scoring, market briefings, stock intelligence, multi-signal recommendations.

## LLM Routing (Phase 6A)

Data-driven cascade from `llm_model_config` DB table (migration 012). TokenBudget tracks per-model limits. Admin API at `/api/v1/admin/llm-models`.

## DB Migrations

Alembic head: migration 014 (beta/dividend_yield/forward_pe on stocks).
Chain: 012 (LLM config) -> 013 (decline_count on chat_session) -> 014 (enriched stock data).

## Key Entry Points

- `backend/main.py` — FastAPI app, mounts all routers (including market router added Phase 7)
- `backend/config.py` — Pydantic Settings from `backend/.env`
- `backend/database.py` — async engine + `async_session_factory`
- `backend/dependencies.py` — `get_current_user` JWT dependency
- `backend/tools/registry.py` — ToolRegistry (24 internal + MCP adapters)
- `backend/tools/build_registry.py` — constructs registry with all 24 tools
- `backend/agents/guards.py` — input/output guardrails (Phase 7)
- `backend/mcp_server/server.py` — FastMCP at `/mcp` (Streamable HTTP)

## Core Architecture Patterns

- **No module-level mutable state** — constants + settings only
- **Async by default** — Celery tasks bridge via `asyncio.run()`
- **Tool boundary for external APIs** — all external calls through `backend/tools/`
- **Pre-computed signals** — nightly Celery Beat; dashboard reads pre-computed data
- **Three-layer MCP** — consume external MCPs -> enrich -> expose at `/mcp`

## Environment Variables

All secrets in `backend/.env` (gitignored). Template: `backend/.env.example`.
CI-only: `CI_DATABASE_URL`, `CI_REDIS_URL`, `CI_JWT_SECRET_KEY`, `CI_JWT_ALGORITHM`, `CI_POSTGRES_PASSWORD`
