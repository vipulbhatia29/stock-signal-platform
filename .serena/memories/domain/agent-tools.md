---
scope: project
category: domain
phase: 4B (IN PROGRESS)
---

# Agent Tools Domain

## Architecture (Phase 4B)
- `backend/agents/base.py` — BaseAgent ABC
- `backend/agents/registry.py` — AgentRegistry (discover + route)
- `backend/agents/loop.py` — agentic tool-calling loop
- `backend/agents/stream.py` — NDJSON streaming to frontend
- `backend/agents/general_agent.py` — general purpose + web search
- `backend/agents/stock_agent.py` — stock analysis + signals + forecasting
- `backend/tools/registry.py` — ToolRegistry (all tools discoverable)
- `backend/routers/chat.py` — chat endpoints (POST /chat/message, GET /chat/sessions)

## LLM Routing
- Groq: primary for agentic tool-calling loops (fast/cheap, GROQ_API_KEY)
- Claude Sonnet: synthesis and final response (ANTHROPIC_API_KEY)
- LM Studio: offline fallback (no key needed, local inference)

## Streaming Protocol
- NDJSON (newline-delimited JSON) from backend to frontend.
- Each line: {"type": "token"|"tool_call"|"tool_result"|"done", "content": ...}
- Frontend ChatPanel reads the stream and renders incrementally.

## DB Models (migration 008)
- `ChatSession`: id, user_id, title, created_at, updated_at
- `ChatMessage`: id, session_id, role (user/assistant/tool), content, tool_calls, created_at
