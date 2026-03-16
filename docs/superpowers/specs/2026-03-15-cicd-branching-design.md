# CI/CD + Branching Strategy Design

**Date:** 2026-03-15
**Branch:** `feat/phase-4b-ai-chatbot`
**Status:** Draft — pending implementation

---

## 1. Overview

This spec covers two things in one implementation:

1. **CI/CD pipeline** — GitHub Actions workflows that automatically run lint, type checks,
   tests, and builds on every PR and every merge. Prevents broken code from reaching `main`.

2. **Branching strategy** — Two long-lived protected branches (`develop` + `main`) that map
   directly to the Phase 6 deployment environments (staging + production).

Additionally, this spec includes **documentation catch-up tasks** for Phase 4A UI changes
(already shipped) that were not reflected in FSD, TDD, or CLAUDE.md.

---

## 2. Branching Strategy

### 2.1 Branch Model

Two long-lived branches. Both are protected — nothing merges directly, everything goes
through a PR.

```
main        ← production-ready at all times
develop     ← staging; integration-tested before promoting to main

feat/*      ← daily feature work (current pattern, unchanged)
hotfix/*    ← emergency fixes only, branched from main
```

### 2.2 Normal Feature Flow

```
feat/my-feature
  └─ PR → develop   [CI: fast gate runs — lint + unit + API tests + Jest]
          merge ↓
       develop
          └─ PR → main   [CI: full gate runs — all of above + integration + build]
                  merge ↓
               main
                  └─ deploy.yml trigger (stub now; wired in Phase 6)
```

### 2.3 Hotfix Flow

For urgent production fixes that cannot wait for the develop cycle:

```
main
  └─ hotfix/critical-fix branch
       └─ PR → main       [CI: full gate runs — ci-pr with branches: [main]]
               merge ↓
            main  ← fix is live
       also └─ PR → develop  [separate PR: hotfix/* → develop]
                    CI runs → merge  ← keep develop in sync with main
```

The back-merge to `develop` is a separate PR opened immediately after the `main` merge.
`develop` branch protection requires a PR — you cannot push directly. Open
`hotfix/* → develop` (or `main → develop`) as soon as the production fix lands.

### 2.4 Branch Protection Rules

**`main` (strict):**
- Require pull request before merging ✓
- Require status checks to pass before merging: `ci-merge / build` ✓
- Require branches to be up to date before merging ✓
- Require linear history ✓ (no merge commits — keeps `git log` clean)
- Do not allow bypassing the above settings ✓

**`develop` (standard):**
- Require pull request before merging ✓
- Require status checks to pass: `ci-pr / backend-test`, `ci-pr / frontend-test` ✓
- Allow administrators to bypass ✓ (escape hatch for emergencies)

### 2.5 Day-to-Day Workflow (what changes for you)

Previously: `feat/* → PR → main`
Now: `feat/* → PR → develop → PR → main`

The extra PR (`develop → main`) takes 30 seconds to open and only happens when you've
accumulated a batch of features you're confident in. Think of it as your "shipping" moment.
The CI gate does the verification work — you just click merge.

---

## 3. GitHub Actions Workflows

Three workflow files under `.github/workflows/`:

### 3.1 `ci-pr.yml` — PR gate (fast)

**Trigger:** `pull_request` with `branches: [develop, main]` — covers both normal feature PRs to `develop` and emergency hotfix PRs directly to `main`
**Target runtime:** < 3 minutes
**Purpose:** Fast feedback while actively developing. Must complete before you can merge.

**Jobs (run in parallel):**

```yaml
backend-lint:
  - uv run ruff check backend/ tests/ scripts/ --no-fix  (fail on any error)
  - uv run ruff format backend/ tests/ scripts/ --check  (fail if not formatted)

frontend-lint:
  - npm run lint              (ESLint zero errors)
  - npx tsc --noEmit          (TypeScript strict mode, zero type errors)

backend-test:
  services:
    postgres: timescale/timescaledb:latest-pg16 (port 5432)
    redis:    redis:7-alpine (port 6379)
  steps:
    - uv run alembic upgrade head    (run migrations against CI DB)
    - uv run pytest tests/unit/ tests/api/ -v --tb=short

frontend-test:
  - npm ci
  - npx jest --passWithNoTests        # note: add "test": "jest" to package.json scripts
  - npm run lint -- src/              # note: lint script needs explicit path target
```

