# Project State (updated Session 53, 2026-03-25)

## Current Phase
- Phase 1-5: ALL COMPLETE
- Phase 5.5 (Security): COMPLETE — PR #79, Redis refresh token blocklist
- Phase 5.6 (MCP stdio): ALL COMPLETE (S1-S6 Done, PRs #81-84, #86). Epic KAN-119 Done.
- Phase 6A (LLM Factory & Cascade): IN PROGRESS — Session 54
- Phase 6B (Agent Observability): spec approved, plan pending
- Phase 6C (Testing Infrastructure): spec approved, plan pending

## JIRA Phase 6A
- Epic KAN-139: Phase 6A — LLM Factory & Cascade (To Do)
- KAN-140: S1 V1 Deprecation (In Progress — Session 54)
- KAN-141: S2 Bug Fix + Token Budget
- KAN-142: S3 LLM Model Config
- KAN-143: S4 GroqProvider Cascade
- KAN-144: S5 Admin API + Tier Config
- KAN-145: S6 Tool Result Truncation + Tests
- KAN-146: S7 Integration Testing + Docs

## Session 54 Summary
Phase 6A LLM Factory & Cascade — ALL 7 stories (KAN-140–146) shipped in one session.
V1 deprecated, multi-model cascade, TokenBudget, admin API, tool truncation, tier wiring.
766 unit tests. Alembic head: c965b4058c70 (migration 012). 7 commits on feat/KAN-140-v1-deprecation.

## Stats
- ~980 total tests (766 unit + ~180 API + 7 e2e + 24 integration + 107 frontend)
- 41 new tests this session (net +31 after V1 deletion)
- 20 internal tools, 4 MCP adapter wrappers
- Alembic head: c965b4058c70 (migration 012)

## Session 52 Summary
Dashboard refresh bug sprint — 4 fixes:
1. Route shadowing: `/forecasts/portfolio` matched by `/{ticker}` → moved before parameterized route.
2. Partial cache invalidation: Refresh All now invalidates all 9 dashboard query keys (was 2).
3. Unnecessary `/forecasts/portfolio` call: guarded with `enabled: hasPositions`.
4. Stale prices: `on_conflict_do_nothing` → `on_conflict_do_update` in `market_data.py`.
Pre-existing test failure: `test_analyze_stock_tool_error_handling` (connects to running local DB).
Remaining: S6 (validation), earnings_snapshots investigation, llm_call_log/tool_execution_log dead code.

## Phase 5.6 JIRA
- KAN-119: Epic (In Progress — needs transition to Done)
- KAN-121: Refinement (Done)
- KAN-132-135: S1-S4 (Done)
- KAN-136: S5 Integration Tests (Done)
- KAN-131: S6 Validation (Done)

## Open Bugs
- None — KAN-138 fixed (PR #93) and Done

## New Files This Session
- tests/integration/test_mcp_stdio.py — 14 integration tests
- tests/integration/test_mcp_regression.py — 6 regression tests