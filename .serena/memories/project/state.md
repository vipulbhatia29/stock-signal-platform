# Project State

## Current Phase
- SaaS Launch Roadmap Phase A COMPLETE (Session 67)
- 3 open JIRA tickets: KAN-157 (ReAct eval), KAN-152 (OAuth), KAN-211 (Test Hardening Epic)
- Test hardening Epic KAN-211 has 5 stories: KAN-212-216

## Resume Point
- Pick next task: KAN-212 (Tool orchestration tests — quick win, ~10h, no brainstorm)
- Or: KAN-157 (Live LLM eval — needs technical brainstorm, SaaS Phase B)
- Or: KAN-152 (Google OAuth — needs business + technical brainstorm, SaaS Phase C)

## Session 67 Accomplishments
- KAN-186 COMPLETE: TokenBudget → Redis sorted sets (Lua scripts, fail-open, NOSCRIPT recovery)
- KAN-186 COMPLETE: ObservabilityCollector reads → llm_call_log DB table (cross-worker ground truth)
- Admin endpoints updated to pass DB session for observability reads
- main.py reordered: Redis pool → TokenBudget → ObservabilityCollector → CacheService
- Code review: NOSCRIPT recovery added (clear cached SHAs on Redis error)
- 8 files changed, 16 token budget tests, 14 observability tests, 1045 unit tests total
- Docs: project-plan Phase A marked complete, TDD §3.13 + §5.4 updated, PROGRESS.md entry

## Test Counts
- ~1045 unit + ~180 API + 7 e2e + 24 integration + 107 frontend = ~1152 total tests
- Alembic head: 1a001d6d3535 (migration 014)

## Branch
- develop — PR pending for KAN-186

## JIRA Board (8 open tickets)
- KAN-186: TokenBudget → Redis — DONE (pending PR merge)
- KAN-157: Live LLM eval — rescoped for ReAct (SaaS Phase B, needs technical brainstorm)
- KAN-152: Google OAuth PKCE (SaaS Phase C, needs business + technical brainstorm)
- KAN-211: Test Suite Hardening Epic
- KAN-212: S1 Tool orchestration tests (~10h)
- KAN-213: S2 Pipeline mock refactor (~8h)
- KAN-214: S3 Error path tests (~8h)
- KAN-215: S4 ReAct loop integration test (~6h)
- KAN-216: S5 Frontend component tests (~15h, deferrable)