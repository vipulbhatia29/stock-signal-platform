# Product Requirements Document (PRD)

## Stock Signal Platform

**Version:** 5.0
**Author:** Vipul Bhatia
**Date:** April 2026

---

## 1. Executive Summary

Stock Signal Platform is a multi-user investment decision-support SaaS designed
for passive investors who want data-driven guidance without becoming full-time
traders. The platform automates signal detection across US equity markets,
tracks portfolios, forecasts price trends, and surfaces actionable buy/hold/sell
recommendations through both a visual dashboard and a conversational AI analyst.

The core philosophy is **"tell me what to do and show me why"** -- not just show data, but
synthesize multiple signals into clear, confidence-weighted recommendations with
full evidence lineage that a busy professional can act on in 5 minutes a day.

**Observability is the SaaS differentiator.** Users see how their subscription money
works. Every AI analysis shows cost, latency, tools used, and evidence quality.
This transparency builds trust and justifies subscription pricing.

**What makes this different from Bloomberg/TradingView:** Those tools are for technical users who want raw data. This platform is for passive investors who want a financial analyst that explains its reasoning, shows its sources, and personalizes advice to their portfolio.

---

## 2. Problem Statement

### Who is this for?

Passive investors -- professionals who:

- Have savings they want to grow beyond CDs, savings accounts, and index funds
- Don't have time to monitor markets daily or learn candlestick patterns
- Want to make informed stock picks but feel overwhelmed by the volume of data
- Are comfortable with technology and want to automate what can be automated
- Invest in US equity markets (stocks + ETFs)

### What problems does this solve?

1. **Signal overload.** Hundreds of indicators; investors don't know which matter. The platform computes relevant signals and synthesizes them into a single composite score.
2. **Emotional investing.** Retail investors buy high and sell low. The platform enforces discipline through rule-based alerts: trailing stop-losses, concentration warnings, and fundamental deterioration flags.
3. **No portfolio awareness.** Buy decisions made without considering existing holdings. The platform tracks actual holdings and factors allocation into every recommendation.
4. **Scattered information.** Price data, fundamentals, news, and portfolio are on different sites. The platform consolidates everything with an AI analyst that answers questions across all of it.
5. **Trust deficit.** AI financial advice is risky without verification. Every claim links to a specific data source, timestamp, and tool result.
6. **Black-box AI.** Users paying for AI analysis deserve to know what they're paying for. Per-query cost, latency, tool executions, and evidence quality are exposed.

---

## 3. Target User Persona

**Name:** Vipul (and investors like him)
**Age:** 30-50 | **Occupation:** Technology professional
**Investment experience:** Intermediate -- understands stocks and market cycles but not technical analysis or quantitative methods.
**Time available:** 15-30 minutes per day
**Markets:** US equities + ETFs | **Portfolio size:** $15K-$150K
**Goals:** Build long-term wealth, beat inflation, protect capital during downturns
**Pain points:** Doesn't know what to buy, when to buy it, when to sell, or how much to allocate

---

## 4. Product Vision

### Current State

A **Daily Intelligence Briefing** dashboard with 5 information zones, a stock screener with watchlist, enriched stock detail pages, portfolio tracking with FIFO P&L, Prophet-based price forecasting, and a **ReAct AI financial analyst** with 25 internal tools + 4 MCP adapters. Full authentication (Google OAuth, email verification, password reset, account deletion). Admin command center with LLM management and cost analytics.

### Near-term Vision

- **Phase F:** Stripe subscriptions with tiered pricing (Free/Pro/Premium)
- **Phase G:** Cloud deployment (containerized, managed DB, production observability)
- **Tech debt:** KAN-395-399 (convergence task wiring, SQL integration tests, router extraction)

### Recently Completed

- **Phase D:** Test suite overhaul ✅ — tiered architecture (T0-T5), 14 CI checks, 13 Semgrep rules, Playwright E2E, MSW integration, nightly Lighthouse. ~2,319 total tests.
- **Phase 8.6+: Forecast Intelligence** ✅ — 13 sprints across 4 specs (A/D/B/C), 19 JIRA tickets (KAN-369 Epic). See sections 5.20-5.23 below.

### Long-term Vision

A personal investment AI that learns from feedback over time, pre-computes daily briefings, and manages risk automatically. Multi-agent architecture triggered by eval data. The platform becomes your investment co-pilot -- with full transparency into what the AI is doing and what it costs.

