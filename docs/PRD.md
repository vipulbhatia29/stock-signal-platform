# Product Requirements Document (PRD)

## Stock Signal Platform

**Version:** 1.0
**Author:** Vipul Bhatia
**Date:** March 2026
**Status:** Living Document (Phase 1-2 complete, Phase 2.5 complete)

---

## 1. Executive Summary

Stock Signal Platform is a personal investment decision-support system designed
for part-time investors who want data-driven guidance without becoming full-time
traders. The platform automates signal detection across US equity markets,
tracks portfolios, and surfaces actionable buy/hold/sell
recommendations through both a visual dashboard and a conversational AI interface.

The core philosophy is **"tell me what to do"** — not just show data, but
synthesize multiple signals into clear, confidence-weighted recommendations
that a busy professional can act on in 5 minutes a day.

---

## 2. Problem Statement

### Who is this for?

Part-time investors — professionals who:

- Have savings they want to grow beyond CDs, savings accounts, and index funds
- Don't have time to monitor markets daily or learn candlestick patterns
- Want to make informed stock picks but feel overwhelmed by the volume of data
- Are comfortable with technology and want to automate what can be automated
- Invest in US equity markets

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
consolidates everything into one place with an AI that can answer questions
across all of it.

**Problem 5: Learning curve.** Most investors want to learn but don't know where
to start. The platform serves as a learning companion — it explains why it's
recommending something, what the signals mean, and how they relate to each other.

---

## 3. Target User Persona

**Name:** Vipul (and investors like him)
**Age:** 30-50
**Occupation:** Technology professional
**Investment experience:** Intermediate — understands basics of stocks, mutual
funds, and market cycles but not technical analysis or quantitative methods.
**Time available:** 15-30 minutes per day for investment decisions
**Markets:** US equities
**Portfolio size:** $15K-$150K
**Goals:** Build long-term wealth, beat inflation meaningfully, protect capital
during downturns
**Pain points:** Doesn't know what to buy, when to buy it, when to sell, or how
much to allocate

---

## 4. Product Vision

### Phase 1-2 Vision (Current State)
A dashboard that shows me computed signals for my watchlist stocks and a screener
that ranks the broader universe by a composite score. I can see at a glance which
stocks are bullish and which are deteriorating.

> **Implemented in Sessions 1-12.** Dashboard, screener, stock detail page, and design system are built.

### Phase 3+ Vision (Full Product)
An intelligent system that knows my portfolio, monitors the market continuously,
and proactively tells me: "AAPL hit oversold with bullish MACD divergence.
You're underweight in Tech sector. Consider adding $5K. Here's why." I review for
5 minutes and act.

### Long-term Vision
A personal investment AI that learns from my decisions over time, backtests
strategies before recommending them, and manages risk automatically. The
platform becomes my investment co-pilot.

---

## 5. Features & Requirements

### 5.1 Signal Engine (P0 — Must Have)

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

> **Status:** Not yet implemented. Planned for Phase 3 (see FSD FR-5.1).

| Signal | Threshold | Interpretation |
|--------|----------|----------------|
| P/E Ratio | vs 5Y avg and sector | Undervalued / Fair / Overvalued |
| PEG Ratio | <1 favorable | Cheap relative to growth |
| Free Cash Flow Yield | FCF / Market Cap | Higher = better; compare to sector |
| Debt-to-Equity | <1 preferred | Financial health indicator |
| Interest Coverage | >2x safe | Can the company service its debt? |
| Piotroski F-Score | 0-9 scale | 7-9 strong; <4 weak |

**Composite Score:**

A single 0-10 score combining technical and fundamental signals with
configurable weights. Phase 1 implementation: 100% technical signals (4 indicators at 2.5 points each, 0-10 scale). Phase 3 will add fundamental signals and rebalance to configurable weights (see FSD FR-5.2).
Signal confluence (when multiple signals agree) amplifies the score.

**Acceptance Criteria:**
- Can compute all signals for any valid US stock ticker
- Signals are labeled consistently (bullish/bearish/neutral or equivalent)
- Composite score reflects confluence of signals
- Results are stored in database for historical tracking
- Computation completes in <5 seconds per ticker

### 5.2 Recommendation Engine (P0 — Must Have)

> **Implementation status:** Phase 1 delivers basic score-threshold recommendations only: Score ≥8 → BUY, 5-7 → WATCH, <5 → AVOID. No portfolio awareness, no position sizing, no macro regime. Full portfolio-aware recommendations planned for Phase 3.

**Description:** Transform raw signals into actionable buy/hold/sell decisions
that factor in portfolio context, macro regime, and position sizing.

