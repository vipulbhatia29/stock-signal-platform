# Product Requirements Document (PRD)

## Stock Signal Platform

**Version:** 3.0
**Author:** Vipul Bhatia
**Date:** March 2026
**Status:** Living Document — Phases 1-8 complete, SaaS Launch Roadmap Phases A-B.5 (BU-1 through BU-4) complete

---

## 1. Executive Summary

Stock Signal Platform is a multi-user investment decision-support SaaS designed
for passive investors who want data-driven guidance without becoming full-time
traders. The platform automates signal detection across US equity markets,
tracks portfolios, forecasts price trends, and surfaces actionable buy/hold/sell
recommendations through both a visual dashboard and a conversational AI analyst.

The core philosophy is **"tell me what to do and show me why"** — not just show data, but
synthesize multiple signals into clear, confidence-weighted recommendations with
full evidence lineage that a busy professional can act on in 5 minutes a day.

**Observability is the SaaS differentiator.** Users see how their subscription money
works. Every AI analysis shows cost, latency, tools used, and evidence quality.
This transparency builds trust and justifies subscription pricing. Observability
is not an internal ops concern — it is a user-facing product feature.

**What makes this different from Bloomberg/TradingView:** Those tools are for technical users who want raw data. This platform is for passive investors who want a financial analyst that explains its reasoning, shows its sources, and personalizes advice to their portfolio — and lets them see exactly what the AI did and what it cost.

---

## 2. Problem Statement

### Who is this for?

Passive investors — professionals who:

- Have savings they want to grow beyond CDs, savings accounts, and index funds
- Don't have time to monitor markets daily or learn candlestick patterns
- Want to make informed stock picks but feel overwhelmed by the volume of data
- Are comfortable with technology and want to automate what can be automated
- Invest in US equity markets (stocks + ETFs)

### What problems does this solve?

**Problem 1: Signal overload.** There are hundreds of technical and fundamental
indicators. A part-time investor doesn't know which ones matter, how to compute
them, or how to interpret conflicting signals. The platform computes the signals
that matter and synthesizes them into a single composite score.

**Problem 2: Emotional investing.** Most retail investors buy high (FOMO) and
sell low (panic). They hold losers too long and sell winners too early. The
platform enforces discipline through rule-based alerts: trailing stop-losses,
position concentration warnings, and fundamental deterioration flags.

**Problem 3: No portfolio awareness.** Investors often make buy decisions without
considering what they already own. They end up overexposed to a single sector or
stock. The platform tracks actual holdings and factors allocation into every
recommendation.

**Problem 4: Information is scattered.** Price data is on one site, fundamentals
on another, news on a third, and your portfolio on a broker app. The platform
consolidates everything into one place with an AI analyst that can answer questions
across all of it — and shows exactly where every number came from.

**Problem 5: Trust deficit.** AI-generated financial advice is risky if you can't verify it. The platform shows full data lineage — every claim links to a specific data source, timestamp, and tool result. No hallucinated numbers, no opinions disguised as facts.

**Problem 6: Black-box AI.** Users paying for AI-powered analysis deserve to know what they're paying for. The platform exposes per-query cost, latency, tool executions, and evidence quality — turning the AI from a black box into a glass box.

---

## 3. Target User Persona

**Name:** Vipul (and investors like him)
**Age:** 30-50
**Occupation:** Technology professional
**Investment experience:** Intermediate — understands basics of stocks, mutual
funds, and market cycles but not technical analysis or quantitative methods.
**Time available:** 15-30 minutes per day for investment decisions
**Markets:** US equities + ETFs
**Portfolio size:** $15K-$150K
**Goals:** Build long-term wealth, beat inflation meaningfully, protect capital
during downturns
**Pain points:** Doesn't know what to buy, when to buy it, when to sell, or how
much to allocate

---

## 4. Product Vision

### Current State (Phases 1-8 Complete + SaaS Roadmap A-B.5)

A **Daily Intelligence Briefing** dashboard with 5 information zones (Market Pulse, Signals, Portfolio, Alerts, News), a stock screener with watchlist tab, enriched stock detail pages, portfolio tracking with FIFO P&L, Prophet-based price forecasting, and a **ReAct AI financial analyst** that:

- Classifies intent and selects relevant tools from 28 available (24 internal + 4 MCP adapters)
- Reasons through analysis in an iterative loop (observe → think → act → repeat)
- Gathers data from internal tools, SEC filings (Edgar), macro data (FRED), news (Alpha Vantage), analyst ratings (Finnhub), and web search (SerpAPI)
- Synthesizes analysis with confidence scoring, bull/base/bear scenarios, and time horizon recommendations
- Shows full evidence lineage (every number traces to a source + timestamp)
- Personalizes to your portfolio (concentration risk, existing exposure, dividend sustainability)
- Refuses to answer questions it cannot ground in data
- Detects stale data and auto-refreshes before analyzing
- Costs tracked per query — users see what the AI did and what it cost