---

## 5. Features & Requirements

Detailed functional specifications, acceptance criteria, and API contracts are in **[FSD.md](FSD.md)** and **[TDD.md](TDD.md)**. This section provides a product-level overview of each feature area.

### 5.1 Signal Engine (P0)

Computes 7 technical signals (RSI, MACD, SMA crossover, Bollinger Bands, Sharpe, annualized return, volatility) plus per-stock QuantStats risk analytics (Sortino, max drawdown, alpha, beta via `pandas-ta-openbb`). Fundamental scoring via Piotroski F-Score (0-9, scaled to 0-5 points). Synthesizes into a 0-10 composite score (50% technical, 50% fundamental). Additional fundamental data (P/E, PEG, margins, ROE, analyst targets) is materialized to DB during ingestion and accessible via API + agent tools, but not yet scored. See [FSD.md FR-3](FSD.md) for signal parameters and thresholds.

### 5.2 Recommendation Engine (P0)

Portfolio-aware buy/hold/sell decisions with position sizing. Equal-weight targeting, max 5% per position, max 30% per sector. Divestment rules engine with configurable thresholds (trailing stop-loss, concentration, weak fundamentals). See [FSD.md Section 2](FSD.md) for decision rules.

### 5.3 AI Financial Analyst -- ReAct Agent (P0)

A factual-first financial analyst using a ReAct loop (up to 8 iterations) with rule-based intent classification (8 categories), tool filtering, and parallel tool execution. Input guardrails (PII, injection blocking) and output guardrails (evidence verification, disclaimer injection). Every quantitative claim must trace to a tool result with timestamp. See [FSD.md Section 6](FSD.md) for architecture details and [TDD.md](TDD.md) for API contracts.

### 5.4 LLM Factory & Model Routing (P0)

Data-driven multi-provider LLM routing backed by the `llm_model_config` database table. Groq is primary for agent operations, Anthropic is fallback, OpenAI is emergency. Model configs (provider, tier, priority, rate limits, cost per 1K tokens) are managed via admin API -- no hardcoded cascade. Redis-backed token budgeting (TPM/RPM/TPD/RPD) with fail-open design. Three routing tiers: `cheap` (planning), `quality` (synthesis), `reason` (complex multi-step).

### 5.5 Dashboard -- Daily Intelligence Briefing (P0)

Navy dark command-center theme with 5 zones: Market Pulse (top movers, sector ETFs), Signals (buy-rated and action-required stocks), Portfolio (KPI tiles, health grade, sector allocation), Alerts (severity-colored grid), and News (portfolio-relevant articles with sentiment). Glassmorphism styling with green/orange/red glow system. See [FSD.md Section 3](FSD.md) for component details.

### 5.6 Stock Screener (P0)

Filterable, sortable table with TradingView-style column presets (Overview/Signals/Performance). Grid view with sparklines. Server-side pagination. Watchlist tab with badge count and URL deep-linking. See [FSD.md Section 4](FSD.md).

### 5.7 Portfolio Tracker (P1)

FIFO position tracking, unrealized P&L, sector allocation, portfolio value history (daily snapshots), dividend tracking, rebalancing suggestions with dollar amounts, divestment rules, and portfolio health scoring. See [FSD.md Section 5](FSD.md).

### 5.8 Portfolio Health Scoring (P1)

5-component health score: diversification, concentration risk, fundamental quality, momentum alignment, and income stability. Letter grade (A-F) with materialized history for trend tracking. Exposed as a dashboard KPI tile and available to the AI analyst via `portfolio_health` tool.

### 5.9 Stock Intelligence (P1)

Enriched stock detail pages with intelligence panel: insider trades, analyst upgrades/downgrades, EPS revisions, and short interest data. Available to the AI analyst via `get_stock_intelligence` tool. See [FSD.md Section 14](FSD.md).

### 5.10 AI-Powered Stock Recommendations (P1)

LLM-generated stock recommendations that synthesize signals, fundamentals, and market context into actionable buy suggestions with reasoning. Available via `recommend_stocks` tool. Distinct from the rule-based recommendation engine (5.2) -- this uses AI to generate narrative explanations.

### 5.11 Recommendation Scorecard (P1)