This is the core differentiator — the "tell me what to do" layer. Without this,
the platform is just another dashboard showing data.

**Decision Rules:**

| Condition | Action | Confidence |
|-----------|--------|------------|
| Composite ≥8 + not overweight + macro not Risk-Off | **BUY** | High |
| Composite ≥8 + macro Risk-Off | **BUY** | Low (flagged) |
| Composite ≥8 + already overweight (>5% portfolio) | **HOLD** | High |
| Composite 5-7 + currently held | **HOLD** | Medium |
| Composite 5-7 + not held | **WATCH** | Medium |
| Composite <5 + currently held | **SELL** | Medium |
| Composite <5 + trailing stop breached | **SELL** | High |
| Piotroski drops below 4 + currently held | **SELL** | High |

**Position Sizing:**
- Target allocation: equal-weight across recommended positions
- Maximum per position: 5% of total portfolio value
- Suggested buy amount: (target allocation - current allocation) × portfolio value
- Minimum trade size: $100 (ignore recommendations below this)
- Cash reserve: always maintain at least 10% cash

**Requirements:**
- Generate daily recommendations after signal computation
- Each recommendation includes: action, confidence level, reasoning summary,
  suggested dollar amount, and the signals that drove the decision
- "Action Required" section on dashboard showing only items needing attention
- Recommendations respect portfolio context (won't say "buy" if overexposed)
- Macro regime adjusts confidence (not the action itself)

**Acceptance Criteria:**
- Every recommendation traces back to specific signals and portfolio state
- No recommendation is generated without current signal data (<24h old)
- Position sizing respects all caps (5% position, 30% sector, 10% cash)
- User can see reasoning for every recommendation

### 5.3 Stock Dashboard (P0 — Must Have)

**Description:** Visual overview of tracked stocks with current signals.

**Requirements:**
- Watchlist view with stock cards showing: ticker, price, sentiment badge,
  composite score, last updated
- Sector filter toggle (Technology, Healthcare, Financials, etc.)
- Click-through to detailed signal view per stock
- Signal history chart showing how signals changed over time
- Add/remove tickers from watchlist

**Acceptance Criteria:**
- Dashboard loads in <2 seconds with pre-computed data
- Supports at least 50 tracked stocks without performance degradation
- Responsive layout (works on desktop and tablet)

### 5.4 Screener (P0 — Must Have)

**Description:** Filter and rank the stock universe by signal criteria.

**Requirements:**
- TradingView-style column preset tabs: Overview (Ticker, Name, Sector, Price, Change%, Score), Signals (Ticker, RSI, MACD, SMA, Bollinger, Score), Performance (Ticker, Return, Volatility, Sharpe, Score). Also includes grid view with sparkline cards.
- Filter by: RSI state, MACD state, Sector, Composite Score range, Index
- Sort by any column
- Highlight rows based on composite score thresholds:
  - Green (≥8): Strong buy candidate
  - Yellow (5-7): Watch
  - Red (<5): Avoid or sell

**Acceptance Criteria:**
- Screener uses server-side pagination and filtering via `GET /api/v1/stocks/signals/bulk`. Supports index, RSI, MACD, sector, and composite score range filters.
- Can screen at least 200 stocks
- Results match manual signal computation

### 5.4a Stock Index Management (Built in Phase 2)

System maintains S&P 500, NASDAQ-100, and Dow 30 as first-class `StockIndex` entities with membership tracking. Dashboard shows index cards; screener filters by index.

### 5.4b On-Demand Data Ingestion (Built in Phase 2)

`POST /api/v1/stocks/{ticker}/ingest` fetches OHLCV data from yfinance, computes signals, and stores results. Delta fetch if data exists. Rate-limited to 5 requests/minute.

### 5.4c Design System (Built in Phase 2.5)

Bloomberg-inspired dark mode, semantic color tokens (OKLCH), financial-specific components (Sparkline, SignalMeter, MetricCard, ChangeIndicator, Breadcrumbs), chart design system with `useChartColors()` hook, responsive layouts, and entry animations with `prefers-reduced-motion` support.

### 5.5 Portfolio Tracker (P1 — Should Have)

**Description:** Track actual investment positions with real-time P&L.

**Requirements:**
- Log buy/sell transactions: ticker, date, quantity, price, fees
- Current holdings view: ticker, avg cost, current price, P&L ($ and %),
  allocation % of portfolio
- Sector allocation breakdown (pie chart)
- Historical portfolio value chart (from nightly portfolio snapshots)
- Cost basis tracking (FIFO method)
- Dividend income tracking: record dividend payments, show yield,
  total income over time
- Stock split handling: adjust historical quantities and cost basis
  automatically when splits are detected

**Position Sizing Integration:**
- Show current allocation vs target allocation per position
- Highlight over/under-weight positions
- Suggested rebalancing trades with dollar amounts

**Rules Engine:**
- Trailing stop-loss: configurable per stock (default 20%), alert when breached
- Position concentration: alert when any stock >5% of portfolio
- Sector concentration: alert when any sector >30% of portfolio
- Fundamental deterioration: alert when Piotroski drops below 4
- Cash reserve: alert when cash drops below 10% of portfolio

**Acceptance Criteria:**
- P&L calculations are accurate to the cent
- Allocation percentages sum to 100%
- Alerts fire correctly based on configured thresholds
- Can handle portfolios of up to 50 positions

### 5.6 AI Chatbot — Financial Intelligence Platform (P1 — Should Have)

**Description:** Three-layer financial intelligence platform: consume external data via MCP servers, enrich in backend with caching and cross-source analysis, expose as reusable MCP server. The chatbot is the first consumer, not the last.

**Requirements:**
- Natural language input with streaming response (NDJSON/SSE)
- Agent can call platform tools AND external data sources across 5 layers:
  - Layer 1: Fundamentals (existing DB — signals, Piotroski, portfolio)
  - Layer 2: SEC Filings (10-K, 10-Q, 13F, insider trades via EdgarTools MCP)
  - Layer 3: News + Sentiment (Alpha Vantage MCP, social sentiment via Finnhub)
  - Layer 4: Macro + Geopolitical (FRED MCP for macro data, GDELT for geopolitical events)
  - Layer 5: Analyst + Alternative (analyst ratings, ESG, supply chain via Finnhub)
- Multi-step reasoning: a single question can trigger 3-5+ tool calls across layers
- Markdown-formatted responses with embedded data tables
- Agent selector: General (web search, Q&A) and Stock Analysis (full toolkit)
- Chat history preserved per session (24h expiry)
- Tool Registry with pluggable tools and MCPAdapter for external sources
- Warm data pipeline: pre-processed analyst consensus, FRED indicators, institutional holdings
- Graceful degradation: individual tool failures don't crash the response
- Few-shot prompted agents for reliable tool selection
- Exposed as MCP server at `/mcp` (Streamable HTTP) for Claude Code, Cursor, future apps

**Example Interactions:**

| User Says | Agent Does |
|-----------|-----------|
| "Analyse AAPL" | Fetches signals → gets 10-K risk factors → fetches news sentiment → gets analyst ratings → synthesizes report |
| "How is my portfolio doing?" | Reads positions → computes P&L → checks sector exposure → gets macro context → summarizes |
| "What should I buy in Tech?" | Screens Technology sector → checks analyst consensus → reviews macro environment → checks portfolio overlap → recommends top 3 |
| "How exposed am I to the Iran situation?" | Fetches geopolitical events → maps to affected sectors → calculates portfolio exposure → gets oil/treasury data → synthesizes risk assessment |
| "Show me MSFT's insider trading" | Fetches Form 4 data → summarizes recent insider buys/sells → contextualizes with price action |

**Acceptance Criteria:**
- Response starts streaming within 2 seconds
- Multi-tool queries complete within 15 seconds
- Agent correctly identifies which tools to call based on user intent
- No hallucinated data — all numbers come from tool calls
- MCP server at `/mcp` callable by external MCP clients
- Graceful degradation when external data sources are unavailable

### 5.7 Price Forecasting (P1 — Should Have)

**Description:** Forward-looking price projections using Facebook Prophet.

**Requirements:**
- Generate 3-month, 6-month, and 9-month price targets
- 80% confidence interval bands
- Factor in US market holidays (NYSE/NASDAQ calendar)
- Visualize forecast chart with historical data overlay
- Cache forecasts (recompute weekly, not on every request)

**Acceptance Criteria:**
- Forecast generates in <10 seconds per ticker
- Confidence intervals are reasonable (not absurdly wide or narrow)
- Holiday calendar is correct for NYSE/NASDAQ

### 5.8 Background Processing & Alerts (P2 — Nice to Have)

**Description:** Automated nightly data refresh and proactive notifications.

**Requirements:**
- Nightly job: refresh OHLCV data for all watchlist tickers
- Nightly job: recompute all signals and store snapshots
- Weekly job: update Prophet forecasts
- Daily job: check all alert rules (stop-loss, concentration, deterioration)
- Notification channels: Telegram bot, email (future: push notifications)
- Morning briefing: summary of overnight signal changes, portfolio P&L,
  any triggered alerts

**Acceptance Criteria:**
- All nightly jobs complete within 30 minutes for 200 tickers
- Alerts are delivered within 5 minutes of trigger
- No duplicate alerts for the same condition within 24 hours

### 5.9 Macro Overlay (P2 — Nice to Have)

**Description:** Market regime indicators to calibrate overall risk exposure.

**Signals:**

| Indicator | Source | Interpretation |
|-----------|--------|----------------|
| Yield Curve (10Y-2Y) | FRED API | Inversion = recession warning |
| VIX | Yahoo Finance | >30 = high fear (contrarian buy) |
| Unemployment Claims | FRED API | Rising trend = economic weakening |
| Fed Funds Rate | FRED API | Cuts = bullish; Hikes = headwinds |

**Requirements:**
- Dashboard widget showing current macro regime: Risk-On / Neutral / Risk-Off
- Macro overlay adjusts recommendation confidence (bullish signals in Risk-Off
  regime should be flagged as lower confidence)

### 5.10 MCP Tool Server (P1 — Pulled forward to Phase 4B)

**Description:** Expose platform intelligence as a single MCP server for external AI access. Originally Phase 6; pulled forward because the Tool Registry (Phase 4B core) is the same abstraction the MCP server exposes.

**Requirements:**
- Single MCP server at `/mcp` using Streamable HTTP transport
- Exposes all Tool Registry tools (internal + proxied external) via MCP protocol
- Tools callable by Claude Code, Cursor, or any MCP-compatible client
- Authenticated via JWT (same auth as REST API)
- Same business logic as chatbot tools — MCP is just a transport layer

---

## 6. Non-Functional Requirements

### Performance
- Dashboard page load: <2 seconds (with pre-computed data)
- Signal computation: <5 seconds per ticker
- Chat response first token: <2 seconds
- API response time (cached data): <200ms

### Scalability
- Support up to 500 tracked tickers
- Support up to 100 portfolio positions
- Handle up to 10 concurrent users (personal use + friends/family)

### Security
- JWT-based authentication with token refresh
- Bcrypt password hashing (cost factor 12)
- All API endpoints authenticated (except login/register)
- Secrets in environment variables, never in code
- HTTPS in production

### Reliability
- Graceful handling of yfinance rate limits and timeouts
- LLM strategy: Groq (primary for agentic tool-calling loops — fast/cheap),
  Claude Sonnet (synthesis and final response), local model via LM Studio
  (offline fallback when APIs are down)
- Background jobs retry on failure (max 3 attempts)
- Database backups (daily in production)

### Data
- Stock price history: at least 10 years where available
- Signal snapshots: retain indefinitely (for backtesting later)
- Portfolio transactions: immutable audit trail
- User data: minimal PII, GDPR-style deletion on request

---

## 7. Out of Scope (Explicitly NOT Building)

- Real-time tick-by-tick data or intraday trading signals
- Broker integration or automated trade execution
- Options, futures, crypto, forex, or commodities
- Social features (following other investors, public portfolios)
- Mobile native app (responsive web only for now)
- Backtesting engine (future consideration)
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
| Portfolio awareness | User knows current allocation at all times | Dashboard engagement |

---

## 9. Technical Architecture Summary

See `CLAUDE.md` for detailed technical stack and conventions.

**Key architectural decisions:**
- Monolith-first, microservice-ready (clean domain boundaries)
- PostgreSQL + TimescaleDB for both operational and time-series data
- Redis for caching and background job brokering
- FastAPI (async) for all backend APIs
- Next.js single-page app (no iframes, no second framework)
- LangChain/LangGraph for AI agent orchestration
- Celery for background job scheduling
- MCP-ready tool design (extract to MCP servers in Phase 6)

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| yfinance rate limiting or API changes | Data fetch fails | Cache aggressively; add paid fallback API (Twelve Data) |
| LLM costs escalate with heavy chat usage | Monthly cost exceeds budget | Groq for routine tool loops; Claude only for synthesis; local models via LM Studio |
| Signal composite score is poorly calibrated | Bad recommendations | Start with rule-based scoring; track accuracy; iterate weights based on outcomes |
| Scope creep into trading features | Never ships | Hard boundary: analysis and signals only, no trade execution |
| Single-user system doesn't generalize | Can't share with others | Role-based auth from day one; multi-tenant data model |

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
| Composite Score | Platform-specific 0-10 score combining multiple signals |
| Signal Confluence | When multiple independent signals agree on direction |
| MCP | Model Context Protocol — standard for AI tool interoperability |
| TimescaleDB | PostgreSQL extension optimized for time-series data |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | March 2026 | Vipul Bhatia | Initial draft |
| 1.1 | March 2026 | Claude (Session 13) | Synced with implementation reality (Phases 1-2.5 complete) |
