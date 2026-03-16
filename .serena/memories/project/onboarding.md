---
scope: project
category: onboarding
---

# Setup Guide

## Prerequisites
- Docker Desktop running
- uv installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Node.js 20+ with npm
- gh CLI authenticated (`gh auth login`)

## Bootstrap

```bash
uv sync                                     # Install all Python deps + create .venv/
cd frontend && npm install                  # Install frontend deps
docker compose up -d postgres redis         # Start Postgres (5433) + Redis (6380)
cp backend/.env.example backend/.env        # Create secrets file — fill in required vars
uv run alembic upgrade head                 # Run DB migrations
uv run python scripts/sync_sp500.py         # Seed S&P 500 stock registry (optional but recommended)
```

## Required .env Values (minimum to start)

```
DATABASE_URL=postgresql+asyncpg://stockuser:stockpass@localhost:5433/stockdb
REDIS_URL=redis://localhost:6380/0
JWT_SECRET_KEY=<any-long-random-string>
ANTHROPIC_API_KEY=<your-key>
```

## Verify

```bash
uv run pytest tests/unit/ -v               # All unit tests should be green
uv run uvicorn backend.main:app --reload --port 8181  # Backend at localhost:8181
cd frontend && npm run dev                 # Frontend at localhost:3000
```

Open `http://localhost:3000` — register a user, log in, search for AAPL.

## First Data Ingest

From the UI: search for any ticker (e.g. AAPL) and click "Add to Watchlist" — triggers
`POST /api/v1/stocks/{ticker}/ingest` which fetches price history + computes signals.

Or via API:
```bash
curl -X POST http://localhost:8181/api/v1/stocks/AAPL/ingest \
  -H "Cookie: access_token=<your-jwt>"
```

## Known Port Quirks
- Postgres: **5433** (NOT 5432) — `DATABASE_URL` must use 5433
- Redis: **6380** (NOT 6379) — `REDIS_URL` must use 6380

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `passlib AttributeError` on hash | Pin `bcrypt==4.2.1` in pyproject.toml, run `uv sync` |
| Postgres connection refused | Check `docker compose ps` — use port 5433 |
| Redis connection refused | Check `docker compose ps` — use port 6380 |
| `VIRTUAL_ENV` warning from uv | Ignore — uv uses `.venv/` correctly via `uv run` |
| `uv.lock` out of date after pull | Run `uv sync` to resync local venv |
| yfinance returns empty DataFrame | Ticker invalid or rate-limited — wait and retry |

## Note on Global Memories (New Machine)
Until `memory-platform` repo exists: clone this repo and Serena memories are in `.serena/memories/`.
Global memories (`global/` prefix) live at `~/.serena/memories/global/` — must be rewritten
manually on a new machine until `sync-global-memories.sh` exists.
