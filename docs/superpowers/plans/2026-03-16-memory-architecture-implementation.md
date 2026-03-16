# Memory Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from 5 monolithic Serena memories to a 20-file atomic memory system with lifecycle tooling, slimmed CLAUDE.md, and machine-level workspace rules.

**Architecture:** Three-scope memory topology (session/ephemeral, project/committed, global/machine-wide) with agent-driven promotion via `/ship` command. Atomic files named for Serena's relevance inference. Deferred `memory-platform` repo until second stockanalysis project starts.

**Tech Stack:** Serena MCP (memory read/write/delete), Claude Code slash commands (.claude/commands/), GitHub CLI (gh), git

**Spec:** `docs/superpowers/specs/2026-03-16-memory-architecture-design.md`

---

## Chunk 1: Foundation

### Task 1: Back up CLAUDE.md before replacement

**Files:**
- Create: `docs/superpowers/archive/CLAUDE-backup-2026-03-16.md` (copy of current CLAUDE.md)

- [ ] **Step 1: Copy CLAUDE.md to archive**

  Read CLAUDE.md in full, write the entire content verbatim to `docs/superpowers/archive/CLAUDE-backup-2026-03-16.md`.

- [ ] **Step 2: Verify the backup**

  Read `docs/superpowers/archive/CLAUDE-backup-2026-03-16.md` — confirm it matches CLAUDE.md line count and starts with `# stock-signal-platform`.

- [ ] **Step 3: Commit**

  ```bash
  git add docs/superpowers/archive/CLAUDE-backup-2026-03-16.md
  git commit -m "chore: backup CLAUDE.md before memory architecture migration"
  ```

---

### Task 2: Fix .gitignore to expose .serena/memories/ to git

**Files:**
- Modify: `.gitignore` (line 66 area — currently has `.serena/` which gitignores everything)

- [ ] **Step 1: Locate the current .serena entry**

  Open `.gitignore`. Find the line that reads `.serena/` (or `**/.serena/`).

- [ ] **Step 2: Replace the broad ignore with surgical ignores**

  Replace `.serena/` with:
  ```
  # Serena — commit project memories, ignore cache and ephemeral session
  .serena/cache/
  .serena/memories/session/*
  !.serena/memories/session/.gitkeep
  .serena/project.local.yml
  ```

  **Critical:** Use `*` not trailing slash for session/ — trailing slash would ignore the directory itself, preventing .gitkeep from being tracked.

- [ ] **Step 3: Verify .serena/memories/ is no longer ignored**

  ```bash
  git check-ignore -v .serena/memories/project_overview.md
  ```
  Expected: no output (not ignored).

- [ ] **Step 4: Commit**

  ```bash
  git add .gitignore
  git commit -m "chore: fix .gitignore to expose .serena/memories/ for project memory sharing"
  ```

---

### Task 3: Create session/ staging directory with .gitkeep

**Files:**
- Create: `.serena/memories/session/.gitkeep`

- [ ] **Step 1: Create the .gitkeep file**

  Create an empty file at `.serena/memories/session/.gitkeep`. This preserves the directory in git while session memories themselves are gitignored.

- [ ] **Step 2: Verify git sees .gitkeep but not hypothetical session files**

  ```bash
  git status .serena/memories/session/
  ```
  Expected: `.serena/memories/session/.gitkeep` as untracked (or new file). A test file `test.md` placed there should NOT appear in `git status`.

- [ ] **Step 3: Commit**

  ```bash
  git add .serena/memories/session/.gitkeep
  git commit -m "chore: add session/ memory staging directory (gitignored except .gitkeep)"
  ```

---

### Task 4: Add gh CLI to Claude Code allowed tools

**Files:**
- Modify: `.claude/settings.json`

- [ ] **Step 1: Read current settings.json**

  Read `.claude/settings.json`. Find the `allowedTools` array.

- [ ] **Step 2: Add Bash(gh *) to allowed tools**

  Add `"Bash(gh *)"` to the `allowedTools` array. This permits the `/ship` command to run `gh pr create` without a per-call approval prompt.

- [ ] **Step 3: Verify JSON is valid**

  ```bash
  uv run python -c "import json; json.load(open('.claude/settings.json'))"
  ```
  Expected: no output (valid JSON).

- [ ] **Step 4: Commit**

  ```bash
  git add .claude/settings.json
  git commit -m "chore: allow gh CLI in Claude Code tool permissions for /ship command"
  ```

---

## Chunk 2: Memory Migration

### Task 5: Write global/conventions/python-style

**Files:**
- Create: `~/.serena/memories/global/conventions/python-style.md` (via Serena write_memory with `global/` prefix)

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/conventions/python-style`. Content:

  ```markdown
  ---
  scope: global
  category: conventions
  applies_to: all Python projects (stockanalysis domain)
  ---

  # Python Style Conventions

  - Type hints on ALL functions. Google-style docstrings.
  - Async by default for FastAPI endpoints and DB operations.
  - Pydantic v2 for API schemas; SQLAlchemy 2.0 `mapped_column` style.
  - Use `X | None` (PEP 604) — never `Optional[X]` or `Union[X, None]`.
  - `logging.getLogger(__name__)` — never bare `print()` in backend code.
  - No module-level mutable state. Use constants (UPPER_CASE) and `settings` only.
  - No bare `except:` — always `except Exception` or specific type.
  - `datetime.now(timezone.utc)` not `datetime.utcnow()` (deprecated).
  - Mutable default args: `def f(x: list | None = None): x = x or []`
  - Nested conditionals > 2 levels: use early returns / guard clauses.
  - `eval()` / `exec()`: NEVER — find a safe alternative.
  ```

- [ ] **Step 2: Verify write succeeded**

  Use Serena `read_memory` with key `global/conventions/python-style` — confirm content is present.

---

### Task 6: Write global/conventions/typescript-style

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/conventions/typescript-style`. Content:

  ```markdown
  ---
  scope: global
  category: conventions
  applies_to: all TypeScript/Next.js projects (stockanalysis domain)
  ---

  # TypeScript / Frontend Style Conventions

  - Strict mode enabled — no `any` types, no `@ts-ignore`.
  - All API calls go through `lib/api.ts` (centralized fetch with cookie auth).
  - Use TanStack Query for server state — never raw `useEffect` + `fetch`.
  - Components use shadcn/ui primitives; style with Tailwind utility classes.
  - Charts use Recharts exclusively. Never inline styles.
  - Keep components under 150 lines; extract sub-components when exceeded.
  - Use Next.js App Router patterns (server components where possible).
  - Use `next/image` for all images (not `<img>`).
  - `hsl(var(--x))` in Recharts: use `useChartColors()` hook — needs resolved color strings, not CSS var references.
  - localStorage: lazy `useState(() => { if (typeof window === "undefined") return default; return localStorage.getItem(key) ?? default; })`.
  - base-ui/shadcn v4: triggers use `render={<Button />}` prop, NOT `asChild`.
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/conventions/typescript-style` — confirm present.

