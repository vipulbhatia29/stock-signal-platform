# Stock Signal Platform — Project Plan

## Phase 1: Signal Engine + Database + API (Weeks 1-2)

### Goal
Fetch stock data, compute technical signals, store in database, expose via API.

### Deliverables
1. **Docker Compose** running Postgres+TimescaleDB and Redis
2. **Database models:** User, UserPreference, Stock, Watchlist, StockPrice (hypertable), SignalSnapshot (hypertable)
3. **Alembic migrations** with TimescaleDB hypertable creation
4. **`backend/tools/market_data.py`** — fetch OHLCV via yfinance, store to TimescaleDB
5. **`backend/tools/signals.py`** — compute RSI(14), MACD(12,26,9), SMA 50/200, Bollinger Bands
   - Label each signal: bullish / bearish / neutral
   - Compute composite score (0-10) — Phase 1 uses 100% technical weights
     (Phase 3 rebalances to 50% technical + 50% fundamental, see FSD FR-3.2)
   - Compute annualized return, volatility, Sharpe ratio
6. **`backend/tools/recommendations.py`** — basic recommendation engine:
   - Score ≥8 → BUY, 5-7 → WATCH, <5 → AVOID (no portfolio context yet)
   - Store as RecommendationSnapshot rows
7. **`backend/routers/stocks.py`** — REST endpoints:
   - `GET /api/v1/stocks/{ticker}/signals` — current signals
   - `GET /api/v1/stocks/{ticker}/prices` — historical prices
   - `POST /api/v1/stocks/watchlist` — add ticker to watchlist
   - `GET /api/v1/recommendations` — today's actionable items
8. **Auth:** JWT login/register + refresh endpoint, password hashing, rate limiting (slowapi)
9. **Seed scripts:** `scripts/sync_sp500.py` (stock universe), `scripts/seed_prices.py` (backfill)
10. **Tests:** unit tests for all signal computations, API tests for all endpoints
11. **Verification:** can call API and get computed signals + recommendations for AAPL and MSFT

### Success Criteria
- `uv run pytest` passes with >80% coverage on backend/tools/signals.py
  and backend/tools/recommendations.py
- Can call `GET /api/v1/recommendations` and see actionable BUY/SELL/HOLD items
- JWT refresh flow works end-to-end

---

## Phase 2: Dashboard + Screener UI (Weeks 3-4)

### Goal
Visual dashboard showing watchlist, signals, and a stock screener.
Includes backend pre-requisites (cookie auth, index model, new endpoints).

### Deliverables — Backend Pre-requisites
1. **httpOnly cookie auth** — login/refresh set Secure httpOnly cookies; dual-mode
   auth dependency (cookie + header); `POST /auth/logout` clears cookies
2. **Stock index membership model** — `StockIndex` + `StockIndexMembership` tables;
   Alembic migration; `GET /api/v1/indexes`, `GET /api/v1/indexes/{id}/stocks` endpoints;
   seed scripts for S&P 500, NASDAQ-100, Dow 30
3. **On-demand data ingestion** — `POST /api/v1/stocks/{ticker}/ingest` endpoint;
   delta fetch (only new data since `last_fetched_at`); signal computation after fetch
4. **Bulk signals endpoint** — `GET /api/v1/stocks/signals/bulk` with index filter,
   pagination, RSI/MACD/sector/score filters, sorting; `DISTINCT ON (ticker)` query
5. **Signal history endpoint** — `GET /api/v1/stocks/{ticker}/signals/history`
   returning chronological snapshots (default 90 days, max 365)

### Deliverables — Frontend
6. **Next.js app** with App Router, Tailwind, shadcn/ui, dark/light theme toggle
7. **Login + Register pages** with cookie-based JWT auth flow
8. **Dashboard page** showing:
   - Major index cards (S&P 500, NASDAQ-100, Dow 30) — click navigates to screener
   - User's watchlist as stock cards (ticker, price, sentiment badge, return, last updated)
   - Inline search bar to add tickers to watchlist (triggers ingestion if needed)
   - Sector filter toggle
9. **Screener page** with filterable, sortable table:
   - Columns: Ticker, RSI Signal, MACD, vs SMA 200, Ann. Return, Volatility, Sharpe, Score
   - Filters: Index, RSI state, MACD state, Sector, Composite Score range
   - Row color-coding: green (≥8), yellow (5-7), red (<5)
   - Server-side pagination, URL state for shareable filters
10. **Stock detail page** with:
    - Price chart (Recharts) with 1M/3M/6M/1Y/5Y timeframe selector
    - Signal breakdown cards (RSI, MACD, SMA, Bollinger)
    - Signal history chart (composite score + RSI over time)
    - Risk & return section (annualized return, volatility, Sharpe)
11. **Auth guard** — redirect to login if no valid cookie; auto-refresh on 401
12. **API integration** via TanStack Query + centralized fetch wrapper (cookie auth)

