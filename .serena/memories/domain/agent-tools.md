---
scope: project
category: domain
updated_by: session-47-final
phase: Phase 5 COMPLETE — 20 internal tools, entity registry, 10 planner few-shots
---

# Agent Tools Domain

## Architecture — Phase 4D: Plan→Execute→Synthesize (unchanged)

Full spec: `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md`
JIRA: Epic KAN-61 (Done)

### Three-Phase Agent Loop
- **Planner (Sonnet):** Scope enforcement, intent classification, tool plan generation, pronoun resolution via EntityRegistry
- **Executor (mechanical, no LLM):** Calls tools via ToolRegistry, $PREV_RESULT resolution, retries, circuit breaker, 45s timeout. Updates EntityRegistry after each tool result.
- **Synthesizer (Sonnet):** Confidence scoring (≥65%), bull/base/bear scenarios, collapsible evidence tree, portfolio personalization

### Data Materialization Principle
- ALL yfinance data materialized to DB during ingestion (ingest_stock is universal pipeline)
- Agent tools READ FROM DB, never yfinance at runtime
- **Exception:** DividendSustainabilityTool calls yfinance on-demand (payout ratio not persisted)
- Chat detects stale → "Let me refresh..." → ingest → all pages update

### Internal Tools (20 total — Session 47)
**Original (9):** analyze_stock, compute_signals, get_recommendations, get_portfolio_exposure, screen_stocks, search_stocks, ingest_stock, web_search, get_geopolitical_events

**Added Session 39 (4):** get_fundamentals, get_analyst_targets, get_earnings_history, get_company_profile — all read from DB

**Added Session 47 (7):**
- `get_forecast` — reads ForecastResult for ticker, enriches with Sharpe direction + confidence level
- `get_sector_forecast` — maps sector name → ETF ticker, reads ETF forecast + sector stock count
- `get_portfolio_forecast` — weighted portfolio forecast via Portfolio→Position→ForecastResult
- `compare_stocks` — side-by-side signals + fundamentals + forecasts for 2-5 tickers
- `get_recommendation_scorecard` — wraps compute_scorecard(), hit rate + alpha + per-horizon breakdown
- `dividend_sustainability` — on-demand yfinance: payout ratio, FCF coverage, sustainability rating
- `risk_narrative` — structured risk assessment: signal + fundamental + forecast + sector ETF context

### Entity Registry (Session 47)
- `backend/agents/entity_registry.py` — session-scoped, not persisted to DB
- Tracks discussed tickers with recency ordering (ordered dict)
- `extract_from_tool_result()` — auto-populates from tool output (ticker, comparisons, contributions)
- `resolve_pronouns()` — "it" → last 1, "both" → last 2, "them" → last N
- Serialized as plain dicts in AgentStateV2 (LangGraph TypedDict)
- Plan node injects `resolved_pronouns` + `entity_context` into user_context for planner

### Planner Few-Shots (Session 47 additions: 10 new)
Forecast, sector forecast, portfolio forecast, comparison, pronoun resolution ("compare them", "what about it?"), scorecard, dividend sustainability, risk narrative

### MCP Adapters (4, unchanged)
EdgarTools, Alpha Vantage, FRED, Finnhub

### MCP Server
Streamable HTTP at `/mcp` (FastMCP on FastAPI)

### LLM Client (Phase 6A — data-driven cascade)
tier_config loaded from `llm_model_config` DB table at startup. Groq models cascade by priority with TokenBudget (80% threshold). Fallback: Groq → Anthropic → OpenAI. Admin API: `/api/v1/admin/llm-models`.

### Key Decisions
- V1 ReAct graph DELETED (Session 54). AGENT_V2 flag removed. V2 is the only path.
- Scope: financial context only, data-grounded only
- Cross-session memory: Level 1 (portfolio + preferences at session start)
- Feedback: thumbs up/down + trace logging via query_id
