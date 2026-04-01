# Project Index: Stock Signal Platform

> Stock analysis SaaS for part-time investors — US equities, signal detection, portfolio tracking, AI-powered recommendations.

Generated: 2026-04-01 | Session: 81 | Alembic head: `5c9a05c38ee1` (migration 023)

## Project Structure

```
backend/                    FastAPI + SQLAlchemy async + Celery
├── agents/                 LangGraph ReAct loop, guards, planner, context
├── migrations/versions/    23 Alembic migrations (TimescaleDB hypertables)
├── models/ (20 files)      SQLAlchemy 2.0 ORM models
├── observability/          Collector, writer, token_budget, langfuse, queries, routers
├── routers/ (16 files)     API routers mounted under /api/v1/
│   └── stocks/ (4 files)   Sub-routers: data, search, watchlist, recommendations
├── schemas/ (13 files)     Pydantic v2 request/response models
├── services/ (14 files)    Business logic layer (signals, portfolio, cache, etc.)
├── tasks/ (13 files)       Celery tasks + nightly pipeline (9-step chain)
└── tools/ (30+ files)      25 internal tools + 4 MCP adapters + registry
frontend/                   Next.js 15 + TypeScript + Tailwind v4 + shadcn/ui
├── src/app/(authenticated)/ 8 route groups: dashboard, screener, portfolio, stocks, sectors, observability, admin, chat
├── src/components/ (68)    UI components (shadcn primitives + domain components)
├── src/hooks/ (12 files)   TanStack Query hooks for all data fetching
├── src/lib/                api.ts (fetch wrapper), auth.ts, format.ts, utils.ts
└── src/types/api.ts        ~115 exported TypeScript interfaces (single source of truth)
tests/                      1296 backend + 329 frontend = 1625 total
├── unit/ (signals, services, tools, pipeline, agents, mcp, chat, guards, observability)
├── api/ (endpoint tests with testcontainers)
├── integration/ (MCP stdio + regression)
└── frontend src/__tests__/ (67 test suites)
docs/
├── PRD.md, FSD.md, TDD.md  Product/functional/technical specs
├── superpowers/specs/       20 design specs
├── superpowers/plans/       20 implementation plans
└── superpowers/archive/     Completed feature archives
```

## Entry Points

| Entry | Path | Command |
|-------|------|---------|
| Backend API | `backend/main.py` | `uv run uvicorn backend.main:app --reload --port 8181` |
| Frontend | `frontend/` | `cd frontend && npm run dev` (port 3000) |
| Celery Worker | `backend/tasks/__init__.py` | `uv run celery -A backend.tasks worker` |
| MCP Tool Server | `backend/mcp_server.py` | `uv run python -m backend.mcp_server` |
| Nightly Pipeline | `backend/tasks/market_data.py` | Celery Beat (4-phase chain) |
| Migrations | `backend/migrations/` | `uv run alembic upgrade head` |
| Unit Tests | `tests/unit/` | `uv run pytest tests/unit/ -q` |
| Frontend Tests | `frontend/` | `npx jest --no-coverage` |

## Core Models (29)

User, UserPreference, OAuthAccount, Stock, Watchlist, StockPrice (hypertable), SignalSnapshot (hypertable), PortfolioSnapshot (hypertable), Portfolio, Position, Transaction, RebalancingSuggestion, DividendPayment, EarningsSnapshot, ForecastResult, ModelVersion, RecommendationSnapshot, RecommendationOutcome, ChatSession, ChatMessage, InAppAlert, AssessmentResult, AssessmentRun, LLMCallLog, ToolExecutionLog, LLMModelConfig, LoginAttempt, PipelineRun, PipelineWatermark, PortfolioHealthSnapshot

## Backend Models (detailed)

| File | Model | Purpose |
|------|-------|---------|
| `backend/models/user.py` | User | Core user identity, email, password hash, email_verified, deleted_at |
| `backend/models/oauth_account.py` | OAuthAccount | OAuth provider linking (provider, provider_sub, user FK) |
| (other 27 models) | — | See Core Models list above |

## Backend Services (detailed)

| File | Service | Purpose |
|--------|---------|---------|
| `backend/services/email.py` | EmailService | Resend API integration (verification, reset, deletion emails) |
| `backend/services/google_oauth.py` | GoogleOAuthService | OAuth 2.0 auth code flow, JWKS validation |
| (other 12 services) | — | Signals, portfolio, cache, stocks, etc. |

## API Routes (16 routers)

