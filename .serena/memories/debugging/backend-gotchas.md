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
- Autogenerate also falsely detects ALL tables as new (rewrites entire schema) — MUST manually write incremental migrations for add_column/create_table only.
- If DB has stale alembic_version (points to migration N but tables are missing), clear it: `DELETE FROM alembic_version;` then `uv run alembic upgrade head`.
- After pulling: `uv sync` to keep local venv in sync with `uv.lock`.
- **Startup validation (Session 51):** `main.py` lifespan now checks critical tables exist in `information_schema`. If missing, app refuses to start with a clear error. This catches stale alembic_version before 500 errors happen.

## Docker Port Conflicts
- `idp-postgres` (port 5433) conflicts with `ssp-postgres` (port 5433). Stop `idp-postgres` when working on this project: `docker stop idp-postgres`.
- Two containers on the same port can cause unpredictable connection routing and potential data loss.
- After any DB issue: check `docker ps | grep 5433` for conflicting containers.

## yfinance
- `on_conflict_do_nothing` was silently skipping existing price rows — intraday/pre-settlement prices never got corrected. Fixed in Session 52: changed to `on_conflict_do_update` in `market_data.py` so price columns are overwritten on re-ingest.
- Route ordering in `forecasts.py`: `/forecasts/{ticker}` must come AFTER `/forecasts/portfolio` — FastAPI matches routes in definition order, and `{ticker}` greedily matches "portfolio".

## LangChain StructuredTool + LangGraph ToolNode
- `StructuredTool.from_function(coroutine=fn)` with `**kwargs` signature creates a schema with a single `kwargs` parameter. LangChain inconsistently wraps/unwraps params.
- Fix: define explicit Pydantic `args_schema` per tool (KAN-60).
- Tool `execute(params: dict)` must be wrapped to accept `**kwargs` since StructuredTool passes keyword args, not a dict.
- Tool return value must be a JSON string (not ToolResult dataclass) — LangChain ToolMessage expects string content.
- `on_tool_end` event's `output` is a `ToolMessage` object, not a plain dict. Access `.content` (string) and `json.loads()` it.

## API Tests — DB Isolation (KAN-58 FIXED)
- Both `tests/api/conftest.py` and `tests/unit/conftest.py` only override `db_url` when `CI=true`.
- Locally, all tests fall through to root conftest's testcontainers (ephemeral DB).
- Dev DB is never touched by tests. Safe to run `pytest tests/api/` locally.

## SignalResult Attribute Names
- `SignalResult` uses flat attributes: `rsi_value`, `rsi_signal`, `macd_value`, `macd_signal_label`, `sma_signal`, `bb_position`
- NOT nested: `signals.rsi.value` or `signals.macd.signal` — those don't exist
- Always check the actual dataclass definition before accessing attributes

## ContextVar for Request-Scoped Tool Data
- Tools called via LangGraph ToolNode don't receive the FastAPI request or user object.
- Use `contextvars.ContextVar` — set in the router before streaming, read in tool `execute()`.
- Module: `backend/request_context.py` — `current_user_id: ContextVar[UUID | None]`
- Returns empty DataFrame for invalid/delisted tickers.
- Rate limiting: 0.5s delay between batch fetches.
- Mock at tool boundary (`fetch_prices`) not at `yf.download`.

## FastMCP Parameter Dispatch
- FastMCP dispatches tool call arguments as **keyword arguments** to handler functions.
- If handler has `_handler(params: dict)` and client sends `{"query": "AAPL"}`, FastMCP calls `_handler(query="AAPL")` → ValidationError.
- Fix: MCPToolClient wraps params as `{"params": {...}}` before sending. Handler receives the full dict.
- This applies to ALL tools — discovered by integration tests in Session 51 (was silently broken before).

## anyio / pytest-asyncio Teardown
- MCP `stdio_client` uses anyio TaskGroup. If you `connect()` in a fixture and `close()` in teardown, you get `RuntimeError: Attempted to exit cancel scope in a different task`.
- Fix: wrap `close()` in `try/except RuntimeError` in fixture teardown. Harmless — subprocess is dead anyway.

## bcrypt (passlib removed Session 59)
- passlib removed in Session 59 (KAN-174). Direct `bcrypt` used now (>=4.2.1, unpinned).
- `hash_password()` and `verify_password()` in `backend/dependencies.py` use `bcrypt.hashpw`/`bcrypt.checkpw`.
- Old gotcha "bcrypt must be pinned to 4.2.x (passlib compat)" NO LONGER APPLIES — passlib is gone.

## compute_signals()
- Accepts optional `piotroski_score` param — omit for pure technical composite.

## Celery
- Tasks are synchronous. Bridge to async via `asyncio.run()`.

## fetch_fundamentals()
- Synchronous function. In async context: `await loop.run_in_executor(None, fetch_fundamentals, ticker)`.
- `fetch_analyst_data()` and `fetch_earnings_history()` also synchronous — same executor pattern.
- FundamentalResult dataclass: fields with `= None` defaults MUST come after required fields or Python raises `TypeError: non-default argument follows default`.

## AsyncMock for DB tool tests
- Testing tools that use `async with async_session_factory() as session:` requires a properly structured mock.
- Pattern: `mock_cm = AsyncMock(); mock_cm.__aenter__.return_value = mock_session; mock_cm.__aexit__.return_value = None; patch("backend.database.async_session_factory", return_value=mock_cm)`
- Do NOT use `AsyncMock()` directly as the session factory return value — its `__aenter__` returns another coroutine, causing "object has no attribute" errors.