**Platform infrastructure:**
- Multi-provider LLM factory with automatic cascade (Groq primary, Anthropic fallback, OpenAI emergency)
- Redis-backed token budgeting across multiple workers
- Langfuse tracing for deep query analysis
- Assessment framework with golden dataset (20 queries, 5-dimension scoring)
- Input/output guardrails (PII detection, injection blocking, disclaimer injection)
- Self-healing nightly pipeline (9-step chain: prices, signals, recommendations, forecasts, evaluation, drift detection, alerts, health snapshots, sector ETFs)
- MCP tool server for external AI client access (Claude Code, Cursor, etc.)

### Near-term Vision (SaaS Roadmap B.5-E)

- **BU-5-7:** Observability frontend (user-facing query analytics), admin dashboard (LLM management, cost analytics)
- **Phase C:** Google OAuth for real user signups
- **Phase D:** Stripe subscriptions with tiered pricing (Free/Pro/Premium)
- **Phase E:** Cloud deployment (containerized, managed DB, production observability)

### Long-term Vision

A personal investment AI that learns from feedback over time, pre-computes daily briefings, and manages risk automatically. Multi-agent architecture triggered by eval data (when single-agent quality drops below threshold for specific intent categories). The platform becomes your investment co-pilot — with full transparency into what the AI is doing and what it costs.

---

## 5. Features & Requirements

### 5.1 Signal Engine (P0) ✅ COMPLETE

**Description:** Compute technical and fundamental signals for any stock ticker
across US markets.

**Technical Signals:**

| Signal | Parameters | Output |
|--------|-----------|--------|
| RSI | Period: 14 | Value (0-100) + Label: Oversold (<30) / Neutral / Overbought (>70) |
| MACD | Fast: 12, Slow: 26, Signal: 9 | Histogram value + Label: Bullish / Bearish |
| SMA Crossover | 50-day and 200-day | Label: Golden Cross / Death Cross / Above / Below |
| Bollinger Bands | Period: 20, StdDev: 2 | Position: Upper / Middle / Lower |
| Sharpe Ratio | 252-day rolling | Value (annualized) |
| Annualized Return | 1Y trailing | Percentage |
| Volatility | 252-day rolling std | Percentage (annualized) |

**Fundamental Signals:**

| Signal | Source | Implementation |
|--------|--------|----------------|
| P/E Ratio | yfinance | `fetch_fundamentals()` |
| PEG Ratio | yfinance | `fetch_fundamentals()` |
| Free Cash Flow Yield | yfinance | `fetch_fundamentals()` |
| Debt-to-Equity | yfinance | `fetch_fundamentals()` |
| Piotroski F-Score (0-9) | Computed from 9 criteria | `compute_piotroski()` |
| Revenue/Earnings Growth | yfinance `.info` | Materialized to `Stock` model |
| Gross/Operating/Profit Margins | yfinance `.info` | Materialized to `Stock` model |
| Return on Equity | yfinance `.info` | Materialized to `Stock` model |
| Beta | yfinance `.info` | Materialized to `Stock` model |
| Dividend Yield | yfinance `.info` | Materialized to `Stock` model |
| Forward P/E | yfinance `.info` | Materialized to `Stock` model |

**Composite Score:** 0-10 scale, 50% technical + 50% fundamental (Piotroski blending). Computed during ingestion, stored in `signal_snapshots` hypertable. Thresholds: BUY >= 8, WATCH >= 5, AVOID < 5.

**Enriched Data:** All materialized into DB during ingestion — available to both stock detail page and AI analyst:

| Data | Source | Storage |
|---|---|---|
| Analyst price targets (current, high, low, mean) | yfinance | `Stock` model columns |
| Analyst consensus (buy/hold/sell counts) | yfinance | `Stock` model columns |
| Earnings history + surprise % | yfinance | `EarningsSnapshot` hypertable |
| Company profile (summary, employees, market cap) | yfinance | `Stock` model columns |
| Full income statement, balance sheet, cash flow | yfinance | Extended `FundamentalResult` |
| Price change % | Computed | `SignalSnapshot.change_pct` |

### 5.2 Recommendation Engine (P0) ✅ COMPLETE

**Description:** Portfolio-aware buy/hold/sell decisions with position sizing.

**Decision Rules (implemented):**

| Condition | Action | Confidence |
|-----------|--------|------------|
| Composite >= 8 + not overweight | **BUY** | High |
| Composite >= 8 + at position cap (5%) | **HOLD** | High |
| Composite 5-7 + currently held | **HOLD** | Medium |
| Composite 5-7 + not held | **WATCH** | Medium |
| Composite <5 + currently held | **SELL** | Medium/High |

