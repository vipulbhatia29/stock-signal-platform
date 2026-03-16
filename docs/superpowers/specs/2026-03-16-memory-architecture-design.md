# Memory Architecture Design
**Date:** 2026-03-16
**Status:** Approved — ready for implementation
**Approach:** B — Staged (local-first, platform layer deferred until second stockanalysis project)

---

## 1. Problem Statement

The current memory system has five structural failures:

1. **Monolithic memories** — `style_and_conventions.md` is 8,104 bytes mixing Python conventions, TypeScript conventions, React gotchas, Phase 4A design tokens, and portfolio domain rules. Every task loads all of it regardless of relevance.
2. **374-line CLAUDE.md** — always loaded into every session context. Contains reference material that should be on-demand.
3. **No workspace layer** — `~/.claude/CLAUDE.md` does not exist. Three projects on this machine share zero universal rules.
4. **No lifecycle** — no staging area, no promotion pipeline, no staleness audit. Knowledge goes directly to permanent memory with no review. Memories rot silently.
5. **`.serena/` fully gitignored** — project memories exist only on the local machine. Zero multi-developer sharing capability despite memories being committed to the repo intent.

---

## 2. Design Approach: Staged (Option B)

Fix the local system now. Defer the `memory-platform` repo and `global/` memories until a second stockanalysis project is created.

**Trigger for memory-platform creation:** When the first second stockanalysis project starts (e.g., `rag-knowledge-pipeline`, `observability-platform`, or `agentic-ops`). This is a hard requirement — see Section 9.

**Rationale:** The `global/` memory scope in Serena (`~/.serena/memories/global/`) is machine-local by design. With one machine and one project, the only gaps are token efficiency, lifecycle discipline, and shareability via git — all solvable without a platform repo. The platform layer is designed here but deferred until real cross-project usage validates which conventions actually generalize.

---

## 3. Memory Topology: Three Scopes

### Scope 1 — Session (ephemeral, gitignored)

```
.serena/memories/session/
  .gitkeep                     ← directory tracked, contents gitignored
```

- Agents write freely here mid-task — no review, no classification required
- Contents are gitignored (never committed)
- Cleared at end of session by `/ship` command
- Lifetime: current session only

### Scope 2 — Project (committed, repo-specific)

```
.serena/memories/
  project/
    state.md                   ← branch, phase, test count, resume point (CI-writable)
    stack.md                   ← ports, entry points, package manager (rarely changes)
  domain/
    signals-and-screener.md    ← RSI/MACD/Piotroski, composite scoring, Prophet
    portfolio-tracker.md       ← FIFO, positions, transactions, rebalancing gotchas
    agent-tools.md             ← LangChain/LangGraph, tool registry, streaming
  architecture/
    timescaledb-patterns.md    ← hypertable upsert, PK constraints, Alembic gotchas
    frontend-design-system.md  ← Phase 4A tokens, Sparkline, ChatPanel, layout vars
  conventions/
    auth-patterns.md           ← JWT cookie, bcrypt pin, rate limiter gotchas
  debugging/
    backend-gotchas.md         ← bcrypt, asyncpg, enum, lazy imports, circular deps
    frontend-gotchas.md        ← Recharts, setState, base-ui v4, localStorage
  serena/
    tool-usage.md              ← Serena MCP prefix, activate_project, tool mapping
```

- Committed to git — shareable with all developers who clone the repo
- Domain-specific knowledge only (nothing that generalises across projects)
- `project/state.md` is the one machine-written memory — CI updates it after every green run
- Global/ candidates flagged in memory frontmatter, promoted when `memory-platform` is created

### Scope 3 — Global (machine-wide, Serena-native)

```
~/.serena/memories/global/
  conventions/
    python-style.md            ← accessed as global/conventions/python-style
    typescript-style.md
    testing-patterns.md
    git-workflow.md
    error-handling.md
  architecture/
    system-overview.md
    api-versioning.md
    security-standards.md
  debugging/
    mock-patching-gotchas.md
  onboarding/
    setup-guide.md
```

- Serena resolves `global/` prefix natively — no symlinks, no cross-repo dependencies
- Written once manually during Phase 0 implementation
- Accessible from all projects on the machine transparently
- Source of truth migrated to `memory-platform` repo at cloud deployment trigger (Section 9)

---

## 4. CLAUDE.md Transformation

