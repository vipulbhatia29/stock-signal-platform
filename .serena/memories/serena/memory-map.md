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
| global/debugging/mock-patching-gotchas | Patch at lookup site, AsyncMock, decorator stacking |
| global/architecture/system-overview | Full stack, principles, local dev ports |
| global/onboarding/setup-guide | Bootstrap a new machine |

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
