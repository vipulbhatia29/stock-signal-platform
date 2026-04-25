# AGENTS.md — Stock Signal Platform

Instructions for AI coding agents working in this repository.

## CRITICAL — First Thing You Must Do

**Your very first tool call in every session MUST be:**

```
activate_project("stock-signal-platform")
```

This activates the Serena MCP server, which gives you access to symbolic code tools, project memories, and the full codebase. **Nothing works until you do this.** Do not read files, do not run commands, do not write code — activate the project first.

## Session Start

After activating Serena, complete these steps before writing any code:
1. Read `PROJECT_INDEX.md` — full repo map
2. Read `PROGRESS.md` — current state
3. Run `git status && git log --oneline -5`
4. Read Serena memory `project/state` — current phase, branch, test count
5. Run `uv run pytest tests/unit/ -q --tb=short` — confirm baseline green

## Serena MCP (Symbolic Code Tools)

This repo has a Serena MCP server configured and you have already activated it (see above). **Use Serena tools as your primary way to read and edit code.** Fall back to raw file reads only when Serena cannot do the job.

Key tools:
- `activate_project("stock-signal-platform")` — MUST be called before any other Serena tool
- `get_symbols_overview` — list top-level symbols in a file (classes, functions)
- `find_symbol` — search for symbols by name pattern, optionally with body
- `find_referencing_symbols` — find callers/references to a symbol
- `replace_symbol_body` — edit a function/class body by symbol name
- `insert_before_symbol` / `insert_after_symbol` — add code around symbols
- `read_memory` / `write_memory` / `list_memories` — access project knowledge base

### Serena Memory Map

Load memories relevant to your task. Do not load everything.

| Memory Key | Content |
|---|---|
| `project/state` | Current phase, branch, test count, resume point |
| `project/stack` | Entry points, critical gotchas, package manager |
| `project/testing` | Test commands, layout, fixtures, factory-boy |
| `global/conventions/python-style` | Python typing, async, logging, forbidden patterns |
| `global/conventions/typescript-style` | TS strict mode, TanStack, shadcn, Recharts |
| `global/conventions/testing-patterns` | pytest, factory-boy, testcontainers, mock rules |
| `global/conventions/git-workflow` | Conventional commits, branch strategy, PR flow |
| `global/conventions/error-handling` | Logging levels, error handling by context |
| `global/debugging/mock-patching-gotchas` | Patch lookup-site rule, AsyncMock |
| `architecture/system-overview` | Services, ports, entry points, filesystem layout |
| `architecture/timescaledb-patterns` | Hypertable upsert, Alembic gotchas |
| `architecture/auth-jwt-flow` | Full JWT flow, token storage, OWASP checklist |
| `architecture/celery-patterns` | Celery entry points, asyncio.run() bridge |
| `debugging/backend-gotchas` | asyncpg, UserRole enum, circular imports |
| `debugging/frontend-gotchas` | ESLint hooks, Recharts, template literals |
| `conventions/auth-patterns` | JWT, httpOnly cookies, direct bcrypt |

## Stack

**Backend:** Python 3.12+ / FastAPI / SQLAlchemy 2.0 async / Celery / TimescaleDB (Postgres 16) / Redis
**Frontend:** Next.js 16 / React 19 / TypeScript strict / Tailwind v4 / shadcn v4 / Recharts 3
**Package managers:** `uv` (Python), `npm` (frontend)
**Linter:** Ruff (Python), ESLint (TypeScript)
**Type checker:** Pyright (Python), `tsc --noEmit` (frontend)
**Tests:** pytest (backend), Jest + MSW v2 (frontend), Playwright (E2E)

## Commands

```bash
# Backend
uv run uvicorn backend.main:app --reload --port 8181
uv run pytest tests/unit/ -q --tb=short
uv run pytest tests/api/ -q --tb=short
uv run ruff check --fix backend/ tests/ scripts/
uv run ruff format backend/ tests/ scripts/
uv run alembic upgrade head
uv run alembic current

# Frontend
cd frontend && npm run dev          # port 3000
cd frontend && npm run lint
cd frontend && npx tsc --noEmit
cd frontend && npx jest

# Infrastructure
docker compose up -d postgres       # port 5433
docker compose up -d redis          # port 6380

# Celery
uv run celery -A backend.tasks worker --loglevel=info
```

## File Layout

```
backend/
├── agents/          LangGraph ReAct loop, intent classifier, guards
├── config.py        Pydantic Settings (loads backend/.env)
├── database.py      get_async_session() FastAPI dependency
├── main.py          Router mounting under /api/v1/
├── migrations/      Alembic (TimescaleDB hypertables via raw SQL)
├── models/          SQLAlchemy 2.0 ORM (27 models, 5 hypertables)
├── observability/   Collector, writer, langfuse, token budget, context vars
├── routers/         19 FastAPI routers under /api/v1/
├── schemas/         Pydantic v2 request/response
├── services/        Business logic (signals, portfolio, cache, pipeline)
├── tasks/           Celery tasks (nightly pipeline, alerts, forecasts)
└── tools/           25 internal tools + 4 MCP adapters + registry

frontend/
├── src/app/         App Router — 8 route groups
├── src/components/  68+ UI components (ui/ = shadcn primitives)
├── src/hooks/       16 TanStack Query hooks
├── src/lib/         api.ts (fetch wrapper), auth.ts, utils
├── src/types/       api.ts (~115 exported types — single source of truth)
└── src/__tests__/   Jest + MSW v2 tests

tests/
├── unit/            Service, router, tool, agent, pipeline tests
├── api/             Endpoint tests (testcontainers)
├── integration/     MCP stdio, regression, migration validation
├── e2e/             Playwright (dashboard, auth, portfolio)
├── fixtures/        Factory-boy model fixtures
└── semgrep/         Custom rule validation
```

