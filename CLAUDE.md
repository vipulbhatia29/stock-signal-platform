# stock-signal-platform

Personal stock analysis and investment signal platform for part-time investors.
Covers US equity markets. Goal: automate signal detection, portfolio
tracking, and surface actionable buy/hold/sell recommendations.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async), Celery
- **Frontend:** Next.js (latest stable), React, TypeScript, Tailwind CSS, shadcn/ui, Recharts
- **Database:** PostgreSQL 16 + TimescaleDB extension
- **Cache/Broker:** Redis 7
- **AI/ML:** LangChain, LangGraph, Facebook Prophet, scikit-learn, pandas-ta
- **LLM:** Groq (primary for agentic tool-calling loops — fast/cheap), Claude Sonnet
  (synthesis and final response via Anthropic API), LM Studio (offline fallback)
- **Data:** yfinance (market data), FRED API (macro signals)
- **Auth:** JWT (python-jose) + bcrypt (passlib), rate limiting (slowapi)
- **Package manager:** uv (NOT pip, NOT poetry)
- **Docs:** MkDocs Material
- **Testing:** pytest, pytest-asyncio, pytest-cov, httpx, factory-boy, testcontainers, freezegun

## Virtual Environment

This project uses `uv` for package management. The venv lives at `.venv/` in project root.

- All Python commands MUST use `uv run` prefix (e.g., `uv run pytest`, `uv run alembic`)
- NEVER use `pip install` — use `uv add <package>` to add dependencies
- NEVER use bare `python` — use `uv run python`
- The venv is created automatically by `uv sync`

## Commands

```bash
# Setup
uv sync                                                    # Install all dependencies + create venv
cd frontend && npm install                                 # Install frontend deps

# Infrastructure
docker compose up -d postgres redis                        # Start Postgres + Redis
uv run alembic upgrade head                                # Run DB migrations

# Development
uv run uvicorn backend.main:app --reload --port 8181       # Start backend
cd frontend && npm run dev                                 # Start frontend (port 3000)
uv run mkdocs serve                                        # Docs (port 8000)
uv run celery -A backend.tasks worker --loglevel=info      # Celery worker
uv run celery -A backend.tasks beat --loglevel=info        # Celery scheduler

# Testing
uv run pytest tests/unit/ -v                               # Unit tests (fast, no deps)
uv run pytest tests/integration/ -v                        # Integration (needs Docker)
uv run pytest tests/api/ -v                                # API endpoint tests
uv run pytest --cov=backend --cov-fail-under=80            # Full suite + coverage

# Linting
uv run ruff check backend/ tests/                          # Lint Python
uv run ruff format backend/ tests/                         # Format Python
cd frontend && npm run lint                                # Lint frontend
```

## Project Structure