| Prefix | Router | Key Endpoints |
|--------|--------|---------------|
| `/auth` | auth.py | login, register, refresh, logout, me, OIDC, Google OAuth, email verification, password reset, account settings, account deletion, admin tools (20+ endpoints) |
| `/stocks` | stocks/ | signals, prices, analytics, ingest, search, watchlist, fundamentals, news, intelligence, benchmark, OHLC |
| `/portfolio` | portfolio.py | transactions, positions, summary, history, dividends, rebalancing, analytics, health |
| `/preferences` | preferences.py | GET + PATCH user preferences (incl. rebalancing_strategy) |
| `/recommendations` | — | list + history |
| `/forecasts` | forecasts.py | ticker, portfolio, sectors |
| `/indexes` | indexes.py | list + stocks per index |
| `/chat` | chat.py | NDJSON streaming, sessions, feedback |
| `/alerts` | alerts.py | list + dismiss |
| `/sectors` | sectors.py | summary, stocks, correlation |
| `/news` | news.py | dashboard news (per-user split cache) |
| `/observability` | observability.py | KPIs, queries, query detail, grouped charts, assessments |
| `/admin` | admin.py | LLM config, system health, command center |
| `/health` | health.py | readiness + liveness |

## Frontend Pages (Auth Overhaul)

| Path | Page | Purpose |
|------|------|---------|
| `frontend/src/app/auth/verify-email/page.tsx` | Email Verification | Email verification landing (token-based confirmation) |
| `frontend/src/app/auth/forgot-password/page.tsx` | Forgot Password | Password reset request form |
| `frontend/src/app/auth/reset-password/page.tsx` | Reset Password | Password reset form (token-based) |
| `frontend/src/app/(authenticated)/account/page.tsx` | Account Settings | Profile, security, linked accounts, danger zone (delete account) |
| `frontend/src/components/email-verification-banner.tsx` | Email Verification Banner | Verification prompt in authenticated layout |

## Migrations

| File | Alembic Revision | Purpose |
|------|------------------|---------|
| `backend/migrations/versions/023_*.py` | `5c9a05c38ee1` | Auth overhaul: oauth_accounts table, email_verified flag, deleted_at, ChatSession FK fix |
| (previous 22 migrations) | (c870473fe107 and earlier) | Core models, hypertables, indexes, etc. |

## Agent Architecture

- **ReAct loop** (`agents/react_loop.py`) — feature-flagged `REACT_AGENT=true`
- **25 internal tools**: analyze_stock, screen_stocks, compute_signals, get_recommendations, web_search, geopolitical, search_stocks, ingest_stock, fundamentals, analyst_targets, earnings_history, company_profile, get_forecast, get_sector_forecast, get_portfolio_forecast, compare_stocks, recommendation_scorecard, dividend_sustainability, risk_narrative, portfolio_health, portfolio_analytics, portfolio_exposure, market_briefing, stock_intelligence, recommend_stocks
- **4 MCP adapters**: Edgar (10-K), Alpha Vantage (news sentiment), FRED (economic series), Finnhub (analyst ratings)
- **Intent classifier** (`agents/intent_classifier.py`) — 8 intents, tool group filtering

## Nightly Pipeline (4-phase chain)

```
Phase 0: Cache invalidation
Phase 1: SPY refresh → Price refresh + signal computation (QuantStats per-stock)
Phase 2: [parallel] Forecast refresh, recommendations, forecast eval, rec eval, portfolio snapshots (+ QuantStats portfolio)
Phase 3: Drift detection
Phase 4: [parallel] Alerts, health snapshots, rebalancing materialization
```

## Infrastructure

| Service | Port | Notes |
|---------|------|-------|
| Backend (FastAPI) | 8181 | `uv run uvicorn` |
| Frontend (Next.js) | 3000 | `npm run dev` |
| PostgreSQL + TimescaleDB | 5433 | Docker |
| Redis | 6380 | Docker |
| Langfuse | 3001 | Docker (DB on 5434) |

## Key Dependencies

| Package | Purpose |
|---------|---------|
| fastapi + uvicorn | API framework |
| sqlalchemy[asyncio] + asyncpg | Async ORM + PostgreSQL |
| celery + redis | Background tasks + Beat scheduler |
| langgraph + langchain | Agent ReAct loop |
| pandas-ta-openbb | Technical indicators (RSI, MACD, SMA, Bollinger) |
| quantstats | Risk analytics (Sortino, drawdown, alpha, beta, Calmar, VaR, CAGR) |
| pyportfolioopt | Portfolio optimization (min vol, max Sharpe, risk parity) |
| prophet | Price forecasting |
| yfinance | Market data source |
| langfuse | LLM observability |
| pyjwt | JWT authentication |
| resend | Email sending API |
| tanstack/react-query | Frontend data fetching |
| recharts | Frontend charts |
| shadcn/ui | UI component library |
