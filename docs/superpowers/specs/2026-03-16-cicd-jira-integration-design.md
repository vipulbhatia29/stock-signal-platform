# CI/CD Pipeline + JIRA Integration Design

**Date:** 2026-03-16
**Branch:** `feat/KAN-23-cicd-jira`
**Epic:** KAN-22
**Status:** Draft — pending review
**Supersedes:** `2026-03-15-cicd-branching-design.md` (which remains as reference but this spec is authoritative)

---

## 1. Overview

This spec covers the complete CI/CD pipeline and its integration with the JIRA-based agentic SDLC workflow. It combines three concerns:

1. **GitHub Actions CI/CD** — automated quality gates on every PR and merge
2. **Git branching strategy** — two-track protected branches (develop + main)
3. **JIRA integration** — agent-driven ticket management with one automation rule for human-triggered events

### Design Principles

- **Agent-driven orchestration** — the AI agent updates JIRA directly; CI is a quality gate only, never touches JIRA
- **CI stays pure** — workflows validate code quality, nothing else
- **Human gates at PR merge** — the one action that isn't automated
- **One JIRA Automation rule** — PR merged → transition linked issues to Done (handles human-triggered events)

---

## 2. Git Branching Strategy

### 2.1 Branch Model

```
main        ← production-ready at all times, protected
develop     ← integration branch, accumulates Story PRs, protected
feat/*      ← Story-level branches (one per JIRA Story)
hotfix/*    ← emergency fixes, branched from main
```

### 2.2 Naming Conventions (mandatory)

| What | Pattern | Example |
|------|---------|---------|
| Story branch | `feat/KAN-[story#]-[kebab-name]` | `feat/KAN-3-tool-orchestration` |
| Hotfix branch | `hotfix/KAN-[bug#]-[kebab-name]` | `hotfix/KAN-42-fix-auth-crash` |
| PR title | `[KAN-X] Summary of changes` | `[KAN-3] Tool orchestration — BaseAgent, ToolRegistry, agentic loop` |
| Commit message | Conventional commits, KAN ref in body | `feat: add BaseAgent ABC\n\nRef: KAN-7` |

### 2.3 Normal Feature Flow

```
feat/KAN-3-tool-orchestration
  └─ PR → develop   [CI: ci-pr.yml — lint + unit + API + Jest]
          merge ↓
       develop
          └─ PR → main   [CI: ci-merge.yml — all above + integration + build]
                  merge ↓
               main
                  └─ deploy.yml trigger (stub until Phase 6)
```

### 2.4 Hotfix Flow

```
main
  └─ hotfix/KAN-42-fix-auth-crash
       └─ PR → main       [CI: ci-pr.yml runs]
               merge ↓
            main  ← fix is live
       also └─ PR → develop  [separate PR: back-merge to keep develop in sync]
```

### 2.5 Branch Protection Rules

**`main` (strict):**
- Require pull request before merging ✓
- Require status checks to pass: `ci-merge / build` ✓
- Require branches to be up to date ✓
- Require linear history (no merge commits) ✓
- Do not allow bypassing ✓

**`develop` (standard):**
- Require pull request before merging ✓
- Require status checks: `ci-pr / backend-test`, `ci-pr / frontend-test` ✓
- Allow administrators to bypass ✓ (emergency escape hatch)

---

## 3. GitHub Actions Workflows

Three workflow files under `.github/workflows/`. **No JIRA logic in any workflow** — CI is a pure quality gate.

### 3.1 `ci-pr.yml` — PR Gate (fast)

**Trigger:** `pull_request` with `branches: [develop, main]`
**Target runtime:** < 3 minutes
**Purpose:** Fast feedback on every PR. Must pass before merge is allowed.

**Jobs (run in parallel):**

```yaml
backend-lint:
  steps:
    - uv run ruff check backend/ tests/ scripts/ --no-fix
    - uv run ruff format backend/ tests/ scripts/ --check

frontend-lint:
  steps:
    - npm run lint
    - npx tsc --noEmit

backend-test:
  services:
    postgres: timescale/timescaledb:latest-pg16 (port 5432)
    redis: redis:7-alpine (port 6379)
  env:
    DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
    REDIS_URL: ${{ secrets.CI_REDIS_URL }}
    JWT_SECRET_KEY: ${{ secrets.CI_JWT_SECRET_KEY }}
    JWT_ALGORITHM: ${{ secrets.CI_JWT_ALGORITHM }}
    CI: true
  steps:
    - uv run alembic upgrade head
    - uv run pytest tests/unit/ tests/api/ -v --tb=short

frontend-test:
  steps:
    - npm ci
    - npx jest --passWithNoTests
```

### 3.2 `ci-merge.yml` — Merge Gate (full)

**Trigger:** `push` to `develop`
**Target runtime:** 5-10 minutes
**Purpose:** Full confidence check before develop → main promotion.