**Position Sizing:** Equal-weight targeting, max 5% per position, max 30% per sector, minimum $100 trade size. `GET /api/v1/portfolio/rebalancing` returns per-position BUY_MORE/HOLD/AT_CAP suggestions with dollar amounts.

**Divestment Rules Engine:** Configurable via user preferences — trailing stop-loss (20%), position concentration (5%), sector concentration (30%), weak fundamentals (composite <3). Alert badges on positions table.

### 5.3 Dashboard — Daily Intelligence Briefing (P0) ✅ COMPLETE

Navy dark command-center theme redesigned as a **5-zone Daily Intelligence Briefing** for passive investors:

| Zone | Content | Data Source |
|------|---------|-------------|
| **Zone 1: Market Pulse** | Market status, top movers (gainers/losers with ScoreRing + MetricsStrip), sector ETF performance bars | `GET /market/briefing` |
| **Zone 2: Signals** | Buy-rated and action-required stocks as SignalStockCards with ActionBadge, score, metrics | `GET /stocks/signals/bulk` |
| **Zone 3: Portfolio** | KPI tiles (total value, day change, unrealized P&L, health grade), sector allocation, portfolio health history | `GET /portfolio/summary`, `GET /portfolio/health` |
| **Zone 4: Alerts** | Alert grid with severity-colored AlertTiles, unread badge, link to full alerts page | `GET /alerts` |
| **Zone 5: News** | Per-user news combining portfolio + recommendation tickers, sentiment badges | `GET /news/dashboard` |

Glassmorphism card styling with green/orange/red glow system. Watchlist relocated to Screener page as a tab with badge count.

### 5.4 Screener (P0) ✅ COMPLETE

Filterable, sortable table with TradingView-style column presets (Overview/Signals/Performance). Grid view with sparklines. Index/sector/RSI/MACD/score filters. Server-side pagination. **Watchlist tab** with badge count and URL deep-linking (`?tab=watchlist`).

### 5.5 Portfolio Tracker (P1) ✅ COMPLETE

FIFO position tracking, unrealized P&L, sector allocation, portfolio value history (daily snapshots), dividend tracking (yield, annual income, payment history), rebalancing suggestions with dollar amounts, divestment rules with configurable thresholds, portfolio health scoring with materialized history.

### 5.6 AI Financial Analyst — ReAct Agent (P0) ✅ COMPLETE

**Description:** A factual-first financial analyst that reasons through analysis in an iterative loop, gathering data and synthesizing personalized recommendations with full evidence lineage.

**Architecture: ReAct Loop (Reason + Act)**

| Component | What it does |
|---|---|
| **Intent Classifier** | Rule-based classification into 8 intent categories, ticker extraction, pronoun resolution. Out-of-scope and simple lookups bypass the LLM entirely (zero cost). |
| **Tool Filter** | Maps intent to relevant tool subset (stock: 8 tools, portfolio: 8, market: 5, comparison: 5). Planner sees <= 10 tools instead of 28. |
| **ReAct Loop** | Up to 8 iterations of observe-think-act. LLM decides which tools to call, observes results, reasons about what to do next. Parallel tool execution (up to 4 concurrent). 45-second wall clock timeout. |
| **Guardrails** | Input: PII detection (SSN, credit card), injection pattern blocking, length limits. Output: evidence verification, disclaimer injection, decline counter with escalation. |

**Scope enforcement:** Financial context and peripherals only. Speculative questions ("Will AAPL hit $300?"), non-financial questions ("Capital of Uganda?"), and ungroundable questions ("Best stock to buy?") are politely declined. No tools fire, no cost incurred.

**Data grounding rule:** Every quantitative claim must trace to a tool result with timestamp. No claims from LLM parametric memory. Missing data is acknowledged, not filled in.

**Output format:**
- Confidence score (>= 65% = actionable, show full analysis)
- Bull/base/bear scenarios with probability allocations
- Time horizon recommendations (3-month, 6-month, long-term)
- Collapsible "Show Evidence" section linking every claim to its source
- Conflicting signals framed as insight (high confidence + severe bear case = position conservatively)

**Stale data detection:** If stock data is older than latest market close, the agent auto-refreshes via `ingest_stock` before analyzing. User sees "Data is stale — let me refresh and analyze..." All pages update.

