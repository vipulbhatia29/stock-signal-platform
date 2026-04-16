# Stock Signal Platform

An investment decision-support platform for US equities. Combines technical analysis, fundamental scoring, Prophet forecasting, portfolio tracking, and an AI financial analyst — all in a dark command-center UI designed for busy professionals who want data-driven guidance without becoming full-time traders.

> **Philosophy:** "Tell me what to do and show me why." Every recommendation comes with confidence scoring, evidence lineage, and bull/base/bear scenarios. No hallucinated numbers, no opinions disguised as facts.

## Screenshots

| Dashboard | Screener | Stock Detail |
|-----------|----------|--------------|
| ![Dashboard](screenshots/04-dashboard-watchlist-aapl.png) | ![Screener](screenshots/06-screener-table.png) | ![Stock Detail](screenshots/05-stock-detail-aapl.png) |

## Who Is This For?

Part-time investors — professionals who:

- Have savings they want to grow beyond index funds and savings accounts
- Don't have time to monitor markets daily or learn candlestick patterns
- Want to make informed stock picks but feel overwhelmed by the volume of financial data
- Are comfortable with technology and want to automate what can be automated
- Invest primarily in US equity markets (stocks + ETFs)

**Typical user profile:** 30-50 year old tech professional, $15K-$150K portfolio, 15-30 minutes/day for investment decisions.

## What Does It Do?

### Signal Engine

Computes technical and fundamental indicators for 500+ stocks, synthesized into a single **composite score (0-10)** that blends:

| Technical Signals (50%) | Fundamental Score (50%) |
|------------------------|--------------------------|
| RSI (14-period) — overbought/oversold | Piotroski F-Score (0-9, scaled to 0-5 pts) |
| MACD (12,26,9) — momentum | |
| SMA 50/200 Crossover — golden/death cross | **Also materialized (not scored):** |
| Bollinger Bands (20,2) — volatility position | P/E, PEG, FCF Yield, D/E, margins, ROE |
| Annualized Return, Volatility, Sharpe Ratio | Revenue/Earnings Growth, analyst targets |
| Sortino, Max Drawdown, Alpha, Beta (via QuantStats) | |

**Score interpretation:** 8-10 = BUY, 5-7 = WATCH, <5 = AVOID. Scores are portfolio-aware — if you already hold a stock at full allocation, it becomes HOLD instead of BUY.

### AI Financial Analyst (Chat)

A conversational interface powered by LangGraph that can answer questions like:

- *"Should I buy AAPL right now?"*
- *"Compare NVDA and AMD"*
- *"How is my portfolio exposed to tech?"*
- *"What are the risks of holding TSLA?"*

The agent uses a **ReAct Loop** architecture (default, feature-flagged via `REACT_AGENT=true`):

1. **Intent** — understand what the user is asking
2. **Plan** — decide which tool to call next
3. **Execute** — call the tool and observe results
4. **Reason** — decide if more tools are needed or if the answer is ready

A legacy **Plan-Execute-Synthesize** pipeline (planner, mechanical executor, synthesizer) is available for rollback by setting `REACT_AGENT=false`.

The agent has access to 25 internal tools and 4 MCP adapters, with guardrails for PII detection, prompt injection defense, and automatic disclaimer insertion. Every claim traces back to a specific data source and timestamp.

### LLM Factory

Data-driven multi-provider cascade configured via `llm_model_config` table in the database. Provider priority, rate limits, and cost tracking are all DB-managed — no code changes needed to adjust the cascade.

| Provider | Default Role | Use Case |
|----------|-------------|----------|
| **Groq** (Llama/Mixtral) | Primary (agent) | Tool-calling loops, fast inference |
| **Anthropic** (Claude Sonnet) | Fallback / synthesis | Complex reasoning, planning |
| **OpenAI** (GPT-4o) | Secondary fallback | Additional capacity |

Features token budgeting per tier, per-query cost tracking, and Redis-backed rate limiting with Lua scripts for atomic operations.

### Prophet Forecasting & Backtesting

- Stock-level + 11 SPDR sector ETF + portfolio-level forecasts
- 90/180/270-day prediction horizons with confidence intervals
- Weekly model retraining (Sunday 2 AM ET) with **per-ticker calibrated drift detection** (threshold = `backtest_mape × 1.5`, self-healing demotion after 3 consecutive failures). Nightly cap: 100 new models; user-initiated ingests bypass cap.
- Walk-forward backtesting engine with 5 metrics (MAPE, MAE, RMSE, direction accuracy, CI containment)
- VIX regime overlay for forecast confidence
- AccuracyBadge component showing model accuracy tier (Excellent/Good/Fair/Poor)
- News sentiment regressors feeding Prophet (stock, sector, macro — feature-flagged)

### News Sentiment Pipeline