**Jobs (sequential — each depends on previous):**

```yaml
lint:           (same as ci-pr.yml backend-lint + frontend-lint)

unit-and-api:   (same as ci-pr.yml backend-test + frontend-test)

integration:
  services: postgres + redis
  env:
    DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
    REDIS_URL: ${{ secrets.CI_REDIS_URL }}
    JWT_SECRET_KEY: ${{ secrets.CI_JWT_SECRET_KEY }}
    JWT_ALGORITHM: ${{ secrets.CI_JWT_ALGORITHM }}
    CI: true
    TEST_ENV: integration
  steps:
    - uv run alembic upgrade head
    - uv run pytest tests/integration/ -v --tb=short || [ $? -eq 5 ]
  note: tests/integration/ currently has only __init__.py. Exit code 5
        (no tests collected) is treated as success. Real integration tests
        added in future phases.

build:
  steps:
    - npm ci
    - npm run build
```

**Status check for branch protection:** `ci-merge / build` is what `main`'s branch protection watches. If `build` is green, all upstream jobs passed (sequential dependency).

### 3.3 `deploy.yml` — Deployment Stub

**Trigger:** `push` to `main`
**Purpose:** Establishes the hook for Phase 6.

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        run: |
          echo "TODO Phase 6: wire deployment here"
```

---

## 4. CI Environment & Secrets

### 4.1 GitHub Actions Secrets

Stored in GitHub → repo Settings → Secrets and variables → Actions.

| Secret name | Value | Used by |
|---|---|---|
| `CI_POSTGRES_PASSWORD` | `postgres` | Service container config |
| `CI_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/test_db` | pytest + Alembic |
| `CI_REDIS_URL` | `redis://localhost:6379` | pytest / backend |
| `CI_JWT_SECRET_KEY` | `ci-test-secret-not-real-change-in-prod` | pytest / auth tests |
| `CI_JWT_ALGORITHM` | `HS256` | pytest / auth tests |

These are throwaway CI-only values — not real credentials.

### 4.2 `uv` Caching in CI

`uv.lock` must be committed (currently gitignored). Remove from `.gitignore` and commit.

```yaml
- name: Cache uv packages
  uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ hashFiles('uv.lock') }}
    restore-keys: uv-
```

npm caching:
```yaml
- name: Cache npm
  uses: actions/cache@v4
  with:
    path: frontend/node_modules
    key: npm-${{ hashFiles('frontend/package-lock.json') }}
```

---

## 5. Testcontainers Fixture Split

### 5.1 Problem

The current `tests/conftest.py` starts Docker containers via testcontainers at session scope. This works locally but fails in GitHub Actions (Docker-in-Docker overhead, privileged mode required).

### 5.2 Solution: Environment-based fixture override

**Root conftest — guard testcontainers:**

```python
# tests/conftest.py
@pytest.fixture(scope="session")
def postgres_container():
    if os.environ.get("CI"):
        pytest.skip("Testcontainers disabled in CI — using service containers")
    # ... existing testcontainers startup code ...
```

**Sub-level conftests — override db_url:**

```python
# tests/unit/conftest.py (NEW)
# tests/api/conftest.py (NEW)
# tests/integration/conftest.py (NEW)

@pytest.fixture(scope="session")
def db_url():
    """Override root conftest — use DATABASE_URL env var."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail("DATABASE_URL not set — check .env or CI config")
    return url
```

### 5.3 Resolution Across Environments

| Environment | DATABASE_URL source | Testcontainers? |
|-------------|-------------------|-----------------|
| Local dev | `.env` → `postgresql+asyncpg://...localhost:5433/...` | No (Docker Compose) |
| CI (GitHub Actions) | Secret → `postgresql+asyncpg://...localhost:5432/...` | No (service container) |

### 5.4 Key Constraint

The existing `_setup_database` autouse fixture depends on `db_url`. Sub-level conftest overrides take precedence in pytest's fixture resolution — so no test files need to change. Only conftest files are modified.

---

## 6. Mandatory Test Categories

### 6.1 CI Gate Requirements

| Category | Path | Runner | Gate |
|----------|------|--------|------|
| Unit tests | `tests/unit/` | `pytest` | ci-pr.yml |
| API tests | `tests/api/` | `pytest` | ci-pr.yml |
| Integration tests | `tests/integration/` | `pytest` | ci-merge.yml |
| Frontend tests | `frontend/src/__tests__/` | `jest` | ci-pr.yml |
| Backend lint | `backend/`, `tests/`, `scripts/` | `ruff` | ci-pr.yml |
| Frontend lint | `frontend/src/` | `eslint` + `tsc` | ci-pr.yml |
| Production build | `frontend/` | `npm run build` | ci-merge.yml |

### 6.2 Test Coverage Expectations (per subtask, enforced by code review)