**24 Internal Tools:**
- `search_stocks` — resolve company name -> ticker (DB + Yahoo Finance)
- `ingest_stock` — universal data pipeline (prices + signals + fundamentals + targets + earnings + profile)
- `analyze_stock` — technical signals + composite score (from DB)
- `get_fundamentals_extended` — financials, growth, margins (from DB)
- `get_analyst_targets` — price targets + consensus (from DB)
- `get_earnings_history` — EPS history + surprise track record (from DB)
- `get_company_profile` — business summary, sector, employees (from DB)
- `compute_signals` — raw signal computation
- `get_recommendations` — portfolio-aware BUY/HOLD/SELL
- `get_portfolio_exposure` — sector allocation, P&L, concentration risk
- `screen_stocks` — filter by score, sector, RSI state
- `web_search` — general web search (SerpAPI)
- `get_geopolitical_events` — GDELT geopolitical events
- `get_forecast` — Prophet price forecast for a ticker (90/180/270 day)
- `get_sector_forecast` — sector ETF forecast
- `get_portfolio_forecast` — weighted portfolio forecast
- `compare_stocks` — side-by-side stock comparison
- `get_recommendation_scorecard` — recommendation accuracy metrics
- `dividend_sustainability` — dividend health and coverage analysis
- `risk_narrative` — risk factor narrative generation
- `portfolio_health` — portfolio health score breakdown
- `market_briefing` — market overview with sector performance
- `get_stock_intelligence` — upgrades, insider trades, EPS revisions, short interest
- `recommend_stocks` — AI-powered stock recommendations

**4 External MCP Adapters:**
- EdgarTools -> SEC filings (10-K sections, 13-F, insider trades, 8-K)
- Alpha Vantage -> news + sentiment
- FRED -> macroeconomic data (840K+ series)
- Finnhub -> analyst ratings, ESG, social sentiment, supply chain

**Cost efficiency:** ReAct loop calls LLM per iteration (typically 2-4 iterations). Intent classification and tool filtering are rule-based (zero LLM cost). Prompt caching reduces input token costs ~90%.

**Cross-session memory:** Portfolio + preferences + watchlist injected at session start. Agent knows your holdings without being told.

**Feedback:** Thumbs up/down on every response, stored with full trace (query_id links to all LLM calls + tool executions).

**Error handling:** Tool failures -> retry once -> mark unavailable -> continue with partial data. 3+ consecutive failures -> circuit breaker. 45-second wall clock timeout. User sees honest messages: "I couldn't access [source], here's what I could gather."

**Feature-flagged:** Behind `REACT_AGENT=true` (now default). Old Plan-Execute-Synthesize pipeline available behind flag for rollback.

### 5.7 LLM Factory & Tiered Providers (P0) ✅ COMPLETE

**Description:** Data-driven multi-provider LLM cascade with token budgeting and cost tracking.

**Multi-Provider Cascade:**

| Priority | Provider | Models | Use Case |
|----------|----------|--------|----------|
| 1 (Primary) | Groq | Llama, Mixtral variants | Fast, cheap — planner + reasoning tiers |
| 2 (Fallback) | Anthropic | Claude Sonnet | Quality fallback — synthesizer tier |
| 3 (Emergency) | OpenAI | GPT-4o-mini | Last resort — universal fallback |

**Token Budgeting:** Redis-backed sliding windows (Lua scripts) for TPM/RPM/TPD/RPD limits per model. 80% threshold triggers cascade to next provider. Fail-open design — Redis downtime does not block requests.

**DB-Backed Model Configs:** `llm_model_config` table stores provider, model, tier, priority, rate limits, and cost per 1K tokens. Admin API for CRUD + reload without redeploy.

**Cost Tracking:** Every LLM call logged with `cost_usd` computed from model pricing. Per-query cost aggregation available via admin API.

**Tier Routing:**
- `cheap` tier: fast models for planning, intent classification
- `quality` tier: stronger models for synthesis, reasoning
- `reason` tier: best models for complex multi-step reasoning

### 5.8 Observability Platform (P0) ✅ COMPLETE (Backend)

**Description:** Full-stack observability as a user-facing product feature, not just internal ops.

**ObservabilityCollector:** In-memory real-time metrics per query — latency, token counts, cost, tool executions, cache hits. Writes to `llm_call_log` and `tool_execution_log` tables for persistence.

**Langfuse Integration:** Parallel tracing system (does not replace ObservabilityCollector). Per-query trace with spans for each ReAct iteration, LLM generation, and tool execution. Feature-flagged on `LANGFUSE_SECRET_KEY`. Fire-and-forget — errors never propagate.

**Assessment Framework:**
- Golden dataset: 20 curated queries (10 intent, 5 reasoning, 3 failure handling, 2 behavioral)
- 5-dimension scoring: tool_selection, grounding, termination, external_resilience (deterministic) + reasoning_coherence (LLM judge)
- CI workflow: weekly automated + on-demand manual runs
- Assessment runner with dry-run and live modes

**Admin Endpoints:**
- LLM metrics: call counts, latency, cost by model and tier
- Tier health: healthy/degraded/down/disabled per provider
- Query analytics: per-query cost breakdown (model + tool costs)
- Fallback rate: cross-provider cascade frequency
- Chat audit: full session traces

