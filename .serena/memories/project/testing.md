---
scope: project
category: project
---

# Testing Reference

## Test Commands

```bash
# Backend — fast, no external deps
uv run pytest tests/unit/ -v                          # Unit tests (~1045, <10s)
uv run pytest tests/unit/test_{module}.py -v          # Single module

# Backend — requires Docker (testcontainers auto-manages Postgres+Redis)
uv run pytest tests/integration/ -v                   # Integration tests
uv run pytest tests/api/ -v                           # API endpoint tests (~190)

# Full suite with coverage
uv run pytest --cov=backend --cov-fail-under=80       # Coverage gate

# Frontend
cd frontend && npx jest --watchAll=false               # Component tests (~107)
cd frontend && npx jest src/__tests__/components/      # Specific component dir
```

## Test Layout

```
tests/
├── conftest.py          # Shared: DB engine, Redis, auth fixtures, factories
├── unit/                # No external deps. Pure logic, tool functions, schemas.
│   └── conftest.py      # TEST_ENV guard — overrides to prevent testcontainers
├── integration/         # Real Postgres + TimescaleDB + Redis via testcontainers
├── api/                 # FastAPI endpoints via httpx AsyncClient
│   └── conftest.py      # TEST_ENV guard
└── e2e/                 # Playwright browser tests
```

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

## CI Behaviour

- `tests/unit/` and `tests/api/` run in CI with `TEST_ENV=ci` guard
- `TEST_ENV=ci` in sub-level `conftest.py` skips testcontainers (CI uses real services via env vars)
- `CI_DATABASE_URL`, `CI_REDIS_URL` etc. from GitHub Actions Secrets