**Why service containers instead of testcontainers here:**
testcontainers spins up Docker-in-Docker inside GitHub Actions, which adds 60-90 seconds
of overhead and requires privileged mode. GitHub's native service containers start
alongside the job in ~10 seconds. For CI speed, service containers win.
testcontainers remain correct for local `tests/integration/` runs.

**Testcontainers fixture conflict — IMPORTANT:**
The existing `tests/conftest.py` defines a session-scoped `postgres_container` fixture
that starts a real Docker container via testcontainers. This conftest is shared across
`tests/unit/` and `tests/api/`. If CI simply runs `pytest tests/unit/ tests/api/`, pytest
will collect and fire this fixture, attempt Docker-in-Docker, and fail.

**Resolution:** Add a `tests/ci_conftest.py` override pattern — specifically, add
`tests/unit/conftest.py` and `tests/api/conftest.py` that provide the `async_db_session`
and `client` fixtures pointing at the service container URLs (via `DATABASE_URL` env var)
instead of launching testcontainers. The session-level `postgres_container` fixture in the
root `tests/conftest.py` should be guarded with a `pytest.mark.integration` skip when not
in integration mode. Concretely:
- Add `pytestmark` or fixture guard in root conftest: only start containers when
  `TEST_ENV=integration` env var is set
- CI `ci-pr.yml` does NOT set `TEST_ENV=integration` → testcontainers never start
- CI `ci-merge.yml` integration job DOES set `TEST_ENV=integration` → testcontainers start
  OR the integration job also uses service containers consistently

The implementation plan must specify this fixture split explicitly.

### 3.2 `ci-merge.yml` — merge gate (full)

**Trigger:** `push` to `develop` (fires after a PR merges)
**Target runtime:** 5-10 minutes
**Purpose:** Full confidence check before `develop → main` promotion is allowed.

**Jobs (sequential — each depends on previous):**

```yaml
lint:          (same as ci-pr.yml backend-lint + frontend-lint)
unit-and-api:  (same as ci-pr.yml backend-test + frontend-test)
integration:
  services: postgres + redis (same as above)
  env:
    TEST_ENV: integration      # signals "integration mode" — NOT a trigger to launch
                               # testcontainers. All DB access uses service containers
                               # via DATABASE_URL env var throughout CI (both PR and merge
                               # gates). testcontainers are for local runs only.
                               # The db_url fixture in tests/integration/ must read from
                               # DATABASE_URL env var, not launch a container.
  steps:
    - uv run alembic upgrade head
    - uv run pytest tests/integration/ -v --tb=short || [ $? -eq 5 ]
  note: tests/integration/ currently has only __init__.py — pytest exits code 5 (no tests
        collected). The `|| [ $? -eq 5 ]` idiom treats "no tests found" as success so the
        job passes. This job is a stub; add real integration tests here in future phases.

**Fixture architecture for CI (applies to ALL three jobs):**
- `tests/unit/conftest.py` and `tests/api/conftest.py` override `db_url` to read from
  `DATABASE_URL` env var (points at service container) — no Docker started
- `tests/integration/conftest.py` does the same — no Docker started in CI
- Root `tests/conftest.py` `postgres_container` fixture is guarded:
  `if os.environ.get("TEST_ENV") == "local_docker": start container else: skip`
- The `_setup_database` autouse fixture depends on `db_url` — the sub-level conftest
  overrides of `db_url` take precedence over root conftest, so autouse resolves correctly
- On local dev: `TEST_ENV` unset → sub-level conftests read `DATABASE_URL` from your
  `.env` (points at Docker on port 5433). testcontainers only used if explicitly invoked.
- This means `uv run pytest tests/unit/ -v` works locally without Docker running,
  as long as `DATABASE_URL` is set in `.env`.
build:
  steps:
    - npm ci
    - npm run build    (Next.js production build — catches any build-time errors)
```

**Status check for branch protection:** The `build` job is what `main`'s branch protection
watches. If `build` is green, all upstream jobs also passed (sequential dependency).

### 3.3 `deploy.yml` — deployment stub

**Trigger:** `push` to `main`
**Purpose:** Establishes the hook now so Phase 6 just fills it in.

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to production
        run: |
          echo "TODO Phase 6: wire Azure deployment here"
          echo "Will use: az containerapp update ..."