**User-Scoped Visibility:** Regular users see their own query metrics (cost, latency, tools used). Admins see aggregate platform analytics. This transparency is the subscription value proposition.

### 5.9 MCP Tool Server (P1) ✅ COMPLETE

**Description:** Model Context Protocol server exposing all platform tools for external AI clients.

**Architecture:**
- FastMCP subprocess spawned at startup (stdio transport for agent, Streamable HTTP at `/mcp` for external clients)
- JWT authentication middleware
- All 28 tools (24 internal + 4 MCP adapters) available
- Own database connection pool (process isolation)
- Health endpoint with ok/degraded/disabled status
- Feature-flagged: `MCP_TOOLS=true` (default). Kill switch falls back to direct in-process calls.

**External Clients:** Claude Code, Cursor, or any MCP-compatible client can connect and use all platform tools with their own authentication.

### 5.10 Redis Cache Service (P1) ✅ COMPLETE

**Description:** Multi-tier caching layer for sub-100ms response on frequently accessed data.

**3-Tier Namespace:**
- `app:` — shared across all users (market data, sector ETFs, indexes)
- `user:{id}:` — per-user data (portfolio, recommendations, news)
- `session:{id}:` — per-chat session (tool results within a conversation)

**4 TTL Tiers:**
| Tier | TTL | Use Case |
|------|-----|----------|
| Volatile | 5 min | Real-time market data |
| Standard | 30 min | User portfolio, recommendations |
| Stable | 4 hours | Stock fundamentals, company profiles |
| Session | Chat lifetime | Agent tool results within a conversation |

**Agent Tool Caching:** 10 tools with session-level caching — repeated queries within a conversation return cached results instantly.

**Lifecycle:** Warmup on startup (market indexes, sector ETFs). Nightly invalidation during pipeline run. Partial invalidation on data changes (9 query key patterns).

### 5.11 Input/Output Guardrails (P1) ✅ COMPLETE

**Description:** Security and quality guardrails on all agent interactions.

**Input Guards:**
- Length limits (message + conversation history)
- PII detection: SSN patterns, credit card numbers, email addresses
- Injection pattern blocking: prompt injection, jailbreak attempts
- Control character sanitization

**Output Guards:**
- Evidence verification: quantitative claims must link to tool results
- Disclaimer injection on financial advice
- Decline counter: tracks consecutive declines per session, escalates on threshold

**Multi-turn Abuse:** `decline_count` tracked on ChatSession (DB-persisted). Escalation after repeated adversarial attempts.

### 5.12 Forecast Engine (P1) ✅ COMPLETE

**Description:** Statistical price forecasting for stocks, sectors, and portfolios.

**Prophet-Based Forecasting:**
- 90/180/270-day horizons for individual stocks
- 11 SPDR sector ETFs (XLK, XLF, XLV, XLE, XLC, etc.)
- Portfolio-level forecasts via weighted aggregation with correlation-based confidence bands

**Retraining Schedule:**
- Biweekly full retrain (Sunday 2 AM)
- Daily predict-only refresh
- Drift-triggered retrain when MAPE > 20% or volatility spike

**Evaluation:** BUY/SELL recommendations evaluated at 30/90/180 days vs SPY benchmark. `RecommendationOutcome` tracks actual performance.

**7 Conversational Forecast Tools:** `get_forecast`, `get_sector_forecast`, `get_portfolio_forecast`, `compare_stocks`, `get_recommendation_scorecard`, `dividend_sustainability`, `risk_narrative`.

### 5.13 Dashboard — Daily Intelligence Briefing (P0) ✅ COMPLETE

See Section 5.3 for full zone breakdown. Key components:

- **ScoreRing** — circular composite score visualization
- **ActionBadge** — BUY/SELL/HOLD/WATCH with color coding
- **MetricsStrip** — compact RSI/MACD/SMA/Sharpe chips per stock
- **SignalStockCard** — stock card with score, badge, metrics
- **MoverRow** — top gainer/loser with change %
- **PortfolioKPITile** — portfolio stat with sparkline trend
- **HealthGradeBadge** — A/B/C/D/F grade with color
- **SectorPerformanceBars** — horizontal bars per sector ETF
- **AlertTile** — severity-colored alert card
- **NewsArticleCard** — news item with sentiment badge

### 5.14 Stock Detail Page Enrichment (P1) ✅ COMPLETE

Enriched stock detail page with:
- Intelligence panel: upgrades/downgrades, insider trades, EPS revisions, short interest
- News feed with sentiment classification
- Benchmark comparison chart (vs SPY)
- Candlestick/line chart toggle (OHLC data)
- Price chart with 1M/3M/6M/1Y/5Y timeframe selector
- Signal breakdown cards + signal history chart
- Fundamentals card (P/E, PEG, FCF yield, D/E, Piotroski bar)
- Forecast card with confidence intervals

