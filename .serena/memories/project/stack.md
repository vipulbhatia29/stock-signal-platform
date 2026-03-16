---
scope: project
category: project
---

# Project Stack & Entry Points

## Key Entry Points
- Backend: `backend/main.py` (FastAPI app, routers, startup events)
- Config: `backend/config.py` (Pydantic Settings, .env support)
- DB: `backend/database.py` (async engine + session factory — `async_session_factory`)
- Auth: `backend/dependencies.py` (JWT validation, `get_current_user`)

## Critical Gotchas
- `bcrypt` pinned to 4.2.x (passlib incompatible with bcrypt 5.x)
- Docker ports: Postgres 5433, Redis 6380 (NOT defaults)
- `API_BASE = "/api/v1"` in `lib/api.ts` — hooks use `/portfolio/...` NOT `/api/v1/portfolio/...` (double-prefix bug)
- `async_session_factory` is the correct import name (from `backend/database.py`)
- Route ordering matters: literal segments must come before path params in FastAPI
- Celery tasks are sync; use `asyncio.run()` bridge for async code
- TimescaleDB hypertable upsert needs `constraint="tablename_pkey"` (named constraint)
- Python heredoc via Bash escapes backticks in JS template literals — use Edit/Write tools for JS/TS
- `fetch_fundamentals()` is synchronous — use `run_in_executor` in async context
- Alembic autogenerate falsely drops TimescaleDB indexes — always review diffs

## Package Manager
- uv (NOT pip, NOT poetry). All commands: `uv run <cmd>`. Add deps: `uv add <pkg>`.
