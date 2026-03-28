---
scope: project
category: serena
purpose: taxonomy anchor — ensures new modules are documented in Serena
---

# Memory Taxonomy Map

## Global Memories (~/.serena/memories/global/)
Truly cross-project patterns only — nothing stock-signal-platform specific here.

| Key | Content |
|-----|---------|
| global/conventions/python-style | Python typing, async, logging, forbidden patterns |
| global/conventions/typescript-style | TS strict mode, TanStack Query, shadcn, Recharts |
| global/conventions/testing-patterns | pytest, factory-boy, testcontainers, mock rules |
| global/conventions/git-workflow | Conventional commits, branch strategy, PR flow (generic) |
| global/conventions/error-handling | Logging levels, error handling by context |
| global/debugging/mock-patching-gotchas | Patch at lookup site, AsyncMock, decorator stacking |
| global/templates/agentic-sdlc-setup | Reusable template: JIRA + CI/CD + agent workflow setup for new projects |

## Project Memories (.serena/memories/ — in repo)
| Key | Content |
|-----|---------|
| project/state | Current phase, branch, Alembic head, test count, resume point |
| project/stack | Entry points, critical gotchas, package manager rules |
| project/testing | Test commands, test layout, fixtures, factory-boy, freezegun, CI |
| project/onboarding | Bootstrap a new machine: clone, uv sync, .env, Docker, first ingest |
| architecture/system-overview | Services table, ports, entry points, filesystem layout, env vars, critical files |
| architecture/timescaledb-patterns | Hypertable upsert, Alembic caution, continuous aggregates |
| architecture/frontend-design-system | Navy theme, Recharts colors, shared components, shadcn v4 |
| architecture/auth-jwt-flow | Full JWT request flow, token storage, OWASP checklist, critical files |
| architecture/celery-patterns | Celery entry points, asyncio.run() bridge, beat schedule, task naming |
| domain/signals-and-screener | Signal computation, screener, market hours UTC gotcha |
| domain/portfolio-tracker | Portfolio tools, API double-prefix, patch() helper |
| domain/agent-tools | 24 internal tools, EntityRegistry, ReAct loop (Phase 8B), MCP adapters, LLM tier routing |
| debugging/backend-gotchas | asyncpg, UserRole enum, circular imports, Alembic, yfinance |
| debugging/frontend-gotchas | ESLint hooks, Recharts colors, API prefix, next/image |
| serena/tool-usage | MCP prefix, tool priority, symbolic reading, editing |
| serena/memory-map | This file — taxonomy anchor |
| conventions/auth-patterns | JWT, httpOnly cookies, frontend auth, bcrypt pinning, security rules |
| conventions/jira-sdlc-workflow | **MANDATORY** — full JIRA SDLC process, board, refinement lifecycle, branching, CI/CD, automation rules, transition IDs |
| architecture/cicd-pipeline | CI/CD workflows, branch protection, fixture split, test expectations, GitHub secrets |
| architecture/implement-local-workflow | LM Studio bridge, complexity scoring, /implement-local skill, observability |
| architecture/mcp-transport-strategy | stdio (Phase 5.6) → Streamable HTTP (Phase 10), transport evolution |
| project/jira-integration-brainstorm | JIRA instance details, full ticket map (KAN-1 through KAN-29), transition IDs, automation rules |

## Scope Rule
**Global = truly cross-project** (language conventions, generic patterns).
**Project = anything with a file path, port number, or domain concept** from this repo.
When in doubt: project-scoped.

## New Module Checklist
When adding a module in Phase 4B, 5, or 6+:
1. Create `domain/<module-name>.md` covering: purpose, key functions, gotchas, integration points.
2. Add row to this memory-map table.
3. If debugging discoveries arise: append to `debugging/backend-gotchas` or `debugging/frontend-gotchas`.
4. If a pattern is truly project-agnostic: flag with `GLOBAL-CANDIDATE: true` in frontmatter.
5. Promote to `global/` via `/ship` when the PR is ready.
