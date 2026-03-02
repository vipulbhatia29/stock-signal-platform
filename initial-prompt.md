# Initial Prompt for Claude Code — Session 1

Copy and paste this into Claude Code after opening the project directory.

---

## Prompt

```
Read CLAUDE.md and project-plan.md to understand the full project context.
Also read docs/PRD.md for the product requirements — it defines WHAT we're
building and WHY. docs/FSD.md defines detailed functional behavior.
docs/TDD.md defines the technical design. docs/data-architecture.md defines
the complete data model, TimescaleDB configuration, and model versioning
strategy. CLAUDE.md defines HOW to build it (conventions, commands, rules).

We're starting Phase 1: Signal Engine + Database + API. For this first session,
set up the project foundation. Here's what I need:

1. PYTHON PROJECT SETUP:
   - Initialize with `uv init` if not already done
   - Add all Phase 1 Python dependencies to pyproject.toml:
     fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic,
     pydantic, pydantic-settings, python-jose[cryptography], passlib[bcrypt],
     yfinance, pandas, pandas-ta, numpy, redis, celery, structlog,
     python-dotenv, httpx, slowapi
   - Add dev dependencies: pytest, pytest-asyncio, pytest-cov, httpx,
     factory-boy, testcontainers[postgres,redis], freezegun, ruff
   - Run `uv sync` to create the venv and install everything
   - Verify the venv works: `uv run python -c "import fastapi; print('OK')"`

2. DATABASE SETUP:
   - Create `backend/database.py` with async SQLAlchemy engine and session factory
   - Create `backend/config.py` with Pydantic Settings loading from backend/.env
     Include: DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, CORS_ORIGINS,
     RATE_LIMIT_PER_MINUTE, USER_TIMEZONE, ACCESS_TOKEN_EXPIRE_MINUTES,
     REFRESH_TOKEN_EXPIRE_DAYS
   - Copy backend/.env.example to backend/.env (I'll fill in the keys after)
   - Initialize Alembic: `uv run alembic init backend/migrations`
   - Configure alembic.ini to use async and read DATABASE_URL from settings
   - Create initial models in backend/models/ (REFER TO docs/data-architecture.md
     for the complete schema — it is the source of truth for all table definitions):
     - user.py: User + UserPreference
     - stock.py: Stock + Watchlist
     - price.py: StockPrice (TimescaleDB hypertable)
     - signal.py: SignalSnapshot (TimescaleDB hypertable)
     - recommendation.py: RecommendationSnapshot (TimescaleDB hypertable)
   - Generate and apply the initial migration
   - Include TimescaleDB create_hypertable() calls in migration via op.execute()

3. FASTAPI SKELETON:
   - Create `backend/main.py` with FastAPI app, CORS middleware (allow CORS_ORIGINS
     from config), health check endpoint, rate limiting via slowapi
   - Create `backend/routers/auth.py` with:
     - POST /auth/login (returns access + refresh tokens)
     - POST /auth/register
     - POST /auth/refresh (refresh token → new access token)
   - Create `backend/schemas/` with Pydantic models for auth requests/responses
   - Mount routers under /api/v1/

4. TESTING FOUNDATION:
   - Create `tests/conftest.py` with:
     - Async database session fixture (use testcontainers for real Postgres+TimescaleDB)
     - Redis client fixture (use testcontainers)
     - FastAPI test client fixture (httpx AsyncClient with ASGI transport)
     - Authenticated client fixture (with valid JWT)
     - Factory-boy factories for User, UserPreference, and Stock
   - Create `tests/unit/test_health.py` that tests the health endpoint
   - Create `tests/api/test_auth.py` with auth endpoint tests including
     token refresh flow
   - Run all tests and make sure they pass

5. VERIFY EVERYTHING:
   - `docker compose up -d postgres redis` should start infrastructure
   - `uv run alembic upgrade head` should create all tables + hypertables
   - `uv run uvicorn backend.main:app --port 8181` should start the server
   - `uv run pytest -v` should pass all tests
   - Document what was done in PROGRESS.md

Think hard about the architecture before coding. Use Plan Mode first to outline
your approach, then implement.
```

---

## After Claude Code finishes

1. Fill in your API keys in `backend/.env`
2. Verify: `docker compose up -d && uv run alembic upgrade head && uv run pytest -v`
3. If all green, commit: `git add -A && git commit -m "feat: initial project scaffold with database and auth"`
4. Push: `git push -u origin feat/initial-scaffold`