```

This does nothing useful today but establishes the trigger pattern.

---

## 4. GitHub Actions Secrets

Secrets are stored in GitHub → repo Settings → Secrets and variables → Actions.
They are encrypted at rest, never appear in logs, and are only available to workflow runs
on the correct branch.

**These are throwaway CI-only values — not your real credentials.**

| Secret name | Value to set | Used by |
|---|---|---|
| `CI_POSTGRES_PASSWORD` | `postgres` | Service container config |
| `CI_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/test_db` | pytest + Alembic |
| `CI_REDIS_URL` | `redis://localhost:6379` | pytest / backend |
| `CI_JWT_SECRET_KEY` | `ci-test-secret-not-real-change-in-prod` | pytest / auth tests |
| `CI_JWT_ALGORITHM` | `HS256` | pytest / auth tests |

Note: Alembic in this project uses `create_async_engine` and reads `settings.DATABASE_URL`
(the `postgresql+asyncpg://` URL) — no separate sync URL is required. `DATABASE_URL_SYNC`
is not needed in CI.

**How to add them:**
1. Go to `https://github.com/vipulbhatia29/stock-signal-platform/settings/secrets/actions`
2. Click "New repository secret"
3. Enter name and value exactly as above
4. Repeat for all 5 secrets

The workflow files reference them as `${{ secrets.CI_DATABASE_URL }}` etc.

---

## 5. CI Environment Configuration

The workflow jobs need a `.env`-equivalent for the backend to read config from.
Rather than writing a `.env` file to disk (security risk), the workflows inject
secrets directly as environment variables in the job step:

```yaml
- name: Run backend tests
  env:
    DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
    REDIS_URL: ${{ secrets.CI_REDIS_URL }}
    JWT_SECRET_KEY: ${{ secrets.CI_JWT_SECRET_KEY }}
    JWT_ALGORITHM: ${{ secrets.CI_JWT_ALGORITHM }}
  run: uv run pytest tests/unit/ tests/api/ -v --tb=short
```

The existing `backend/config.py` Pydantic Settings already reads from environment
variables, so no code changes are needed.

---

## 6. `uv` Caching in CI

`uv` is fast but still downloads packages. GitHub Actions cache prevents re-downloading
on every run.

**Important:** `uv.lock` is currently gitignored in this project. `hashFiles('uv.lock')`
on a file not in the repo returns an empty string, making the cache key useless.
**The implementation must commit `uv.lock`** — this is `uv`'s recommended practice for
reproducible builds, and it resolves the existing CLAUDE.md troubleshooting entry about
lock file conflicts. Remove `uv.lock` from `.gitignore` and commit it as part of this
implementation.

Once committed, the cache key works correctly:

```yaml
- name: Cache uv packages
  uses: actions/cache@v4
  with:
    path: ~/.cache/uv
    key: uv-${{ hashFiles('uv.lock') }}
    restore-keys: uv-
```

Similarly for npm:
```yaml
- name: Cache npm
  uses: actions/cache@v4
  with:
    path: frontend/node_modules
    key: npm-${{ hashFiles('frontend/package-lock.json') }}
```

---

## 7. Documentation Catch-Up: Phase 4A UI (Already Shipped)

Phase 4A (Session 29) shipped 25 UI tasks but docs were not updated. This spec
includes catch-up updates to reflect current reality.

### 7.1 FSD updates needed

**Section 4 (NFR) — add NFR-7: Developer Experience:**
```
### NFR-7: Developer Experience
- All PRs to develop must pass CI gate before merge
- All merges to main must pass full CI gate (includes integration + build)
- main branch is always deployable — no broken builds permitted
- Branch protection enforced via GitHub branch rules (no direct push)
```

**Section 2 (Functional Requirements) — update UI/Frontend section:**
- Dark-only application (`forcedTheme="dark"`) — light mode removed
- New shell layout: 54px icon sidebar (`SidebarNav`), `Topbar`, resizable `ChatPanel`
- New dashboard components: `StatTile` (5-tile overview row), `AllocationDonut`
  (CSS conic-gradient), `PortfolioDrawer` (bottom slide-up)
- `Sparkline` replaced with raw SVG `<polyline>` for jagged financial chart aesthetics
- Typography: Sora (UI labels) + JetBrains Mono (numbers/metrics)
- Chat panel: docked right side, drag-resizable, width persisted to localStorage

### 7.2 TDD updates needed

**New section: Frontend Architecture (Phase 4A)**

Add after the existing frontend structure section:

