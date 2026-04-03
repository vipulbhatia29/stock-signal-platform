---
scope: project
category: architecture
updated_by: session-91
---

# CI/CD Pipeline Architecture

## Workflows (`.github/workflows/`)

### ci-pr.yml — PR Quality Gate
- **Trigger:** PR to develop or main
- **Target:** < 3 minutes
- **Jobs (parallel):**
  - `backend-lint` — ruff check + ruff format --check + semgrep
  - `frontend-lint` — eslint + tsc --noEmit
  - `backend-test` — pytest tests/unit/ tests/api/ (with TimescaleDB + Redis service containers)
  - `frontend-test` — npm test (jest)
- **Concurrency:** cancels stale runs on same branch
- **Path filtering:** dorny/paths-filter routes backend/frontend jobs by file changes

### ci-merge.yml — Full Merge Gate
- **Trigger:** push to develop or main
- **Target:** 5-10 minutes
- **Jobs (sequential):** lint → unit-and-api → integration → build → ci-gate
- `ci-gate` is aggregator — requires all relevant checks pass (path-filtered)
- `build` job is what main's branch protection watches
- Integration tests: `tests/integration/` (testcontainers for API + DB integration)

### ci-gate.yml — Aggregator Check
- **Trigger:** path-filtered from ci-merge
- **Jobs:**
  - Collects status from all checks (backend-lint, backend-test, pyright, frontend-lint, frontend-test, semgrep, etc.)
  - Requires **13 total checks** to pass (all green → gate passes)
  - Allows gradual rollout of new checks (optional → required promotion after 2 weeks)

### ci-nightly.yml — Scheduled Suite
- **Trigger:** Weekdays 04:00 UTC (cron-scheduled)
- **Target:** 20-30 minutes
- **Jobs:**
  - `lighthouse` — full Lighthouse audit (performance, accessibility, SEO, best practices) against production build
  - `chart-sizing` — Playwright Recharts rendering (no animations, wait for completion)
  - `heap-snapshot` — memory leak detection (baseline heap profiles)
  - `responsive-design` — mobile viewports (iPhone 12, iPad)
  - `hypothesis-extended` — property tests with `max_examples=200` (vs 20 in ci-pr)

### ci-eval.yml — Performance Benchmarks
- **Trigger:** push to develop (nightly)
- **Target:** LLM eval suite (token budget, latency, quality metrics)
- Used for Phase 8.6+ observability validation

### deploy.yml — CD Pipeline (stub for Phase 9+)
- **Trigger:** push to main
- Placeholder for cloud deployment (ECS, Kubernetes, etc.)

## CI Checks (13 total via ci-gate)

1. `ci-pr/backend-lint` — ruff + semgrep
2. `ci-pr/backend-test` — pytest (unit + api)
3. `ci-pr/backend-pyright` — type checking (186 baseline errors, advisory)
4. `ci-pr/frontend-lint` — eslint + tsc
5. `ci-pr/frontend-test` — jest
6. `ci-merge/build` — full build artifact
7. `ci-gate` — aggregator (passes when all 6+ relevant checks green)
8-13. `ci-nightly/*` (lighthouse, chart, heap, responsive, hypothesis, eval)

**Custom Semgrep rules:** `.semgrep/stock-signal-rules.yml` (13 rules)
- JWT token claims (iat required), no str(e) anywhere, no hardcoded secrets, auth guards on health endpoint, hashed_password guard before verify, nullable check before login, OAuth state lifecycle, IDOR detail endpoints, etc.

## Pyright Static Analysis

- **Baseline:** 186 type errors (type-stub gaps, no real bugs)
- **PR check:** `--outputjson | jq '.generalDiagnostics' | changed-files filter` — only report errors in modified files
- **Merge check:** Full codebase check (baseline can grow, must not exceed +5% per quarter)
- **Promotion path:** New checks start as advisory, promote to required after 2 weeks of green

