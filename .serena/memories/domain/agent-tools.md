---
scope: project
category: domain
updated_by: session-56
phase: Phase 7 KAN-158/159/160 COMPLETE — 24 internal tools, guardrails, enriched data, response_type routing
---

# Agent Tools Domain

## Architecture — Plan->Execute->Synthesize (unchanged)

Full spec: `docs/superpowers/specs/2026-03-20-phase-4d-agent-intelligence-design.md`

### Three-Phase Agent Loop
- **Planner (Sonnet):** Scope enforcement, intent classification, tool plan generation, pronoun resolution via EntityRegistry, response_type routing (Phase 7)
- **Executor (mechanical, no LLM):** Calls tools via ToolRegistry, $PREV_RESULT resolution, retries, circuit breaker, 45s timeout. Tool param validation (ticker format, query sanitization — Phase 7 guardrails).
- **Synthesizer (Sonnet):** Confidence scoring (>=65%), bull/base/bear scenarios, evidence tree, portfolio personalization. Output validation: unsupported high-confidence claims downgraded (Phase 7 guardrails).

### Internal Tools (24 total — Session 56)
**Original (9):** analyze_stock, compute_signals, get_recommendations, get_portfolio_exposure, screen_stocks, search_stocks, ingest_stock, web_search, get_geopolitical_events

**Phase 4D (4):** get_fundamentals, get_analyst_targets, get_earnings_history, get_company_profile — all read from DB

**Phase 5 (7):** get_forecast, get_sector_forecast, get_portfolio_forecast, compare_stocks, get_recommendation_scorecard, dividend_sustainability, risk_narrative

**Phase 7 (4 — Session 56):**
- `portfolio_health` — HHI diversification, signal quality, Sharpe risk, income, sector balance -> 0-10 score + grade
- `market_briefing` — S&P 500/NASDAQ/Dow/VIX + 10 sector ETFs + portfolio news + upcoming earnings
- `get_stock_intelligence` — analyst upgrades/downgrades, insider transactions, earnings calendar, EPS revisions (wraps intelligence.py)
- `recommend_stocks` — multi-signal consensus (signals 35%, fundamentals 25%, momentum 20%, portfolio fit 20%)

### Phase 7 Guardrails (KAN-158)
- Input guard: length (2000 chars), control char stripping, PII detection (SSN/CC/phone), injection detection (10 patterns)
- Output guard: validate_synthesis_output (downgrade unsupported high confidence)
- Financial disclaimer auto-appended to every substantive response
- decline_count on ChatSession — session flagged after 5 declines
- Tool param validation: ticker format regex, search query URL rejection

### Phase 7 Data Enrichment (KAN-159)
- Stock model: beta, dividend_yield, forward_pe (migration 014, extracted during ingest)
- `backend/tools/news.py` — yfinance + Google News RSS (defusedxml for XXE)
- `backend/tools/intelligence.py` — upgrades, insider, earnings, EPS revisions
- API endpoints: GET /stocks/{ticker}/news, GET /stocks/{ticker}/intelligence (volatile cache)
- Dividend sync in ingest tool + nightly pipeline

### Planner response_type (KAN-160)
- Planner outputs `response_type`: stock_analysis | portfolio_health | market_briefing | recommendation | comparison
- Propagated through AgentStateV2 -> synthesize_node -> user_context
- 6 new few-shot examples for health, briefing, recommendations, intelligence

### Entity Registry (unchanged from Session 47)
- Session-scoped ticker tracking for pronoun resolution
- Serialized in AgentStateV2

### MCP Adapters (4, unchanged)
EdgarTools, Alpha Vantage, FRED, Finnhub

### LLM Client (Phase 6A — data-driven cascade)
tier_config from llm_model_config DB table. Groq cascade by priority with TokenBudget. Admin API: /api/v1/admin/llm-models.

### Key Decisions
- V1 ReAct graph DELETED (Session 54). V2 is the only path.
- Scope: financial context only, data-grounded only
- Portfolio health schemas separated from infra health (portfolio_health.py vs health.py)
