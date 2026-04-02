# stock-signal-platform

Stock analysis SaaS platform for part-time investors — US equities, signal detection, portfolio tracking, AI-powered recommendations. Multi-user cloud deployment target — design for scale, not single-user.

## Session Start

Before writing any code:
1. Read `PROJECT_INDEX.md` — full repo map
2. Read `PROGRESS.md` — where we left off
3. Read Serena memory `conventions/jira-sdlc-workflow` — **mandatory SDLC process**
4. Run `git status && git log --oneline -5`
5. Query JIRA board: `project = KAN AND status != Done ORDER BY rank ASC`
6. Identify current phase of active Epics (Refinement? Implementation?)
7. Pick next unblocked Subtask and present to PM for approval
8. **Local LLM triage (MANDATORY — NO EXCEPTIONS)** — before EVERY implementation task, score it (context_span + convention_density + ambiguity, each 1-5). If total ≤ 8: MUST present "This scores X/15 — suitable for `/implement-local`. Delegate to local LLM? (y/n)" and WAIT for answer. This applies to subagent tasks too — ask BEFORE dispatching. "Speed" and "parallel execution" are NOT valid reasons to skip. User is evaluating local LLM — skipping = lost data.
9. Run `uv run pytest tests/unit/ -q --tb=short` — confirm baseline green

## Memory Map

All conventions, patterns, and gotchas live in Serena memories — NOT in this file.
Load what you need for the task at hand:

| Memory Key | Content |
|---|---|
| `project/state` | Current phase, branch, test count, resume point |
| `project/stack` | Entry points, critical gotchas, package manager |
| `project/testing` | Test commands, test layout, fixtures, factory-boy, freezegun, CI |
| `global/conventions/python-style` | Python typing, async, logging, forbidden patterns |
| `global/conventions/typescript-style` | TS strict mode, TanStack, shadcn, Recharts |
| `global/conventions/testing-patterns` | pytest, factory-boy, testcontainers, mock rules |
| `global/conventions/git-workflow` | Conventional commits, branch strategy, PR flow |
| `global/conventions/error-handling` | Logging levels, error handling by context |
| `global/debugging/mock-patching-gotchas` | Patch lookup-site rule, AsyncMock |
| `project/onboarding` | Bootstrap: clone, uv sync, .env, Docker, first ingest |
| `architecture/system-overview` | Services, ports, entry points, filesystem layout, env vars |
| `architecture/timescaledb-patterns` | Hypertable upsert, Alembic gotchas |
| `architecture/frontend-design-system` | Navy theme, Recharts colors, shadcn v4 |
| `architecture/auth-jwt-flow` | Full JWT flow, token storage, OWASP checklist |
| `architecture/celery-patterns` | Celery entry points, asyncio.run() bridge, beat schedule |
| `domain/signals-and-screener` | Signal computation, screener |
| `domain/portfolio-tracker` | Portfolio tools, API prefix gotcha |
| `domain/agent-tools` | Agents, LLM routing, NDJSON streaming |
| `architecture/cicd-pipeline` | CI/CD workflows, branch protection, fixture split, test expectations |
| `project/jira-integration-brainstorm` | JIRA instance details, ticket map, transition IDs, automation rules |
| `debugging/backend-gotchas` | asyncpg, UserRole enum, circular imports |
| `debugging/frontend-gotchas` | ESLint hooks, Recharts, template literals |
| `conventions/auth-patterns` | JWT, httpOnly cookies, direct bcrypt |
| `conventions/jira-sdlc-workflow` | **MANDATORY** — full JIRA SDLC process, branching, CI/CD integration |
| `serena/tool-usage` | Serena MCP prefix, tool priority rules |
| `serena/memory-map` | Full taxonomy — use when adding new modules |

## 10 Hard Rules

