---
scope: project
category: debugging
---

# Backend Debugging Gotchas

## asyncpg / pytest-asyncio
- Nested transactions cause "event loop closed" errors.
- Solution: per-test engine + truncate tables approach (not rollback).
- Use `async_session_factory` from `backend/database.py` (correct name).

## UserRole enum
- SQLAlchemy sends `.name` (uppercase) not `.value` to Postgres by default.
- Fix: add `values_callable=lambda e: [m.value for m in e]` to `Enum()` in model definition.

## Circular imports
- `stocks` and `portfolio` routers have circular dependency.
- Fix: lazy imports inside endpoint functions (not at module level).

## Alembic
- `uv run alembic upgrade head` (not bare `alembic`).
- Autogenerate falsely drops TimescaleDB indexes — always review output before running.
- After pulling: `uv sync` to keep local venv in sync with `uv.lock`.

## yfinance
- Returns empty DataFrame for invalid/delisted tickers.
- Rate limiting: 0.5s delay between batch fetches.
- Mock at tool boundary (`fetch_prices`) not at `yf.download`.

## passlib / bcrypt
- bcrypt >= 5.0 broke passlib API. Pin `bcrypt==4.2.1` in pyproject.toml.

## compute_signals()
- Accepts optional `piotroski_score` param — omit for pure technical composite.

## Celery
- Tasks are synchronous. Bridge to async via `asyncio.run()`.

## fetch_fundamentals()
- Synchronous function. In async context: `await loop.run_in_executor(None, fetch_fundamentals, ticker)`.