### 5.15 Search Autocomplete (P1) ✅ COMPLETE

Search by company name or ticker. Local DB results first, supplemented by Yahoo Finance for stocks not yet in the platform. "Add from market" group with PlusCircle icon for external results. Debounced (300ms), includes ETFs.

### 5.16 Background Processing & Alerts (P1) ✅ COMPLETE

Self-healing nightly pipeline (9-step chain): price fetch -> signal computation -> recommendation generation -> Prophet forecast -> evaluation -> drift detection -> alerts -> health snapshots -> sector ETF refresh. PipelineWatermark for gap recovery, PipelineRun for observability. In-app alerts with AlertBell dropdown (Popover + unread badge + severity colors). Alert deduplication via `dedup_key`.

### 5.17 News Aggregation (P1) ✅ COMPLETE

Per-user news endpoint combining portfolio tickers + recommendation tickers. Google RSS integration with `defusedxml` parsing. Keyword-based sentiment classification (bullish/bearish/neutral). Redis-cached per user (standard TTL). General market news included alongside ticker-specific articles.

### 5.18 Sectors & Correlation (P1) ✅ COMPLETE

Sectors page with: sector accordion (11 canonical sectors), drill-down stocks table per sector, correlation matrix heatmap with ticker chip selector. 3 backend endpoints. Sector name normalization (aliases + ETF mapping).

### 5.19 Macro Overlay (P2 — Partially Built)

FRED adapter provides macro data (yields, oil, unemployment). Market regime indicator (Risk-On/Neutral/Risk-Off) not yet implemented as a dashboard widget.

---

## 6. Non-Functional Requirements

### Performance
- Dashboard page load: <2 seconds (with pre-computed data)
- Signal computation: <5 seconds per ticker
- Chat response — simple query: <3 seconds (1 LLM call)
- Chat response — full analysis: <30 seconds (ReAct loop, 2-4 iterations)
- API response time (cached data): <100ms (Redis cache-aside)
- API response time (uncached data): <200ms

### Scalability
- Support up to 500 tracked tickers
- Support up to 100 portfolio positions per user
- Handle up to 100 concurrent users (multi-worker Uvicorn)
- Redis-backed token budgeting scales across N workers
- DB connection pool configurable via environment variables

### Security
- JWT-based authentication with httpOnly cookies + header dual-mode
- Direct bcrypt password hashing (passlib removed)
- All API endpoints authenticated (except login/register)
- Secrets in environment variables, never in code
- HTTPS in production
- IDOR protection: user-scoped data isolation on all detail endpoints
- Input guardrails: PII detection, injection blocking, control char sanitization
- Output guardrails: generic error messages (no `str(e)` in user-facing output)
- Redis refresh token blocklist with JTI rotation
- MCP auth middleware on tool server endpoints
- OIDC SSO support (feature-flagged, disabled when unconfigured)

### Observability
- Structured tracing on every agent query (ObservabilityCollector + Langfuse)
- Per-query cost tracking with model-level granularity
- Per-tool execution logging with cache hit tracking
- Tier health monitoring (healthy/degraded/down/disabled)
- Fallback rate tracking across provider cascades
- Assessment framework with golden dataset validation

### Multi-tenancy
- User-scoped data isolation on all endpoints (portfolio, alerts, chat, preferences)
- User-scoped observability (users see own query metrics, admins see all)
- Per-user news aggregation based on portfolio + recommendations
- Per-user cache namespace (`user:{id}:`)

### Cache
- Sub-100ms response on cached endpoints
- 4-tier TTL strategy (volatile 5m / standard 30m / stable 4h / session)
- 3 namespace tiers (app-shared / user-scoped / session-scoped)
- Warmup on startup, nightly invalidation, partial invalidation on writes

### Cost
- AI analyst: ~$0.03-0.05 per comprehensive analysis (ReAct loop, 2-4 LLM calls)
- Data: $0 base (yfinance free tier) + optional paid APIs (SerpAPI, Finnhub)
- Model tiering: simple queries routed to cheap models, complex queries to quality models
- Per-query cost visible to users (observability differentiator)

### Reliability
- Graceful handling of yfinance rate limits and timeouts
- LLM fallback chain: Groq (primary) -> Anthropic Sonnet (fallback) -> OpenAI GPT-4o-mini (emergency)
- Tool-level failure isolation — individual tool failures don't crash the response
- Circuit breaker after 3 consecutive tool failures
- Background jobs retry on failure (max 3 attempts)
- MCP tool server: 3-restart fallback to direct calls + health reporting
- Redis fail-open: cache/token budget failures do not block requests
- Pipeline self-healing: gap recovery via watermarks, partial success tracking