- 4 news providers: **Finnhub** (primary), **SEC EDGAR** (8-K filings), **Fed RSS/FRED** (macro), **Google News** (fallback)
- LLM-based sentiment scoring (GPT-4o-mini) with event type classification
- 3 sentiment channels: stock-level, sector-level, macro-level
- Exponential decay aggregation for daily sentiment rollups
- 4x/day ingestion + scoring via Celery tasks
- Quality flags: ok, suspect (low confidence), invalidated (manual override)
- XML parsing uses `defusedxml` for XXE safety

### Signal Convergence & Divergence UX

- Multi-signal convergence analysis across 5+ indicators (RSI, MACD, SMA, Piotroski, Prophet forecast, news sentiment)
- **Traffic light UX** — signal-by-signal bullish/bearish/neutral display with color coding
- **Divergence alerts** — warning when forecast direction opposes technical signal majority
- Historical hit rate computation for divergence patterns
- Natural-language rationale explaining each convergence state
- Portfolio-level and sector-level convergence aggregation

### Portfolio Tracker

- FIFO-based P&L computation across BUY/SELL transactions
- Real-time position values with unrealized gain/loss
- Sector allocation breakdown with concentration warnings
- Dividend tracking with full payment history
- Divestment rules engine (stop-loss, concentration limits, fundamental deterioration)
- Rebalancing suggestions (3 strategies: min volatility, max Sharpe, risk parity via PyPortfolioOpt)
- Daily portfolio snapshots for historical value tracking
- **Portfolio forecast:** Black-Litterman allocation, Monte Carlo simulation (10K paths), CVaR (95th/99th percentile)

### Stock Intelligence & Recommendations

- **Stock intelligence** — insider trades, analyst upgrades/downgrades, EPS revisions, short interest
- **AI-powered stock recommendations** — daily BUY/SELL/WATCH/AVOID with confidence scoring and evidence lineage
- **Recommendation scorecard** — accuracy tracking against SPY benchmark at 30/90/180-day horizons
- **Portfolio health scoring** — risk-adjusted metrics, concentration analysis, diversification grades
- **Geopolitical events analysis** — assess market impact of geopolitical developments on portfolio holdings
- **Market briefing synthesis** — daily market summary combining signals, news, and macro data

### Stock Screener

- Filter and sort 500+ stocks by any signal, score, sector, or index membership
- Server-side pagination with URL state for shareable filter configurations
- Color-coded rows: green (strong buy), yellow (watch), red (avoid)
- Column presets: Overview, Signals, Performance

### Nightly Automation Pipeline

A 6-phase Celery Beat pipeline runs at 9:30 PM ET every trading day:

| Phase | What | Duration |
|-------|------|----------|
| **0** | Cache invalidation (stale screener/signal keys) | <1 min |
| **1** | Price refresh + signal computation (fast path, parallel via `Semaphore(5)`) | ~2 min |
| **1.5** | yfinance info + dividends (slow path, sequential) | ~20 min |
| **2** | Forecast refresh, recommendations, forecast/rec evaluation, portfolio snapshots (parallel) | ~10 min |
| **3** | Convergence snapshot (5-signal alignment for all tickers) | ~2 min |
| **4** | Drift detection (per-ticker calibrated thresholds) | ~1 min |
| **5** | Alert generation, health snapshots, rebalancing (parallel) | ~2 min |

Additionally: data quality scanning (10 checks) at 4 AM ET, retention purge (forecasts 30d, news 90d) at 3:30 AM ET, news ingestion 4x/day, sentiment scoring 1h after each ingest, warm data syncs at 6-7 AM ET. All outbound API calls rate-limited via Redis token-bucket (`TokenBucketLimiter`).

All pipeline tasks tracked via `@tracked_task` decorator with `PipelineRunner` lifecycle (per-ticker success/failure recording, watermark-based gap detection).

### Authentication & Account Management

Full-featured auth system supporting both traditional and social login:

- **Google OAuth 2.0** — sign up, log in, or auto-link an existing account to Google. Stateless PKCE-style flow with state + nonce validation and JWKS caching.
- **Email verification** — new accounts receive a verification email via Resend. Unverified users are soft-blocked from write operations (add to watchlist, portfolio transactions, etc.) until they confirm their address.
- **Password reset** — forgot-password flow with time-limited, single-use tokens. No email enumeration; per-email rate limiting.
- **Account settings** — `/account` page with four sections: profile info, change/set password, Google link/unlink, and danger zone.
- **Account deletion** — soft-delete with a 30-day grace period before anonymization. A Celery Beat task (3:15 AM daily) purges expired accounts.
- **Admin tools** — admin-only endpoints to manually verify an email address or recover a soft-deleted account within the grace window.

### In-App Alerts

Bell icon with unread count, severity-colored badges, and undo dismiss. Alert categories:
- Signal flip (e.g., RSI moved from oversold to neutral)
- New buy recommendation
- Drift warning (model accuracy degrading)
- Divestment rule triggered

### Observability & Command Center

