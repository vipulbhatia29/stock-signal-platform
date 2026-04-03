## Project State (Session 88)

**Current phase:** Phase 8.6+ Forecast Intelligence (Epic KAN-369)
**Spec A (Backtesting): COMPLETE** — Sprints 1-4, PR #177 merged to develop
**Resume point:** Sprint 5 (KAN-378) — PipelineRegistry + seed tasks (Spec D start)
**Branch for Spec D:** `feat/KAN-371-admin-pipelines` (create from develop)

### Session 88 Summary
- Spec A implemented across 4 sprints in one session: models, BacktestEngine, CacheInvalidator, convergence classifiers, calibrated drift, backtest API
- Sonnet implemented, Opus reviewed each sprint (4 expert reviews + 1 composite cross-sprint)
- PR #177 merged (squash) — 33 files, +2643 lines, 114 new tests
- 3 ADRs added: Prophet train-once-predict-many (009), calibrated drift (010), cache invalidation (011)
- JIRA: KAN-374/375/376/377 → Ready for Verification. KAN-378/379 updated with pipeline scheduling details + schedule editor UI requirements
- CI: 2 fixes (ruff format on migration, pyright date self-reference via `from __future__ import annotations`)

### Key Facts
- Alembic head: `b2351fa2d293` (migration 024 — forecast intelligence tables)
- Backend tests: 1494 unit
- Frontend tests: 378 + 42 E2E + 27 nightly = ~1941 total
- Internal tools: 25 + 4 MCP adapters
- 5 new models: BacktestRun, SignalConvergenceDaily, NewsArticle, NewsSentimentDaily, AdminAuditLog
- 5 new services/tasks: BacktestEngine, CacheInvalidator, convergence classifiers, calibrated drift, backtest router (5 endpoints)
- Docker: Postgres 5433, Redis 6380, Langfuse 3001+5434

### Key Decisions (Session 88)
- Prophet trains weekly, not daily — convergence layer provides daily freshness (ADR-009)
- Drift threshold: per-ticker backtest_mape × 1.5, fallback 20% (ADR-010)
- Cache invalidation: event-driven for per-ticker, TTL for user-scoped (ADR-011)
- Pipeline schedules editable by admin via UI (KAN-378/379 — new requirement)
- TaskDefinition includes `rationale` field explaining WHY each schedule was chosen