### Data
- Stock price history: at least 10 years where available
- Signal snapshots: retain indefinitely (for backtesting later)
- Portfolio transactions: immutable audit trail
- Enriched data (fundamentals, targets, earnings): materialized in DB, refreshed during ingestion
- Forecast models: versioned, biweekly retrain, drift-detected
- LLM call logs: full trace (model, tokens, cost, latency, cache_hit)
- Tool execution logs: full trace (tool, params, result summary, duration)
- User data: minimal PII, GDPR-style deletion on request

---

## 7. Out of Scope (Explicitly NOT Building)

- Real-time tick-by-tick data or intraday trading signals
- Broker integration or automated trade execution
- Options, futures, crypto, forex, or commodities
- Social features (following other investors, public portfolios)
- Mobile native app (responsive web only for now)
- RAG over historical SEC filings (current 10-K only)
- Price predictions ("Will AAPL hit $300?")
- Multi-year historical filing comparisons (high-token, deferred)
- Multi-currency portfolio consolidation

---

## 8. Success Metrics

### Core Product Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Daily active usage | Used at least 5 days/week by primary user | Login frequency |
| Signal accuracy | Composite score >= 8 stocks outperform market over 6 months | Backtest against historical data |
| Recommendation hit rate | >60% of BUY recommendations beat SPY at 90-day horizon | RecommendationOutcome evaluation |
| Decision speed | Investment decision made in <10 minutes | Self-reported |
| Alert usefulness | >80% of triggered alerts lead to a review action | Alert-to-action ratio |
| AI analyst trust | >80% of responses rated thumbs-up | Feedback ratio from ChatMessage |
| Evidence quality | 100% of quantitative claims have tool citations | Post-synthesis validation |

### Agent Quality Metrics

| Metric | Target | How Measured |
|--------|--------|-------------|
| Agent query cost (median) | <$0.05 | LLMCallLog aggregation per query_id |
| Agent query cost (p95) | <$0.15 | LLMCallLog aggregation per query_id |
| Agent latency (median) | <10 seconds | ObservabilityCollector per query |
| Agent latency (p95) | <30 seconds | ObservabilityCollector per query |
| Assessment pass rate | >85% on golden dataset | Weekly CI eval job (5-dimension scoring) |
| Hallucination rate | 0% | Grounding dimension in assessment framework |
| Tool selection accuracy | >90% correct tool set per intent | tool_selection dimension in assessment |
| Fallback rate | <5% of queries cascade to backup provider | fallback_rate_last_60s() metric |

---

## 9. Technical Architecture Summary

See `CLAUDE.md` for detailed technical stack and conventions.

**Key architectural decisions:**
- Monolith-first, microservice-ready (clean domain boundaries via service layer)
- PostgreSQL + TimescaleDB for both operational and time-series data
- Redis for caching, token budgeting, refresh token blocklist, and Celery brokering
- FastAPI (async) for all backend APIs — 16 router modules
- Next.js App Router with Tailwind v4 + shadcn/base-ui
- Navy dark command-center theme with Sora/JetBrains Mono fonts

**Agent Architecture:**
- ReAct loop (`agents/react_loop.py`): intent -> tool filter -> reason-act iterations -> response
- Rule-based intent classifier (8 categories, zero LLM cost for out-of-scope)
- LLM Factory: data-driven model cascade (Groq -> Anthropic -> OpenAI)
- Token budgeting: Redis sorted sets with Lua scripts, fail-open
- Input/output guardrails: PII, injection, disclaimer, decline tracking

**Data Pipeline:**
- Celery Beat nightly chain (9 steps)
- Prophet forecasting engine with drift detection
- All external data materialized to DB during ingestion (yfinance as primary source)
- MCP adapters for SEC (Edgar), macro (FRED), news (Alpha Vantage), ratings (Finnhub)

**Observability Pipeline:**
- ObservabilityCollector: in-memory metrics + DB persistence
- Langfuse: parallel tracing (feature-flagged, fire-and-forget)
- Assessment framework: golden dataset + 5-dimension scoring + CI job

**Cache Layer:**
- CacheService: 3-tier namespace, 4 TTL tiers, cache-aside pattern
- Agent tool session cache (10 tools)
- Warmup on startup, nightly invalidation

**External APIs:**
- yfinance (primary data source — free)
- SerpAPI (web search)
- GDELT (geopolitical events)
- Alpha Vantage (news + sentiment)
- Edgar/SEC (filings, insider trades)
- FRED (macroeconomic data)
- Finnhub (analyst ratings, ESG, supply chain)
- Google RSS (news aggregation)
- Wikipedia (company info)

**MCP Tool Server:**
- FastMCP subprocess (stdio transport for agent)
- Streamable HTTP at `/mcp` for external clients
- JWT authentication, health endpoint
- Phase 10 target: separate container on :8282