Every AI interaction is instrumented end-to-end:
- **Per-query cost tracking** — see exactly what each chat message costs across LLM providers
- **Langfuse tracing** — parallel traces for chat sessions, ReAct loop spans, and LLM generations
- **Provider cascade metrics** — fallback rates, latency percentiles, token usage by tier
- **Assessment engine** — golden dataset of 20 queries scored across 5 dimensions for regression detection
- **Admin LLM management** — hot-reload model configs, chat session audit with full transcripts
- **Platform Command Center** — admin-only `/admin/command-center` dashboard with **5 zones** (System Health, API Traffic, LLM Operations, Pipeline, Forecast Health) + 3 drill-down sheets, 15s auto-polling, per-zone circuit breakers

### MCP Tool Server

The platform exposes its tool registry via [Model Context Protocol](https://modelcontextprotocol.io/) (MCP), mounted at `/mcp` with JWT authentication. This lets external AI tools (Claude Code, Cursor, etc.) call any of the 29 registered tools directly — search stocks, get signals, run forecasts, check portfolio exposure — all through a standardized protocol.

### Cache Service

Redis-backed caching with a 3-tier namespace system:

| Namespace | Scope | Example |
|-----------|-------|---------|
| `app:` | Shared across all users | Market data, stock metadata |
| `user:` | Per-user isolation | Portfolio summaries, recommendations |
| `session:` | Per-chat session | Agent tool results during a conversation |

Four TTL tiers: volatile (60s), standard (5min), stable (1hr), session (until chat ends). Warm-up on startup, nightly invalidation after pipeline runs.

## Data Sources

| Source | Data | Integration | Cost |
|--------|------|-------------|------|
| [yfinance](https://github.com/ranaroussi/yfinance) | OHLCV prices, fundamentals, analyst targets, earnings, dividends | Direct | Free |
| [Finnhub](https://finnhub.io/) | Stock + market news, analyst ratings, ESG, supply chain | Direct (news) + MCP (agent) | Free tier |
| [SEC EDGAR](https://www.sec.gov/edgar/) | 8-K/10-K filings for company events | Direct (news) + MCP (agent) | Free |
| [Federal Reserve](https://www.federalreserve.gov/) | Fed press releases, FRED economic data releases | Direct (news RSS) | Free |
| [Google News](https://news.google.com/) | Broad stock + market news (RSS fallback) | Direct (RSS) | Free |
| [FRED API](https://fred.stlouisfed.org/docs/api/) | Macro indicators — yield curve, unemployment, GDP | MCP | Free (API key) |
| [Alpha Vantage](https://www.alphavantage.co/) | News sentiment analysis | MCP | Free tier |
| [SerpAPI](https://serpapi.com/) | Web/news search for the AI agent | Direct | Free tier (100/month) |
| Wikipedia | S&P 500, NASDAQ-100, Dow 30 constituent lists | Direct | Free |
| [Resend](https://resend.com/) | Transactional email (verification, password reset) | Direct | Free tier |
| [Google OAuth](https://developers.google.com/identity) | OAuth 2.0 authentication + JWKS validation | Direct | Free |

No paid data subscriptions required. All core functionality works with just the free yfinance library. XML parsing uses `defusedxml` for XXE safety.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, async SQLAlchemy 2.0, Pydantic v2 |
| **Frontend** | Next.js 15, TypeScript, Tailwind CSS v4, shadcn/ui (base-ui), Recharts, TanStack Query |
| **Database** | PostgreSQL 16 + TimescaleDB (time-series hypertables) |
| **Cache/Broker** | Redis 7 (cache + Celery broker + JWT token blocklist) |
| **AI/ML** | LangGraph (agent orchestration), Claude Sonnet (LLM), Prophet (forecasting) |
| **LLM Providers** | Groq (primary agent), Anthropic (fallback/synthesis), OpenAI (secondary) — DB-driven cascade |
| **Observability** | Langfuse (tracing), ObservabilityCollector (metrics), Assessment Engine (eval) |
| **Background** | Celery + Celery Beat (task scheduling) |
| **Auth** | JWT (httpOnly cookies + Bearer tokens), bcrypt password hashing, Google OAuth 2.0 (PKCE + JWKS) |
| **Email** | Resend API (transactional email — verification, password reset); dev console fallback |
| **MCP** | FastMCP server (tool exposure), 4 MCP adapters (external data) |
| **Package Management** | uv (Python), npm (Node.js) |
| **CI/CD** | GitHub Actions (lint, test, build), branch protection on main + develop |

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| **OS** | macOS, Linux, or WSL2 | macOS or Ubuntu 22+ |
| **Python** | 3.12+ | 3.12 |
| **Node.js** | 20+ | 22+ |
| **Docker** | Docker Desktop or Docker Engine | Docker Desktop |
| **RAM** | 4 GB | 8 GB (Prophet model training is memory-intensive) |
| **Disk** | 2 GB (deps + data) | 5 GB |
| **CPU** | 2 cores | 4 cores |

> **Note:** Native Windows is not supported. Use WSL2 on Windows.

## API Keys Required

| Key | Required? | Purpose | Get It |
|-----|-----------|---------|--------|
| `ANTHROPIC_API_KEY` | **Yes** | AI agent (Claude Sonnet for planning + synthesis) | [console.anthropic.com](https://console.anthropic.com/settings/keys) |
| `JWT_SECRET_KEY` | **Yes** | Authentication tokens (generate: `python -c "import secrets; print(secrets.token_hex(32))"`) | Self-generated |
| `GROQ_API_KEY` | No | Fast/cheap LLM fallback for tool-calling loops | [console.groq.com](https://console.groq.com/keys) |
| `OPENAI_API_KEY` | No | Additional LLM fallback (GPT models) | [platform.openai.com](https://platform.openai.com/api-keys) |
| `SERPAPI_API_KEY` | No | Web/news search tool in AI agent | [serpapi.com](https://serpapi.com/manage-api-key) |
| `FRED_API_KEY` | No | Federal Reserve macro data (yield curve, unemployment) | [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html) |
| `FINNHUB_API_KEY` | No | Analyst ratings, ESG scores, supply chain | [finnhub.io](https://finnhub.io/register) |
| `ALPHA_VANTAGE_API_KEY` | No | News sentiment analysis | [alphavantage.co](https://www.alphavantage.co/support/#api-key) |
| `GOOGLE_CLIENT_ID` | No | Google OAuth 2.0 login/register | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| `GOOGLE_CLIENT_SECRET` | No | Google OAuth 2.0 login/register | [console.cloud.google.com](https://console.cloud.google.com/apis/credentials) |
| `RESEND_API_KEY` | No | Transactional email (verification + password reset). Without it, emails are printed to the dev console. | [resend.com](https://resend.com/api-keys) |

**Minimum to get started:** Just `ANTHROPIC_API_KEY` and a self-generated `JWT_SECRET_KEY`. Everything else is optional.

## Installation

### Automated (Recommended)

```bash
git clone https://github.com/vipulbhatia29/stock-signal-platform.git
cd stock-signal-platform
chmod +x setup.sh run.sh
./setup.sh              # Installs deps, starts Docker, runs migrations
./run.sh start          # Starts all services (backend, frontend, Celery)
```

Run `./setup.sh --check` to verify prerequisites without installing anything.

### Manual Setup

#### 1. Clone and configure

```bash
git clone https://github.com/vipulbhatia29/stock-signal-platform.git
cd stock-signal-platform
cp backend/.env.example backend/.env    # Edit with your API keys
```

#### 2. Start infrastructure

```bash
docker compose up -d                    # TimescaleDB on :5433, Redis on :6380
```

#### 3. Install dependencies

```bash
uv sync                                 # Python dependencies
cd frontend && npm install && cd ..     # Frontend dependencies
```

#### 4. Initialize database

```bash
uv run alembic upgrade head             # Run all migrations
```

#### 5. Bootstrap data

Run in order — each step depends on the previous:

```bash
# Step 1: Stock universe — S&P 500 constituents (~503 stocks)
uv run python -m scripts.sync_sp500

# Step 2: ETFs — 12 SPDR sector ETFs + SPY benchmark, 10 years of prices
uv run python -m scripts.seed_etfs

# Step 3: Prices + signals — 10 years of OHLCV, computes all technical indicators
uv run python -m scripts.seed_prices --universe

# Step 4: Index memberships — NASDAQ-100, Dow 30
uv run python -m scripts.sync_indexes

# Step 5: Fundamentals — P/E, Piotroski, analyst targets, earnings, margins
uv run python -m scripts.seed_fundamentals --universe

# Step 6: Dividends — full payment history
uv run python -m scripts.seed_dividends --universe

# Step 7: Forecasts — train Prophet models, generate 90/180/270d predictions
uv run python -m scripts.seed_forecasts --universe
```

**Timing:** Steps 1-4 ~2 min, Steps 5-6 ~10 min each, Step 7 ~3 min. Full bootstrap: ~25 minutes.

All scripts support `--dry-run` (preview without writing) and `--tickers AAPL MSFT` (seed specific tickers).

#### 6. Start services

```bash
# Terminal 1: Backend API
uv run uvicorn backend.main:app --reload --port 8181

# Terminal 2: Frontend
cd frontend && npm run dev              # http://localhost:3000

# Terminal 3: Celery worker (background tasks)
uv run celery -A backend.tasks worker --loglevel=info

# Terminal 4 (optional): Celery Beat (scheduled tasks — nightly pipeline, etc.)
uv run celery -A backend.tasks beat --loglevel=info
```

Or use the convenience script: `./run.sh start` (starts everything), `./run.sh stop`, `./run.sh status`.

#### 7. Create your account

Open http://localhost:3000, register with email + password, and start adding tickers to your watchlist.

## Architecture

```mermaid
graph TB
    subgraph Clients
        NextJS["Next.js SPA<br/>:3000"]
    end

    subgraph FastAPI["FastAPI :8181"]
        MW["Middleware<br/>CORS | JWT | Rate Limit | HttpMetrics"]

        subgraph Routers["19 Routers"]
            R_Auth["/auth<br/>register, login, OAuth,<br/>verify, reset, account"]
            R_Stocks["/stocks<br/>signals, screener, watchlist"]
            R_Portfolio["/portfolio<br/>transactions, positions,<br/>rebalancing, forecast"]
            R_Chat["/chat<br/>stream, sessions, feedback"]
            R_Forecast["/forecasts<br/>ticker, sector, portfolio"]
            R_Alerts["/alerts"]
            R_Backtest["/backtests<br/>summary, run, calibrate"]
            R_Conv["/convergence<br/>ticker, portfolio, sector"]
            R_Sent["/sentiment<br/>ticker, bulk, macro, articles"]
            R_Pipelines["/admin/pipelines<br/>groups, runs, cache"]
            R_Admin["/admin<br/>command center, LLM, chat audit"]
            R_Obs["/observability"]
            R_Other["+ /market, /news, /sectors,<br/>/indexes, /preferences, /health"]
        end

        subgraph Agent["AI Agent Layer"]
            V1["ReAct Loop (default)"]
            V2["Plan→Execute→Synthesize (rollback)"]
            Guard["Guardrails<br/>PII | Injection | Disclaimer"]
            LLM["LLMClient<br/>DB-driven cascade<br/>Groq → Anthropic → OpenAI<br/>token budgeting + cost tracking"]
        end

        subgraph ToolLayer["29 Tools"]
            T_Internal["25 Internal Tools<br/>market data, signals, fundamentals,<br/>forecasting, portfolio, recommendations,<br/>risk, dividends, health, briefing,<br/>intelligence, geopolitical, scorecard"]
            T_MCP["4 MCP Adapters<br/>Edgar | Alpha Vantage | FRED | Finnhub"]
        end

        subgraph Observability
            OC["ObservabilityCollector<br/>per-query metrics"]
            LF["Langfuse<br/>parallel tracing"]
            AE["Assessment Engine<br/>golden dataset scoring"]
            CC["Command Center<br/>5-zone admin dashboard"]
            HM["HTTP Metrics<br/>Redis sliding window"]
        end

        subgraph ServiceLayer["Service Layer"]
            SL_BT["BacktestEngine"]
            SL_Conv["SignalConvergenceService"]
            SL_PF["PortfolioForecastService"]
            SL_News["NewsIngestionService"]
            SL_Sent["SentimentScorer"]
            SL_Cache["CacheInvalidator"]
            SL_Pipe["PipelineRegistry"]
        end

        Cache["Cache Service<br/>Redis 3-tier namespace<br/>4 TTL tiers"]

        MCPServer["MCP Server<br/>/mcp (JWT auth)"]
    end

    subgraph Storage
        PG[("PostgreSQL + TimescaleDB<br/>:5433<br/>24 migrations")]
        Redis[("Redis 7<br/>:6380<br/>cache + broker + token blocklist")]
    end

    subgraph Background["Celery"]
        CW["Worker<br/>11-step nightly pipeline<br/>+ 4x/day news sentiment"]
        CB["Beat Scheduler<br/>9:30 PM ET daily + intraday"]
    end

    subgraph External["External APIs"]
        YF["yfinance<br/>prices, fundamentals, news"]
        Serp["SerpAPI<br/>web search"]
        Wiki["Wikipedia<br/>index constituents"]
        FRED["FRED (MCP)<br/>macro data"]
        Edgar["Edgar (MCP)<br/>SEC filings"]
        FH["Finnhub (MCP)<br/>analyst, ESG"]
        AV["Alpha Vantage (MCP)<br/>sentiment"]
        Resend["Resend<br/>transactional email"]
        GoogleOAuth["Google OAuth 2.0<br/>JWKS + token exchange"]
    end

    NextJS --> MW
    MW --> Routers
    Routers --> Agent
    Routers --> ToolLayer
    Routers --> ServiceLayer
    Agent --> ToolLayer
    Agent --> LLM
    Agent --> Guard
    ToolLayer --> PG
    ToolLayer --> Cache
    ServiceLayer --> PG
    ServiceLayer --> Cache
    SL_News --> FH
    SL_News --> Edgar
    SL_Sent --> External
    SL_Cache --> Redis
    Cache --> Redis
    CB --> CW
    CW --> ToolLayer
    CW --> ServiceLayer
    ToolLayer --> YF
    ToolLayer --> Serp
    T_MCP --> FRED
    T_MCP --> Edgar
    T_MCP --> FH
    T_MCP --> AV
    LLM --> External
    Routers --> Resend
    Routers --> GoogleOAuth
    Observability --> PG
    Observability --> LF
    MCPServer --> ToolLayer
```

## Project Structure

```
stock-signal-platform/
├── backend/
│   ├── main.py              # FastAPI entry point, lifespan, middleware, tool registration
│   ├── config.py            # Pydantic Settings (.env loader)
│   ├── database.py          # Async SQLAlchemy session factory
│   ├── validation.py        # Input validation (TickerPath, signal enums, dedup)
│   ├── models/              # SQLAlchemy ORM models (Stock, Signal, Portfolio, Chat, Forecast...)
│   ├── schemas/             # Pydantic v2 request/response schemas
│   ├── routers/             # 19 FastAPI route handlers (+ backtesting, convergence, sentiment, admin_pipelines)
│   ├── services/            # Service layer (convergence, portfolio_forecast, rationale, news/, cache_invalidator, pipeline_registry, backtesting...)
│   │   └── news/            # News providers (Finnhub, EDGAR, Fed RSS, Google) + sentiment scorer
│   ├── tools/               # 25 internal tools + 4 MCP adapters
│   │   └── adapters/        # MCP adapters (Edgar, Alpha Vantage, FRED, Finnhub)
│   ├── agents/              # LangGraph AI agents
│   │   ├── react_loop.py    # ReAct loop (default agent architecture)
│   │   ├── graph.py         # Plan→Execute→Synthesize (rollback option)
│   │   ├── guards.py        # Guardrails (PII, injection, disclaimer)
│   │   ├── llm_client.py    # Multi-provider cascade with token budgeting
│   │   ├── model_config.py  # DB-driven provider cascade configuration
│   │   └── providers/       # Anthropic, Groq, OpenAI provider implementations
│   ├── observability/       # ObservabilityCollector, Langfuse, metrics, admin routers
│   ├── mcp_server/          # FastMCP server (expose tools via MCP protocol)
│   ├── tasks/               # 15 Celery task files (nightly pipeline, news sentiment, convergence, assessment, seed)
│   └── migrations/          # 24 Alembic migrations
├── frontend/
│   ├── src/app/             # Next.js App Router pages
│   ├── src/components/      # React components (dashboard, screener, portfolio, chat)
│   ├── src/hooks/           # Custom hooks (auth, streaming, data fetching)
│   ├── src/lib/             # API client, auth, chart theme, utilities
│   └── src/types/           # 105 TypeScript API type definitions
├── scripts/                 # Bootstrap and sync scripts
├── tests/
│   ├── unit/                # Unit tests (by domain: signals, portfolio, agents, forecasting)
│   ├── api/                 # API endpoint tests (testcontainers for DB isolation)
│   ├── integration/         # Integration tests (MCP, cache, observability, agent flows)
│   ├── e2e/                 # Playwright E2E + nightly performance tests
│   ├── semgrep/             # Custom Semgrep rule tests
│   └── eval/                # Assessment engine (golden dataset scoring)
├── frontend/src/__tests__/  # Frontend component + MSW integration tests
├── docs/                    # PRD, FSD, TDD, specs, plans
├── docker-compose.yml       # TimescaleDB + Redis + Langfuse
├── setup.sh                 # Automated setup script
├── run.sh                   # Service management script
└── pyproject.toml           # Python dependencies (managed by uv)
```

## Testing

```bash
# Backend unit tests
uv run pytest tests/unit/ -v

# Backend API tests (uses testcontainers — spins up isolated Postgres)
uv run pytest tests/api/ -v

# Integration tests (MCP server, end-to-end flows)
uv run pytest tests/integration/ -v

# Frontend component tests
cd frontend && npm test

# All backend tests
uv run pytest tests/ -v

# Linting
uv run ruff check backend/ tests/      # Python lint
uv run ruff format backend/ tests/     # Python format
cd frontend && npm run lint             # TypeScript/React lint
```

**Test coverage:** ~2,319 total tests (1,848 backend + 423 frontend + 48 E2E + 27 nightly perf). Coverage: ~69% (floor 60%). Tiered test architecture (T0-T4), 14 CI checks via `ci-gate`, 13 custom Semgrep rules as permanent guardrails.

## API Endpoints

Endpoints across 19 routers. Key endpoints listed below — full interactive docs at http://localhost:8181/docs (Swagger UI).

<details>
<summary><strong>Auth</strong> — 17 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/register` | POST | Create account (sends verification email) |
| `/api/v1/auth/login` | POST | Login (returns JWT in httpOnly cookie) |
| `/api/v1/auth/refresh` | POST | Refresh access token |
| `/api/v1/auth/logout` | POST | Logout (blocklist refresh token) |
| `/api/v1/auth/verify-email` | POST | Verify email address with token |
| `/api/v1/auth/resend-verification` | POST | Re-send verification email |
| `/api/v1/auth/forgot-password` | POST | Request password reset email |
| `/api/v1/auth/reset-password` | POST | Reset password with token |
| `/api/v1/auth/oauth/google/authorize` | GET | Initiate Google OAuth flow |
| `/api/v1/auth/oauth/google/callback` | GET | Google OAuth callback (new user / auto-link / returning) |
| `/api/v1/auth/account` | GET | Current account info |
| `/api/v1/auth/account/password` | PUT | Change or set password |
| `/api/v1/auth/account/google/unlink` | DELETE | Unlink Google account |
| `/api/v1/auth/account/delete` | DELETE | Soft-delete account (30-day grace period) |
| `/api/v1/auth/admin/verify-email` | POST | Admin: manually verify a user's email |
| `/api/v1/auth/admin/recover-account` | POST | Admin: recover soft-deleted account |

</details>

<details>
<summary><strong>Stocks</strong> — 13 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/stocks/search` | GET | Search stocks by name or ticker |
| `/api/v1/stocks/{ticker}/prices` | GET | Historical OHLCV prices |
| `/api/v1/stocks/{ticker}/signals` | GET | Current technical + fundamental signals |
| `/api/v1/stocks/{ticker}/signals/history` | GET | Signal history over time |
| `/api/v1/stocks/{ticker}/fundamentals` | GET | P/E, PEG, FCF yield, Piotroski, margins |
| `/api/v1/stocks/{ticker}/ingest` | POST | On-demand data ingestion for any ticker |
| `/api/v1/stocks/signals/bulk` | GET | Screener — filter/sort/paginate 500+ stocks |
| `/api/v1/stocks/watchlist` | GET | User's watchlist with latest signals |
| `/api/v1/stocks/watchlist` | POST | Add ticker to watchlist |
| `/api/v1/stocks/watchlist/{ticker}` | DELETE | Remove from watchlist |
| `/api/v1/stocks/watchlist/{ticker}/acknowledge` | POST | Acknowledge signal change |
| `/api/v1/stocks/watchlist/refresh-all` | POST | Refresh all watchlist prices |
| `/api/v1/stocks/recommendations` | GET | Today's BUY/SELL/WATCH/AVOID items |

</details>

<details>
<summary><strong>Portfolio</strong> — 8 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/portfolio/transactions` | POST | Log a BUY/SELL transaction |
| `/api/v1/portfolio/transactions` | GET | Transaction history |
| `/api/v1/portfolio/transactions/{id}` | DELETE | Delete a transaction |
| `/api/v1/portfolio/positions` | GET | Current holdings with live P&L |
| `/api/v1/portfolio/summary` | GET | KPI totals + sector allocation |
| `/api/v1/portfolio/rebalancing` | GET | Position sizing suggestions |
| `/api/v1/portfolio/snapshots` | GET | Historical portfolio value |
| `/api/v1/portfolio/dividends` | GET | Dividend payment history |

</details>

<details>
<summary><strong>Chat</strong> — 5 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/chat/stream` | POST | AI agent chat (NDJSON streaming) |
| `/api/v1/chat/sessions` | GET | List chat sessions |
| `/api/v1/chat/sessions/{id}` | GET | Get session messages |
| `/api/v1/chat/sessions/{id}` | PATCH | Rename session |
| `/api/v1/chat/sessions/{id}` | DELETE | Delete session |

</details>

<details>
<summary><strong>Forecasts</strong> — 4 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/forecasts/{ticker}` | GET | Prophet forecast with confidence bands |
| `/api/v1/forecasts/sectors/{sector}` | GET | Sector ETF forecast |
| `/api/v1/forecasts/portfolio` | GET | Portfolio-level forecast |
| `/api/v1/forecasts/compare` | GET | Compare forecasts across tickers |

</details>

<details>
<summary><strong>Backtesting</strong> — 5 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/backtests/summary/all` | GET | Paginated backtest summary across all tickers |
| `/api/v1/backtests/{ticker}` | GET | Latest backtest result for a ticker |
| `/api/v1/backtests/{ticker}/history` | GET | Backtest history for a ticker |
| `/api/v1/backtests/run` | POST | Trigger backtest run (admin) |
| `/api/v1/backtests/calibrate` | POST | Trigger seasonality calibration (admin) |

</details>

<details>
<summary><strong>Convergence</strong> — 4 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/convergence/{ticker}` | GET | Signal convergence with divergence alert + rationale |
| `/api/v1/convergence/{ticker}/history` | GET | Historical convergence snapshots |
| `/api/v1/convergence/portfolio/{id}` | GET | Portfolio convergence summary |
| `/api/v1/sectors/{sector}/convergence` | GET | Sector convergence summary |

</details>

<details>
<summary><strong>Sentiment</strong> — 4 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/sentiment/{ticker}` | GET | Daily sentiment timeseries |
| `/api/v1/sentiment/{ticker}/articles` | GET | Paginated articles with scores |
| `/api/v1/sentiment/bulk` | GET | Bulk sentiment for multiple tickers |
| `/api/v1/sentiment/macro` | GET | Macro sentiment timeseries |

</details>

<details>
<summary><strong>Admin Pipelines</strong> — 8 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/admin/pipelines/groups` | GET | List all pipeline groups |
| `/api/v1/admin/pipelines/groups/{group}` | GET | Get single group with execution plan |
| `/api/v1/admin/pipelines/groups/{group}/run` | POST | Trigger pipeline group run |
| `/api/v1/admin/pipelines/runs/{run_id}` | GET | Get run status |
| `/api/v1/admin/pipelines/groups/{group}/runs` | GET | Get active run for group |
| `/api/v1/admin/pipelines/groups/{group}/history` | GET | Run history |
| `/api/v1/admin/pipelines/cache/clear` | POST | Clear cache by pattern |
| `/api/v1/admin/pipelines/cache/clear-all` | POST | Clear all whitelisted caches |

</details>

<details>
<summary><strong>Alerts, Market, News, Sectors, Indexes, Preferences, Tasks, Health, Observability</strong></summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/alerts` | GET | In-app alerts (signal flips, drift, new buys) |
| `/api/v1/alerts/{id}/dismiss` | POST | Dismiss an alert |
| `/api/v1/alerts/bulk-dismiss` | POST | Dismiss multiple alerts |
| `/api/v1/market/...` | GET | Market data endpoints |
| `/api/v1/news/...` | GET | News feed endpoints |
| `/api/v1/sectors/summary` | GET | Sector performance overview |
| `/api/v1/sectors/{sector}/stocks` | GET | Stocks in a sector with drill-down |
| `/api/v1/sectors/correlation` | GET | Sector correlation matrix |
| `/api/v1/indexes` | GET | List tracked indexes (S&P 500, NASDAQ-100, Dow 30) |
| `/api/v1/indexes/{index}/stocks` | GET | Index constituents |
| `/api/v1/preferences` | GET | User preferences |
| `/api/v1/preferences` | PATCH | Update preferences |
| `/api/v1/observability/...` | GET | User-scoped observability metrics |
| `/api/v1/tasks/run-nightly` | POST | Manually trigger nightly pipeline |
| `/health` | GET | Health check |

</details>

<details>
<summary><strong>Admin / Command Center</strong> — 10 endpoints</summary>

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/admin/command-center` | GET | Aggregate dashboard (5 zones, 10s cache) |
| `/api/v1/admin/command-center/api-traffic` | GET | API traffic drill-down |
| `/api/v1/admin/command-center/llm` | GET | LLM per-model cost + cascade log |
| `/api/v1/admin/command-center/pipeline` | GET | Pipeline run history |
| `/api/v1/admin/llm-models` | GET | List LLM model configs |
| `/api/v1/admin/llm-models/{id}` | PATCH | Update model config (priority, enabled) |
| `/api/v1/admin/llm-models/reload` | POST | Hot-reload model configs from DB |
| `/api/v1/admin/chat-sessions` | GET | List all user chat sessions |
| `/api/v1/admin/chat-sessions/{id}` | GET | Full session transcript |
| `/api/v1/admin/chat-stats` | GET | Aggregate chat usage stats |

</details>

## Configuration

All configuration is via environment variables in `backend/.env`. See `backend/.env.example` for the full list with descriptions.

<details>
<summary><strong>Key settings</strong></summary>

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...localhost:5433/stocksignal` | Postgres connection string |
| `REDIS_URL` | `redis://localhost:6380/0` | Redis connection string |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origins |
| `RATE_LIMIT_PER_MINUTE` | `60` | API rate limit per user |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | JWT refresh token TTL |
| `USER_TIMEZONE` | `America/New_York` | Timezone for market hours |
| `REACT_AGENT` | `true` | Use ReAct loop agent (set `false` for Plan-Execute-Synthesize) |
| `MCP_TOOLS` | `false` | Enable MCP tool server at `/mcp` |
| `LANGFUSE_SECRET_KEY` | — | Langfuse secret for tracing (optional) |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse public key (optional) |
| `LANGFUSE_HOST` | `http://localhost:3001` | Langfuse server URL |
| `FINNHUB_API_KEY` | — | Finnhub API key for MCP adapter |
| `ALPHA_VANTAGE_API_KEY` | — | Alpha Vantage key for MCP adapter |

</details>

## Development

- **Package manager:** [uv](https://docs.astral.sh/uv/) for Python, npm for Node.js. Never use `pip install`.
- **Branching:** `main` (production) <- `develop` (integration) <- `feat/KAN-*` (feature branches). All PRs target `develop`.
- **Pre-commit hooks:** Ruff lint + format, frontend lint — installed automatically.
- **CI:** GitHub Actions with 14 checks via `ci-gate`: backend lint + tests (testcontainers), frontend lint + tests, MCP integration, E2E (Playwright), Semgrep (13 custom rules), Pyright type checking, and nightly performance (Lighthouse, heap, responsive).

## Roadmap

**Recently completed:**
- **Forecast Intelligence (Phase 8.6+)** ✅ — backtesting engine, news sentiment pipeline (4 providers + LLM scoring), signal convergence UX (traffic lights + divergence alerts), portfolio forecasting (Black-Litterman + Monte Carlo + CVaR), admin pipeline orchestrator. 13 sprints, 4 specs. See [`docs/superpowers/specs/2026-04-02-forecast-intelligence-design.md`](docs/superpowers/specs/2026-04-02-forecast-intelligence-design.md).

**Next up:**
- **Phase F: Subscriptions + Monetization** — Stripe integration, tier enforcement (Free/Pro/Premium), LLM tier routing
- **Phase G: Cloud Deployment** — Docker Compose, MCP transport swap (stdio → Streamable HTTP), Terraform/IaC
- **Tech debt (KAN-395-399)** — wire convergence snapshot task, SQL integration tests, portfolio router extraction

## License

Private project. Not licensed for redistribution.
