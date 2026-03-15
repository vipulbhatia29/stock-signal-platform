# stock-signal-platform

Personal stock analysis and investment signal platform for part-time investors.
Covers US equity markets. Goal: automate signal detection, portfolio
tracking, and surface actionable buy/hold/sell recommendations.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Celery
- **Frontend:** Next.js (latest stable), React, TypeScript, Tailwind CSS, shadcn/ui, Recharts
- **Database:** PostgreSQL 16 + TimescaleDB extension
- **Cache/Broker:** Redis 7
- **AI/ML:** LangChain, LangGraph, Facebook Prophet, scikit-learn, pandas-ta
- **LLM:** Groq (primary for agentic tool-calling loops — fast/cheap), Claude Sonnet
  (synthesis and final response via Anthropic API), LM Studio (offline fallback)
- **Data:** yfinance (market data), FRED API (macro signals)
- **Auth:** JWT (python-jose) + bcrypt (passlib), httpOnly cookies, rate limiting (slowapi)
- **Package manager:** uv (NOT pip, NOT poetry)
- **Docs:** MkDocs Material
- **Testing:** pytest, pytest-asyncio, pytest-cov, httpx, factory-boy, testcontainers, freezegun

## Session Start

Before writing any code, orient yourself:

1. Read `PROGRESS.md` — understand where we left off and what's next
2. Run `git status` and `git log --oneline -5` — verify branch state
3. Run `uv run pytest tests/unit/ -v` — confirm baseline is green
4. If unclear what to work on, ask

## Virtual Environment

This project uses `uv` for package management. The venv lives at `.venv/` in project root.

- All Python commands MUST use `uv run` prefix (e.g., `uv run pytest`, `uv run alembic`)
- NEVER use `pip install` — use `uv add <package>` to add dependencies
- NEVER use bare `python` — use `uv run python`
- The venv is created automatically by `uv sync`
- Before adding a dependency, check if an existing one covers the need
- Pin critical packages with known compatibility issues (e.g., `bcrypt==4.2.1`)
- Production deps: `[project.dependencies]`; dev-only: `[dependency-groups] dev`
- After adding a dep: `uv sync`, then verify tests still pass

## Commands

```bash
# Setup
uv sync                                                    # Install all dependencies + create venv
cd frontend && npm install                                 # Install frontend deps

# Infrastructure
docker compose up -d postgres redis                        # Start Postgres + Redis
uv run alembic upgrade head                                # Run DB migrations

# Development
uv run uvicorn backend.main:app --reload --port 8181       # Start backend
cd frontend && npm run dev                                 # Start frontend (port 3000)
uv run mkdocs serve                                        # Docs (port 8000)
uv run celery -A backend.tasks worker --loglevel=info      # Celery worker
uv run celery -A backend.tasks beat --loglevel=info        # Celery scheduler

# Testing
uv run pytest tests/unit/ -v                               # Unit tests (fast, no deps)
uv run pytest tests/integration/ -v                        # Integration (needs Docker)
uv run pytest tests/api/ -v                                # API endpoint tests
uv run pytest --cov=backend --cov-fail-under=80            # Full suite + coverage

# Linting (run before every commit)
uv run ruff check backend/ tests/ scripts/ --fix           # Lint + auto-fix Python
uv run ruff format backend/ tests/ scripts/                # Format Python
cd frontend && npm run lint                                # Lint frontend
```

**Lint workflow:** Write code -> `ruff check --fix` -> `ruff format` -> verify zero errors -> commit. NEVER commit with lint errors.

## Project Structure

