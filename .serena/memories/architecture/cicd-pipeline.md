---
scope: project
category: architecture
updated_by: session-37
---

# CI/CD Pipeline Architecture

## Workflows (`.github/workflows/`)

### ci-pr.yml — PR Quality Gate
- **Trigger:** PR to develop or main
- **Target:** < 3 minutes
- **Jobs (parallel):**
  - `backend-lint` — ruff check + ruff format --check
  - `frontend-lint` — eslint + tsc --noEmit
  - `backend-test` — pytest tests/unit/ tests/api/ (with TimescaleDB + Redis service containers)
  - `frontend-test` — npm test (jest)
- **Concurrency:** cancels stale runs on same branch

### ci-merge.yml — Full Merge Gate
- **Trigger:** push to develop or main
- **Target:** 5-10 minutes
- **Jobs (sequential):** lint → unit-and-api → integration → build
- `build` job is what main's branch protection watches
- Integration tests: `tests/integration/` (currently stub, exits 0)

### deploy.yml — Stub
- **Trigger:** push to main
- Does nothing until Phase 6

## Service Containers in CI
- PostgreSQL: `timescale/timescaledb:latest-pg16` on port 5432
- Redis: `redis:7-alpine` on port 6379
- Testcontainers are for LOCAL dev only — never start in CI

## GitHub Secrets (5)
- `CI_POSTGRES_PASSWORD` — postgres
- `CI_DATABASE_URL` — postgresql+asyncpg://postgres:postgres@localhost:5432/test_db
- `CI_REDIS_URL` — redis://localhost:6379
- `CI_JWT_SECRET_KEY` — ci-test-secret-not-real-change-in-prod
- `CI_JWT_ALGORITHM` — HS256

## Branch Protection
- **main:** Requires `ci-merge / build`, linear history, no bypass
- **develop:** Requires `ci-pr / backend-test` + `ci-pr / frontend-test`, admin bypass allowed

## Testcontainers Fixture Split
Root `tests/conftest.py` guards testcontainers with `pytest.fail()` when `CI=true`.
Sub-level conftests (`tests/unit/`, `tests/api/`, `tests/integration/`) override `db_url` to read from `DATABASE_URL` env var.
Every new test directory MUST have its own `conftest.py` with `db_url` override.

## Action Versions (bumped Session 37)
- `actions/checkout@v6` (Node.js 24)
- `actions/setup-node@v6` (Node.js 24)
- `astral-sh/setup-uv@v7` (Node.js 24)
- GitHub deprecated Node.js 20 actions from June 2, 2026 — always use latest major.

## Caching
- uv: `~/.cache/uv` keyed on `uv.lock` hash
- npm: `actions/setup-node@v6` built-in cache keyed on `package-lock.json`
- `uv.lock` is committed (not gitignored)
- Cache service transient failures are GitHub-side, not actionable — jobs still pass without cache

## Test Coverage Expectations (per subtask)
| Code type | Required tests |
|-----------|---------------|
| New DB model | Unit test for creation, relationships, constraints |
| New endpoint | 3 min: auth (401), happy path (200/201), error (400/404/422) |
| New service function | Unit test per public function, edge cases |
| New frontend component | Render test + key interaction test |
| Bug fix | Regression test that fails without fix, passes with it |

## Git Branching
```
main ← production-ready
  └── develop ← integration (ALWAYS branch from here)
        └── feat/KAN-[story#]-[name] ← Story branches
```
- **ALWAYS branch from `develop`**: `git checkout develop && git pull origin develop && git checkout -b feat/KAN-...`
- Never branch from `main` — `develop` diverges between Epic promotions, causing merge conflicts on PR
- Branch per Story, not per subtask
- PR title: `[KAN-X] Summary`
- Commit body: `Ref: KAN-X`
- Hotfixes: `hotfix/KAN-[bug#]-[name]` → main + back-merge to develop
