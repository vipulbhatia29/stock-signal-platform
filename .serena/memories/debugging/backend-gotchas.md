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

## passlib / bcrypt
- bcrypt >= 5.0 broke passlib API. Pin `bcrypt==4.2.1` in pyproject.toml.

## compute_signals()
- Accepts optional `piotroski_score` param — omit for pure technical composite.

## Celery
- Tasks are synchronous. Bridge to async via `asyncio.run()`.

## fetch_fundamentals()
- Synchronous function. In async context: `await loop.run_in_executor(None, fetch_fundamentals, ticker)`.