### Project CLAUDE.md: 374 lines → ~60 lines

Transform from reference manual to routing manifest. Every piece of knowledge that doesn't need to be in every session context moves to a named Serena memory.

**Structure:**
```markdown
# stock-signal-platform
Fullstack stock analysis platform. See PROJECT_INDEX.md for full repo map.

## Services
| Service  | Port | Entry point       |
|----------|------|-------------------|
| Backend  | 8181 | backend/main.py   |
| Frontend | 3000 | frontend/app/     |
| Postgres | 5433 | docker compose    |
| Redis    | 6380 | docker compose    |

## Hard Rules (non-negotiable — 8 rules maximum)
1. uv run prefix on all Python — never bare python or pip
2. No bare except: — always except Exception or specific type
3. No print() in backend — use logging.getLogger(__name__)
4. X | None not Optional[X] (PEP 604)
5. All API calls through lib/api.ts — never raw fetch()
6. Never commit to main/develop directly — everything through PR
7. ruff check --fix && ruff format before every commit
8. Every public function has a unit test — no exceptions

## Memory Map
| Topic                  | Read this memory                        |
|------------------------|-----------------------------------------|
| Python conventions     | global/conventions/python-style         |
| TS/React conventions   | global/conventions/typescript-style     |
| Testing patterns       | global/conventions/testing-patterns     |
| Git workflow           | global/conventions/git-workflow         |
| Mock patching          | global/debugging/mock-patching-gotchas  |
| Project state          | project/state                           |
| Commands & ports       | project/stack                           |
| Backend gotchas        | debugging/backend-gotchas               |
| Frontend gotchas       | debugging/frontend-gotchas              |
| Signals domain         | domain/signals-and-screener             |
| Portfolio domain       | domain/portfolio-tracker                |
| Agent tools domain     | domain/agent-tools                      |
| Design system          | architecture/frontend-design-system     |
| TimescaleDB patterns   | architecture/timescaledb-patterns       |
| Auth patterns          | conventions/auth-patterns               |
| Serena tool usage      | serena/tool-usage                       |

## Session Start
1. Read PROJECT_INDEX.md
2. read_memory("project/state")
3. git status && git log --oneline -5
4. uv run pytest tests/unit/ -v
```

### Workspace CLAUDE.md: new file at `~/.claude/CLAUDE.md`

Universal rules that apply across all projects on this machine regardless of domain:

```markdown
# Workspace Rules

Applies to all projects. Project CLAUDE.md adds project-specific rules on top.

## Universal Hard Rules
1. Never commit .env files, API keys, or secrets — ever
2. Conventional commits: feat/fix/chore/docs/test/refactor prefixes always
3. uv over pip for all Python projects
4. No direct commits to main or develop — everything through PR
5. Run tests before creating any PR

## Workspace Layout
- ~/Documents/projects/stockanalysis/ — stockanalysis domain projects
- Shared conventions: global/conventions/* (Serena global memories)
- Platform repo: deferred — create when second stockanalysis project starts

## Tool Preferences
- Serena symbolic tools over Read/Grep/Edit for code exploration
- gh CLI for all GitHub operations
- docker compose for local infrastructure
```

---

## 5. The `/ship` Command

A new project-level slash command at `.claude/commands/ship.md`. Distinct name from the plugin's `/commit-push-pr` to avoid the same-name picker collision in Claude Code. `/ship` is the full workflow including memory promotion; `/commit-push-pr` remains available for simple commits.

**Workflow:**
```
Step 0 — Session memory scan
  List .serena/memories/session/ contents
  If empty → skip to Step 2 (zero overhead)
  If non-empty → for each session memory:
    a. Read content
    b. Classify scope: project/ vs global/ candidate
       - Contains domain concepts (stock, portfolio, ticker)? → project/
       - Generic pattern true for any Python/TS project? → global/ candidate
    c. Classify category: conventions / architecture / debugging / domain
    d. Identify target memory file (append vs new)
    e. Present recommendation with 2-sentence reasoning
    f. On developer approval: write to target memory file
       - global/ candidates: note in PR description as follow-up item
       - project/ items: written and staged immediately
    g. Clear session/ file after promotion

Step 1 — Stage changes
  git add (includes promoted memory files + code changes)

Step 2 — Commit
  Conventional commit message
  Memory promotions committed in same commit as code that produced them

Step 3 — Push
  git push -u origin <branch>

Step 4 — PR creation
  gh pr create with:
  - Standard PR body (summary + test plan)
  - If global/ candidates exist: append section
    "⚠️ Memory promotion pending: X global/ candidates identified.
     Open memory-platform PR after this merges: [list]"

Step 5 — Clear session/
  Use mcp__plugin_serena_serena__delete_memory for each session/* memory
  (iterate list_memories() filtered to "session/" topic)
  Do NOT use shell rm — avoids deleting .gitkeep which must remain tracked
```