1. **uv only** — `uv run`, `uv add`. Never `pip install` or bare `python`.
2. **Test everything** — unit test every public function; endpoint tests: auth + happy + error.
3. **Lint before commit** — `ruff check --fix` then `ruff format` then zero errors.
4. **No secrets in code** — `.env` only, never committed.
5. **Async by default** — FastAPI endpoints and DB calls are always async.
6. **Edit, don't create** — prefer editing existing files over creating new ones.
7. **No mutable module state** — constants and `settings` only at module level.
8. **Serena first** — use symbolic tools for all code reads/edits. Built-ins only when Serena can't.
9. **JIRA workflow** — follow `conventions/jira-sdlc-workflow` exactly. Never skip refinement. Never create implementation subtasks before plan is approved.
10. **No str(e) anywhere** — never pass `str(e)` to `ToolResult(error=...)`, `HTTPException(detail=...)`, or any user-facing output. Log the real error, return a safe generic message.

## Testing Conventions

- **Tier architecture** — tests are organized in tiers T0-T5. Full spec: `docs/superpowers/specs/2026-04-01-test-suite-overhaul.md`
- **xdist for unit tests ONLY** — `pytest-xdist -n auto` on `tests/unit/` only. API/integration tests run sequentially (shared DB = race conditions).
- **E2E against production build** — Playwright runs against `next build && next start`, never `next dev` (Lighthouse scores differ 20-30 points).
- **Coverage at sprint end** — no hooks, no mid-edit checks. Before the PR, report coverage delta and uncovered files. PM decides: fix gaps or ship.
- **Quality gates phased rollout** — new CI gates start as optional. Promote to required via `ci-gate` after 2 weeks of green runs.
- **Semgrep custom rules** — `.semgrep/stock-signal-rules.yml` encodes Hard Rules + auth/JWT patterns as permanent guardrails. Test rules in `tests/semgrep/`.
- **Hypothesis `max_examples`** — `20` in CI (fast), `200` in nightly (thorough).
- **Recharts in Playwright** — disable animations (`isAnimationActive={false}`) or wait for completion. Chart sizing is Playwright-only (jsdom has no layout engine).
- **Every bug fix gets a regression test** — `@pytest.mark.regression`, reproduces the bug, prevents recurrence.

## Services (local dev)

| Service | Command | Port |
|---|---|---|
| Backend | `uv run uvicorn backend.main:app --reload --port 8181` | 8181 |
| Frontend | `cd frontend && npm run dev` | 3000 |
| Postgres | `docker compose up -d postgres` | **5433** |
| Redis | `docker compose up -d redis` | **6380** |
| Celery worker | `uv run celery -A backend.tasks worker --loglevel=info` | — |
| Langfuse | `docker compose up -d langfuse-db langfuse-server` | **3001** |
| Langfuse DB | (auto with langfuse-server) | **5434** |
| Docs | `uv run mkdocs serve` | 8000 |

## Git Branching

```
main        ← production-ready, protected (ci-merge/build required)
develop     ← integration branch, protected (ci-pr/backend-test + frontend-test)
feat/KAN-*  ← Story branches → PR to develop
hotfix/KAN-* ← emergency fixes → PR to main + back-merge to develop
```

- **ALWAYS branch from `develop`**, never from `main`:
  `git checkout develop && git pull origin develop && git checkout -b feat/KAN-[story#]-[kebab-name]`
- PR title: `[KAN-X] Summary`
- Never commit directly to main or develop
- Never skip hooks (`--no-verify`) — fix the underlying issue
- `uv.lock` is committed — run `uv sync` after pulling
- CI secrets (GitHub Actions Secrets, never in .env): `CI_DATABASE_URL`, `CI_REDIS_URL`, `CI_JWT_SECRET_KEY`, `CI_JWT_ALGORITHM`, `CI_POSTGRES_PASSWORD`

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
8. **If sprint complete** — run `uv run pytest --cov=backend --cov-report=term-missing -q` and report coverage delta + uncovered files. Get PM approval before shipping.
9. Run `/ship` — promote session memories and open PR
