# Backend

FastAPI application with async SQLAlchemy, LangChain agents, and Celery background tasks.

## Key Patterns

- `config.py` uses Pydantic Settings to load `backend/.env`
- `database.py` provides `get_async_session()` as a FastAPI dependency
- All routers are mounted in `main.py` under `/api/v1/`
- Tools in `tools/` are registered via `ToolRegistry` and called by agents
- Agents in `agents/` are registered via `AgentRegistry` and selected by the chat router
- Background tasks in `tasks/` are Celery tasks scheduled by Celery Beat

## Important

- Always use `uv run` to run Python commands
- Database URL format: `postgresql+asyncpg://user:pass@localhost:5432/stocksignal`
- Redis URL format: `redis://localhost:6379/0`
- TimescaleDB hypertables are created via raw SQL in Alembic migrations after table creation