```
## Frontend Shell Architecture (Phase 4A)

Layout:
  app/(authenticated)/layout.tsx  ← "use client"; root shell
    SidebarNav (54px fixed)       ← icon nav, tooltip labels, Popover logout
    flex-col main:
      Topbar                      ← market status, signal count, AI toggle
      <children> (page content)
    ChatPanel (--cp wide)         ← docked right, drag-resize, hidden via transform

CSS Layout Variables (globals.css @theme inline):
  --sw: 54px    sidebar width
  --cp: 280px   chat panel width (persisted to localStorage)

Font Loading (app/layout.tsx):
  Sora + JetBrains Mono via next/font/google
  Set as CSS vars: --font-sora, --font-jetbrains-mono
  Applied via: cn(sora.variable, jetbrainsMono.variable) on <body>

Component Inventory (new in Phase 4A):
  SidebarNav           icon-only sidebar with tooltip labels
  Topbar               market status chip, signal count, AI toggle
  ChatPanel            drag-resize stub; Phase 4B wires to backend
  StatTile             dashboard KPI tile with accent gradient top border
  AllocationDonut      CSS conic-gradient pie; no chart library
  PortfolioDrawer      bottom slide-up with PortfolioValueChart

Hook Locations:
  usePositions()           hooks/use-stocks.ts (extracted from portfolio-client)
  usePortfolioSummary()    hooks/use-stocks.ts (extracted from portfolio-client)
  usePortfolioHistory()    hooks/use-stocks.ts (extracted from portfolio-client)
  useWatchlist()           hooks/use-stocks.ts (existing)

localStorage Keys:
  All keys in lib/storage-keys.ts with stocksignal: namespace prefix
  CHAT_PANEL_WIDTH: stocksignal:cp-width
  SCREENER_DENSITY: stocksignal:density

Market Hours:
  lib/market-hours.ts — pure isNYSEOpen() function
  Uses IANA America/New_York timezone (DST-correct)
  No API call — client-side only
```

### 7.3 CLAUDE.md updates needed

**Git section** — update branch conventions:
```
- Main development target: `develop` branch (not `main` directly)
- feat/* → PR → develop → PR → main
- main is production-ready at all times
- Never commit to main or develop directly (update from "Never commit to main directly")
```

**Commands section** — no changes needed (CI runs automatically)

**Environment Variables section** — add CI vars table note:
```
CI-only secrets (stored in GitHub Actions Secrets, never in .env):
  CI_DATABASE_URL, CI_REDIS_URL, CI_JWT_SECRET_KEY, CI_JWT_ALGORITHM, CI_POSTGRES_PASSWORD
```

**Troubleshooting section** — remove the `uv.lock` conflicts entry (resolved by committing
the lockfile). Add instead: "`uv.lock` committed — run `uv sync` after pulling to keep
local venv in sync."

---

## 8. File Structure

```
.github/
  workflows/
    ci-pr.yml       ← PR gate: lint + unit + API + Jest (~3 min)
    ci-merge.yml    ← merge gate: full suite + build (~8 min)
    deploy.yml      ← deploy stub (no-op until Phase 6)
```

No new source files. No new dependencies. No database migrations.

---

## 9. Success Criteria

- [ ] Opening a PR to `develop` automatically triggers `ci-pr.yml`
- [ ] PR shows ✅ or ❌ status checks from GitHub Actions
- [ ] Merging a broken PR is blocked by branch protection when CI fails
- [ ] Merging to `develop` automatically triggers `ci-merge.yml`
- [ ] `develop → main` PR shows `ci-merge / build` status check
- [ ] All 5 CI secrets set in GitHub Actions Secrets (no DATABASE_URL_SYNC needed)
- [ ] `develop` branch exists and is protected
- [ ] `main` branch protection updated to require `ci-merge / build`
- [ ] FSD, TDD, CLAUDE.md updated to reflect Phase 4A and CI/CD reality
- [ ] `uv.lock` committed and removed from `.gitignore`
- [ ] `tests/conftest.py` testcontainers fixture guarded with `TEST_ENV=integration` check
- [ ] `package.json` has `"test": "jest"` script and lint script has explicit path target
- [ ] Hotfix back-merge process documented (PR hotfix/* → develop after main merge)

---

## 10. Out of Scope

- Docker image building and pushing (Phase 6)
- Azure deployment wiring (Phase 6)
- Staging server provisioning (Phase 6)
- E2E / Playwright tests in CI (Phase 6 or later)
- Slack/email notifications on CI failure (Phase 6)
- Dependabot / automated dependency updates (Phase 6)