```
stock-signal-platform/
├── backend/
│   ├── main.py                # FastAPI app, mount routers, startup events
│   ├── config.py              # Pydantic Settings (.env support)
│   ├── database.py            # SQLAlchemy async engine + session factory
│   ├── dependencies.py        # Auth: JWT, password hashing, get_current_user
│   ├── agents/                # LangChain/LangGraph agent definitions
│   │   ├── base.py            # BaseAgent ABC
│   │   ├── registry.py        # AgentRegistry (discover + route to agents)
│   │   ├── loop.py            # Agentic tool-calling loop
│   │   ├── stream.py          # NDJSON streaming to frontend
│   │   ├── general_agent.py   # General purpose + web search
│   │   └── stock_agent.py     # Stock analysis + signals + forecasting
│   ├── tools/                 # Agent tools — each is a future MCP server
│   │   ├── registry.py        # ToolRegistry
│   │   ├── market_data.py     # yfinance: fetch US stock OHLCV, store to TimescaleDB
│   │   ├── signals.py         # RSI, MACD, SMA, Bollinger, composite score
│   │   ├── recommendations.py # Buy/Hold/Sell decisions, position sizing
│   │   ├── fundamentals.py    # P/E, PEG, FCF yield, Piotroski F-Score
│   │   ├── forecasting.py     # Prophet price forecasts
│   │   ├── portfolio.py       # Positions, cost basis, P&L, allocation
│   │   ├── screener.py        # Filter + rank by composite criteria
│   │   └── search.py          # Web/news search
│   ├── routers/               # FastAPI endpoint handlers
│   ├── models/                # SQLAlchemy 2.0 ORM models
│   ├── schemas/               # Pydantic v2 request/response schemas
│   ├── services/              # Business logic (between routers and tools)
│   ├── tasks/                 # Celery background jobs
│   └── migrations/            # Alembic DB migrations
├── frontend/                  # Next.js (TypeScript + Tailwind + shadcn/ui)
│   ├── app/                   # App Router pages
│   ├── components/            # Reusable UI components
│   ├── lib/                   # Utilities (api.ts, auth, hooks)
│   └── types/                 # Shared TypeScript types
├── tests/
│   ├── conftest.py            # Shared fixtures: DB, Redis, factories, auth
│   ├── unit/                  # No external deps, fast (<5s)
│   ├── integration/           # Real Postgres/Redis via testcontainers
│   └── api/                   # FastAPI endpoint tests via httpx
├── docs/                      # MkDocs Material source
├── data/                      # Local data (gitignored)
│   ├── models/                # Serialized ML model artifacts
│   │   ├── prophet/           # Per-ticker Prophet models
│   │   └── composite_scorer/  # Global scoring models
│   └── backups/               # pg_dump backups
├── infra/                     # Terraform (future)
└── scripts/                   # Utility scripts (seed data, backfill, etc.)
```

## Architecture Principles

- Monolith-first, microservice-ready: clean domain boundaries between modules
- Each tool group in `backend/tools/` has clean interfaces for future MCP server extraction
- Frontend is a SINGLE Next.js app — NO iframes, NO Plotly Dash, NO second framework
- Background jobs (Celery) pre-compute signals nightly; dashboard reads pre-computed data
- Agents call tools via ToolRegistry now; will call via MCP protocol later

## Testing — NON-NEGOTIABLE

- Every module MUST have a corresponding test file in `tests/`
- Every public function MUST have at least one unit test
- Every FastAPI endpoint MUST have auth + happy path + error path tests
- Every agent tool MUST have a unit test with mocked LLM
- Use factory-boy for test data, never raw dicts
- Use testcontainers for integration tests, never SQLite substitutes
- Use freezegun for time-dependent tests (signal computations depend on dates)
- Always run relevant tests after creating a module: `uv run pytest tests/unit/test_{module}.py -v`
- Fix ALL test failures before moving on

### Mock & Patch Guidelines

- ALWAYS patch where the name is looked up, not where it is defined:
  `@patch("backend.routers.stocks.fetch_prices")` NOT `@patch("backend.tools.market_data.fetch_prices")`
- Use `AsyncMock` for async functions, `MagicMock` for sync
- For yfinance/external API calls: mock at the tool boundary (e.g., mock `fetch_prices`, not `yf.download`)
- Stack `@patch` decorators bottom-up: bottom decorator = first function parameter
- For DB-dependent tests: use the real async session from testcontainers fixtures, do not mock SQLAlchemy
- Never mock what you don't own at a granular level — mock your own wrapper functions instead

## Code Conventions

### Python

- Type hints on ALL functions, Google-style docstrings
- Async by default for FastAPI endpoints and DB operations
- Pydantic v2 for all API schemas; SQLAlchemy 2.0 `mapped_column` style
- Use `X | None` syntax (PEP 604), never `Optional[X]` or `Union[X, None]`
- Use `logging.getLogger(__name__)` for logging, never bare `print()` in backend code
  (scripts may use `print()` for CLI output)
