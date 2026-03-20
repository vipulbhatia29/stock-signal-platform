---
scope: project
category: domain
updated_by: session-39
phase: 4D (KAN-62 complete — enriched data layer shipped)
---

# Agent Tools Domain

## Architecture — Phase 4D: Plan→Execute→Synthesize

Full spec: `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md`
Plan: `docs/superpowers/plans/2026-03-20-phase-4d-agent-intelligence.md`
JIRA: Epic KAN-61, Stories KAN-62-68

### Three-Phase Agent Loop (replaces ReAct)
- **Planner (Sonnet):** Scope enforcement, intent classification, tool plan generation, stale data detection
- **Executor (mechanical, no LLM):** Calls tools via ToolRegistry, $PREV_RESULT resolution, retries, circuit breaker, 45s timeout
- **Synthesizer (Sonnet):** Confidence scoring (≥65%), bull/base/bear scenarios, collapsible evidence tree, portfolio personalization

### Data Materialization Principle
- ALL yfinance data materialized to DB during ingestion (ingest_stock is universal pipeline)
- Agent tools READ FROM DB, never yfinance at runtime
- Chat detects stale → "Let me refresh..." → ingest → all pages update

### Internal Tools (13 total — Session 39)
Existing (9): analyze_stock, compute_signals, get_recommendations, get_portfolio_exposure, screen_stocks, search_stocks, ingest_stock, web_search, get_geopolitical_events
Added Session 39 (4): get_fundamentals, get_analyst_targets, get_earnings_history, get_company_profile — all read from DB (materialized during ingestion)

### Ingest Pipeline Enrichment (Session 39)
Both `ingest_ticker` endpoint and `IngestStockTool` now call:
1. `fetch_fundamentals()` → growth, margins, ROE, market cap → Stock model
2. `fetch_analyst_data()` → target prices, buy/hold/sell → Stock model
3. `fetch_earnings_history()` → quarterly EPS → EarningsSnapshot table
4. `persist_enriched_fundamentals()` + `persist_earnings_snapshots()` write to DB

### New DB Objects (Session 39)
- Stock model: +15 columns (business_summary, employees, website, market_cap, revenue_growth, gross_margins, operating_margins, profit_margins, return_on_equity, analyst_target_mean/high/low, analyst_buy/hold/sell)
- EarningsSnapshot table: ticker+quarter PK, eps_estimate, eps_actual, surprise_pct
- Alembic migration 009

### MCP Adapters (4)
- EdgarTools → SEC filings (10-K, 10-Q, 8-K, 13F, Form 4)
- Alpha Vantage → news + sentiment
- FRED → macroeconomic data
- Finnhub → analyst ratings, ESG, social sentiment, supply chain

### MCP Server
- Streamable HTTP at `/mcp` (FastMCP on FastAPI)
- Same Tool Registry powers both chat endpoint and MCP server

### LLM Client (Phase 4D: tier routing)
- tier_config dict: planner → [Sonnet, GPT-4o-mini], synthesizer → [Sonnet, GPT-4o-mini]
- Executor is mechanical — no LLM calls
- Prompt caching for Sonnet system prompt + tool schemas

### Key Decisions
- Feature-flagged behind AGENT_V2=true
- No RAG — structured data via tools, unstructured (10-K) small enough for context
- No paid APIs — yfinance covers all enriched data
- Scope: financial context only, data-grounded only. Speculative/ungroundable declined.
- Cross-session memory: Level 1 (portfolio + preferences at session start)
- Feedback: thumbs up/down + trace logging via query_id