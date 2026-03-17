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
- **Tool boundary for external APIs** — yfinance, FRED, web search calls go through `backend/tools/`, never directly from routers. Routers call services or tools only.
- **Pre-computed signals** — Celery Beat runs nightly signal computation; dashboard reads pre-computed data. Agents call tools on-demand.
- **Three-layer MCP architecture** — Layer 1: consume external MCPs (EdgarTools, Alpha Vantage, FRED, Finnhub). Layer 2: enrich in backend (Tool Registry + caching). Layer 3: expose as MCP server at `/mcp` (Streamable HTTP). See `domain/agent-tools` memory for full details.

## LLM Routing

- **Groq** (`GROQ_API_KEY`) — primary for agentic tool-calling loops (fast, cheap)
- **Claude Sonnet** (`ANTHROPIC_API_KEY`) — synthesis and final response generation
- **LM Studio** — offline fallback, no key required, local inference

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
