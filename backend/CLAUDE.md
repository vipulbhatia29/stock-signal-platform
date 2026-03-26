# Backend

FastAPI application with async SQLAlchemy, LangGraph agents, and Celery background tasks.

## Commands

```bash
uv run uvicorn backend.main:app --reload --port 8181  # Start backend
uv run pytest tests/unit/ -q --tb=short                # Unit tests
uv run pytest tests/api/ -q --tb=short                 # API tests (needs testcontainers)
uv run ruff check --fix backend/ tests/                # Lint
uv run ruff format backend/ tests/                     # Format
uv run alembic upgrade head                            # Apply migrations
uv run alembic current                                 # Check migration head
```

## Key Patterns

- `config.py` uses Pydantic Settings to load `backend/.env`
- `database.py` provides `get_async_session()` as a FastAPI dependency
- All routers are mounted in `main.py` under `/api/v1/`
- 24 internal tools + 4 MCP adapters in `tools/` registered via `ToolRegistry` (build_registry.py)
- Agent pipeline: Plan→Execute→Synthesize (LangGraph StateGraph in `agents/graph.py`)
- Input/output guardrails in `agents/guards.py` (PII, injection, disclaimer)
- Background tasks in `tasks/` are Celery tasks scheduled by Celery Beat (9-step nightly chain)

## Important

- Always use `uv run` to run Python commands
- Database URL format: `postgresql+asyncpg://user:pass@localhost:5433/stockdb` (port **5433**)
- Redis URL format: `redis://localhost:6380/0` (port **6380**)
- TimescaleDB hypertables are created via raw SQL in Alembic migrations after table creation
- Alembic head: migration 015 (portfolio_health_snapshots)
- New models must be imported in `backend/models/__init__.py` for Alembic discovery + test teardown
