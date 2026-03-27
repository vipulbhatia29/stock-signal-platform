---
scope: project
category: future_work
created_by: session-60
---

# Multi-Agent Architecture Brainstorm — Session 60

## Context
During KAN-172/173 service layer brainstorm, PM questioned why we load 1 agent with 24 tools instead of having specialized agents. This led to a deep architectural discussion.

## Current Architecture
Single Agent V2 (LangGraph StateGraph): Plan → Execute → Synthesize
- 24 internal tools + 4 MCP adapters
- 2 LLM calls per query (planner + synthesizer), 1 for simple lookups
- Planner is non-deterministic (LLM-based intent + tool selection)
- Executor is mechanical (no LLM, just runs tools in plan order)
- All 24 tool descriptions sent to planner every query (~2K tokens)

## Problems Identified
1. **Token waste:** 24 tool descriptions sent even when only 6-8 are relevant
2. **Hallucination risk:** More tools = more wrong choices, especially on free-tier LLMs (Groq)
3. **Extensibility ceiling:** Adding retirement planning, options, crypto → 40-50+ tools makes single planner unreliable
4. **Testing:** Can't test one domain's planning behavior in isolation

## Proposed Solution: Two-Phase Migration

### Phase 1: Intent-Based Tool Filtering (KAN-188, near-term)
- After planner classifies intent, filter tool set before generating plan steps
- Rule-based, no extra LLM call
- Intent → tool group mapping:
  - `stock_analysis` → ~8 tools
  - `portfolio` → ~5 tools
  - `market_overview` → ~3 tools
  - `simple_lookup` → ~2 tools
  - cross-domain → all 24 (fallback)
- Gets 80% of benefit at 20% of complexity

### Phase 2: Multi-Agent Architecture (KAN-189 Epic, Phase 9+)
```
User query → Meta-Router → Specialized Agent(s) → Response Aggregator → User
```

Specialized agents:
- Stock Analysis Agent (8 tools)
- Portfolio Management Agent (6 tools)
- Market Overview Agent (5 tools)
- [Future] Retirement Planning Agent
- [Future] Options/Derivatives Agent
- [Future] Tax Optimization Agent

### Open Design Decisions (require full brainstorm session)
1. **Meta-Router strategy:** Rule-based vs lightweight LLM vs hybrid
2. **Cross-domain queries:** Parallel dispatch + aggregator vs fallback general agent vs agent-to-agent calls
3. **Shared context/state:** Shared StateGraph vs full conversation history per agent vs scratchpad
4. **Conversation memory:** Per-agent vs shared session
5. **LLM routing per agent:** Per-agent model config vs global tiers
6. **Streaming/UX:** Interleaved parallel streams vs sequential
7. **Error isolation:** Partial results from successful agents even if one fails
8. **Migration strategy:** Incremental from Agent V2 → multi-agent

## Key Insight: Service Layer is the Prerequisite
Without `backend/services/`, you can't split into specialized agents because business logic is tangled into routers and tools. With services:
- Services don't care who calls them (router, tool, agent, task)
- Agent split is purely an orchestration change, zero service layer changes
- Each specialized agent gets its own subset of tools, each tool wraps the same services

## Decision: Granular + Pipeline Services
- **Atomic services** (for tools/planner): `get_signals()`, `compute_signals()`, `get_positions()` — composable
- **Pipeline services** (for routers/Celery): `ingest_ticker()` — transactional sequences that must not be broken
- Planner never calls pipelines — it assembles atomic tools non-deterministically
- Routers/Celery call pipelines for guaranteed multi-step operations

## JIRA Tickets Created
- **KAN-188** (Story): Intent-based tool filtering — near-term, depends on KAN-172
- **KAN-189** (Epic): Multi-Agent Architecture — Phase 9+, full design session needed

## References
- Agent V2 spec: `docs/superpowers/specs/` (Phase 4D)
- LangGraph multi-agent patterns: supervisor, hierarchical, plan-and-execute
- Anthropic best practice: fewer tools per call = better accuracy