Tracks recommendation accuracy over time. Hit rates at 30/90/180-day horizons vs SPY benchmark. Enables users and the AI analyst to assess the platform's track record via `get_recommendation_scorecard` tool.

### 5.12 Geopolitical Events Analysis (P1)

GDELT-sourced geopolitical event monitoring relevant to portfolio holdings and market sectors. Available to the AI analyst via `get_geopolitical_events` tool for incorporating macro-political risk into analysis.

### 5.13 Market Briefing Synthesis (P1)

AI-synthesized market overview combining sector performance, top movers, and macro context into a digestible briefing. Available via `market_briefing` tool and surfaced in the dashboard Market Pulse zone.

### 5.14 Forecast Engine (P1)

Prophet-based price forecasting for stocks (90/180/270-day), 11 sector ETFs, and portfolio-level weighted aggregation. Biweekly retrain, daily predict-only refresh. **Per-ticker calibrated drift detection** (threshold = `backtest_mape × 1.5`, 3-failure self-healing demotion). News sentiment regressors (stock, sector, macro — feature-flagged). Recommendation evaluation at 30/90/180 days vs SPY. See [FSD.md FR-11](FSD.md).

### 5.15 Admin Command Center (P1)

**5-zone** operational dashboard: System Health (DB, Redis, Celery, Langfuse, MCP), API Traffic (RPS, latency percentiles, error rate), LLM Operations (tier health, costs, cascade rate, token budgets), Pipeline (run history, watermarks, next run), and **Forecast Health** (backtest accuracy %, sentiment coverage %). 3 drill-down sheets, 15s auto-polling, per-zone circuit breakers. Admin API for model config CRUD + reload without redeploy, chat session audit with full transcripts.

### 5.16 Observability Platform (P0)

Full-stack observability as a user-facing product feature. ObservabilityCollector for in-memory real-time metrics. Langfuse integration for deep tracing. Assessment framework with 20-query golden dataset and 5-dimension scoring. User-scoped visibility (users see own costs; admins see aggregate). See [FSD.md Section 8](FSD.md).

### 5.17 MCP Tool Server (P1)

Model Context Protocol server exposing all platform tools for external AI clients (Claude Code, Cursor). FastMCP subprocess with stdio transport for agent, Streamable HTTP at `/mcp` for external clients. JWT authentication. See [TDD.md](TDD.md) for protocol details.

### 5.18 Authentication & Account Management (P0)

Google OAuth 2.0, email verification (Resend API), self-service password reset, account settings page, and account deletion with 30-day soft-delete grace period. IDOR protection, refresh token blocklist, user-level token revocation. See [FSD.md Section 20](FSD.md).

### 5.19 Supporting Features (P1-P2)

- **Redis Cache Service:** 3-tier namespace (app/user/session), 4 TTL tiers, agent tool session caching, warmup + nightly invalidation.
- **News Aggregation:** Per-user news from Google RSS (dashboard) + 4-provider news sentiment pipeline (Finnhub, EDGAR, Fed RSS, Google News) with LLM scoring.
- **Sectors & Correlation:** Sector accordion, drill-down stocks, correlation matrix heatmap, sector convergence.
- **Search Autocomplete:** DB-first with Yahoo Finance supplementation for unknown tickers.
- **Background Processing & Alerts:** 11-step nightly pipeline + 4x/day news ingestion, in-app alerts with deduplication, gap recovery via watermarks.
- **Input/Output Guardrails:** PII detection, injection blocking, evidence verification, disclaimer injection, decline tracking.
- **Event-Driven Cache Invalidation:** `CacheInvalidator` with 7 event methods, batched Redis deletes, fire-and-forget. Admin can clear patterns via API.
- **Macro Overlay (partial):** FRED adapter for macro data. Market regime indicator planned but not yet surfaced.

### 5.20 Backtesting Engine (P1) ✅

Walk-forward validation for Prophet models. Expanding window generation with 5 accuracy metrics (MAPE, MAE, RMSE, direction accuracy, CI containment). Per-ticker calibrated drift thresholds (backtest_mape × 1.5) with self-healing demotion after 3 consecutive failures. AccuracyBadge component showing model tier (Excellent/Good/Fair/Poor). Admin-triggered backtest runs and seasonality calibration. See [FSD.md FR-24](FSD.md).

### 5.21 News Sentiment Pipeline (P1) ✅

