---
scope: project
category: future_work
created_by: session-60
updated_by: session-133 (trimmed — most items resolved)
---

# Agent Architecture Redesign — Status Pointer

**Original analysis:** Session 60, 3-prong analysis (current state, gaps, roadmap).

## Resolved Items (7/8)
- ✅ Step 1: ReAct loop (Session 63, Phase 8B)
- ✅ Step 2: Tool filtering + intent classifier (Session 64, Phase 8C)
- ✅ Step 3: Observability audit — cost_usd, cache_hit, agent_id, fallback_rate, per-query cost (Sessions 62-67)
- ✅ LLM tier routing: data-driven cascade from DB (Phase 6A)
- ✅ TokenBudget → Redis (Session 67, KAN-186)
- ✅ OpenAI/Anthropic/Groq providers wired (Session 55+)
- ✅ Full obs SDK (Epic KAN-457, Sessions 113-129)

## Remaining (1/8 — not actively planned)
- Step 4-6: Dynamic concurrency controller, multi-agent fan-out, fallback stagger
- These depend on production load patterns not yet available (single-user dev)
- Will revisit when moving to multi-tenant SaaS deployment

## Key Decisions (still valid)
- `backend/services/` and `backend/tools/` layers are stable — agents call atomic services
- NDJSON streaming transport unchanged
- ReAct loop is the only agent path (old Plan→Execute→Synthesize deleted Session 54)
