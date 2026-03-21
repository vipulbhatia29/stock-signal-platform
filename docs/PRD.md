# Product Requirements Document (PRD)

## Stock Signal Platform

**Version:** 2.0
**Author:** Vipul Bhatia
**Date:** March 2026
**Status:** Living Document — Phases 1-4C complete, Phase 4D complete, Phase 4E/4F pending

---

## 1. Executive Summary

Stock Signal Platform is a personal investment decision-support system designed
for passive investors who want data-driven guidance without becoming full-time
traders. The platform automates signal detection across US equity markets,
tracks portfolios, and surfaces actionable buy/hold/sell
recommendations through both a visual dashboard and a conversational AI analyst.

The core philosophy is **"tell me what to do and show me why"** — not just show data, but
synthesize multiple signals into clear, confidence-weighted recommendations with
full evidence lineage that a busy professional can act on in 5 minutes a day.

**What makes this different from Bloomberg/TradingView:** Those tools are for technical users who want raw data. This platform is for passive investors who want a financial analyst that explains its reasoning, shows its sources, and personalizes advice to their portfolio.

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

### Current State (Phases 1-4D Complete)

A command-center dashboard with computed signals, a screener, portfolio tracking with FIFO P&L, and an **AI financial analyst** that:
- Plans its research before executing (shows you what it's investigating)
- Gathers data from 13 internal tools + 4 external data sources
- Synthesizes analysis with confidence scoring, bull/base/bear scenarios, and time horizon recommendations
- Shows full evidence lineage (every number traces to a source + timestamp)
- Personalizes to your portfolio (concentration risk, existing exposure)
- Refuses to answer questions it can't ground in data
- Detects stale data and auto-refreshes before analyzing

### Near-term Vision (Phases 4E-4F)

Security hardening + full UI redesign based on Lovable prototype. Stock detail page enriched with financials, analyst targets, earnings history, and company profile.

### Long-term Vision

A personal investment AI that learns from feedback over time, pre-computes daily briefings, and manages risk automatically. Subscription model for external users. The platform becomes your investment co-pilot.

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

**Fundamental Signals:** ✅ COMPLETE (Session 21+)

| Signal | Source | Implementation |
|--------|--------|----------------|
| P/E Ratio | yfinance | `fetch_fundamentals()` |
| PEG Ratio | yfinance | `fetch_fundamentals()` |
| Free Cash Flow Yield | yfinance | `fetch_fundamentals()` |
| Debt-to-Equity | yfinance | `fetch_fundamentals()` |
| Piotroski F-Score (0-9) | Computed from 9 criteria | `compute_piotroski()` |
| Revenue/Earnings Growth | yfinance `.info` | Materialized to `Stock` model (Phase 4D) |
| Gross/Operating/Profit Margins | yfinance `.info` | Materialized to `Stock` model (Phase 4D) |
| Return on Equity | yfinance `.info` | Materialized to `Stock` model (Phase 4D) |

**Composite Score:** 0-10 scale, 50% technical + 50% fundamental (Piotroski blending). Computed during ingestion, stored in `signal_snapshots` hypertable.

**Enriched Data (Phase 4D):** ✅ COMPLETE

All materialized into DB during ingestion — available to both stock detail page and AI analyst:

| Data | Source | Storage |
|---|---|---|
| Analyst price targets (current, high, low, mean) | yfinance | `Stock` model columns |
| Analyst consensus (buy/hold/sell counts) | yfinance | `Stock` model columns |
| Earnings history + surprise % | yfinance | `EarningsSnapshot` hypertable |
| Company profile (summary, employees, market cap) | yfinance | `Stock` model columns |
| Full income statement, balance sheet, cash flow | yfinance | Extended `FundamentalResult` |

### 5.2 Recommendation Engine (P0) ✅ COMPLETE

**Description:** Portfolio-aware buy/hold/sell decisions with position sizing.

**Decision Rules (implemented):**

| Condition | Action | Confidence |
|-----------|--------|------------|
| Composite ≥8 + not overweight | **BUY** | High |
| Composite ≥8 + at position cap (5%) | **HOLD** | High |
| Composite 5-7 + currently held | **HOLD** | Medium |
| Composite 5-7 + not held | **WATCH** | Medium |
| Composite <5 + currently held | **SELL** | Medium/High |

**Position Sizing:** Equal-weight targeting, max 5% per position, max 30% per sector, minimum $100 trade size. `GET /api/v1/portfolio/rebalancing` returns per-position BUY_MORE/HOLD/AT_CAP suggestions with dollar amounts.

**Divestment Rules Engine:** Configurable via user preferences — trailing stop-loss (20%), position concentration (5%), sector concentration (30%), weak fundamentals (composite <3). Alert badges on positions table.

### 5.3 Stock Dashboard (P0) ✅ COMPLETE

Navy dark command-center theme. StatTile grid (5 KPIs), AllocationDonut, watchlist cards with signal badges, sector filter, PortfolioDrawer, market status indicator.

### 5.4 Screener (P0) ✅ COMPLETE

Filterable, sortable table with TradingView-style column presets (Overview/Signals/Performance). Grid view with sparklines. Index/sector/RSI/MACD/score filters. Server-side pagination.

### 5.5 Portfolio Tracker (P1) ✅ COMPLETE

FIFO position tracking, unrealized P&L, sector allocation, portfolio value history (daily snapshots), dividend tracking (yield, annual income, payment history), rebalancing suggestions with dollar amounts, divestment rules with configurable thresholds.

### 5.6 AI Financial Analyst (P1) ✅ COMPLETE (Phase 4D)

**Description:** A factual-first financial analyst that plans research, gathers comprehensive data, and synthesizes personalized analysis with full evidence lineage.

**Architecture: Plan → Execute → Synthesize**

| Phase | Model | What it does |
|---|---|---|
| **Plan** | Claude Sonnet | Classifies intent, enforces scope, checks data freshness, generates ordered tool plan |
| **Execute** | Mechanical (no LLM) | Calls tools via ToolRegistry, validates results, handles retries/failures |
| **Synthesize** | Claude Sonnet | Builds confidence score, scenarios, evidence tree, personalizes to portfolio |

**Scope enforcement:** Financial context and peripherals only. Speculative questions ("Will AAPL hit $300?"), non-financial questions ("Capital of Uganda?"), and ungroundable questions ("Best stock to buy?") are politely declined. No tools fire, no cost incurred.

**Data grounding rule:** Every quantitative claim must trace to a tool result with timestamp. No claims from LLM parametric memory. Missing data is acknowledged, not filled in.

**Output format:**
- Confidence score (≥65% = actionable, show full analysis)
- Bull/base/bear scenarios with probability allocations
- Time horizon recommendations (3-month, 6-month, long-term)
- Collapsible "Show Evidence" section linking every claim to its source
- Conflicting signals framed as insight (high confidence + severe bear case = position conservatively)

**Stale data detection:** If stock data is older than latest market close, the agent auto-refreshes via `ingest_stock` before analyzing. User sees "Data is stale — let me refresh and analyze..." All pages update.

**13 Internal Tools:**
- `search_stocks` — resolve company name → ticker (DB + Yahoo Finance)
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

**4 External MCP Adapters:**
- EdgarTools → SEC filings (10-K sections, 13-F, insider trades, 8-K)
- Alpha Vantage → news + sentiment
- FRED → macroeconomic data (840K+ series)
- Finnhub → analyst ratings, ESG, social sentiment, supply chain

**Cost efficiency:** Sonnet called exactly twice per query (plan + synthesize). Executor is mechanical — no LLM cost. Prompt caching reduces input token costs ~90%.

**Cross-session memory:** Portfolio + preferences + watchlist injected at session start. Agent knows your holdings without being told.

**Feedback:** Thumbs up/down on every response, stored with full trace (query_id links to all LLM calls + tool executions).

**Error handling:** Tool failures → retry once → mark unavailable → continue with partial data. 3+ consecutive failures → circuit breaker. 45-second wall clock timeout. User sees honest messages: "I couldn't access [source], here's what I could gather."

**Feature-flagged:** Behind `AGENT_V2=true` for safe rollback.

### 5.7 Search Autocomplete (P1) ✅ COMPLETE

Search by company name or ticker. Local DB results first, supplemented by Yahoo Finance for stocks not yet in the platform. "Add from market" group with PlusCircle icon for external results. Debounced (300ms), includes ETFs.

### 5.8 MCP Tool Server (P1) ✅ COMPLETE

FastMCP at `/mcp` (Streamable HTTP), JWT auth, exposes all Tool Registry tools. Callable by Claude Code, Cursor, or any MCP client.

### 5.9 Price Forecasting (P2 — Future)

Facebook Prophet or similar. Deferred — no implementation yet.

### 5.10 Background Processing & Alerts (P2 — Partially Built)

Celery Beat: 30-min watchlist auto-refresh, daily analyst/FRED sync, weekly 13F sync. Telegram/email notifications not yet implemented.

### 5.11 Macro Overlay (P2 — Partially Built)

FRED adapter provides macro data (yields, oil, unemployment). Market regime indicator (Risk-On/Neutral/Risk-Off) not yet implemented as a dashboard widget.

### 5.12 Stock Detail Page Enrichment (P1 — Phase 4D.2, Pending)

Once enriched data is materialized in DB, the stock detail page should display:
- Revenue, net income, margins, growth rates
- Analyst price targets (current vs target range visualization)
- Earnings history (EPS estimate vs actual chart, beat/miss streak)
- Company profile (business summary, employees, website, market cap)
- Analyst consensus (buy/hold/sell bar chart)

---

## 6. Non-Functional Requirements

### Performance
- Dashboard page load: <2 seconds (with pre-computed data)
- Signal computation: <5 seconds per ticker
- Chat response — simple query: <3 seconds (1 LLM call)
- Chat response — full analysis: <30 seconds (plan + tools + synthesis)
- API response time (cached data): <200ms

### Scalability
- Support up to 500 tracked tickers
- Support up to 100 portfolio positions
- Handle up to 10 concurrent users (personal use initially, subscription later)

### Security
- JWT-based authentication with httpOnly cookies + header dual-mode
- Bcrypt password hashing (pinned 4.2.x for passlib compat)
- All API endpoints authenticated (except login/register)
- Secrets in environment variables, never in code
- HTTPS in production
- Phase 4E pending: MCP auth middleware, chat session IDOR fix, exception info leak fix

### Cost
- AI analyst: ~$0.03-0.05 per comprehensive analysis (Sonnet × 2 calls)
- Data: $0 (yfinance free tier, no paid APIs)
- Model tiering ready for subscription: can route simple queries to cheaper models

### Reliability
- Graceful handling of yfinance rate limits and timeouts
- LLM fallback chain: Claude Sonnet (primary) → GPT-4o-mini (fallback)
- Tool-level failure isolation — individual tool failures don't crash the response
- Circuit breaker after 3 consecutive tool failures
- Background jobs retry on failure (max 3 attempts)

### Data
- Stock price history: at least 10 years where available
- Signal snapshots: retain indefinitely (for backtesting later)
- Portfolio transactions: immutable audit trail
- Enriched data (fundamentals, targets, earnings): materialized in DB, refreshed during ingestion
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

| Metric | Target | How Measured |
|--------|--------|-------------|
| Daily active usage | Used at least 5 days/week by primary user | Login frequency |
| Signal accuracy | Composite score ≥8 stocks outperform market over 6 months | Backtest against historical data |
| Recommendation hit rate | >60% of BUY recommendations beat SPY at 90-day horizon | RecommendationOutcome evaluation |
| Decision speed | Investment decision made in <10 minutes | Self-reported |
| Alert usefulness | >80% of triggered alerts lead to a review action | Alert-to-action ratio |
| AI analyst trust | >80% of responses rated thumbs-up | Feedback ratio from ChatMessage |
| Evidence quality | 100% of quantitative claims have tool citations | Post-synthesis validation |
| Cost per query | <$0.10 per comprehensive analysis | LLMCallLog aggregation |

---

## 9. Technical Architecture Summary

See `CLAUDE.md` for detailed technical stack and conventions.
See `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md` for agent architecture.

**Key architectural decisions:**
- Monolith-first, microservice-ready (clean domain boundaries)
- PostgreSQL + TimescaleDB for both operational and time-series data
- Redis for caching and background job brokering
- FastAPI (async) for all backend APIs
- Next.js App Router with Tailwind + shadcn/ui
- LangGraph StateGraph for 3-phase agent orchestration (Plan→Execute→Synthesize)
- Celery for background job scheduling
- yfinance as sole data source (no paid APIs) — all data materialized to DB during ingestion
- MCP server at `/mcp` for external AI client access
- Feature-flagged agent V2 (`AGENT_V2=true`) for safe rollback

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| yfinance rate limiting or API changes | Data fetch fails | Cache aggressively in DB; `ingest_stock` is sole yfinance touchpoint; can swap to FMP ($14/mo) without changing tools |
| LLM costs escalate with heavy usage | Monthly cost exceeds budget | Sonnet called only 2x per query; prompt caching; model tiering ready for subscription |
| Signal composite score is poorly calibrated | Bad recommendations | Track accuracy via RecommendationOutcome; iterate weights; thumbs up/down feedback |
| Agent hallucinates financial data | User makes bad investment decision | No claim without tool citation; evidence tree; scope enforcement; speculative queries declined |
| Scope creep into trading features | Never ships | Hard boundary: analysis and signals only, no trade execution |
| Single-user system doesn't generalize | Can't monetize | Role-based auth from day one; multi-tenant data model; subscription tiers designed (deferred) |

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
| GPA | Goal-Plan-Action — agent pattern where LLM plans before executing |
| Evidence Tree | Hierarchical citation linking every analysis claim to its data source |
| Data Materialization | Storing fetched data in DB during ingestion, not querying APIs at runtime |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | March 2026 | Vipul Bhatia | Initial draft |
| 1.1 | March 2026 | Claude (Session 13) | Synced with implementation reality (Phases 1-2.5 complete) |
| 2.0 | March 2026 | Claude (Session 38) | Major update: Phases 3-4D complete. Added AI analyst architecture (Plan→Execute→Synthesize), enriched data layer, search autocomplete, data materialization, scope enforcement, evidence lineage, feedback loop, model tiering. Restructured to reflect current product state. |
