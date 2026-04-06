# AGENTS.md — Stock Signal Platform

Quick reference for AI agents. See `CLAUDE.md` for full context.

## Running Services

```bash
# Backend (port 8181)
uv run uvicorn backend.main:app --reload --port 8181

# Frontend (port 3000)
cd frontend && npm run dev

# Celery worker
uv run celery -A backend.tasks worker --loglevel=info
```

## Tests

```bash
# Unit tests (fast, parallel)
uv run pytest tests/unit/ -q --tb=short

# API tests (sequential, uses testcontainers)
uv run pytest tests/api/ -v

# All backend tests
uv run pytest tests/ -v

# Frontend tests
cd frontend && npm test
```

## Linting & TypeCheck

```bash
# Python lint + format
uv run ruff check --fix backend/ tests/
uv run ruff format backend/ tests/

# Python typecheck
uv run pyright backend/ tests/

# Frontend lint
cd frontend && npm run lint
```

## Bootstrap (7 steps, ordered)

1. `uv run python -m scripts.sync_sp500` — S&P 500 constituents
2. `uv run python -m scripts.seed_etfs` — 12 SPDR ETFs + 2y prices
3. `uv run python -m scripts.seed_prices --universe` — OHLCV + indicators
4. `uv run python -m scripts.sync_indexes` — NASDAQ-100, Dow 30
5. `uv run python -m scripts.seed_fundamentals --universe` — P/E, Piotroski
6. `uv run python -m scripts.seed_dividends --universe` — Dividend history
7. `uv run python -m scripts.seed_forecasts --universe` — Prophet models

## Key Conventions

- **Package manager:** `uv` only (never `pip`)
- **Python version:** 3.12+
- **Always async:** FastAPI endpoints and DB calls are async
- **No `str(e)`:** Never pass raw exception to user output; log it, return generic message
- **Serena first:** Use symbolic tools for code reads/edits (Serena MCP)
- **Git:** Branch from `develop`, PR to `develop`, never directly to `main`
- **Branch naming:** `feat/KAN-*`, `hotfix/KAN-*`
- **PR format:** `[KAN-X] Summary`
- **JIRA:** Use Atlassian MCP (`mcp__plugin_atlassian__searchJiraIssuesUsingJql`) to query board: `project = KAN AND status != Done ORDER BY rank ASC`

## Database

```bash
# Migrations
uv run alembic upgrade head

# Docker services (Postgres 5433, Redis 6380)
docker compose up -d
```

## Important Files

- Entry point: `backend/main.py`
- Config: `backend/config.py` (loads `.env`)
- Database: `backend/database.py`
- Models: `backend/models/`
- Routers: `backend/routers/`
- Frontend: `frontend/src/app/`

## Quick Start

```bash
./setup.sh
./run.sh start
```

## External Resources

- API docs: http://localhost:8181/docs
- Frontend: http://localhost:3000
- Docs server: http://localhost:8000