## Ports

| Service | Port |
|---------|------|
| Backend API | 8181 |
| Frontend | 3000 |
| Postgres (TimescaleDB) | **5433** (not 5432) |
| Redis | **6380** (not 6379) |
| Langfuse | 3001 |
| Langfuse DB | 5434 |

## Hard Rules

1. **uv only** — `uv run`, `uv add`. Never `pip install` or bare `python`.
2. **Test everything** — unit test every public function; endpoint tests: auth + happy path + error case.
3. **Lint before commit** — `ruff check --fix` then `ruff format` then zero errors.
4. **No secrets in code** — `.env` only, never committed.
5. **Async by default** — FastAPI endpoints and DB calls are always async.
6. **Edit, don't create** — prefer editing existing files over creating new ones.
7. **No mutable module state** — constants and `settings` only at module level.
8. **Serena first** — use Serena symbolic tools for all code reads/edits. Raw file tools only as fallback.
9. **No str(e) anywhere** — never pass `str(e)` to `ToolResult(error=...)`, `HTTPException(detail=...)`, or any user-facing output. Log the real error, return a safe generic message.

## Domain Gotchas

- `composite_score` API returns 0-10 (not 0-1). Thresholds: BUY >= 8, WATCH >= 5, AVOID < 5.
- Position model field is `avg_cost_basis` (not `avg_cost`). Position has `portfolio_id` (not `user_id`).
- `SignalSnapshot.computed_at` (not `snapshot_date`).
- `API_BASE = "/api/v1"` in `api.ts` — hooks use `/portfolio/...` NOT `/api/v1/portfolio/...` (double-prefix bug).
- `pandas-ta-openbb` requires `import importlib.metadata` before `import pandas_ta` (package bug, noqa: F401).
- QuantStats returns NaN/Inf — always guard with `math.isfinite()`. `calmar()` returns inf when drawdown=0.
- PyPortfolioOpt `weight_bounds` max must be >= 1/n_assets for feasibility.
- TimescaleDB hypertables are created via raw SQL in Alembic migrations after table creation. Alembic autogenerate falsely drops TimescaleDB indexes — always manually review migrations.
- Observability models use `__table_args__={"schema": "observability"}` — do NOT import in `backend/models/__init__.py`.
- New non-observability models MUST be imported in `backend/models/__init__.py` for Alembic discovery + test teardown.
- `LangfuseService` wrapper — all Langfuse SDK calls go through `backend/observability/langfuse.py` (fire-and-forget, feature-flagged on `LANGFUSE_SECRET_KEY`).
- Fire-and-forget `try-except` blocks mask import bugs — always test fire-and-forget paths.
- IDOR on detail endpoints — list endpoints naturally scope by user, detail endpoints need explicit `user_id` check.
- Raw SQL INSERT in migrations must include `id` column with `gen_random_uuid()` when no server_default.
- ContextVars live in `backend/observability/context.py` (shim at `backend/request_context.py`).

## Frontend Conventions

- App Router (not Pages Router) — all routes in `src/app/`.
- All data fetching uses TanStack Query — never raw `fetch` in components.
- Charts use Recharts. Disable animations (`isAnimationActive={false}`) for Playwright tests.
- UI primitives from shadcn v4 in `src/components/ui/`. Popover/Trigger use `@base-ui/react` with `render` prop, NOT `asChild`.
- Tailwind v4: use `font-family: var(--font-sora)` in `@layer base`, not `@theme`.
- Jest needs `testEnvironment: "jsdom"` (not `"node"`).
- `types/api.ts` (~115 exported types) is the single source of truth for all backend schema types.

## Testing Conventions

- Tests organized in tiers T0-T5. Spec: `docs/superpowers/specs/2026-04-01-test-suite-overhaul.md`.
- `pytest-xdist -n auto` for unit tests ONLY. API/integration tests run sequentially (shared DB = race conditions).
- Use factory-boy fixtures from `tests/fixtures/`. Do not create ad-hoc test data.
- Every bug fix gets a regression test — `@pytest.mark.regression`.
- Semgrep custom rules in `.semgrep/stock-signal-rules.yml`. Test rules in `tests/semgrep/`.
- Hypothesis `max_examples=20` in CI, `200` in nightly.
- Mock patching: patch at the lookup site, not the definition site. Use `AsyncMock` for async functions.

## Git

- Branch from `develop`, never from `main`.
- PR target is always `develop`.
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
- PR title: `[KAN-X] Summary`.
- Never commit directly to `main` or `develop`.
- Never skip hooks (`--no-verify`).
- `uv.lock` is committed — run `uv sync` after pulling.

## Do NOT

- **Do not modify shadcn primitives** in `frontend/src/components/ui/`. Use composition and wrapper components.
- **Do not add dependencies** without justification. This repo has a large dependency surface.
- **Do not run `git push`** in eval branches. Commits are for local diff extraction only.
- **Do not commit `.env` files**, API keys, JWT secrets, or credentials.
- **Do not create new files** when editing an existing file would suffice.

## Key Documents

- `docs/PRD.md` — product requirements
- `docs/FSD.md` — functional requirements + acceptance criteria
- `docs/TDD.md` — technical design, API contracts
- `project-plan.md` — phased build plan
- `PROGRESS.md` — session log
- `docs/superpowers/specs/` — design specs per sprint
- `docs/superpowers/plans/` — implementation plans