**Required permission additions to `.claude/settings.json`:**
```json
"Bash(gh *)"
```
Note: session/ cleanup uses Serena's `delete_memory` tool, not shell `rm`, so no additional Bash permission is needed for that step.

---

## 6. The `/check-stale-memories` Command

New project-level slash command at `.claude/commands/check-stale-memories.md`.

**When to run:** Start of each phase, before any major refactor, or on demand.

**Workflow:**
```
Step 1 — List all project memories
  mcp__plugin_serena_serena__list_memories()

Step 2 — For each memory, validate:
  a. File paths mentioned → Glob to verify existence
  b. Symbol names mentioned → find_symbol() to verify existence
  c. Described behaviour → read symbol body → verify accuracy
  d. Frontmatter global/ candidate flags → surface for promotion decision

Step 3 — Produce status table:
  | Memory                          | Status           | Issues              |
  |---------------------------------|------------------|---------------------|
  | project/state                   | OK               | —                   |
  | debugging/backend-gotchas       | STALE            | `_ticker_linker.py` renamed |
  | domain/portfolio-tracker        | GLOBAL-CANDIDATE | No domain dependency found |

Step 4 — For each non-OK entry:
  STALE          → propose corrected content, ask approval, write fix
  GLOBAL-CANDIDATE → ask "ready to promote? open memory-platform PR?"
  REMOVE         → ask confirmation, delete memory

Step 5 — Commit all fixes
  Branch: docs/fix-stale-memories-<date>
  PR against develop
```

---

## 7. Memory Lifecycle: Four Flows

### Flow 1 — Discovery (Agent → Session)
- **Trigger:** Agent discovers pattern, gotcha, or decision mid-task
- **Writer:** Implementation Agent (free write, no classification required)
- **Destination:** `session/` — gitignored, never committed
- **Lifetime:** Current session only

### Flow 2 — Promotion (Session → Project or Global candidate)
- **Trigger:** Developer runs `/ship` at PR creation time — automatic, not a separate ceremony
- **Classifier:** Agent autonomously classifies scope and category, presents recommendation
- **Classification logic:**
  - Contains stock/portfolio/ticker domain concepts → project/
  - Generic Python/TS/testing pattern → global/ candidate
  - Already exists in global/ → recommend appending
  - Ambiguous → default to project/, flag frontmatter as `global-candidate: true`
- **Developer role:** Approve or override the agent's recommendation
- **Destination:** project/ memory files committed in same PR as code

### Flow 3 — Graduation (Project → Global)
- **Trigger:** Second stockanalysis project creation (hard trigger, see Section 9)
- **Writer:** Developer deliberate act via PR against `memory-platform`
- **Review:** CODEOWNERS by category (architects for architecture/, platform team for conventions/, team leads for debugging/)
- **Destination:** `~/.serena/memories/global/` on all machines via `sync-global-memories.sh`

### Flow 4 — Staleness Audit
- **Trigger:** Phase start, pre-major-refactor, or on demand
- **Runner:** Developer via `/check-stale-memories`
- **Output:** OK / STALE / GLOBAL-CANDIDATE / REMOVE status table
- **Action:** Fixes committed on `docs/fix-stale-memories-<date>` branch

---

## 8. .gitignore Fix

**Current state:** `.serena/` is entirely gitignored — project memories are invisible to git.

**Required change:** Replace `.serena/` with surgical ignores:

```gitignore
# Serena — commit project memories, ignore cache and ephemeral session
.serena/cache/
.serena/memories/session/*
!.serena/memories/session/.gitkeep
.serena/project.local.yml
```

The `*` + negation pattern correctly ignores all session memory content while tracking `.gitkeep` so the directory exists on clone. A trailing-slash pattern (`.serena/memories/session/`) would ignore the directory entirely including `.gitkeep`, making the directory absent for developers who clone fresh.