```
stock-signal-platform/
├── backend/
│   ├── main.py                # FastAPI app, mount routers, startup events
│   ├── config.py              # Pydantic Settings (.env support)
│   ├── database.py            # SQLAlchemy async engine + session factory
│   ├── agents/                # LangChain/LangGraph agent definitions
│   │   ├── base.py            # BaseAgent ABC
│   │   ├── registry.py        # AgentRegistry (discover + route to agents)
│   │   ├── loop.py            # Agentic tool-calling loop
│   │   ├── stream.py          # NDJSON streaming to frontend
│   │   ├── general_agent.py   # General purpose + web search
│   │   └── stock_agent.py     # Stock analysis + signals + forecasting
│   ├── tools/                 # Agent tools — each is a future MCP server
│   │   ├── registry.py        # ToolRegistry
│   │   ├── market_data.py     # yfinance: fetch US stock OHLCV, store to TimescaleDB
│   │   ├── signals.py         # RSI, MACD, SMA, Bollinger, composite score
│   │   ├── recommendations.py # Buy/Hold/Sell decisions, position sizing
│   │   ├── fundamentals.py    # P/E, PEG, FCF yield, Piotroski F-Score
│   │   ├── forecasting.py     # Prophet price forecasts
│   │   ├── portfolio.py       # Positions, cost basis, P&L, allocation
│   │   ├── screener.py        # Filter + rank by composite criteria
│   │   └── search.py          # Web/news search
│   ├── routers/               # FastAPI endpoint handlers
│   ├── models/                # SQLAlchemy 2.0 ORM models
│   ├── schemas/               # Pydantic v2 request/response schemas
│   ├── services/              # Business logic (between routers and tools)
│   ├── tasks/                 # Celery background jobs
│   └── migrations/            # Alembic DB migrations
├── frontend/                  # Next.js (TypeScript + Tailwind + shadcn/ui)
├── tests/
│   ├── conftest.py            # Shared fixtures: DB, Redis, factories, auth
│   ├── unit/                  # No external deps, fast (<5s)
│   ├── integration/           # Real Postgres/Redis via testcontainers
│   └── api/                   # FastAPI endpoint tests via httpx
├── docs/                      # MkDocs Material source
├── data/                      # Local data (gitignored)
│   ├── models/                # Serialized ML model artifacts
│   │   ├── prophet/           # Per-ticker Prophet models
│   │   └── composite_scorer/  # Global scoring models
│   └── backups/               # pg_dump backups
├── infra/                     # Terraform (future)
└── scripts/                   # Utility scripts (seed data, backfill, etc.)
```

## Architecture Principles

- Monolith-first, microservice-ready: clean domain boundaries between modules
- Each tool group in `backend/tools/` has clean interfaces for future MCP server extraction
- Frontend is a SINGLE Next.js app — NO iframes, NO Plotly Dash, NO second framework
- Background jobs (Celery) pre-compute signals nightly; dashboard reads pre-computed data
- Agents call tools via ToolRegistry now; will call via MCP protocol later

## Testing — NON-NEGOTIABLE

- Every module MUST have a corresponding test file in `tests/`
- Every public function MUST have at least one unit test
- Every FastAPI endpoint MUST have auth + happy path + error path tests
- Every agent tool MUST have a unit test with mocked LLM
- Use factory-boy for test data, never raw dicts
- Use testcontainers for integration tests, never SQLite substitutes
- Use freezegun for time-dependent tests (signal computations depend on dates)
- Always run relevant tests after creating a module: `uv run pytest tests/unit/test_{module}.py -v`
- Fix ALL test failures before moving on

## Code Conventions

- Type hints on ALL functions, Google-style docstrings
- Async by default for FastAPI endpoints and DB operations
- Pydantic v2 for all API schemas; SQLAlchemy 2.0 mapped_column style
- Git: conventional commits (feat:, fix:, chore:, docs:, test:, refactor:)
- Branch per feature: `feat/signal-engine`, `feat/dashboard`, etc.
- Never commit to main directly

## Key Documents

- `docs/PRD.md` — Product Requirements Document. The source of truth for WHAT
  we're building and WHY. Read this first for product context.
- `docs/FSD.md` — Functional Specification Document. Detailed functional and
  non-functional requirements with acceptance criteria for every feature.
- `docs/TDD.md` — Technical Design Document. HOW to build it: component
  architecture, API contracts, service layer design, integration patterns.
- `docs/data-architecture.md` — Data architecture, entity model, TimescaleDB
  configuration, model versioning strategy, and data flow diagrams.
- `project-plan.md` — Phased build plan with deliverables per phase.
- `PROGRESS.md` — Session log tracking what was built and what's next.

## Environment Variables

All secrets live in `backend/.env` (gitignored). See `backend/.env.example` for template.
Required: ANTHROPIC_API_KEY, JWT_SECRET_KEY, DATABASE_URL, REDIS_URL
Optional: GROQ_API_KEY, SERPAPI_API_KEY, FRED_API_KEY, OPENAI_API_KEY