- No module-level mutable state (mutable dicts, lists). Use constants (UPPER_CASE) and `settings` only
- No bare `except:` — always `except Exception` or a specific type
- `datetime.now(timezone.utc)` not `datetime.utcnow()` (deprecated)

### TypeScript / Frontend

- Strict mode enabled — no `any` types, no `@ts-ignore`
- All API calls go through `lib/api.ts` (centralized fetch with cookie auth)
- Use TanStack Query for server state, never raw `useEffect` + `fetch`
- Components use shadcn/ui primitives; style with Tailwind utility classes
- Charts use Recharts exclusively
- Keep components under 150 lines; extract sub-components when exceeded
- Use Next.js App Router patterns (server components where possible)
- Use `next/image` for all images (not `<img>`)

### Git

- Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
- Branch per feature: `feat/signal-engine`, `feat/dashboard`, etc.
- Never commit to main directly

## Anti-Patterns — Do NOT Do These

### Python

| Anti-Pattern | Do This Instead |
|---|---|
| `from typing import Optional` | `X \| None` (PEP 604) |
| Bare `except:` or `except: pass` | Catch specific exceptions; log + re-raise or return meaningful error |
| `print()` in backend code | `logger.info()` / `logger.warning()` / `logger.error()` |
| Raw SQL strings in routers | SQLAlchemy ORM queries in tools/services layer |
| `pip install` / bare `python` | `uv add` / `uv run python` |
| Synchronous DB calls | Always use async session + `await` |
| `datetime.utcnow()` | `datetime.now(timezone.utc)` |
| `eval()` / `exec()` | NEVER — find a safe alternative |
| Mutable default args (`def f(x=[])`) | `def f(x: list \| None = None): x = x or []` |
| Nested conditionals > 2 levels | Early returns / guard clauses |

### TypeScript

| Anti-Pattern | Do This Instead |
|---|---|
| `any` type | Proper type or `unknown` + type narrowing |
| `useEffect` + `fetch` for data | TanStack Query (`useQuery` / `useMutation`) |
| `@ts-ignore` | Fix the type error |
| Raw `fetch()` calls | `lib/api.ts` wrapper with cookie auth |
| Inline styles | Tailwind utility classes |
| `<img>` elements | `<Image />` from `next/image` |
| `setState()` inside `useEffect` body (sync) | Lazy `useState(() => initialValue)` for one-time reads; callbacks only inside effects |
| `hsl(var(--x))` in Recharts | `useChartColors()` hook — Recharts needs resolved color strings, not CSS var references |
| New React context without lazy localStorage init | Use `useState<T>(() => { if (typeof window === "undefined") return default; return localStorage.getItem(key) ?? default; })` |

### Architecture

| Anti-Pattern | Do This Instead |
|---|---|
| Business logic in routers | Move to `services/` or `tools/` layer |
| Direct yfinance calls from routers | Call through `tools/market_data.py` |
| SQLite for integration tests | testcontainers with real PostgreSQL + TimescaleDB |
| Storing secrets in code | `backend/.env` via `config.py` Pydantic Settings |
| Creating new files when editing suffices | Edit existing files first |
| Premature abstraction | Minimum complexity for current task |

## Error Handling & Logging

### Logging

- Every module: `logger = logging.getLogger(__name__)` at module level
- Log levels: `DEBUG` (computation details), `INFO` (operations completed),
  `WARNING` (degraded but functional), `ERROR` (operation failed)
- Include context: `logger.info("Stored %d rows for %s", count, ticker)` — not `logger.info("Done")`
- Use `logger.exception()` inside `except` blocks (auto-includes traceback)
- NEVER log secrets, tokens, or passwords at any level

### Error Handling

| Context | Pattern |
|---|---|
| Routers | Raise `HTTPException` with specific status codes (400, 401, 404, 422) |
| Tools / Services | Raise `ValueError` for invalid inputs; let unexpected errors propagate |
| External APIs (yfinance) | Log WARNING, retry or degrade gracefully |
| Config errors | Fail fast at startup with clear error message |

- Never swallow exceptions silently (`except: pass`)
- Return consistent error shape: `{"detail": "Human-readable message"}`

## Security

