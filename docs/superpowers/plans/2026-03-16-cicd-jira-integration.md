# CI/CD Pipeline + JIRA Integration — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up GitHub Actions CI/CD pipeline with automated quality gates, two-track branching (develop + main), testcontainers fixture split for CI compatibility, and JIRA board configuration for agent-driven orchestration.

**Architecture:** Three GitHub Actions workflows (ci-pr, ci-merge, deploy stub) run as quality gates. The AI agent handles all JIRA transitions via MCP tools. One JIRA Automation rule handles the human-triggered PR merge → Done transition. Testcontainers are guarded behind a `CI` env check; sub-level conftests override `db_url` to read from `DATABASE_URL` env var.

**Tech Stack:** GitHub Actions, pytest, jest, ruff, eslint, tsc, TimescaleDB service containers, JIRA Automation, GitHub for Jira app

**Spec:** `docs/superpowers/specs/2026-03-16-cicd-jira-integration-design.md`

---

## Chunk 1: Test Fixture Split + Local Validation

This chunk modifies the test infrastructure so tests work with both testcontainers (local) and service containers (CI). Must be validated locally before any CI work.

### Task 1: Guard testcontainers in root conftest

**Files:**
- Modify: `tests/conftest.py` (lines 36-62)

- [ ] **Step 1: Add CI guard to `postgres_container` fixture**

Replace the `postgres_container` fixture:

```python
@pytest.fixture(scope="session")
def postgres_container():
    """Start a real Postgres+TimescaleDB container via testcontainers."""
    if os.environ.get("CI"):
        pytest.fail(
            "Testcontainers disabled in CI — using service containers. "
            "Ensure this test directory has a conftest.py that overrides db_url."
        )
    with PostgresContainer(
        image="timescale/timescaledb:latest-pg16",
        username="test",
        password="test",
        dbname="test_stocksignal",
        driver="asyncpg",
    ) as pg:
        yield pg
```

Add `import os` to the top of the file.

- [ ] **Step 2: Add CI guard to `redis_container` fixture**

Replace the `redis_container` fixture:

```python
@pytest.fixture(scope="session")
def redis_container():
    """Start a real Redis container via testcontainers."""
    if os.environ.get("CI"):
        pytest.fail(
            "Testcontainers disabled in CI — using service containers. "
            "Ensure REDIS_URL env var is set."
        )
    with RedisContainer(image="redis:7-alpine") as redis:
        yield redis
```

- [ ] **Step 3: Run tests locally to verify nothing breaks**

Run: `uv run pytest tests/unit/ tests/api/ -v --tb=short -q`
Expected: All tests pass (testcontainers still start because `CI` is not set)

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "fix: guard testcontainers behind CI env check

pytest.fail() ensures loud failure if a test directory lacks its own
conftest.py db_url override in CI, rather than silently skipping.

Ref: KAN-23"
```

### Task 2: Create sub-level conftest for tests/unit/

**Files:**
- Create: `tests/unit/conftest.py`

- [ ] **Step 1: Create the conftest with `db_url` override**

```python
"""Unit test fixtures — overrides root conftest db_url for CI compatibility."""

import os

import pytest


@pytest.fixture(scope="session")
def db_url() -> str:
    """Read DATABASE_URL from environment (CI service container or local .env).

    Overrides root conftest db_url which depends on testcontainers.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            "DATABASE_URL not set. Set it in .env for local dev "
            "or as a CI secret for GitHub Actions."
        )
    return url
```

- [ ] **Step 2: Verify tests still pass locally**

Ensure `DATABASE_URL` is set in your environment (from `.env` or shell):
Run: `uv run pytest tests/unit/ -v --tb=short -q`
Expected: All unit tests pass. The sub-level `db_url` fixture takes precedence — testcontainers should NOT start.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/conftest.py
git commit -m "feat: add tests/unit/conftest.py with db_url override for CI

Sub-level fixture reads DATABASE_URL from env, bypassing testcontainers.
Works with both local Docker Compose and CI service containers.

Ref: KAN-23"
```

### Task 3: Create sub-level conftest for tests/api/

**Files:**
- Create: `tests/api/conftest.py`

- [ ] **Step 1: Create the conftest (same pattern as unit)**

```python
"""API test fixtures — overrides root conftest db_url for CI compatibility."""

import os

import pytest


@pytest.fixture(scope="session")
def db_url() -> str:
    """Read DATABASE_URL from environment (CI service container or local .env).

    Overrides root conftest db_url which depends on testcontainers.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            "DATABASE_URL not set. Set it in .env for local dev "
            "or as a CI secret for GitHub Actions."
        )
    return url