### Success Criteria
- Can register, log in (httpOnly cookies), and be redirected to dashboard
- Dashboard shows index cards and watchlist with live signal data
- Can search and add a new ticker — data is ingested on-demand
- Screener loads 500 stocks in <3 seconds with working filters and sorting
- Stock detail shows price chart + signal breakdown + signal history chart
- Dark/light theme toggle works and persists

---

## Phase 2.5: Design System + UI Polish (Week 4)

### Goal
Establish a cohesive design system informed by TradingView, Robinhood, and
Bloomberg Terminal UI patterns. Fix responsive layout issues, standardize
color/typography tokens, and add financial-specific components.

**Detailed plan:** `.claude/plans/cozy-wandering-backus.md`

### Deliverables — Phase 2 Polish (do now)
1. **Color system overhaul** — financial semantic CSS variables (gain/loss/neutral),
   fix OKLCH/HSL chart color mismatch, migrate hardcoded sentiment classes to CSS vars
2. **Typography tokens** — `lib/typography.ts` with semantic constants (PAGE_TITLE,
   SECTION_HEADING, METRIC_PRIMARY, TICKER, TABLE_NUM)
3. **Chart design system** — `lib/chart-theme.ts` with `useChartColors()` hook,
   standardized `ChartTooltip` component, crosshair cursor
4. **New components:** `ChangeIndicator` (gain/loss with icon+sign+color),
   `SectionHeading`, `ChartTooltip`, `ErrorState`, `Breadcrumbs`
5. **Responsive fixes** — signal cards grid (1/2/4 cols), risk/return grid (1/3 cols),
   responsive chart heights, sticky screener table header
6. **Dark mode tuning** — Bloomberg-inspired warm backgrounds, chart color brightness,
   Sun/Moon toggle icons
7. **Accessibility** — aria-labels on badges, color+icon+sign for all gain/loss
   indicators (WCAG AA compliance)
8. **Fix Session 7 UI bugs** — screener filter placeholders, watchlist score N/A,
   stock detail name, market indexes rendering

### Deliverables — Deferred Enhancements (Phase 2.5+)
9. Screener column preset tabs (TradingView-inspired: Overview | Signals | Performance)
10. `MetricCard`, `Sparkline`, `SignalMeter` components
11. Sentiment-tinted chart gradient (Robinhood-style)
12. Entry animations + `prefers-reduced-motion`
13. DensityProvider (compact/comfortable toggle)
14. Chart grid view toggle for screener

### Success Criteria
- All colors defined as CSS variables, no hardcoded Tailwind sentiment classes
- Charts render correctly in both light and dark mode (OKLCH fix verified)
- Signal cards and risk/return grids responsive at 375px, 768px, 1280px
- All gain/loss indicators use color + icon + sign (accessibility)
- `npm run build` and `npm run lint` pass with zero errors
- Session 7 UI bugs all resolved

---

## Phase 3: Portfolio Tracker + Fundamentals (Weeks 5-6)

### Goal
Track actual positions and add fundamental analysis signals.

### Deliverables
1. **Database models:** Portfolio, Transaction, Position (materialized), DividendPayment,
   CorporateAction, AlertRule, AlertLog, FundamentalSnapshot (hypertable),
   RecommendationSnapshot (hypertable — upgrade from Phase 1 basic version),
   PortfolioSnapshot (hypertable)
2. **`backend/tools/fundamentals.py`** — P/E, PEG, FCF yield, debt-to-equity, Piotroski F-Score
3. **`backend/tools/portfolio.py`** — position tracking, cost basis (FIFO), P&L, allocation %,
   dividend tracking, stock split adjustment
4. **`backend/tools/recommendations.py`** — UPGRADE to portfolio-aware:
   - Factor in current portfolio weight → BUY only if not overweight
   - Position sizing: suggest dollar amounts based on target allocation (5% cap)
   - Cash reserve enforcement (10% minimum)
   - Sector concentration check (30% cap)
   - Decision reasoning stored in JSONB
5. **Portfolio API endpoints:**
   - `POST /api/v1/portfolio/transactions` — log a buy/sell
   - `GET /api/v1/portfolio/positions` — current holdings with P&L
   - `GET /api/v1/portfolio/allocation` — sector/stock allocation breakdown
   - `GET /api/v1/portfolio/history` — portfolio value over time
   - `GET /api/v1/portfolio/dividends` — dividend income history
   - `GET /api/v1/recommendations` — UPGRADED with position sizing and reasoning
6. **Updated composite score** merging technical (50%) + fundamental (50%) signals
7. **Portfolio UI pages:**
   - Holdings table with P&L, allocation bars, vs target allocation
   - Allocation pie chart by sector
   - Portfolio value chart over time
   - Rebalancing suggestions with specific dollar amounts
   - "Action Required" panel showing today's recommendations
8. **Divestment rules engine:**
   - Trailing stop-loss alerts (configurable %, default from UserPreference)
   - Position concentration warnings (>5% of portfolio)
   - Sector concentration warnings (>30% of portfolio)
   - Fundamental deterioration flags (Piotroski drops below 4)
   - Cash reserve warnings (<10% cash)

