# Backend

FastAPI application with async SQLAlchemy, LangGraph agents, and Celery background tasks.

## Commands

```bash
uv run uvicorn backend.main:app --reload --port 8181  # Start backend
uv run pytest tests/unit/ -q --tb=short                # Unit tests
uv run pytest tests/api/ -q --tb=short                 # API tests (needs testcontainers)
uv run ruff check --fix backend/ tests/ scripts/        # Lint
uv run ruff format backend/ tests/ scripts/             # Format
uv run alembic upgrade head                            # Apply migrations
uv run alembic current                                 # Check migration head
```

## Key Patterns

- `config.py` uses Pydantic Settings to load `backend/.env`
- `database.py` provides `get_async_session()` as a FastAPI dependency
- All routers are mounted in `main.py` under `/api/v1/`
- 25 internal tools + 4 MCP adapters in `tools/` registered via `ToolRegistry` (build_registry.py)
- Agent pipeline: ReAct loop (`agents/react_loop.py`, feature-flagged via `REACT_AGENT=true`). Old Plan→Execute→Synthesize still available behind flag.
- Input/output guardrails in `agents/guards.py` (PII, injection, disclaimer)
- Background tasks in `tasks/` are Celery tasks scheduled by Celery Beat (4-phase nightly chain: cache invalidation → SPY+price refresh → parallel forecasts/snapshots → alerts/health/rebalancing)
- Signal indicators use `pandas-ta-openbb` — requires `import importlib.metadata` before `import pandas_ta` (package bug, noqa: F401)
- QuantStats/PyPortfolioOpt for portfolio analytics — always guard with `math.isfinite()` (returns NaN/Inf for edge cases)

## Important

- Always use `uv run` to run Python commands
- Database URL format: `postgresql+asyncpg://user:pass@localhost:5433/stockdb` (port **5433**)
- Redis URL format: `redis://localhost:6380/0` (port **6380**)
- TimescaleDB hypertables are created via raw SQL in Alembic migrations after table creation
- Alembic head: migration 022 (`c870473fe107` — QuantStats columns + rebalancing_suggestions)
- New models must be imported in `backend/models/__init__.py` for Alembic discovery + test teardown
- ContextVars (`current_query_id`, `current_session_id`, etc.) live in `backend/observability/context.py` (shim at `backend/request_context.py`)
- `LangfuseService` in `backend/observability/langfuse.py` (shim at `backend/services/langfuse_service.py`) — all Langfuse SDK calls go through this wrapper (fire-and-forget, feature-flagged on `LANGFUSE_SECRET_KEY`)
- Observability package: `backend/observability/` — collector, writer, token_budget, context, langfuse, queries, routers (admin, health, user_observability). Old paths have re-export shims.
- Observability endpoints at `/api/v1/observability/` — user-scoped (regular users see own data, admins see all)