**CI/CD:**
- `ci-pr.yml`: 4 parallel jobs (backend-lint, frontend-lint, backend-test, frontend-test)
- `ci-merge.yml`: 4 sequential jobs (lint -> unit+api -> integration -> build)
- `ci-eval.yml`: weekly agent assessment + on-demand
- Pre-commit hooks: ruff check + ruff format + type checking
- Branch protection on `main` + `develop`

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| yfinance rate limiting or API changes | Data fetch fails | Cache aggressively in DB; `ingest_stock` is sole yfinance touchpoint; can swap to FMP ($14/mo) without changing tools |
| LLM costs escalate with heavy usage | Monthly cost exceeds budget | Token budgeting per model; model tiering (cheap for planning, quality for synthesis); per-query cost tracking; subscription tiers offset cost |
| Signal composite score is poorly calibrated | Bad recommendations | Track accuracy via RecommendationOutcome; iterate weights; thumbs up/down feedback; assessment framework validates quality weekly |
| Agent hallucinates financial data | User makes bad investment decision | No claim without tool citation; evidence tree; scope enforcement; speculative queries declined; grounding dimension scored at 100% |
| Scope creep into trading features | Never ships | Hard boundary: analysis and signals only, no trade execution |
| Single-user system doesn't generalize | Can't monetize | Multi-tenant data model; user-scoped isolation everywhere; Redis token budgets scale across workers; subscription tiers designed |
| Provider outages (Groq, Anthropic) | Agent unavailable | 3-provider cascade with automatic failover; health monitoring; fallback rate tracking |
| Multi-worker state inconsistency | Overspend on LLM rate limits | Token budgets in Redis (not in-memory); admin metrics read from DB (not process-local) |

---

## 11. Glossary

| Term | Definition |
|------|-----------|
| RSI | Relative Strength Index — momentum oscillator measuring speed of price changes |
| MACD | Moving Average Convergence Divergence — trend-following momentum indicator |
| SMA | Simple Moving Average — average price over N days |
| Piotroski F-Score | 9-point financial strength score based on profitability, leverage, efficiency |
| PEG | Price/Earnings to Growth ratio — P/E adjusted for earnings growth rate |
| FCF | Free Cash Flow — cash generated after capital expenditures |
| Composite Score | Platform-specific 0-10 score combining technical (50%) + fundamental (50%) signals |
| Signal Confluence | When multiple independent signals agree on direction |
| MCP | Model Context Protocol — standard for AI tool interoperability |
| TimescaleDB | PostgreSQL extension optimized for time-series data |
| ReAct | Reason + Act — agent pattern where LLM interleaves thinking and tool calling |
| Evidence Tree | Hierarchical citation linking every analysis claim to its data source |
| Data Materialization | Storing fetched data in DB during ingestion, not querying APIs at runtime |
| LLM Factory | Data-driven model cascade system with automatic provider failover |
| Token Budget | Rate limit tracker per model using Redis sliding windows |
| ObservabilityCollector | Per-query metrics aggregator (latency, tokens, cost, tools) |
| Golden Dataset | Curated set of 20 queries used to evaluate agent quality across 5 dimensions |
| Intent Classifier | Rule-based system that categorizes user queries into 8 intent types |
| Tool Filter | Maps classified intent to a subset of relevant tools (reduces planner cognitive load) |
| Cache-Aside | Pattern: check cache -> miss -> query source -> store in cache -> return |
| FIFO | First In, First Out — method for calculating cost basis on stock positions |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | March 2026 | Vipul Bhatia | Initial draft |
| 1.1 | March 2026 | Claude (Session 13) | Synced with implementation reality (Phases 1-2.5 complete) |
| 2.0 | March 2026 | Claude (Session 38) | Major update: Phases 3-4D complete. Added AI analyst architecture (Plan-Execute-Synthesize), enriched data layer, search autocomplete, data materialization, scope enforcement, evidence lineage, feedback loop, model tiering. Restructured to reflect current product state. |
| 3.0 | March 2026 | Claude (Session 75) | Full platform refresh through Phase 8 + SaaS Roadmap A-B.5. Added: observability as SaaS differentiator (Section 1+4), ReAct agent loop replacing Plan-Execute-Synthesize, LLM Factory with multi-provider cascade, observability platform (Langfuse + assessment framework), MCP tool server architecture, Redis cache service, input/output guardrails, forecast engine, dashboard redesign (5-zone Daily Intelligence Briefing), news aggregation, sectors page. Updated: 24 internal tools + 4 MCP adapters (was 13), agent quality metrics, non-functional requirements (observability, multi-tenancy, cache), technical architecture (ReAct loop, LLM tiering, cache layer, external APIs), risks (provider outages, multi-worker state). |
