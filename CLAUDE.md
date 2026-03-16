# stock-signal-platform

Personal stock analysis platform — US equities, signal detection, portfolio tracking.

## Session Start

Before writing any code:
1. Read `PROJECT_INDEX.md` — full repo map
2. Read `PROGRESS.md` — where we left off
3. Run `git status && git log --oneline -5`
4. Run `uv run pytest tests/unit/ -v` — confirm baseline green
5. If unclear what to work on, ask

## Memory Map

All conventions, patterns, and gotchas live in Serena memories — NOT in this file.
Load what you need for the task at hand:

| Memory Key | Content |
|---|---|
| `project/state` | Current phase, branch, test count, resume point |
| `project/stack` | Entry points, critical gotchas, package manager |
| `global/conventions/python-style` | Python typing, async, logging, forbidden patterns |
| `global/conventions/typescript-style` | TS strict mode, TanStack, shadcn, Recharts |
| `global/conventions/testing-patterns` | pytest, factory-boy, testcontainers, mock rules |
| `global/conventions/git-workflow` | Conventional commits, branch strategy, PR flow |
| `global/conventions/error-handling` | Logging levels, error handling by context |
| `global/debugging/mock-patching-gotchas` | Patch lookup-site rule, AsyncMock |
| `global/architecture/system-overview` | Full stack, ports, principles |
| `architecture/timescaledb-patterns` | Hypertable upsert, Alembic gotchas |
| `architecture/frontend-design-system` | Navy theme, Recharts colors, shadcn v4 |
| `domain/signals-and-screener` | Signal computation, screener |
| `domain/portfolio-tracker` | Portfolio tools, API prefix gotcha |
| `domain/agent-tools` | Agents, LLM routing, NDJSON streaming |
| `debugging/backend-gotchas` | asyncpg, UserRole enum, circular imports |
| `debugging/frontend-gotchas` | ESLint hooks, Recharts, template literals |
| `conventions/auth-patterns` | JWT, httpOnly cookies, bcrypt pinning |
| `serena/tool-usage` | Serena MCP prefix, tool priority rules |
| `serena/memory-map` | Full taxonomy — use when adding new modules |

## 8 Hard Rules

1. **uv only** — `uv run`, `uv add`. Never `pip install` or bare `python`.
2. **Test everything** — unit test every public function; endpoint tests: auth + happy + error.
3. **Lint before commit** — `ruff check --fix` then `ruff format` then zero errors.
4. **No secrets in code** — `.env` only, never committed.
5. **Async by default** — FastAPI endpoints and DB calls are always async.
6. **Edit, don't create** — prefer editing existing files over creating new ones.
7. **No mutable module state** — constants and `settings` only at module level.
8. **Serena first** — use symbolic tools for all code reads/edits. Built-ins only when Serena can't.

## Services (local dev)

| Service | Command | Port |
|---|---|---|
| Backend | `uv run uvicorn backend.main:app --reload --port 8181` | 8181 |
| Frontend | `cd frontend && npm run dev` | 3000 |
| Postgres | `docker compose up -d postgres` | **5433** |
| Redis | `docker compose up -d redis` | **6380** |
| Celery worker | `uv run celery -A backend.tasks worker --loglevel=info` | — |
| Docs | `uv run mkdocs serve` | 8000 |

## Sprint Documents

All specs in `docs/superpowers/specs/`, all plans in `docs/superpowers/plans/`.
Completed features in `docs/superpowers/archive/`. Never read archived files.

## Key Documents

- `docs/PRD.md` — what we're building and why
- `docs/FSD.md` — functional requirements + acceptance criteria
- `docs/TDD.md` — technical design, API contracts
- `project-plan.md` — phased build plan
- `PROGRESS.md` — session log

## End-of-Session Checklist

1. `PROGRESS.md` — session entry added
2. `CLAUDE.md` — update if architecture changed (rare — use Serena memories instead)
3. `project-plan.md` — mark completed deliverables with checkmark and session number
4. `docs/FSD.md` — update if functional requirements changed
5. `docs/TDD.md` — update if API contracts changed
6. Serena memories — update `project/state` (ALWAYS), other memories as needed
7. `MEMORY.md` — update Project State section
8. Run `/ship` — promote session memories and open PR