```

- [ ] **Step 2: Verify tests still pass locally**

Run: `uv run pytest tests/api/ -v --tb=short -q`
Expected: All API tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/api/conftest.py
git commit -m "feat: add tests/api/conftest.py with db_url override for CI

Ref: KAN-23"
```

### Task 4: Create sub-level conftest for tests/integration/

**Files:**
- Create: `tests/integration/conftest.py`

- [ ] **Step 1: Create the conftest (same pattern)**

```python
"""Integration test fixtures — overrides root conftest db_url for CI compatibility."""

import os

import pytest


@pytest.fixture(scope="session")
def db_url() -> str:
    """Read DATABASE_URL from environment (CI service container or local .env).

    Overrides root conftest db_url which depends on testcontainers.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            "DATABASE_URL not set. Set it in .env for local dev "
            "or as a CI secret for GitHub Actions."
        )
    return url
```

- [ ] **Step 2: Commit**

```bash
git add tests/integration/conftest.py
git commit -m "feat: add tests/integration/conftest.py with db_url override for CI

Ref: KAN-23"
```

### Task 5: Full local test run validation

- [ ] **Step 1: Run all tests to confirm nothing regressed**

Run: `uv run pytest tests/unit/ tests/api/ -v --tb=short`
Expected: All tests pass. Testcontainers do NOT start (sub-level `db_url` overrides take precedence, reading from `DATABASE_URL` env var).

- [ ] **Step 2: Run ruff to confirm lint is clean**

Run: `uv run ruff check backend/ tests/ scripts/ --no-fix && uv run ruff format backend/ tests/ scripts/ --check`
Expected: No errors.

---

## Chunk 2: Frontend + Lockfile Prep

Small config changes needed before CI workflows can run.

### Task 6: Add "test" script to frontend package.json

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Add test script**

Add to the `"scripts"` section:
```json
"test": "jest"
```

So scripts becomes:
```json
"scripts": {
  "dev": "next dev",
  "build": "next build",
  "start": "next start",
  "lint": "eslint",
  "test": "jest"
}
```

- [ ] **Step 2: Verify frontend tests run**

Run: `cd frontend && npm test -- --passWithNoTests && cd ..`
Expected: Jest runs, tests pass (20 component tests).

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json
git commit -m "feat: add test script to frontend package.json

Enables 'npm test' for CI. Previously only npx jest was available.

Ref: KAN-23"
```

### Task 7: Commit uv.lock

**Files:**
- Modify: `.gitignore` (remove `uv.lock` line)
- Add: `uv.lock` (newly tracked)

- [ ] **Step 1: Remove uv.lock from .gitignore**

Delete the line `uv.lock` from `.gitignore`.

- [ ] **Step 2: Generate fresh lockfile if needed**

Run: `uv lock`
Expected: `uv.lock` file created/updated.

- [ ] **Step 3: Commit**

```bash
git add .gitignore uv.lock
git commit -m "chore: commit uv.lock for reproducible CI builds

Removed from .gitignore. uv.lock is recommended by astral-sh for
reproducible dependency resolution. CI caches based on lockfile hash.

Ref: KAN-23"
```

---

## Chunk 3: GitHub Actions Workflows

The three workflow files. These can be written and committed without GitHub Secrets being set — they just won't run successfully until secrets are configured.

### Task 8: Create ci-pr.yml (PR gate)

**Files:**
- Create: `.github/workflows/ci-pr.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: ci-pr

on:
  pull_request:
    branches: [develop, main]

concurrency:
  group: ci-pr-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock
      - name: Install dependencies
        run: uv sync --frozen
      - name: Ruff check
        run: uv run ruff check backend/ tests/ scripts/ --no-fix
      - name: Ruff format check
        run: uv run ruff format backend/ tests/ scripts/ --check

  frontend-lint:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - name: ESLint
        run: npm run lint
      - name: TypeScript check
        run: npx tsc --noEmit

  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: ${{ secrets.CI_POSTGRES_PASSWORD }}
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock
      - name: Install dependencies
        run: uv sync --frozen
      - name: Run migrations
        env:
          DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
        run: uv run alembic upgrade head
      - name: Run backend tests
        env:
          DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
          REDIS_URL: ${{ secrets.CI_REDIS_URL }}
          JWT_SECRET_KEY: ${{ secrets.CI_JWT_SECRET_KEY }}
          JWT_ALGORITHM: ${{ secrets.CI_JWT_ALGORITHM }}
          CI: "true"
        run: uv run pytest tests/unit/ tests/api/ -v --tb=short

  frontend-test:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - name: Run frontend tests
        run: npm test -- --passWithNoTests
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/ci-pr.yml
git commit -m "ci: add ci-pr.yml — PR quality gate