4-provider news ingestion (Finnhub, SEC EDGAR, Fed RSS/FRED, Google News) with LLM-based sentiment scoring (GPT-4o-mini). 3 sentiment channels (stock, sector, macro) feeding Prophet as regressors. Exponential decay daily aggregation, quality flags, event type classification. 4x/day Celery ingestion + scoring. XML parsing uses `defusedxml` for XXE safety. See [FSD.md FR-25](FSD.md).

### 5.22 Signal Convergence & Divergence UX (P1) ✅

Multi-signal convergence analysis across 5+ indicators (RSI, MACD, SMA, Piotroski, Prophet forecast, news sentiment). Traffic light UX with signal-by-signal bullish/bearish/neutral display. Divergence alerts when forecast direction opposes technical signal majority. Historical hit rate computation. Natural-language rationale generation. Portfolio-level and sector-level aggregation. See [FSD.md FR-26](FSD.md).

### 5.23 Portfolio Forecast — BL + Monte Carlo + CVaR (P1) ✅

Portfolio-level forecasting combining Black-Litterman allocation (Idzorek view confidences, Prophet views as inputs), vectorized Monte Carlo simulation (10K paths, Cholesky decomposition), and Conditional Value at Risk (95th + 99th percentile). Frontend: BLForecastCard, MonteCarloChart (fan chart), CVaRCard. See [FSD.md FR-27](FSD.md).

---

## 6. Non-Functional Requirements

### Performance

| Metric | Target |
|--------|--------|
| Dashboard page load | <2 seconds (pre-computed data) |
| Signal computation | <5 seconds per ticker |
| Chat response (simple) | <3 seconds |
| Chat response (full analysis) | <30 seconds |
| API response (cached) | <100ms |
| API response (uncached) | <200ms |

### Scalability

Up to 500 tracked tickers, 100 portfolio positions per user, 100 concurrent users (multi-worker Uvicorn). Redis-backed token budgeting scales across N workers.

### Security

JWT with httpOnly cookies, direct bcrypt hashing, IDOR protection, input/output guardrails, refresh token blocklist with JTI rotation, user-level token revocation, Google OAuth with state+nonce CSRF, email verification soft-block, single-use password reset tokens, soft-delete + 30-day hard-purge. See [FSD.md Section 20](FSD.md) for full security spec.

### Observability

Structured tracing on every agent query (ObservabilityCollector + Langfuse). Per-query cost tracking, per-tool execution logging, tier health monitoring, fallback rate tracking, assessment framework with golden dataset validation.

### Data

Stock price history: 10+ years. Signal snapshots: retained indefinitely. Portfolio transactions: immutable audit trail. LLM/tool execution logs: full trace. User data: minimal PII, GDPR-style deletion on request.

### Cost

AI analyst: ~$0.03-0.05 per comprehensive analysis (2-4 LLM calls). Model tiering routes simple queries to cheap models. Per-query cost visible to users.

---

## 7. Out of Scope

- Real-time tick-by-tick data or intraday trading signals
- Broker integration or automated trade execution
- Options, futures, crypto, forex, or commodities
- Social features (following other investors, public portfolios)
- Mobile native app (responsive web only)
- RAG over historical SEC filings (current 10-K only)
- Price predictions ("Will AAPL hit $300?")
- Multi-currency portfolio consolidation

---

## 8. Success Metrics

### Core Product Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Recommendation hit rate | >60% of BUY recs beat SPY at 90 days | `RecommendationOutcome` evaluation pipeline |
| AI analyst trust | >80% thumbs-up rate | `ChatMessage` feedback ratio |
| Evidence quality | 100% of quantitative claims have tool citations | Post-synthesis validation in guardrails |
| Alert usefulness | >80% of alerts lead to a review action | Alert-to-action ratio tracking |

### Agent Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Query cost (median / p95) | <$0.05 / <$0.15 | `LLMCallLog` aggregation per `query_id` |
| Query latency (median / p95) | <10s / <30s | `ObservabilityCollector` per query |
| Assessment pass rate | >85% on golden dataset | Weekly CI eval (5-dimension scoring) |
| Hallucination rate | 0% | Grounding dimension in assessment |
| Tool selection accuracy | >90% correct per intent | `tool_selection` dimension |
| Fallback rate | <5% cascade to backup provider | `fallback_rate_last_60s()` metric |

