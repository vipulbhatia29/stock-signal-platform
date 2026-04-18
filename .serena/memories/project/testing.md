---
scope: project
category: project
---

# Testing Reference

## Test Commands

```bash
# Backend — fast, no external deps
uv run pytest tests/unit/ -v                          # Unit tests (~2233, <60s)
uv run pytest tests/unit/ -n auto                     # Unit tests parallel (xdist)
uv run pytest tests/unit/test_{module}.py -v          # Single module

# Backend — requires Docker (testcontainers auto-manages Postgres+Redis)
uv run pytest tests/integration/ -v                   # Integration tests (sequential — shared DB)
uv run pytest tests/api/ -v                           # API endpoint tests (~454, sequential)

# Full suite with coverage
uv run pytest --cov=backend --cov-fail-under=60 --no-cov-on-fail  # Coverage gate (floor 60%, no-cov-on-fail in CI)

# Frontend
cd frontend && npx jest --watchAll=false               # Component & MSW tests (~423)
cd frontend && npx jest src/__tests__/components/      # Specific component dir
cd frontend && npx jest --coverage                     # Frontend coverage

# E2E
npx playwright test                                    # Playwright E2E (~48 tests, production build)
npm run build && npm start                             # Start production server FIRST

# Nightly perf (local)
uv run pytest tests/nightly/ -v                       # Lighthouse + sizing (~27 tests)
```

## Test Layout & Tiers

```
tests/
├── conftest.py          # Shared: DB engine, Redis, auth fixtures, factories
├── unit/                # T1: No external deps. Pure logic, tool functions, schemas.
│   └── conftest.py      # TEST_ENV guard — overrides to prevent testcontainers
├── integration/         # T3: Real Postgres + TimescaleDB + Redis via testcontainers
├── api/                 # T2: FastAPI endpoints via httpx AsyncClient (sequential)
│   └── conftest.py      # TEST_ENV guard
├── e2e/                 # T4: Playwright browser tests (production build)
└── nightly/             # T5: Lighthouse + chart sizing + heap + responsive
```

**Tiered Architecture (T0-T5):**
- **T0 (smoke):** Pre-commit, lint, type checks
- **T1 (unit):** Pure logic, run parallel with xdist (`-n auto`)
- **T2 (API):** FastAPI endpoints, sequential (shared DB → race conditions)
- **T3 (integration):** Real testcontainers, sequential, fixtures with lifecycle
- **T4 (E2E):** Playwright, production build (never dev server), WCAG 2.0 AA accessibility
- **T5 (nightly):** Lighthouse + chart sizing + responsive testing (weekday 04:00 UTC)

## Test-After-Feature Rule
After every feature addition and smoke test: write tests **immediately** — do NOT defer.
Minimum: happy path + 1 error path per public function, 3 paths per endpoint (auth + happy + error).

## Key Fixtures (from conftest.py)

| Fixture | Scope | What it provides |
|---------|-------|-----------------|
| `db_session` | function | Real async SQLAlchemy session (testcontainers Postgres) |
| `redis_client` | function | Real Redis client (testcontainers Redis) |
| `auth_headers` | function | JWT cookie header for authenticated requests |
| `test_user` | function | Factory-boy User instance in DB |
| `async_client` | function | httpx AsyncClient pointed at the FastAPI app |

## Factory-Boy Pattern

```python
# Always use factories, never raw dicts
from tests.factories import UserFactory, StockFactory

user = UserFactory.create()          # creates in DB
stock = StockFactory.build()         # in-memory only
```

## Time-Dependent Tests

```python
# Use freezegun for signal computations, timestamps, market hours
from freezegun import freeze_time

@freeze_time("2026-03-16 13:00:00")  # 09:00 EDT (market open, DST)
def test_market_is_open():
    assert is_nyse_open() is True
```

## Frontend Testing (Jest + jsdom)

- `testEnvironment: "jsdom"` in `frontend/jest.config.ts`
- `@testing-library/react` + `@testing-library/jest-dom`
- Test files at `frontend/src/__tests__/`
- Mock API calls with `jest.mock("../../lib/api")`
- For hooks: use `renderHook` from `@testing-library/react`

## Test Configuration & CI

**Hypothesis (Property Testing):**
- 20 examples in CI (fast), 200 in nightly (thorough)
- Used for: signal engine, portfolio math, QuantStats, recommendations
- Property tests marked `@given(...)` with custom strategies

**MSW v2 (Frontend):**
- `server.ts` + handlers in `src/__mocks__/handlers.ts`
- Custom `jest-env-with-fetch` (fetch polyfill for jsdom)
- test-utils: setupServer lifecycle (beforeAll/afterEach reset)

**Playwright (E2E):**
- ALWAYS run against production build: `npm run build && npm start`
- NEVER dev server (`next dev` — scores differ 20-30 points)
- @axe-core/playwright for WCAG 2.0 AA
- playwright-lighthouse + @lhci/cli for Lighthouse

**Factory-Boy (5 Phase 8.6+ factories):**
- BacktestRunFactory, SignalConvergenceFactory, PortfolioForecastFactory, RationaleFactory, NewsArticleFactory
- Always use factories, never raw dicts

**Regression Tests:**
- Mark every bug fix: `@pytest.mark.regression`
- Reproduces the bug before fix, prevents recurrence

**Semgrep Custom Rules:**
- 13 rules in `.semgrep/stock-signal-rules.yml`
- Tested in `tests/semgrep/`
- Encodes Hard Rules + auth/JWT patterns as permanent guardrails

**CI Behaviour:**
- `tests/unit/` and `tests/api/` run in CI with `TEST_ENV=ci` guard
- `TEST_ENV=ci` in sub-level `conftest.py` skips testcontainers (CI uses real services via env vars)
- `CI_DATABASE_URL`, `CI_REDIS_URL` etc. from GitHub Actions Secrets
- xdist ONLY for `tests/unit/` (`-n auto`). Never for API/integration (shared DB → race conditions)
- 13 CI checks via ci-gate (12 green, type-check advisory)

**Coverage:**
- Baseline ~69% (floor 60%, --no-cov-on-fail in CI)
- At sprint end: report coverage delta + uncovered files, PM decides (fix gaps or ship)
- No mid-edit checks, no hooks — gate at PR stage only