| Code type | Required tests |
|-----------|---------------|
| New DB model | Unit test for creation, relationships, constraints |
| New endpoint | 3 minimum: auth (401), happy path (200/201), error (400/404/422) |
| New service function | Unit test per public function, edge cases |
| New frontend component | Render test + key interaction test |
| Bug fix | Regression test that fails without fix, passes with it |

Agent verifies these before moving any subtask to Ready for Verification.

---

## 7. JIRA Integration

### 7.1 Agent-Driven Model

The AI agent is the orchestrator. It updates JIRA directly via MCP tools. CI never touches JIRA.

**Agent session protocol:**
1. Query board: `project = KAN AND status != Done ORDER BY rank ASC`
2. Reconcile: check if any "Ready for Verification" tickets have merged PRs → transition to Done
3. Pick next unblocked subtask → present to PM for approval

**Per-subtask flow:**
1. Transition subtask → In Progress
2. Add comment: approach summary
3. Implement on Story branch
4. Run tests locally → green
5. Transition subtask → Ready for Verification
6. Add structured comment (branch, files, tests, results)
7. When all subtasks in Story are Ready → open PR to develop
8. CI runs → green badge
9. Human reviews → merge or reject

### 7.2 JIRA Automation Rule (single rule)

Handles the human-triggered event (PR merge) that the agent can't observe in real-time.

```
Trigger:     When a pull request is merged (GitHub)
Condition:   PR title contains "KAN-"
Action:      Transition linked issues to "Done"
```

Requires: **GitHub for Jira** app installed on Atlassian site.

### 7.3 Epic Completion Flow

1. Agent detects all Stories in Epic are Done (all merged to develop)
2. Agent opens PR: `develop → main` with release summary
3. Human reviews and merges
4. ci-merge.yml full gate runs
5. deploy.yml fires (stub)
6. Agent transitions Epic → Done

### 7.4 Board Configuration

**5-column board:**
```
To Do → In Progress → Blocked → Ready for Verification → Done
```

"Blocked" and "Ready for Verification" must be added via JIRA project settings → Board → Columns before implementation begins. Transition IDs to be discovered and stored in memory after configuration.

### 7.5 GitHub for Jira App

Must be installed from Atlassian Marketplace (free) and connected to the `stock-signal-platform` repository. Enables:
- Smart commits (KAN references in commit messages)
- PR references visible in JIRA issue dev panel
- The automation trigger for PR merged events

---

## 8. File Structure

```
.github/
  workflows/
    ci-pr.yml           ← PR gate: lint + unit + API + Jest (~3 min)
    ci-merge.yml        ← merge gate: full suite + build (~8 min)
    deploy.yml          ← deploy stub (no-op until Phase 6)

tests/
  conftest.py           ← MODIFIED: guard testcontainers behind CI check
  unit/
    conftest.py         ← NEW: db_url override for CI
  api/
    conftest.py         ← NEW: db_url override for CI
  integration/
    conftest.py         ← NEW: db_url override for CI

frontend/
  package.json          ← MODIFIED: add "test": "jest" script

.gitignore              ← MODIFIED: remove uv.lock
uv.lock                 ← NEWLY COMMITTED
```

---

## 9. Success Criteria

- [ ] `develop` branch exists and is protected
- [ ] `main` branch protection updated to require `ci-merge / build`
- [ ] Opening a PR to `develop` triggers `ci-pr.yml` with ✅/❌ status checks
- [ ] Merging broken code to `develop` is blocked by branch protection
- [ ] Push to `develop` triggers `ci-merge.yml` full gate
- [ ] `develop → main` PR shows `ci-merge / build` status check
- [ ] All 5 CI secrets set in GitHub Actions Secrets
- [ ] `uv.lock` committed and removed from `.gitignore`
- [ ] `package.json` has `"test": "jest"` script
- [ ] Testcontainers fixture guarded — CI uses service containers
- [ ] `tests/unit/conftest.py`, `tests/api/conftest.py`, `tests/integration/conftest.py` override `db_url`
- [ ] All 267 backend + 20 frontend tests pass in CI
- [ ] JIRA board has 5 columns (To Do, In Progress, Blocked, Ready for Verification, Done)
- [ ] GitHub for Jira app installed and connected to repository
- [ ] JIRA Automation rule: PR merged → transition to Done
- [ ] Agent can transition tickets via MCP tools with correct transition IDs
- [ ] Hotfix back-merge process documented (PR hotfix/* → develop)

---

## 10. Out of Scope

- Docker image building and pushing (Phase 6)
- Deployment wiring — Azure, AWS, etc. (Phase 6)
- E2E / Playwright tests in CI (Phase 6+)
- Slack/email notifications on CI failure (Phase 6)
- Dependabot / automated dependency updates (Phase 6)
- FSD/TDD/CLAUDE.md doc catch-up (KAN-29, next session)
- Multiple JIRA automation rules — keep it to one
- JIRA API token for headless CI auth (future, when OAuth isn't sufficient)
