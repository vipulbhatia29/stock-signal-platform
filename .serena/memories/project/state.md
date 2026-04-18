# Project State (updated Session 119, 2026-04-18)

## Current Phase
**Platform Observability Infrastructure — Epic KAN-457 (In Progress).** Session 119 shipped PR5 (strangler-fig refactor, PR #247). **Sub-epic 1a (KAN-458) COMPLETE — all 6 PRs merged.**

## Last Shipped (Session 119)
- **KAN-470** — Obs 1a PR5: Strangler-fig refactor — SDK migration of existing emitters (PR #247)

## Test Counts
- Unit: 2312 passed (0 failures)
- API: 454

## Resume Point (next session)
- Start sub-epic 1b (KAN-459 Coverage) — refine, brainstorm, plan
- OR pick from backlog: KAN-429 (JIRA automation, High), KAN-400 (UI Overhaul, Medium)
- Post-PR5 rollout: 2 weeks of green production with `OBS_LEGACY_DIRECT_WRITES=true`, then flip to `false`

## 1a PR Progress (COMPLETE)
| PR | Status | PR # |
|---|---|---|
| PR1 Schema foundation | ✅ | #242 |
| PR2a SDK core | ✅ | #243 |
| PR2b HTTP target + ingest | ✅ | #244 |
| PR3 trace_id + structlog | ✅ | #245 |
| PR4 External API + rate limiter | ✅ | #246 |
| PR5 Strangler-fig refactor | ✅ | #247 |

## Alembic Head
Migration 031 (external_api + rate_limiter, rev `d5e6f7a8b9c0`)

## Parallel backlog
- KAN-429 (High, Bug) — JIRA automation mass-closure
- KAN-400 (Epic, Medium) — UI Overhaul (after Obs Epic)
- KAN-456 (Med) — Langfuse task_tracer wiring
- Follow-up: Move ObservedHttpClient instantiation to provider __init__ for LLM providers (review finding I-3)
- Follow-up: Flip OBS_LEGACY_DIRECT_WRITES to false after 2 weeks of green production
- Follow-up: Cleanup PR to delete legacy direct-write code after flag-flip