- NEVER commit `.env` files, API keys, or JWT secrets
- All user input validated via Pydantic schemas before processing
- SQL injection prevention: always use SQLAlchemy ORM / parameterized queries
- Ticker sanitization: `ticker.upper().strip()`, reject non-alphanumeric (except `.` and `-`)
- JWT tokens stored in httpOnly, Secure, SameSite=Lax cookies
- Rate limiting via slowapi on all endpoints; aggressive limits on expensive endpoints (data ingestion)
- Error messages MUST NOT reveal stack traces or file paths to end users

### Critical Files (modify with extra care)

| File | Why |
|---|---|
| `backend/.env` | All secrets — never commit |
| `backend/dependencies.py` | JWT validation + auth logic — changes can lock out users |
| `backend/config.py` | Settings defaults — affects all services |
| `backend/migrations/` | Database schema — irreversible if deployed |
| `backend/models/` | ORM models — breaking changes cause data loss |

## Key Documents

- `docs/PRD.md` — Product Requirements Document. The source of truth for WHAT
  we're building and WHY. Read this first for product context.
- `docs/FSD.md` — Functional Specification Document. Detailed functional and
  non-functional requirements with acceptance criteria for every feature.
- `docs/TDD.md` — Technical Design Document. HOW to build it: component
  architecture, API contracts, service layer design, integration patterns.
- `docs/data-architecture.md` — Data architecture, entity model, TimescaleDB
  configuration, model versioning strategy, and data flow diagrams.
- `docs/phase2-requirements.md` — Phase 2 Dashboard + Screener UI requirements (COMPLETED).
- `docs/workflow_phase2.md` — Phase 2 implementation workflow (COMPLETED).
- `global-claude-md-for-home-dir/design-principles.md` — Reusable design principles for financial UIs (cross-project reference).
- `project-plan.md` — Phased build plan with deliverables per phase.
- `PROGRESS.md` — Session log tracking what was built and what's next.

### Sprint Document Rules

All sprint artifacts live under `docs/superpowers/` with this structure:

```
docs/superpowers/
├── specs/          # Active design specs (brainstorming output)
├── plans/          # Active implementation plans (writing-plans output)
└── archive/        # Completed specs + plans (moved here after shipping)
```

**Rules:**
- **One canonical location:** ALL specs go in `docs/superpowers/specs/`, ALL plans go in `docs/superpowers/plans/`. NEVER use `.claude/plans/` or any other directory.
- **Naming:** `YYYY-MM-DD-<topic>-design.md` for specs, `<topic>-implementation.md` for plans.
- **Lifecycle:** Active → Implemented → Archived. After a feature ships and tests pass, move both spec and plan to `docs/superpowers/archive/`.
- **Never delete:** `CLAUDE.md`, `PROGRESS.md`, `project-plan.md`, `MEMORY.md`, Serena memories, or incomplete sprint docs.
- **Context budget:** Do NOT read archived files. They exist only for historical reference. If you need to understand a completed feature, read the actual code or PROGRESS.md instead.
- **Serena for code exploration:** When exploring Python backend code, prefer Serena's `find_symbol` and `get_symbols_overview` over reading full files. This saves significant context tokens.

### Documentation Triggers

| When you... | Update... |
|---|---|
| Add/change a DB model | `docs/data-architecture.md` + new Alembic migration |
| Add/change an API endpoint | Pydantic schemas (auto-generates OpenAPI) + `docs/TDD.md` API section |
| Add/change functional requirements | `docs/FSD.md` relevant FR section + Feature × Phase Matrix |
| Add/change a new phase deliverable | `project-plan.md` deliverables + success criteria |
| Add a new tool | `docs/TDD.md` tool registry section |
| Change architecture or conventions | This file (`CLAUDE.md`) |
| Add a new env var | `backend/.env.example` + Environment Variables section in `CLAUDE.md` |
| Complete a session | `PROGRESS.md` with what was done, key decisions, and what's next |
| Ship a feature from an implementation plan | Move completed spec/plan files to `docs/superpowers/archive/`. Extract any reusable design principles to `global-claude-md-for-home-dir/design-principles.md` |
| Delete a file referenced in `mkdocs.yml` | Update `mkdocs.yml` nav to remove or comment out the entry |