Runs on PRs to develop and main. Parallel jobs: backend-lint,
frontend-lint, backend-test (with TimescaleDB + Redis service
containers), frontend-test. Target: < 3 minutes.

Ref: KAN-23"
```

### Task 9: Create ci-merge.yml (merge gate)

**Files:**
- Create: `.github/workflows/ci-merge.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
name: ci-merge

on:
  push:
    branches: [develop, main]

concurrency:
  group: ci-merge-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock
      - run: uv sync --frozen
      - run: uv run ruff check backend/ tests/ scripts/ --no-fix
      - run: uv run ruff format backend/ tests/ scripts/ --check
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npx tsc --noEmit

  unit-and-api:
    needs: lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: ${{ secrets.CI_POSTGRES_PASSWORD }}
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock
      - run: uv sync --frozen
      - name: Run migrations
        env:
          DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
        run: uv run alembic upgrade head
      - name: Run backend tests
        env:
          DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
          REDIS_URL: ${{ secrets.CI_REDIS_URL }}
          JWT_SECRET_KEY: ${{ secrets.CI_JWT_SECRET_KEY }}
          JWT_ALGORITHM: ${{ secrets.CI_JWT_ALGORITHM }}
          CI: "true"
        run: uv run pytest tests/unit/ tests/api/ -v --tb=short
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: cd frontend && npm ci
      - name: Run frontend tests
        run: cd frontend && npm test -- --passWithNoTests

  integration:
    needs: unit-and-api
    runs-on: ubuntu-latest
    services:
      postgres:
        image: timescale/timescaledb:latest-pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: ${{ secrets.CI_POSTGRES_PASSWORD }}
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
          cache-dependency-glob: uv.lock
      - run: uv sync --frozen
      - name: Run migrations
        env:
          DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
        run: uv run alembic upgrade head
      - name: Run integration tests
        env:
          DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
          REDIS_URL: ${{ secrets.CI_REDIS_URL }}
          JWT_SECRET_KEY: ${{ secrets.CI_JWT_SECRET_KEY }}
          JWT_ALGORITHM: ${{ secrets.CI_JWT_ALGORITHM }}
          CI: "true"
        # Exit code 5 = no tests collected (tests/integration/ is empty stub)
        run: uv run pytest tests/integration/ -v --tb=short || [ $? -eq 5 ]

  build:
    needs: integration
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - name: Next.js production build
        run: npm run build
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci-merge.yml
git commit -m "ci: add ci-merge.yml — full merge gate

Runs on push to develop and main. Sequential: lint → unit+api →
integration → build. The 'build' job is what main's branch protection
watches. Target: 5-10 minutes.

Ref: KAN-23"
```

### Task 10: Create deploy.yml (stub)

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Create the stub workflow**

```yaml
name: deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        run: |
          echo "TODO Phase 6: wire deployment here"
          echo "Will use: container deployment to cloud provider"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add deploy.yml stub — placeholder for Phase 6

Triggers on push to main. Does nothing yet — establishes the hook
so Phase 6 just fills in the deployment commands.

Ref: KAN-23"
```

---

## Chunk 4: GitHub Configuration (manual steps)

These steps require manual action in GitHub and JIRA web UIs. The agent should guide the PM through them.

### Task 11: Set GitHub Actions Secrets

- [ ] **Step 1: Navigate to repo secrets page**

Go to: `https://github.com/vipulbhatia29/stock-signal-platform/settings/secrets/actions`

- [ ] **Step 2: Add all 5 secrets**

| Secret name | Value |
|---|---|
| `CI_POSTGRES_PASSWORD` | `postgres` |
| `CI_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/test_db` |
| `CI_REDIS_URL` | `redis://localhost:6379` |
| `CI_JWT_SECRET_KEY` | `ci-test-secret-not-real-change-in-prod` |
| `CI_JWT_ALGORITHM` | `HS256` |

### Task 12: Configure branch protection

- [ ] **Step 1: Protect `develop` branch**

Go to: `https://github.com/vipulbhatia29/stock-signal-platform/settings/branches`
Add rule for `develop`:
- Require pull request before merging ✓
- Require status checks: `ci-pr / backend-test`, `ci-pr / frontend-test`
- Allow administrators to bypass ✓

- [ ] **Step 2: Protect `main` branch**

Add/update rule for `main`:
- Require pull request before merging ✓
- Require status checks: `ci-merge / build`
- Require branches to be up to date ✓
- Require linear history ✓
- Do not allow bypassing ✓

### Task 13: Push feature branch and open PR to validate CI