---

### Task 7: Write global/conventions/testing-patterns

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/conventions/testing-patterns`. Content:

  ```markdown
  ---
  scope: global
  category: conventions
  applies_to: all Python projects (stockanalysis domain)
  ---

  # Testing Patterns

  - Every module MUST have a corresponding test file in `tests/`.
  - Every public function MUST have at least one unit test.
  - Every FastAPI endpoint MUST have auth + happy path + error path tests.
  - Use factory-boy for test data, never raw dicts.
  - Use testcontainers for integration tests — NEVER SQLite substitutes.
  - Use freezegun for time-dependent tests.
  - Run relevant tests after creating a module: `uv run pytest tests/unit/test_{module}.py -v`.
  - Fix ALL test failures before moving on.

  ## Mock & Patch Guidelines
  - ALWAYS patch where the name is LOOKED UP, not where it is defined.
    - `@patch("backend.routers.stocks.fetch_prices")` NOT `@patch("backend.tools.market_data.fetch_prices")`
  - Use `AsyncMock` for async functions, `MagicMock` for sync.
  - For yfinance/external APIs: mock at the tool boundary (mock `fetch_prices`, not `yf.download`).
  - Stack `@patch` decorators bottom-up: bottom = first function parameter.
  - For DB-dependent tests: use real async session from testcontainers fixtures — do NOT mock SQLAlchemy.
  - Never mock what you don't own at a granular level.
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/conventions/testing-patterns` — confirm present.

---

### Task 8: Write global/conventions/git-workflow

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/conventions/git-workflow`. Content:

  ```markdown
  ---
  scope: global
  category: conventions
  applies_to: all stockanalysis domain projects
  ---

  # Git Workflow

  - Conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `refactor:`
  - Branch per feature: `feat/signal-engine`, `feat/dashboard`, etc.
  - Feature flow: `feat/* → PR → develop → PR → main`
  - Never commit to `main` or `develop` directly — everything through a PR.
  - `main` is production-ready at all times; `develop` is staging/integration.
  - Hotfix flow: `hotfix/* → PR → main`, then immediately open second PR `hotfix/* → develop` to back-merge.
  - Lint before every commit: `uv run ruff check --fix` → `uv run ruff format` → verify zero errors.
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/conventions/git-workflow` — confirm present.

---

### Task 9: Write global/conventions/error-handling

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/conventions/error-handling`. Content:

  ```markdown
  ---
  scope: global
  category: conventions
  applies_to: all Python/FastAPI projects (stockanalysis domain)
  ---

  # Error Handling & Logging Conventions

  ## Logging
  - Every module: `logger = logging.getLogger(__name__)` at module level.
  - Levels: `DEBUG` (computation details), `INFO` (operations completed), `WARNING` (degraded), `ERROR` (failed).
  - Include context: `logger.info("Stored %d rows for %s", count, ticker)` — not `logger.info("Done")`.
  - Use `logger.exception()` inside `except` blocks (auto-includes traceback).
  - NEVER log secrets, tokens, or passwords at any level.

  ## Error Handling by Context
  - Routers: raise `HTTPException` with specific status codes (400, 401, 404, 422).
  - Tools/Services: raise `ValueError` for invalid inputs; let unexpected errors propagate.
  - External APIs (yfinance): log WARNING, retry or degrade gracefully.
  - Config errors: fail fast at startup with clear error message.
  - Never swallow exceptions silently (`except: pass`).
  - Return consistent error shape: `{"detail": "Human-readable message"}`.
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/conventions/error-handling` — confirm present.

---

### Task 10: Write global/debugging/mock-patching-gotchas

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/debugging/mock-patching-gotchas`. Content:

  ```markdown
  ---
  scope: global
  category: debugging
  applies_to: all Python projects (stockanalysis domain)
  GLOBAL-CANDIDATE: true
  ---

  # Mock/Patch Gotchas

  ## The lookup-site rule
  Patch where the name is LOOKED UP, not where it is defined.

  ```python
  # Wrong — patches the definition site
  @patch("backend.tools.market_data.fetch_prices")

  # Correct — patches where the router imports it
  @patch("backend.routers.stocks.fetch_prices")
  ```

  ## Lazy imports
  If a module uses lazy imports (to break circular deps), the patch site is the lazy import location.
  Example: `backend.routers.stocks` lazy-imports `fetch_prices` from `backend.tools.market_data` inside the function body.
  Patch: `@patch("backend.tools.market_data.fetch_prices")` (because it's looked up there at call time, not at import time).

  ## Decorator stacking (bottom-up = first param)
  ```python
  @patch("module.B")   # → second param
  @patch("module.A")   # → first param
  def test_foo(mock_a, mock_b): ...
  ```

  ## AsyncMock vs MagicMock
  - `async def` functions: use `AsyncMock`
  - sync functions: use `MagicMock`
  - Mixing causes `RuntimeWarning: coroutine was never awaited`
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/debugging/mock-patching-gotchas` — confirm present.

---

### Task 11: Write global/architecture/system-overview

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/architecture/system-overview`. Content:

  ```markdown
  ---
  scope: global
  category: architecture
  applies_to: stockanalysis domain — stock-signal-platform
  ---

  # System Architecture Overview

  ## Stack
  - Backend: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Celery
  - Frontend: Next.js (latest stable), React, TypeScript, Tailwind CSS, shadcn/ui, Recharts
  - Database: PostgreSQL 16 + TimescaleDB extension
  - Cache/Broker: Redis 7
  - AI/ML: LangChain, LangGraph, Prophet, scikit-learn, pandas-ta
  - LLM: Groq (agentic loops — fast/cheap), Claude Sonnet (synthesis, Anthropic API), LM Studio (offline fallback)
  - Data: yfinance, FRED API
  - Auth: JWT (python-jose) + bcrypt (passlib), httpOnly cookies, rate limiting (slowapi)
  - Package manager: uv (NOT pip, NOT poetry)

  ## Principles
  - Monolith-first, microservice-ready: clean domain boundaries
  - Each tool group in `backend/tools/` has clean interfaces for future MCP server extraction
  - Frontend is a SINGLE Next.js app — NO iframes, NO Plotly Dash, NO second framework
  - Background jobs (Celery) pre-compute signals nightly; dashboard reads pre-computed data
  - Agents call tools via ToolRegistry now; will call via MCP protocol later

  ## Services (local dev)
  - Backend: port 8181 (`uv run uvicorn backend.main:app --reload --port 8181`)
  - Frontend: port 3000 (`cd frontend && npm run dev`)
  - Postgres: port 5433 (Docker — NOT default 5432)
  - Redis: port 6380 (Docker — NOT default 6379)
  - Docs: port 8000 (`uv run mkdocs serve`)
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/architecture/system-overview` — confirm present.

---

### Task 12: Write global/onboarding/setup-guide

- [ ] **Step 1: Write the memory**

  Use Serena `write_memory` with key `global/onboarding/setup-guide`. Content:

  ```markdown
  ---
  scope: global
  category: onboarding
  applies_to: stockanalysis domain — stock-signal-platform
  ---

  # Setup Guide

  ## Prerequisites
  - Docker Desktop running
  - uv installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
  - Node.js 20+ with npm
  - gh CLI authenticated (`gh auth login`)

  ## Bootstrap
  ```bash
  uv sync                                    # Install all Python deps + create .venv/
  cd frontend && npm install                 # Install frontend deps
  docker compose up -d postgres redis        # Start Postgres (5433) + Redis (6380)
  uv run alembic upgrade head               # Run DB migrations
  ```

  ## Verify
  ```bash
  uv run pytest tests/unit/ -v              # Should be green
  uv run uvicorn backend.main:app --port 8181  # Backend starts
  cd frontend && npm run dev                 # Frontend at localhost:3000
  ```

  ## Known port quirks
  - Postgres: 5433 (NOT 5432) — `DATABASE_URL=postgresql+asyncpg://...@localhost:5433/stockdb`
  - Redis: 6380 (NOT 6379) — `REDIS_URL=redis://localhost:6380/0`

  ## Note on global memories (new machine)
  Until `memory-platform` repo exists, clone this repo and run Serena to rebuild project memories.
  When `memory-platform` is created (at second stockanalysis project start), a `sync-global-memories.sh`
  script will populate `~/.serena/memories/global/` on new machines.
  ```

- [ ] **Step 2: Verify write succeeded**

  Read memory `global/onboarding/setup-guide` — confirm present.

---

### Task 13: Write project-scoped memories (project/state, project/stack)

- [ ] **Step 1: Write project/state**

  Use Serena `write_memory` with key `project/state`. Content:

  ```markdown
  ---
  scope: project
  category: project
  updated_by: human + CI
  ---

  # Project State

  - **Current Phase:** Phase 4B — AI Chatbot backend
  - **Current Branch:** feat/phase-4b-ai-chatbot
  - **Alembic Head:** 821eb511d146 (migration 007)
  - **Test Count:** 267 (143 unit + 124 API backend) + 20 frontend component tests
  - **What's next:** ChatSession/ChatMessage models + migration 008 → agents/ (BaseAgent, StockAgent, GeneralAgent, loop, NDJSON streaming) → routers/chat.py → wire ChatPanel stub

  ## Phase Completion
  - Phase 1 (Sessions 1-3): COMPLETE
  - Phase 2 (Sessions 4-7): COMPLETE
  - Phase 2.5 (Sessions 8-13): COMPLETE
  - Phase 3 (Sessions 14-20): COMPLETE
  - Phase 3.5 (Sessions 21-25): COMPLETE
  - Phase 4A UI Redesign (Session 29): COMPLETE
  - Memory Architecture Migration (Session 31): IN PROGRESS
  ```

- [ ] **Step 2: Write project/stack**

  Use Serena `write_memory` with key `project/stack`. Content:

  ```markdown
  ---
  scope: project
  category: project
  ---

  # Project Stack & Entry Points

  ## Key Entry Points
  - Backend: `backend/main.py` (FastAPI app, routers, startup events)
  - Config: `backend/config.py` (Pydantic Settings, .env support)
  - DB: `backend/database.py` (async engine + session factory — `async_session_factory`)
  - Auth: `backend/dependencies.py` (JWT validation, `get_current_user`)

  ## Critical Gotchas
  - `bcrypt` pinned to 4.2.x (passlib incompatible with bcrypt 5.x)
  - Docker ports: Postgres 5433, Redis 6380 (NOT defaults)
  - `API_BASE = "/api/v1"` in `lib/api.ts` — hooks use `/portfolio/...` NOT `/api/v1/portfolio/...` (double-prefix bug)
  - `async_session_factory` is the correct import name (from `backend/database.py`)
  - Route ordering matters: literal segments must come before path params in FastAPI
  - Celery tasks are sync; use `asyncio.run()` bridge for async code
  - TimescaleDB hypertable upsert needs `constraint="tablename_pkey"` (named constraint)
  - Python heredoc via Bash escapes backticks in JS template literals — use Edit/Write tools for JS/TS
  - `fetch_fundamentals()` is synchronous — use `run_in_executor` in async context
  - Alembic autogenerate falsely drops TimescaleDB indexes — always review diffs

  ## Package Manager
  - uv (NOT pip, NOT poetry). All commands: `uv run <cmd>`. Add deps: `uv add <pkg>`.
  ```

- [ ] **Step 3: Verify both writes succeeded**

  Read `project/state` and `project/stack` — confirm content is present.

---

### Task 14: Write architecture memories

- [ ] **Step 1: Write architecture/timescaledb-patterns**

  Use Serena `write_memory` with key `architecture/timescaledb-patterns`. Content:

  ```markdown
  ---
  scope: project
  category: architecture
  ---

  # TimescaleDB Patterns

  ## Hypertables
  - All time-series tables (price_data, signals, etc.) are hypertables.
  - Partition column is always `time` (timestamptz).
  - PK is composite: `(id, time)` — required for hypertable partitioning.

  ## Upsert Pattern
  ```python
  # ON CONFLICT needs the named constraint, not column list
  stmt = insert(PriceData).values(rows)
  stmt = stmt.on_conflict_do_update(
      constraint="price_data_pkey",   # named constraint, NOT index_elements
      set_={"open": stmt.excluded.open, ...}
  )
  await session.execute(stmt)
  ```

  ## Alembic Caution
  Alembic autogenerate FALSELY detects TimescaleDB internal indexes as user-created.
  Always review `alembic revision --autogenerate` output — manually remove any `op.drop_index()`
  calls that reference TimescaleDB-managed indexes (pattern: `_compressed_hypertable_*`).

  ## Continuous Aggregates
  Currently using nightly Celery jobs instead of continuous aggregates (simpler).
  If performance degrades, revisit continuous aggregates for signals pre-computation.
  ```

- [ ] **Step 2: Write architecture/frontend-design-system**

  Use Serena `write_memory` with key `architecture/frontend-design-system`. Content:

  ```markdown
  ---
  scope: project
  category: architecture
  ---

  # Frontend Design System

  ## Phase 4A: Dark Navy Command-Center Shell
  - `forcedTheme="dark"` on ThemeProvider — no light mode toggle.
  - Navy token palette: bg-navy-950/900/800/700, text-navy-100/200/400.
  - Components: SidebarNav, Topbar, ChatPanel (stub), StatTile, AllocationDonut, PortfolioDrawer, Sparkline.

  ## Color System for Recharts
  - Recharts requires literal color strings — CSS variables (`hsl(var(--x))`) don't resolve.
  - Use `useChartColors()` hook (reads via `getComputedStyle`) or local `readCssVar()` for one-off reads.
  - Lazy `useState(() => resolveColor(...))` for colors needing initial paint.

  ## Shared Components
  - `ChangeIndicator`, `SectionHeading`, `ChartTooltip`, `ErrorState`, `Breadcrumbs`
  - `Sparkline` (SVG, no Recharts — for inline sparklines in tables)
  - `SignalMeter`, `MetricCard`, `PortfolioValueChart`
  - `DensityProvider` — screener compact/comfortable toggle

  ## shadcn/base-ui v4 Gotchas
  - `SheetTrigger`, `PopoverTrigger` use `render={<Button />}` prop, NOT `asChild`.
  - Applies to ALL base-ui trigger components.

  ## Testing
  - Jest: `testEnvironment: "jsdom"` (NOT "node").
  - `@testing-library/react` + `@testing-library/jest-dom`.
  - Test files at `frontend/src/__tests__/`.
  ```

---

### Task 15: Write domain memories

- [ ] **Step 1: Write domain/signals-and-screener**

  Use Serena `write_memory` with key `domain/signals-and-screener`. Content:

  ```markdown
  ---
  scope: project
  category: domain
  ---

  # Signals & Screener Domain

  ## Signal Computation
  - `compute_signals()` in `backend/tools/signals.py` — accepts optional `piotroski_score` param.
  - With piotroski_score: 50/50 blending of technical + fundamental composite.
  - Without: pure technical composite.
  - Depends on `backend/tools/fundamentals.py` for Piotroski F-Score calculation.

  ## Screener
  - `backend/tools/screener.py` — filter + rank by composite criteria.
  - Supports DensityProvider (compact/comfortable) on frontend.
  - Screener results are pre-computed nightly by Celery tasks.

  ## Key Gotchas
  - Market hours UTC: March (DST) = EDT (UTC-4). 09:00 EDT = 13:00 UTC (NOT 14:00 UTC).
  - yfinance rate limiting: add 0.5s delay between ticker fetches in batch scripts.
  - yfinance returns empty DataFrame for invalid/delisted tickers — validate before processing.
  ```

- [ ] **Step 2: Write domain/portfolio-tracker**

  Use Serena `write_memory` with key `domain/portfolio-tracker`. Content:

  ```markdown
  ---
  scope: project
  category: domain
  ---

  # Portfolio Tracker Domain

  ## Key Tools
  - `backend/tools/portfolio.py` — positions, cost basis, P&L, allocation.
  - `backend/tools/recommendations.py` — Buy/Hold/Sell decisions, position sizing.
  - Portfolio-aware recommendations blend signal scores with current allocation.

  ## API Gotcha
  - `API_BASE = "/api/v1"` in `lib/api.ts`.
  - Frontend hooks must use paths like `/portfolio/positions` NOT `/api/v1/portfolio/positions`.
  - Double-prefix bug: the api.ts wrapper already prepends API_BASE.

  ## Rebalancing
  - Divestment rules, rebalancing logic, and portfolio-aware recs built in Phase 3.5 (Sessions 21-25).
  - Snapshots and dividend tracking included.

  ## patch<T>() helper
  - `lib/api.ts` exports `patch<T>()` for PATCH requests — use for partial position updates.
  ```

- [ ] **Step 3: Write domain/agent-tools**

  Use Serena `write_memory` with key `domain/agent-tools`. Content:

  ```markdown
  ---
  scope: project
  category: domain
  phase: 4B (IN PROGRESS)
  ---

  # Agent Tools Domain

  ## Architecture (Phase 4B)
  - `backend/agents/base.py` — BaseAgent ABC
  - `backend/agents/registry.py` — AgentRegistry (discover + route)
  - `backend/agents/loop.py` — agentic tool-calling loop
  - `backend/agents/stream.py` — NDJSON streaming to frontend
  - `backend/agents/general_agent.py` — general purpose + web search
  - `backend/agents/stock_agent.py` — stock analysis + signals + forecasting
  - `backend/tools/registry.py` — ToolRegistry (all tools discoverable)
  - `backend/routers/chat.py` — chat endpoints (POST /chat/message, GET /chat/sessions)

  ## LLM Routing
  - Groq: primary for agentic tool-calling loops (fast/cheap, GROQ_API_KEY)
  - Claude Sonnet: synthesis and final response (ANTHROPIC_API_KEY)
  - LM Studio: offline fallback (no key needed, local inference)

  ## Streaming Protocol
  - NDJSON (newline-delimited JSON) from backend to frontend.
  - Each line: `{"type": "token"|"tool_call"|"tool_result"|"done", "content": ...}`
  - Frontend ChatPanel reads the stream and renders incrementally.

  ## DB Models (migration 008)
  - `ChatSession`: id, user_id, title, created_at, updated_at
  - `ChatMessage`: id, session_id, role (user/assistant/tool), content, tool_calls, created_at
  ```

---

### Task 16: Write debugging memories

- [ ] **Step 1: Write debugging/backend-gotchas**

  Use Serena `write_memory` with key `debugging/backend-gotchas`. Content:

  ```markdown
  ---
  scope: project
  category: debugging
  ---

  # Backend Debugging Gotchas

  ## asyncpg / pytest-asyncio
  - Nested transactions cause "event loop closed" errors.
  - Solution: per-test engine + truncate tables approach (not rollback).
  - Use `async_session_factory` from `backend/database.py` (correct name — not `AsyncSessionLocal`).

  ## UserRole enum
  - SQLAlchemy sends `.name` (uppercase) not `.value` to Postgres by default.
  - Fix: add `values_callable=lambda e: [m.value for m in e]` to `Enum()` in model definition.

  ## Circular imports
  - `stocks` ↔ `portfolio` routers have circular dependency.
  - Fix: lazy imports inside endpoint functions (not at module level).

  ## Alembic
  - `uv run alembic upgrade head` (not bare `alembic`).
  - Autogenerate falsely drops TimescaleDB indexes — always review output before running.
  - After pulling: `uv sync` to keep local venv in sync with `uv.lock`.

  ## yfinance
  - Returns empty DataFrame for invalid/delisted tickers.
  - Rate limiting: 0.5s delay between batch fetches.
  - Mock at tool boundary (`fetch_prices`) not at `yf.download`.

  ## passlib / bcrypt
  - bcrypt >= 5.0 broke passlib API. Pin `bcrypt==4.2.1` in pyproject.toml.

  ## compute_signals()
  - Accepts optional `piotroski_score` param — omit for pure technical composite.

  ## Celery
  - Tasks are synchronous. Bridge to async via `asyncio.run()`.

  ## fetch_fundamentals()
  - Synchronous function. In async context: `await loop.run_in_executor(None, fetch_fundamentals, ticker)`.
  ```

- [ ] **Step 2: Write debugging/frontend-gotchas**

  Use Serena `write_memory` with key `debugging/frontend-gotchas`. Content:

  ```markdown
  ---
  scope: project
  category: debugging
  ---

  # Frontend Debugging Gotchas

  ## ESLint react-hooks/set-state-in-effect
  - Calling `setState()` synchronously inside `useEffect` body triggers this error.
  - Fix: use lazy `useState(() => initialValue)` for one-time reads (e.g. localStorage).
  - For reactive updates: use `MutationObserver` callback inside effect, not the effect body directly.

  ## Recharts colors
  - CSS vars (`hsl(var(--x))`) do NOT resolve inside Recharts.
  - Use `useChartColors()` hook (reads via `getComputedStyle`).
  - For initial render: `useState(() => readCssVar('--color-positive'))` — reads synchronously on mount.

  ## API double-prefix
  - `API_BASE = "/api/v1"` is already in `lib/api.ts`.
  - Hook paths: `/portfolio/positions` NOT `/api/v1/portfolio/positions`.

  ## next/image
  - Always `<Image />` from `next/image`, never `<img>`.
  - Requires `width` + `height` or `fill` prop.

  ## Worktree subagents
  - Claude Code permission model restricts Write/Bash in isolated worktrees.
  - Write files from main session; use worktrees for research/read tasks only.

  ## JS template literals via Bash
  - Python heredoc/string replacement via Bash escapes backticks in JS template literals.
  - Use Edit tool or Write tool for JS/TS files with template literals — never Python string ops via Bash.

  ## base-ui/shadcn v4 triggers
  - `SheetTrigger`, `PopoverTrigger`, and ALL base-ui trigger components use `render={<Button />}`, NOT `asChild`.
  ```

---

### Task 17: Write serena tool memories

- [ ] **Step 1: Write serena/tool-usage**

  Use Serena `write_memory` with key `serena/tool-usage`. Content:

  ```markdown
  ---
  scope: project
  category: serena
  ---

  # Serena Tool Usage Rules

  ## MCP Prefix
  Use `mcp__plugin_serena_serena__*` (not `mcp__serena__*`).
  Must call `activate_project("stock-signal-platform")` at session start before any memory reads/writes.

  ## Tool Priority
  ALL file operations use Serena first:
  - `find_file`, `list_dir`, `search_for_pattern`, `read_file` (not Read/Grep/Glob)
  - `replace_content`, `replace_symbol_body`, `insert_after_symbol` (not Edit/Write)
  - This applies to TypeScript, CSS, JSON — not just Python.
  - Built-in Read/Grep/Edit/Glob only when Serena cannot do the job.

  ## Symbolic Reading (token efficiency)
  - `get_symbols_overview(file)` — see all symbols without reading bodies.
  - `find_symbol(name_path, include_body=True)` — read a specific function/class.
  - NEVER read entire files to find one function — use find_symbol first.

  ## Editing
  - Replace entire symbol: `replace_symbol_body`
  - Replace a few lines: `replace_content` (regex or string)
  - Add to end of file: `insert_after_symbol` with last top-level symbol
  - Add to start of file: `insert_before_symbol` with first top-level symbol
  ```

- [ ] **Step 2: Write serena/memory-map**

  Use Serena `write_memory` with key `serena/memory-map`. Content:

  ```markdown
  ---
  scope: project
  category: serena
  purpose: taxonomy anchor — ensures new modules are documented in Serena
  ---

  # Memory Taxonomy Map

  ## Global Memories (~/.serena/memories/global/)
  | Key | Content |
  |-----|---------|
  | global/conventions/python-style | Python typing, async, logging, forbidden patterns |
  | global/conventions/typescript-style | TS strict mode, TanStack Query, shadcn, Recharts |
  | global/conventions/testing-patterns | pytest, factory-boy, testcontainers, mock rules |
  | global/conventions/git-workflow | Conventional commits, branch strategy, PR flow |
  | global/conventions/error-handling | Logging levels, error handling by context |
  | global/debugging/mock-patching-gotchas | Patch lookup-site rule, AsyncMock, decorator stacking |
  | global/architecture/system-overview | Full stack, principles, local dev ports |
  | global/onboarding/setup-guide | Bootstrap steps, port quirks, new-machine note |

  ## Project Memories (.serena/memories/ — in repo)
  | Key | Content |
  |-----|---------|
  | project/state | Current phase, branch, Alembic head, test count, resume point |
  | project/stack | Entry points, critical gotchas, package manager rules |
  | architecture/timescaledb-patterns | Hypertable upsert, Alembic caution, continuous aggregates |
  | architecture/frontend-design-system | Navy theme, Recharts colors, shared components, shadcn v4 |
  | domain/signals-and-screener | Signal computation, screener, market hours UTC gotcha |
  | domain/portfolio-tracker | Portfolio tools, API double-prefix, patch() helper |
  | domain/agent-tools | Agent architecture, LLM routing, NDJSON streaming, DB models |
  | debugging/backend-gotchas | asyncpg, UserRole enum, circular imports, Alembic, yfinance |
  | debugging/frontend-gotchas | ESLint hooks, Recharts colors, API prefix, next/image |
  | serena/tool-usage | MCP prefix, tool priority, symbolic reading, editing |
  | serena/memory-map | This file — taxonomy anchor |
  | conventions/auth-patterns | JWT, httpOnly cookies, bcrypt pinning, rate limiting |

  ## New Module Checklist
  When adding a module in Phase 4B, 5, or 6+:
  1. Create `domain/<module-name>.md` covering: purpose, key functions, gotchas, integration points.
  2. Add row to this memory-map table.
  3. If debugging discoveries arise: append to `debugging/backend-gotchas` or `debugging/frontend-gotchas`.
  4. If a pattern is project-agnostic: flag with `GLOBAL-CANDIDATE: true` in frontmatter.
  5. Promote to `global/` via `/ship` when the PR is ready.
  ```

- [ ] **Step 3: Write conventions/auth-patterns**

  Use Serena `write_memory` with key `conventions/auth-patterns`. Content:

  ```markdown
  ---
  scope: project
  category: conventions
  ---

  # Auth Patterns

  ## JWT + httpOnly Cookies
  - JWT signed with `JWT_SECRET_KEY` (from `backend/config.py` Pydantic Settings).
  - Stored in httpOnly, Secure, SameSite=Lax cookies — NOT localStorage.
  - `python-jose` for JWT encode/decode; `passlib` + `bcrypt==4.2.1` for password hashing.
  - Auth logic: `backend/dependencies.py` → `get_current_user` → inject into endpoints.
  - CRITICAL: `bcrypt` must be pinned to 4.2.x — bcrypt >= 5.0 broke passlib API.

  ## Rate Limiting
  - `slowapi` on all endpoints.
  - Aggressive limits on expensive endpoints: data ingestion, signal computation.

  ## Security Rules
  - NEVER commit `.env` files, API keys, or JWT secrets.
  - All user input validated via Pydantic schemas before processing.
  - Ticker sanitization: `ticker.upper().strip()`, reject non-alphanumeric (except `.` and `-`).
  - Error messages MUST NOT reveal stack traces or file paths to end users.
  - SQL injection prevention: always use SQLAlchemy ORM / parameterized queries.
  ```

- [ ] **Step 4: Verify all serena/ and conventions/ memories written**

  Read `serena/tool-usage`, `serena/memory-map`, `conventions/auth-patterns` — confirm all present.

---

### Task 17b: Delete the 5 old monolithic memories

- [ ] **Step 1: Delete project_overview**

  Use Serena `delete_memory` with key `project_overview`.

- [ ] **Step 2: Delete style_and_conventions**

  Use Serena `delete_memory` with key `style_and_conventions`.

- [ ] **Step 3: Delete suggested_commands**

  Use Serena `delete_memory` with key `suggested_commands`.

- [ ] **Step 4: Delete task_completion_checklist**

  Use Serena `delete_memory` with key `task_completion_checklist`.

- [ ] **Step 5: Delete tool_usage_rules**

  Use Serena `delete_memory` with key `tool_usage_rules`.

- [ ] **Step 6: Verify old memories are gone**

  Use Serena `list_memories` — confirm none of the 5 old keys appear.

- [ ] **Step 7: Commit new memories**

  ```bash
  git add .serena/memories/
  git commit -m "feat: migrate to atomic memory architecture (20 files, 3-scope topology)"
  ```

---

## Chunk 3: Tooling

### Task 18: Slim CLAUDE.md to ~60-line routing manifest

**Files:**
- Modify: `CLAUDE.md` (374 lines → ~60 lines)

- [ ] **Step 1: Write the new slim CLAUDE.md**

  Replace the entire content of `CLAUDE.md` with the routing manifest below.
  The full content that was here is backed up at `docs/superpowers/archive/CLAUDE-backup-2026-03-16.md`.

  ```markdown
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
  3. **Lint before commit** — `ruff check --fix` → `ruff format` → zero errors.
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

  All specs → `docs/superpowers/specs/`, all plans → `docs/superpowers/plans/`.
  Completed features → `docs/superpowers/archive/`. Never read archived files.

  ## Key Documents

  - `docs/PRD.md` — what we're building and why
  - `docs/FSD.md` — functional requirements + acceptance criteria
  - `docs/TDD.md` — technical design, API contracts
  - `project-plan.md` — phased build plan
  - `PROGRESS.md` — session log

  ## End-of-Session Checklist

  1. `PROGRESS.md` — session entry added
  2. `CLAUDE.md` — update if architecture changed (rare now — use Serena memories instead)
  3. `project-plan.md` — mark completed deliverables ✅ with session number
  4. `docs/FSD.md` — update if functional requirements changed
  5. `docs/TDD.md` — update if API contracts changed
  6. Serena memories — update `project/state` (ALWAYS), other memories as needed
  7. `MEMORY.md` — update Project State section
  8. Run `/ship` — promote session memories and open PR
  ```

- [ ] **Step 2: Verify CLAUDE.md line count**

  ```bash
  wc -l CLAUDE.md
  ```
  Expected: ~60-80 lines.

- [ ] **Step 3: Commit**

  ```bash
  git add CLAUDE.md
  git commit -m "refactor: slim CLAUDE.md to routing manifest — full content in Serena memories"
  ```

---

### Task 19: Create ~/.claude/CLAUDE.md (machine-level workspace rules)

**Files:**
- Create: `~/.claude/CLAUDE.md` (not committed — machine-local)

- [ ] **Step 1: Check if ~/.claude/CLAUDE.md already exists**

  ```bash
  ls ~/.claude/CLAUDE.md
  ```
  If it exists, read it first and merge rather than overwrite.

- [ ] **Step 2: Write machine-level CLAUDE.md**

  Write to `~/.claude/CLAUDE.md`:

  ```markdown
  # Workspace Rules — All Projects

  These rules apply to every project on this machine.

  ## Tool Discipline

  - **Serena first:** Use `mcp__plugin_serena_serena__*` for all code reads and edits.
    Activate project before any memory ops: `activate_project("<project-name>")`.
  - **Global memories:** `global/` prefix writes go to `~/.serena/memories/global/` — shared across projects.
  - Built-in Read/Edit/Grep/Glob only when Serena cannot do the job.

  ## Before Writing Any Code

  1. Orient: read project's `PROJECT_INDEX.md` (or equivalent), `PROGRESS.md`, `git log --oneline -5`.
  2. Load 2-3 relevant Serena memories for the task — not everything.
  3. Run baseline tests.

  ## Security Non-Negotiables

  - Never commit `.env`, API keys, JWT secrets, or credentials.
  - Never bypass git hooks (`--no-verify`).
  - Never run `eval()` or `exec()` in generated code.
  - Error messages to end users: no stack traces, no file paths.

  ## Stockanalysis Domain — Serena Global Memories

  | Memory | Description |
  |---|---|
  | `global/conventions/python-style` | Python conventions |
  | `global/conventions/typescript-style` | TypeScript/frontend conventions |
  | `global/conventions/testing-patterns` | Testing approach |
  | `global/conventions/git-workflow` | Git branching + PR flow |
  | `global/conventions/error-handling` | Logging + error handling |
  | `global/debugging/mock-patching-gotchas` | Patch at lookup site |
  | `global/architecture/system-overview` | Stack + ports |
  | `global/onboarding/setup-guide` | Bootstrap a new machine |

  ## Memory Lifecycle

  - **session/** — free agent writes during task (ephemeral, gitignored).
  - **project/** — committed to repo, domain-specific. Updated via `/ship`.
  - **global/** — machine-wide, cross-project. Promoted via PR when proven cross-project.
  - Run `/check-stale-memories` at start of each phase and before major refactors.
  ```

- [ ] **Step 3: Verify file exists and is readable**

  ```bash
  wc -l ~/.claude/CLAUDE.md
  ```
  Expected: ~45-55 lines.

---

### Task 20: Create /ship slash command

**Files:**
- Create: `.claude/commands/ship.md`

- [ ] **Step 1: Create the commands directory if needed**

  ```bash
  mkdir -p .claude/commands
  ```

- [ ] **Step 2: Write the /ship command**

  Write to `.claude/commands/ship.md`:

  ```markdown
  ---
  allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git push:*), Bash(git commit:*), Bash(gh pr create:*), Bash(gh pr view:*), mcp__plugin_serena_serena__list_memories, mcp__plugin_serena_serena__read_memory, mcp__plugin_serena_serena__write_memory, mcp__plugin_serena_serena__delete_memory
  description: Promote session memories, commit, push, and open a PR
  ---

  ## Context

  - Current git status: !`git status`
  - Current git diff: !`git diff HEAD`
  - Current branch: !`git branch --show-current`

  ## Your task

  Execute ALL steps in a single message with multiple tool calls:

  ### Step 0 — Session memory scan and promotion

  1. List all memories with key prefix `session/` using `list_memories`.
  2. If any session memories exist:
     a. Read `serena/memory-map` to understand the taxonomy.
     b. For each session memory, classify it: which project/ or global/ key does it map to?
     c. Present a one-line summary table: `[session/key] → [target/key] (PROMOTE | DISCARD)`.
     d. Wait for human approval before writing.
     e. On approval: write each PROMOTE item to its target key using `write_memory`.
     f. For GLOBAL-CANDIDATE items (frontmatter flag): write to `global/<category>/<name>` key.
     g. Delete promoted session memories using `delete_memory` (NOT shell rm).
  3. If no session memories exist, skip to Step 1.

  ### Step 1 — Stage and commit

  Run `git add` on relevant files (code + any promoted Serena memory files in `.serena/memories/`).
  Do NOT use `git add -A` — stage specific files only.

  ### Step 2 — Commit

  Create a single commit with an appropriate conventional commit message covering all staged changes.
  Memory promotions and code changes go in the same commit.

  ### Step 3 — Push

  Push the branch to origin with `-u` flag if first push.

  ### Step 4 — Create PR

  Create a PR using `gh pr create` with:
  - Title: short (under 70 chars), conventional commit style
  - Body: summary bullets + test plan checklist
  - Base branch: `develop` (not `main`)

  ### Step 5 — Confirm

  Report the PR URL. The session is complete.
  ```

- [ ] **Step 3: Commit the /ship command**

  ```bash
  git add .claude/commands/ship.md
  git commit -m "feat: add /ship slash command for session memory promotion + PR creation"
  ```

---

### Task 21: Create /check-stale-memories slash command

**Files:**
- Create: `.claude/commands/check-stale-memories.md`

- [ ] **Step 1: Write the /check-stale-memories command**

  Write to `.claude/commands/check-stale-memories.md`:

  ```markdown
  ---
  allowed-tools: mcp__plugin_serena_serena__list_memories, mcp__plugin_serena_serena__read_memory, mcp__plugin_serena_serena__find_file, mcp__plugin_serena_serena__find_symbol, mcp__plugin_serena_serena__search_for_pattern, Bash(git branch:*), Bash(git log:*)
  description: Audit all Serena memories for staleness — validates file paths, symbol names, and described behavior
  ---

  ## Your task

  Perform a staleness audit of all Serena project memories. Work methodically through each memory.

  ### Step 1 — List all memories

  Call `list_memories` to get the full list of project-scoped memory keys.

  ### Step 2 — Audit each memory

  For each memory:
  1. Read the memory content.
  2. Check each claim type:

     **File path claims** — any path like `backend/tools/market_data.py`:
     Use `find_file` to verify the file exists. If missing: STALE.

     **Symbol name claims** — any function/class like `compute_signals()`:
     Use `find_symbol` to verify the symbol exists. If missing: STALE.

     **Behavioral claims** — e.g., "bcrypt must be pinned to 4.2.x":
     Use `search_for_pattern` to verify the claim (e.g., check pyproject.toml for bcrypt pin).

     **GLOBAL-CANDIDATE flag** — if `GLOBAL-CANDIDATE: true` in frontmatter:
     Flag for promotion to `global/`.

  ### Step 3 — Report

  Output a markdown table:

  | Memory Key | Status | Issue (if any) |
  |---|---|---|
  | project/state | OK | — |
  | debugging/backend-gotchas | STALE | `_ticker_linker.py` renamed to `ticker_service.py` |
  | domain/agent-tools | GLOBAL-CANDIDATE | frontmatter flag set |
  | conventions/auth-patterns | OK | — |

  Status values:
  - **OK** — all claims verified
  - **STALE** — one or more claims no longer accurate (describe issue)
  - **GLOBAL-CANDIDATE** — frontmatter `GLOBAL-CANDIDATE: true` flagged for global promotion
  - **REMOVE** — memory is entirely superseded or no longer relevant

  ### Step 4 — Propose fixes

  For each STALE or REMOVE item, propose the fix:
  - STALE: show updated text for the affected claim(s)
  - REMOVE: confirm the memory serves no purpose

  Ask for approval before applying any changes.

  ### Step 5 — Apply approved fixes

  On approval, write updated memories using `write_memory`.
  If fixes are significant, offer to commit them:

  ```bash
  git checkout -b docs/fix-stale-memories-<date>
  git add .serena/memories/
  git commit -m "docs: fix stale Serena memories post-refactor"
  ```
  ```

- [ ] **Step 2: Commit the /check-stale-memories command**

  ```bash
  git add .claude/commands/check-stale-memories.md
  git commit -m "feat: add /check-stale-memories slash command for memory staleness audit"
  ```

---

### Task 22: Smoke test

- [ ] **Step 1: Verify all 20 memories are readable**

  Use Serena `list_memories` — confirm all keys from the taxonomy are present.
  Expected: 20 entries across `global/`, `project/`, `architecture/`, `domain/`, `debugging/`, `conventions/`, `serena/`.

- [ ] **Step 2: Verify CLAUDE.md is slim**

  ```bash
  wc -l CLAUDE.md
  ```
  Expected: < 90 lines.

- [ ] **Step 3: Verify .gitignore surgical ignores**

  ```bash
  git check-ignore -v .serena/memories/project_overview.md 2>/dev/null || echo "not ignored — correct"
  git check-ignore -v .serena/memories/session/foo.md && echo "session file ignored — correct"
  ```

- [ ] **Step 4: Verify /ship and /check-stale-memories commands exist**

  ```bash
  ls .claude/commands/
  ```
  Expected: `ship.md` and `check-stale-memories.md` present.

- [ ] **Step 5: Verify baseline tests still pass**

  ```bash
  uv run pytest tests/unit/ -v --tb=short
  ```
  Expected: all green (memory migration doesn't touch Python code).

- [ ] **Step 6: Final commit — update MEMORY.md and PROGRESS.md**

  Update auto-memory `MEMORY.md` Project State section to reflect migration complete.
  Add session 31 entry to `PROGRESS.md`.
  Commit both.

  ```bash
  git add MEMORY.md PROGRESS.md
  git commit -m "docs: session 31 — memory architecture migration complete"
  ```

---

## Execution Summary

| Chunk | Tasks | Key Outcome |
|---|---|---|
| 1 — Foundation | 1-4 | CLAUDE.md backed up, .gitignore fixed, session/ created, gh allowed |
| 2 — Migration | 5-17b | 20 atomic memories written, 5 old monoliths deleted, memories committed |
| 3 — Tooling | 18-22 | CLAUDE.md slimmed, ~/.claude/CLAUDE.md, /ship, /check-stale-memories, smoke test |

**Total commits:** ~10 small, focused commits.
**Test impact:** Zero — no code changes, only infrastructure and documentation.
