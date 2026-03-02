# Progress Log

Track what was built in each Claude Code session.

---

## Session 1 — Project Scaffolding

**Date:** 2026-03-01
**Branch:** `feat/initial-scaffold`
**What was done:**
- [x] Python project initialized with `uv init`, all Phase 1 dependencies added
- [x] `backend/config.py` — Pydantic Settings loading from `backend/.env`
- [x] `backend/database.py` — Async SQLAlchemy engine + session factory
- [x] `backend/main.py` — FastAPI app with CORS, rate limiting (slowapi), health check
- [x] Database models created per `docs/data-architecture.md`:
  - `backend/models/user.py` — User + UserPreference (with UserRole enum)
  - `backend/models/stock.py` — Stock + Watchlist
  - `backend/models/price.py` — StockPrice (TimescaleDB hypertable)
  - `backend/models/signal.py` — SignalSnapshot (TimescaleDB hypertable)
  - `backend/models/recommendation.py` — RecommendationSnapshot (TimescaleDB hypertable)
- [x] Alembic configured for async (env.py reads from Settings)
- [x] Initial migration `001_initial_schema.py` with `create_hypertable()` calls
- [x] Auth system:
  - `backend/dependencies.py` — bcrypt hashing, JWT create/decode, `get_current_user`
  - `backend/routers/auth.py` — POST register, login, refresh
  - `backend/schemas/auth.py` — Pydantic v2 request/response models
- [x] Test foundation:
  - `tests/conftest.py` — testcontainers (real Postgres+TimescaleDB), factory-boy factories (User, UserPreference, Stock), authenticated client fixture
  - `tests/unit/test_health.py` — health check tests
  - `tests/unit/test_dependencies.py` — password hashing + JWT round-trip tests
  - `tests/api/test_auth.py` — register, login, refresh endpoint tests (12 tests)
- [x] All 23 tests pass (`uv run pytest tests/ -v`)
- [x] Docker Compose starts on ports 5433/6380 (to avoid conflicts with other projects)
- [x] `uv run alembic upgrade head` creates all tables + hypertables
- [x] `uv run uvicorn backend.main:app --port 8181` starts server, health check returns OK

**Key decisions:**
- Pinned `bcrypt==4.2.1` (passlib incompatible with bcrypt 5.x)
- Docker ports changed to 5433 (Postgres) and 6380 (Redis) to avoid conflicts
- Test approach: per-test engine + truncate tables (avoids asyncpg event loop issues)

**Next:** Signal engine — `backend/tools/market_data.py`, `backend/tools/signals.py`, `backend/tools/recommendations.py` + stock router endpoints + tests (Phase 1 continued)