### Success Criteria
Can log transactions, see portfolio P&L, get rebalancing suggestions.

---

## Phase 4: Chatbot + AI Agent (Weeks 7-8)

### Goal
Natural language interface that orchestrates all tools.

### Deliverables
1. **Database models:** ChatSession, ChatMessage
2. **`backend/agents/base.py`** — BaseAgent ABC with tool binding
2. **`backend/agents/general_agent.py`** — general Q&A + web search
3. **`backend/agents/stock_agent.py`** — stock analysis orchestrating all tools
4. **`backend/agents/loop.py`** — agentic tool-calling loop (max 15 iterations)
5. **`backend/agents/stream.py`** — NDJSON streaming to frontend
6. **`backend/routers/chat.py`** — `POST /api/v1/chat/stream` with SSE
7. **LLM fallback:** Groq primary for tool loops, Claude Sonnet for synthesis
8. **Chat UI in frontend:**
   - Message bubbles with markdown rendering
   - Streaming response display
   - Agent selector (General / Stock Analysis)
   - Tool execution status indicators
9. **Example queries that should work:**
   - "Analyse AAPL — give me technicals, fundamentals, and recommendation"
   - "How is my portfolio doing? Am I overexposed to any sector?"
   - "What are my top 3 buy candidates in Technology right now?"

### Success Criteria
Can ask natural language questions and get tool-backed, synthesized answers.

---

## Phase 5: Background Jobs + Alerts (Weeks 9-10)

### Goal
Pre-compute signals and send notifications.

### Deliverables
1. **Database models:** ModelVersion, ForecastResult (hypertable), MacroSnapshot (hypertable)
2. **Model versioning:**
   - ModelVersion table tracks training data range, hyperparameters, metrics, artifact path
   - Every ForecastResult links to model_version_id
   - `data/models/` directory for serialized model artifacts
   - Auto-increment version on retrain, only one active per (model_type, ticker)
3. **Celery worker + beat scheduler**
4. **`backend/tasks/refresh_data.py`** — nightly fetch for all watchlist tickers
5. **`backend/tasks/compute_signals.py`** — nightly signal computation + store snapshots
6. **`backend/tasks/run_forecasts.py`** — weekly Prophet forecast with model versioning:
   - Train Prophet per ticker → create ModelVersion row → save artifact → store ForecastResult
   - 3 horizons per ticker: 90d, 180d, 270d
7. **`backend/tasks/evaluate_forecasts.py`** — nightly forecast evaluation loop:
   - Find ForecastResult where target_date ≤ today AND actual_price IS NULL
   - Fill in actual_price and error_pct from StockPrice
   - Aggregate metrics per model_version_id → update ModelVersion.metrics
   - Trigger retrain if accuracy degrades below threshold
8. **`backend/tasks/check_alerts.py`** — check trailing stops, concentration, fundamentals
9. **`backend/tasks/generate_recommendations.py`** — daily recommendation generation:
   - Run after signal computation
   - Apply decision rules from recommendation engine
   - Factor in portfolio state + macro regime
   - Store RecommendationSnapshot rows with price_at_recommendation
10. **`backend/tasks/evaluate_recommendations.py`** — nightly recommendation evaluation:
    - Find recommendations where generated_at + horizon ≤ today AND no outcome exists
    - Evaluate at 3 horizons: 30d, 90d, 180d
    - Compute return vs SPY benchmark, alpha, action_was_correct
    - Store RecommendationOutcome rows
    - Requires SPY in stock universe with daily price data
11. **Notification system:**
    - Telegram bot integration (python-telegram-bot)
    - Daily morning briefing: "3 stocks hit buy signals, portfolio up 1.2%"
    - Real-time alerts for stop-loss triggers
12. **Macro overlay:**
    - FRED API integration for yield curve, VIX proxy, unemployment claims
    - Market regime indicator (risk-on / risk-off / neutral)
13. **Dashboard updates:** pre-computed data loads instantly, last-updated timestamps

### Success Criteria
Signals pre-computed nightly, Telegram alerts firing for configured triggers,
recommendation outcomes evaluated at 30/90/180d horizons with SPY benchmark.

---

## Phase 6: MCP + Deployment (Weeks 11-12)

### Goal
Extract tools as MCP servers and deploy to cloud.

### Deliverables
1. **MCP server wrappers** for: market-data, signal-engine, portfolio, screener
2. **Update agents** to call tools via MCP protocol
3. **Docker Compose** updated with all services containerized
4. **Terraform** for Azure deployment:
   - Azure Container Apps (API, workers, frontend)
   - Azure Database for PostgreSQL Flexible Server + TimescaleDB
   - Azure Cache for Redis
   - Azure Container Registry
5. **GitHub Actions CI/CD:**
   - Lint + test on PR
   - Build + push images on merge to main
   - Deploy to staging on merge, production on tag
6. **Observability:**
   - structlog JSON logging throughout
   - OpenTelemetry instrumentation on FastAPI + Celery
   - Azure Monitor / Application Insights

### Success Criteria
App running in Azure, MCP servers callable independently, CI/CD green.
