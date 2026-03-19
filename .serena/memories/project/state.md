---
scope: project
category: project
updated_by: session-34
---

# Project State

- **Current Phase:** Phase 4B — AI Chatbot (plan approved, implementation starting)
- **Current Branch:** feat/KAN-3-tool-orchestration (KAN-5 branch also pushed)
- **Alembic Head:** 664e54e974c5 (migration 008 — chat + logs)
- **Test Count:** 329 (205 unit + 124 API backend) + 20 frontend component tests
- **CI/CD:** Fully operational — 3 workflows, branch protection on main + develop
- **JIRA:** KAN-6/8/14/7/11 → Ready for Verification. KAN-12/13/15 → To Do (KAN-4 story)
- **What's next:** Create `feat/KAN-4-streaming` branch → KAN-12 (MCP adapters + server + warm pipeline) → KAN-13 (chat router) → KAN-15 (wiring + E2E smoke test)

## Implementation Order (by dependency)
1. KAN-6: DB models + migration + schemas (Plan Tasks 1-4) → branch: feat/KAN-5-conversation-history
2. KAN-8: Tool base classes + ToolRegistry + internal tools (Plan Tasks 5-8) → branch: feat/KAN-3-tool-orchestration
3. KAN-14: LLM client + LangChain providers (Plan Task 10)
4. KAN-7: Agent types + prompt templates (Plan Task 11)
5. KAN-11: LangGraph StateGraph + stream bridge (Plan Tasks 9, 12)
6. KAN-12: MCP adapters + MCP server + warm pipeline (Plan Tasks 13-15) → branch: feat/KAN-4-streaming
7. KAN-13: Chat router + session management (Plan Tasks 16-17)
8. KAN-15: Wire main.py + E2E smoke test (Plan Tasks 18-19)

## Key Architecture Decision (Session 35)
- **LangGraph adopted** for agent orchestration (not custom loop)
- LangChain chat models (ChatGroq, ChatAnthropic, ChatOpenAI) instead of raw SDKs
- MemorySaver checkpointer (→ PostgresSaver in Phase 6)
- Dependencies: langgraph, langchain-core, langchain-groq, langchain-anthropic, langchain-openai

## Git Branch Structure
```
main        ← production-ready, protected
develop     ← integration branch, protected
feat/KAN-*  ← Story branches, PR to develop
```

## Active JIRA Epics
- **KAN-1** Phase 4B — AI Chatbot Backend
  - KAN-16 Refinement Story: ALL DONE (KAN-17–21 complete)
  - KAN-5 Story: Conversation History — subtask KAN-6
  - KAN-3 Story: Tool Orchestration — subtasks KAN-7, KAN-8, KAN-11, KAN-14
  - KAN-4 Story: Streaming Responses — subtasks KAN-12, KAN-13, KAN-15
- **KAN-22** CI/CD Pipeline: ✅ DONE

## Session 35 Summary
Plan approved + LangGraph adopted + JIRA backlog created + implementation started (Tasks 1-12).
- Wrote 19-task plan, reviewed, PM approved (KAN-20/21 Done)
- LangGraph adopted: spec §5/§8/§12/§14 rewritten
- 8 implementation subtasks created under KAN-3/4/5
- PR #11 (plan) merged. Implementation: 12 commits across 2 branches
- KAN-6 (DB+schemas), KAN-8 (tools), KAN-14 (LLM), KAN-7 (agents), KAN-11 (graph) all Ready for Verification
- 62 new tests added (329 total). Migration 008 applied.

## Phase Completion
- Phase 1 (Sessions 1-3): COMPLETE
- Phase 2 (Sessions 4-7): COMPLETE
- Phase 2.5 (Sessions 8-13): COMPLETE
- Phase 3 (Sessions 14-20): COMPLETE
- Phase 3.5 (Sessions 21-25): COMPLETE
- Phase 4A UI Redesign (Session 29): COMPLETE
- Memory Architecture (Session 31): COMPLETE
- CI/CD Epic KAN-22 (Session 34): COMPLETE
- Phase 4B Spec (Session 34): COMPLETE
- Phase 4B Plan (Session 35): COMPLETE — implementation next