---
scope: project
category: architecture
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

**IMPORTANT:** Postgres runs on 5433 (NOT 5432), Redis on 6380 (NOT 6379) — non-default Docker ports.

## Key Entry Points

- `backend/main.py` — FastAPI app factory, mounts all routers, registers startup events
- `backend/config.py` — Pydantic Settings, reads from `backend/.env`, single source of truth for all config
- `backend/database.py` — async engine + `async_session_factory` (correct import name)
- `backend/dependencies.py` — `get_current_user` FastAPI dependency (JWT validation + DB lookup)
- `backend/tools/registry.py` — `ToolRegistry` (all agent tools + MCPAdapters discoverable here)
- `backend/agents/base.py` — `BaseAgent` ABC (StockAgent, GeneralAgent)
- `backend/mcp_server/server.py` — FastMCP server at `/mcp` (Streamable HTTP)
- `frontend/app/(authenticated)/layout.tsx` — authenticated shell: SidebarNav | Topbar + main | ChatPanel

## Core Architecture Patterns

- **No module-level mutable state** — all mutable state in class instances or request scope. Only constants (UPPER_CASE) and `settings` at module level.
- **Async by default** — all FastAPI endpoints and DB operations use `async`/`await`. Celery tasks are the exception (sync, bridge via `asyncio.run()`).
- **Tool boundary for external APIs** — yfinance, FRED, web search calls go through `backend/tools/`, never directly from routers. Routers call services or tools only. Exception: DividendSustainabilityTool calls yfinance on-demand.
- **Pre-computed signals** — Celery Beat runs nightly signal computation; dashboard reads pre-computed data. Agents call tools on-demand.
- **Three-layer MCP architecture** — Layer 1: consume external MCPs (EdgarTools, Alpha Vantage, FRED, Finnhub). Layer 2: enrich in backend (Tool Registry + caching). Layer 3: expose as MCP server at `/mcp` (Streamable HTTP). See `domain/agent-tools` memory for full details.

## LLM Routing (Phase 6A — data-driven cascade)

LLMClient supports `tier_config` for routing different agent phases to different providers:
- **Planner tier** — Groq cascade (llama-3.3-70b → kimi-k2 → llama-4-scout → Sonnet → GPT-4o)
- **Synthesizer tier** — Groq cascade (gpt-oss-120b → kimi-k2 → Sonnet → GPT-4o)
- **Executor** — no LLM (mechanical tool execution)

Model cascade is data-driven from `llm_model_config` DB table (migration 012). TokenBudget tracks TPM/RPM/TPD/RPD per model with 80% proactive threshold. Admin API at `/api/v1/admin/llm-models` (superuser-only).

V1 ReAct graph DELETED in Session 54. AGENT_V2 flag removed. V2 Plan→Execute→Synthesize is the only path.

## Agent Architecture (Plan→Execute→Synthesize)

Three-phase LangGraph StateGraph (V1 ReAct deleted in Session 54):
1. **Planner (LLM):** Classifies intent (stock_analysis/portfolio/market_overview/simple_lookup/out_of_scope), generates ordered tool plan, enforces financial-only scope
2. **Executor (mechanical):** Runs tools via ToolRegistry, resolves `$PREV_RESULT` references, retries (max 1), circuit breaker (3 failures), 45s wall clock timeout
3. **Synthesizer (LLM):** Produces confidence score (0-1), bull/base/bear scenarios, evidence tree with tool citations, portfolio personalization

Conditional edges: out_of_scope→done (decline), simple_lookup→format_simple (no LLM), empty search→replan (max 1)

20 internal tools (7 added in Phase 5: forecast, sector forecast, portfolio forecast, compare stocks, scorecard, dividend sustainability, risk narrative): get_fundamentals, get_analyst_targets, get_earnings_history, get_company_profile — all read from DB (materialized during ingestion)

## Filesystem Layout

```
stock-signal-platform/
├── backend/
│   ├── main.py                # FastAPI app
│   ├── config.py              # Pydantic Settings (.env)
│   ├── database.py            # async engine + async_session_factory
│   ├── dependencies.py        # get_current_user, JWT auth
│   ├── agents/                # BaseAgent, StockAgent, GeneralAgent, loop, stream, llm_client
│   ├── tools/                 # ToolRegistry, BaseTool, MCPAdapters, internal tools
│   ├── mcp_server/            # FastMCP server (Streamable HTTP at /mcp)
│   ├── routers/               # FastAPI endpoint handlers
│   ├── models/                # SQLAlchemy 2.0 ORM models
│   ├── schemas/               # Pydantic v2 request/response schemas
│   ├── services/              # Business logic layer
│   ├── tasks/                 # Celery background jobs
│   └── migrations/            # Alembic DB migrations
├── frontend/
│   ├── app/                   # Next.js App Router pages
│   ├── components/            # Reusable UI components
│   ├── lib/                   # api.ts, hooks, utilities
│   └── types/                 # Shared TypeScript types
├── tests/
│   ├── conftest.py            # Shared fixtures
│   ├── unit/                  # No external deps (<5s)
│   ├── integration/           # Real Postgres+Redis (testcontainers)
│   └── api/                   # FastAPI endpoint tests (httpx)
├── data/                      # Local data (gitignored)
│   ├── models/prophet/        # Per-ticker Prophet model artifacts
│   └── models/composite_scorer/
├── docs/                      # MkDocs Material source
├── scripts/                   # Seed data, backfill utilities
└── infra/                     # Terraform (future)
```

## Environment Variables

All secrets in `backend/.env` (gitignored). Template: `backend/.env.example`.

| Var | Required | Purpose |
|-----|----------|---------|
| `DATABASE_URL` | Yes | `postgresql+asyncpg://...@localhost:5433/stockdb` |
| `REDIS_URL` | Yes | `redis://localhost:6380/0` |
| `JWT_SECRET_KEY` | Yes | JWT signing key |
| `ANTHROPIC_API_KEY` | Yes | Claude Sonnet (synthesis) |
| `GROQ_API_KEY` | No | Groq (agentic loops — fast/cheap) |
| `FRED_API_KEY` | No | FRED macro data |
| `SERPAPI_API_KEY` | No | Web/news search |
| `OPENAI_API_KEY` | No | Optional LLM fallback |
| `ALPHA_VANTAGE_API_KEY` | No | News + sentiment (Phase 4B) |
| `FINNHUB_API_KEY` | No | Analyst ratings, ESG, social sentiment (Phase 4B) |

CI-only (GitHub Actions Secrets, never in `.env`): `CI_DATABASE_URL`, `CI_REDIS_URL`, `CI_JWT_SECRET_KEY`, `CI_JWT_ALGORITHM`, `CI_POSTGRES_PASSWORD`

## Critical Files (modify with extra care)

| File | Why |
|------|-----|
| `backend/.env` | All secrets — never commit |
| `backend/dependencies.py` | JWT validation — changes can lock out all users |
| `backend/config.py` | Settings defaults — affects all services |
| `backend/migrations/` | DB schema — irreversible if deployed |
| `backend/models/` | ORM models — breaking changes cause data loss |