This makes `.serena/memories/` (except `session/` contents) and `.serena/project.yml` committed and shareable. `project.local.yml` (machine-specific language server settings) remains ignored.

---

## 9. Cloud Deployment Trigger: memory-platform Creation

**This is a hard requirement. Do not skip at cloud deployment time.**

When the first second stockanalysis project is created (rag-knowledge-pipeline, observability-platform, agentic-ops, or any other), **before starting that project**, execute:

1. Create `memory-platform` repo in the stockanalysis GitHub org
2. Migrate all `~/.serena/memories/global/` files into `memory-platform/memories/global/` as markdown source
3. Write `scripts/sync-global-memories.sh` — clones repo, writes all files to `~/.serena/memories/global/`
4. Add `CODEOWNERS` with category-weighted approval rules. Replace team handles with actual GitHub username (`@vipulbhatia29`) until GitHub organization teams are created:
   ```
   memories/global/architecture/    @vipulbhatia29    # 2 approvals when teams exist
   memories/global/conventions/     @vipulbhatia29    # 1 approval
   memories/global/debugging/       @vipulbhatia29    # 1 approval, fast
   ```
5. Create `docs/runbooks/new-machine-onboarding.md` with:
   - Install prerequisites (uv, docker, gh CLI, node)
   - Clone all stockanalysis repos
   - Run `sync-global-memories.sh` — **required before first Claude Code session**
   - Run `uv sync` in each Python repo
   - Run `npm install` in each frontend
   - Configure `backend/.env` from `.env.example`
6. Add `sync-global-memories.sh` to CI worker spin-up step for all stockanalysis repos
7. Verify Section 7, Flow 3 (Graduation) in this doc still correctly describes the `memory-platform` PR workflow — no edit needed unless the doc was rolled back

---

## 10. CI Integration: `project/state.md`

CI writes `project/state.md` after every successful test run on the `develop` branch only (not on feature branches — the branch name would be stale by the time an agent reads it on develop). This is the only machine-written project memory.

**Format:**
```markdown
# Project State

- Phase: <current-phase>
- Alembic head: <migration-id>
- Tests: <backend-unit> unit + <backend-api> API + <frontend> frontend
- Resume: <one-line resume point>
- Last CI: <date> (all passing)
```

Note: No `Branch:` field — CI runs on develop merges only, so the branch is always `develop`. Agents get current branch from `git status` (Session Start step 3), not from this file.

Agents read `project/state.md` at session start instead of parsing `PROGRESS.md` in full. `PROGRESS.md` remains the human narrative log.

---

## 11. Migration Path from Current State

The 5 existing monolithic memories must be split into the new atomic structure during implementation:

| Current memory            | Migrates to                                                                 |
|---------------------------|-----------------------------------------------------------------------------|
| `project_overview.md`     | `project/state.md` + `project/stack.md` + `global/architecture/system-overview` |
| `style_and_conventions.md`| `debugging/backend-gotchas.md` + `debugging/frontend-gotchas.md` + `conventions/auth-patterns.md` + `architecture/frontend-design-system.md` + `architecture/timescaledb-patterns.md` + global/conventions/python-style + global/conventions/typescript-style + global/conventions/testing-patterns + global/conventions/git-workflow + global/conventions/error-handling |
| `suggested_commands.md`   | `project/stack.md`                                                          |
| `task_completion_checklist.md` | global/conventions/testing-patterns (append checklist section)         |
| `tool_usage_rules.md`     | `serena/tool-usage.md`                                                      |

**Note on `domain/agent-tools.md`:** This file has no migration source in the existing 5 memories. Its content (LangChain/LangGraph patterns, tool registry design, NDJSON streaming) currently lives in the Tech Stack section of `CLAUDE.md` and session notes in `PROGRESS.md`. Draft it fresh from those sources during implementation — do not search for an existing Serena memory to migrate from.

Original 5 files deleted after migration is verified.

---

## 12. Out of Scope (Deferred to memory-platform phase)

- `memory-platform` repo creation
- `sync-global-memories.sh` script
- CODEOWNERS for global memories
- CI global memory sync on worker spin-up
- `/promote-memory` as standalone command (subsumed into `/ship`)
- Multi-developer CODEOWNERS for project memories
