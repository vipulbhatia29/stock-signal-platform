---
scope: project
category: domain
updated_by: session-34
phase: 4B (spec complete, plan pending)
---

# Agent Tools Domain

## Architecture — Three-Layer MCP Platform
Full spec: `docs/superpowers/specs/2026-03-17-phase-4b-ai-chatbot-design.md`

### Layer 1: Consume External MCPs
- EdgarTools MCP → SEC filings (10-K, 10-Q, 8-K, 13F, Form 4)
- Alpha Vantage MCP → news + sentiment
- FRED MCP → macroeconomic data (840K series)
- Finnhub MCP → analyst ratings, ESG, social sentiment, supply chain, ETFs
- GDELT API → geopolitical events (custom tool wrapper)
- Web search → SerpAPI wrapper

### Layer 2: Backend Enrichment
- Tool Registry (`backend/tools/registry.py`) — central discovery + execution
- MCPAdapter (`backend/tools/base.py`) — auto-discovers external MCP tools
- Internal tools (`backend/tools/*.py`) — analyze_stock, portfolio_exposure, screen_stocks, etc.
- Warm data: Redis cache (Celery tasks: daily analyst/FRED, weekly 13F, on-demand 10-K)

### Layer 3: Expose as MCP Server
- Streamable HTTP at `/mcp` (FastMCP on FastAPI)
- Same Tool Registry powers both chat endpoint and MCP server
- JWT auth (same as REST API)

## File Structure
```
backend/agents/    — BaseAgent, StockAgent, GeneralAgent, loop, stream, llm_client, prompts/
backend/tools/     — registry, base, internal tools, adapters/ (edgar, alpha_vantage, fred, finnhub)
backend/mcp_server/ — FastMCP server + auth
backend/models/    — chat.py (ChatSession, ChatMessage), logs.py (LLMCallLog, ToolExecutionLog)
backend/routers/   — chat.py (POST /api/v1/chat/stream)
backend/tasks/     — warm_data.py (Celery tasks)
```

## LLM Client
- Abstraction: LLMClient with pluggable providers
- Fallback: Groq → Anthropic → Local (LM Studio)
- Retry: exponential backoff for transient errors, immediate switch for quota/timeout
- Provider health tracking: exhausted providers skipped until reset
- Few-shot prompting for all agents (prompts in markdown files)

## Key Design Decisions
- Phase 4B = backend only. Phase 4C = frontend wiring.
- MCP server pulled forward from Phase 6 (minimal incremental effort on top of registry)
- Agent types = registry filters (stock gets all tools, general gets data+news only)
- Graceful degradation: every tool can fail independently
- No new infrastructure: TimescaleDB + Redis + Celery

## DB Models (migration 008)
- ChatSession: id, user_id, agent_type, title, is_active, created_at, last_active_at
- ChatMessage: id, session_id, role, content, tool_calls, model_used, tokens_used, latency_ms
- LLMCallLog: hypertable — per-LLM-call metrics (provider, model, tokens, cost_usd, latency)
- ToolExecutionLog: hypertable — per-tool metrics (tool_name, latency, cache_hit, status)