---

## 9. Technical Architecture Summary

See **[TDD.md](TDD.md)** for detailed technical design and API contracts.

- **Monolith-first**, microservice-ready (clean domain boundaries via service layer)
- **PostgreSQL + TimescaleDB** for operational and time-series data (30 tables, 4 hypertables)
- **Redis** for caching (event-driven invalidation), token budgeting, refresh token blocklist, pipeline state, and Celery brokering
- **FastAPI** (async) -- 19 router modules + service layer (12 services)
- **Next.js** App Router with Tailwind v4 + shadcn/base-ui (16 hooks, 29 components)
- **ReAct agent** with rule-based intent classification, LLM Factory (DB-driven model configs), and 25+4 tools
- **Celery Beat** nightly 11-step pipeline + 4x/day news sentiment + weekly warm data, with self-healing gap recovery
- **Prophet** forecasting with per-ticker calibrated drift detection, walk-forward backtesting, news sentiment regressors
- **Black-Litterman + Monte Carlo + CVaR** portfolio forecasting
- **4-provider news pipeline** (Finnhub, EDGAR, Fed RSS, Google News) with LLM-based sentiment scoring
- **Signal convergence** analysis across 5+ indicators with divergence alerting and rationale generation
- **Langfuse** tracing + ObservabilityCollector + HttpMetricsMiddleware + assessment framework

---

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| yfinance rate limiting or API changes | Cache in DB; `ingest_stock` is sole touchpoint; can swap to FMP without changing tools |
| LLM costs escalate | Token budgeting per model; tiered routing; per-query cost tracking; subscription tiers offset cost |
| Composite score poorly calibrated | Track via `RecommendationOutcome`; iterate weights; thumbs feedback; weekly assessment |
| Agent hallucinates financial data | No claim without tool citation; evidence tree; scope enforcement; grounding scored at 100% |
| Scope creep into trading features | Hard boundary: analysis and signals only, no trade execution |
| Provider outages | 3-provider cascade with automatic failover; health monitoring; fallback rate tracking |

---

## 11. Glossary

| Term | Definition |
|------|-----------|
| Composite Score | Platform-specific 0-10 score combining technical (50%) + fundamental (50%) signals |
| ReAct | Reason + Act -- agent pattern where LLM interleaves thinking and tool calling |
| Evidence Tree | Hierarchical citation linking every analysis claim to its data source |
| LLM Factory | Data-driven model routing system with DB-backed configs and automatic provider failover |
| Token Budget | Rate limit tracker per model using Redis sliding windows |
| MCP | Model Context Protocol -- standard for AI tool interoperability |
| FIFO | First In, First Out -- method for calculating cost basis on stock positions |
| Piotroski F-Score | 9-point financial strength score based on profitability, leverage, efficiency |
| Golden Dataset | Curated set of 20 queries used to evaluate agent quality across 5 dimensions |
| Cache-Aside | Pattern: check cache -> miss -> query source -> store in cache -> return |

---

## Audit Log

| Date | Version | Changes |
|------|---------|---------|
| March 2026 | 1.0 | Initial draft |
| March 2026 | 1.1 | Synced with implementation reality (Session 13) |
| March 2026 | 2.0 | AI analyst architecture, enriched data layer, search, data materialization (Session 38) |
| March 2026 | 3.0 | Full platform refresh: ReAct agent, LLM Factory, observability, MCP, Redis cache, forecast engine, dashboard redesign, news, sectors (Session 75) |
| April 2026 | 4.0 | Audit cleanup: removed inline phase status, deduplicated FSD content (link instead), fixed LLM provider description to reflect DB-driven model configs, added missing features (geopolitical events, stock intelligence, AI recommendations, portfolio health, recommendation scorecard, market briefing, admin command center), added Phase 8.6+ Forecast Intelligence roadmap, added concrete success metrics (Session 87) |
| April 2026 | 5.0 | Phase 8.6+ COMPLETE: added sections 5.20-5.23 (backtesting, news sentiment, convergence UX, portfolio forecast). Updated vision (Phase D + 8.6+ done). Fixed: signal engine (Piotroski is active fundamental), forecast engine (calibrated drift), command center (4→5 zones), pipeline (9→11 steps), architecture (16→19 routers, 12 services). Added cache invalidation to supporting features. (Session 90) |