## Service Containers in CI
- PostgreSQL: `timescale/timescaledb:latest-pg16` on port 5432
- Redis: `redis:7-alpine` on port 6379
- CI uses service containers (not testcontainers) for determinism
- Testcontainers are for LOCAL dev only — never start in GitHub Actions

## GitHub Secrets (5 backend + 0 frontend currently)
- `CI_POSTGRES_PASSWORD` — postgres
- `CI_DATABASE_URL` — postgresql+asyncpg://postgres:postgres@localhost:5432/test_db
- `CI_REDIS_URL` — redis://localhost:6379
- `CI_JWT_SECRET_KEY` — ci-test-secret-not-real-change-in-prod
- `CI_JWT_ALGORITHM` — HS256

(Langfuse, news API keys, etc. added to Actions Secrets when Phase 8.6+ goes to production)

## Branch Protection
- **main:** Requires `ci-gate` (aggregator) + linear history, no direct push, no bypass for PRs
- **develop:** Requires path-filtered checks (`ci-pr/backend-test` for backend changes, `ci-pr/frontend-test` for frontend), admin bypass allowed

## Testcontainers Fixture Split
Root `tests/conftest.py` guards testcontainers with `pytest.fail()` when `CI=true`.
Sub-level conftests (`tests/unit/`, `tests/api/`, `tests/integration/`) override `db_url` to read from `DATABASE_URL` env var.
Every new test directory MUST have its own `conftest.py` with `db_url` override.

## Action Versions (latest stable as of Session 91)
- `actions/checkout@v6` (Node.js 24)
- `actions/setup-node@v6` (Node.js 24)
- `astral-sh/setup-uv@v7` (Node.js 24)
- `dorny/paths-filter@v7` (path-based job routing)
- GitHub deprecated Node.js 20 actions from June 2, 2026 — always use latest major version

## Caching
- uv: `~/.cache/uv` keyed on `uv.lock` hash
- npm: `actions/setup-node@v6` built-in cache keyed on `package-lock.json`
- `uv.lock` is committed (not gitignored)
- Cache service transient failures are GitHub-side — jobs still pass without cache

## Test Tiers & Organization

**Tier architecture** (detailed in `docs/superpowers/specs/2026-04-01-test-suite-overhaul.md`):
- **T0 (Unit):** No I/O, no DB. Path: `tests/unit/`. Run with xdist (`-n auto`)
- **T1 (API):** FastAPI endpoints, mocked external services. Path: `tests/api/`. Sequential (shared fixtures)
- **T2 (Integration):** Database + service integration. Path: `tests/integration/`. Sequential
- **T3 (E2E):** Browser automation (Playwright). Path: `tests/e2e/`. Sequential (shared state)
- **T4 (Nightly):** Long-running suites. CI: `ci-nightly.yml`, max_examples=200
- **T5 (Smoke):** Pre-deployment sanity checks (stub)

## Test Counts & Coverage (Session 91)
- Backend unit tests: 1768
- Frontend tests: 378 (jest)
- E2E tests: 42 (Playwright)
- Nightly performance tests: 27
- **Total:** ~2215 tests
- **Coverage:** ~69% (floor 60%, --no-cov-on-fail in CI to avoid mask failures)
- **Hypothesis properties:** max_examples=20 in ci-pr, max_examples=200 in ci-nightly

## Git Branching
```
main ← production-ready, protected
  └── develop ← integration, protected
        └── feat/KAN-[story#]-[kebab-name] ← Story branches
```
- **ALWAYS branch from `develop`**: `git checkout develop && git pull origin develop && git checkout -b feat/KAN-...`
- Never branch from `main` — `develop` diverges between Epic promotions, causing merge conflicts
- Branch per Story, not per subtask
- PR title: `[KAN-X] Summary`
- Commit body: `Ref: KAN-X`
- Hotfixes: `hotfix/KAN-[bug#]-[name]` → main + back-merge to develop
- Never push after PR merged (review confirms merge status)