- [ ] **Step 1: Push all commits**

```bash
git push origin feat/KAN-23-cicd-jira
```

- [ ] **Step 2: Open PR to develop**

```bash
gh pr create --base develop --title "[KAN-23] CI/CD pipeline + JIRA integration" --body "$(cat <<'PREOF'
## Summary
- 3 GitHub Actions workflows (ci-pr, ci-merge, deploy stub)
- Testcontainers fixture split for CI compatibility
- uv.lock committed for reproducible builds
- Frontend test script added to package.json

## Test plan
- [ ] ci-pr.yml runs all 4 jobs on this PR
- [ ] All backend tests pass with service containers
- [ ] All frontend tests pass
- [ ] Lint checks pass

Ref: KAN-23

🤖 Generated with [Claude Code](https://claude.com/claude-code)
PREOF
)"
```

- [ ] **Step 3: Verify CI runs**

Run: `gh pr checks` (wait for CI to complete)
Expected: All 4 checks pass (backend-lint, frontend-lint, backend-test, frontend-test)

- [ ] **Step 4: Fix any CI failures**

If any job fails, read the logs with `gh run view` and fix.

---

## Chunk 5: JIRA Board Configuration (manual steps)

### Task 14: Add missing board columns

- [ ] **Step 1: Open JIRA board settings**

Go to: `https://vipulbhatia29.atlassian.net/jira/software/projects/KAN/boards` → Board settings → Columns

- [ ] **Step 2: Add "Blocked" column**

Add between "In Progress" and "Done".

- [ ] **Step 3: Add "Ready for Verification" column**

Add between "Blocked" and "Done".

- [ ] **Step 4: Verify 5 columns exist**

Board should show: To Do → In Progress → Blocked → Ready for Verification → Done

### Task 15: Discover and store new transition IDs

- [ ] **Step 1: Query transitions for a ticket**

Use the Atlassian MCP tool `getTransitionsForJiraIssue` on any ticket (e.g., KAN-28) to discover the new transition IDs for Blocked and Ready for Verification.

- [ ] **Step 2: Update Serena memory**

Update `project/jira-integration-brainstorm` memory with all 5 transition IDs.

### Task 16: Install GitHub for Jira app

- [ ] **Step 1: Install the app**

Go to: Atlassian Marketplace → search "GitHub for Jira" → Install
Connect to your GitHub account and select the `stock-signal-platform` repository.

- [ ] **Step 2: Create JIRA Automation rule**

Go to: JIRA → Project Settings → Automation → Create rule

```
Trigger:     When a pull request is merged (GitHub)
Condition:   PR title contains "KAN-"
Action:      Transition the referenced issue to "Done"
```

### Task 17: Verify end-to-end JIRA automation

- [ ] **Step 1: Merge the CI/CD PR (from Task 13)**

Merge the PR created in Task 13 to `develop`.

- [ ] **Step 2: Verify JIRA transition**

Check that the JIRA Automation rule fired and transitioned KAN-23 (or linked issues) to Done.

---

## Chunk 6: Validation + Cleanup

### Task 18: Verify full pipeline

- [ ] **Step 1: Confirm ci-merge.yml fires on develop push**

After merging the PR to `develop`, verify `ci-merge.yml` triggers.
Run: `gh run list --workflow=ci-merge.yml`

- [ ] **Step 2: Verify all status checks exist**

Run: `gh api repos/vipulbhatia29/stock-signal-platform/branches/develop/protection`
Expected: Status checks configured.

### Task 19: Update Serena memories

- [ ] **Step 1: Update `project/state`**

Update with: CI/CD Epic complete, new branch structure, transition IDs.

- [ ] **Step 2: Update `project/jira-integration-brainstorm`**

Mark CI/CD Epic as complete, record all transition IDs.

### Task 20: Success criteria verification

Go through each item in spec Section 9 (Success Criteria) and verify:

- [ ] `develop` branch exists and is protected
- [ ] `main` branch protection requires `ci-merge / build`
- [ ] PR to `develop` triggers `ci-pr.yml`
- [ ] Merging broken code is blocked
- [ ] Push to `develop` triggers `ci-merge.yml`
- [ ] `develop → main` PR shows `ci-merge / build` check
- [ ] All 5 CI secrets set
- [ ] `uv.lock` committed
- [ ] `package.json` has `"test": "jest"`
- [ ] Testcontainers guarded in CI
- [ ] Sub-level conftests override `db_url`
- [ ] All tests pass in CI
- [ ] JIRA board has 5 columns
- [ ] GitHub for Jira app installed
- [ ] JIRA Automation rule configured
- [ ] Agent can transition tickets with correct IDs