**End-of-session checklist** — before wrapping up, verify these are current:
1. `PROGRESS.md` — session entry added (full detail for last 3 sessions; compact older ones)
   - **Maintenance:** When starting a new session, compact the 4th-oldest session in-place.
     When PROGRESS.md exceeds ~200 lines, append full text of compacted sessions to
     `docs/superpowers/archive/progress-full-log.md`, then replace with phase-level summary lines.
   - Full archive: `docs/superpowers/archive/progress-full-log.md` (never read by Claude)
2. `CLAUDE.md` — updated if conventions/architecture changed
3. `project-plan.md` — **ALWAYS** mark completed deliverables with ✅ and session number; add any new pending items
4. `docs/FSD.md` — updated if functional requirements changed
5. `docs/TDD.md` — updated if API contracts or technical design changed
6. `docs/data-architecture.md` — updated if data model changed
7. Serena project memories — **ALWAYS** update via `edit_memory` / `write_memory`:
   - `project_overview` — update Current State (phase, test count, what's next, pending items)
   - `style_and_conventions` — update if conventions or gotchas changed
   - `suggested_commands` — update if new scripts or commands were added
   - This is the primary way context persists across sessions — do not skip
8. Auto-memory `MEMORY.md` — update Project State section to reflect current branch, test count, resume point

## Environment Variables

All secrets live in `backend/.env` (gitignored). See `backend/.env.example` for template.
Required: ANTHROPIC_API_KEY, JWT_SECRET_KEY, DATABASE_URL, REDIS_URL
Optional: GROQ_API_KEY, SERPAPI_API_KEY, FRED_API_KEY, OPENAI_API_KEY

## Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| `passlib` raises `AttributeError` on hash | `bcrypt>=5.0` broke passlib API | Pin `bcrypt==4.2.1` in pyproject.toml |
| Postgres connection refused | Docker on non-default ports | Use port 5433 (not 5432); check `docker compose ps` |
| Redis connection refused | Docker on non-default ports | Use port 6380 (not 6379); check `docker compose ps` |
| `asyncpg` event loop errors in tests | Nested transactions / shared engine | Use per-test engine + truncate tables approach |
| UserRole enum sends uppercase to Postgres | SQLAlchemy uses `.name` not `.value` | Add `values_callable=lambda e: [m.value for m in e]` to `Enum()` |
| `uv.lock` conflicts | Lock file is gitignored | Run `uv sync` to regenerate |
| yfinance returns empty DataFrame | Ticker invalid or rate-limited | Verify ticker on Yahoo Finance; wait and retry |
| yfinance rate limiting in scripts | Too many requests too fast | Add 0.5s delay between tickers |
| `VIRTUAL_ENV` warning from uv | System VIRTUAL_ENV conflicts | Ignore; uv uses `.venv/` correctly via `uv run` |
| ESLint `react-hooks/set-state-in-effect` error | Calling `setState()` synchronously inside `useEffect` body | Use lazy `useState(() => ...)` initializer for one-time reads (e.g. localStorage); use `MutationObserver` callback (not effect body) for reactive updates |
| Worktree subagents can't write files | Claude Code permission model restricts Write/Bash in isolated worktrees | Write files from the main session instead; use worktrees for research/read tasks only |
| `gh auth login` fails with `permission denied` on `~/.config/gh` | Missing config directory | `sudo mkdir -p ~/.config/gh && sudo chown $USER ~/.config/gh` |
| CSS var colors not resolving in Recharts | Recharts needs literal color strings, not `var(--x)` | Use `useChartColors()` hook (reads via `getComputedStyle`) or local `readCssVar()` for one-off reads |
| Sparkline/chart colors wrong on initial render | CSS vars not yet resolved on first paint | Use lazy `useState(() => resolveColor(...))` initializer — reads CSS vars synchronously on mount |
| TimescaleDB hypertable PK uses `ON CONFLICT ... DO UPDATE` | Composite PK `(id, time)` means upsert needs named constraint | Use `constraint="tablename_pkey"` in `on_conflict_do_update()` |
| Python heredoc/script inserts escaped backticks in JS | Template literals get backslash-escaped through shell layers | Use the Edit tool or Write tool for JS/TS files with template literals — never use Python string replacement via Bash for template literal content |
