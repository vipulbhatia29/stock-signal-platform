# JIRA Stories to Create — KAN-233 Command Center

**Action:** Rescope KAN-233 description, then create 12 subtasks.

## Rescope KAN-233 Description

**New summary:** `Platform Operations Command Center (Phase 1 MVP)`
**New description:**
```
Nuclear-reactor-style admin dashboard providing single-pane-of-glass for the entire platform.

Phase 1 MVP: 4 zones (System Health, API Traffic, LLM Operations, Pipeline)
Phase 2: 4 additional zones (Cache, Chat, Auth, Alerts/Forecasting)

Spec: docs/superpowers/specs/2026-03-31-command-center-design.md
Plan: docs/superpowers/plans/2026-03-31-command-center-implementation.md
Prototype: command-center-prototype.html

Key architecture decisions:
- Extract observability code into backend/observability/ bounded package
- Redis-backed HTTP metrics (multi-worker safe, sliding window)
- Aggregate endpoint with asyncio.gather + per-zone circuit breakers + 10s server-side cache
- Frontend polls 15s via TanStack Query, manual refresh on drill-downs
```

## Subtasks (12)

### Sprint 1 — Package Extraction (MERGE GATE)

| # | Summary | Description | Est |
|---|---------|-------------|-----|
| S1a | Extract agents/ observability files to backend/observability/ | Move collector, writer, token_budget. Add re-export shims. Run full test suite. | 2.5h |
| S1b | Extract services/routers/context to backend/observability/ | Move request_context, langfuse, queries, admin/health/observability routers. Update 15+ importers. Alembic verification. | 3h |

### Sprint 2 — Backend Instrumentation (parallelizable)

| # | Summary | Description | Est |
|---|---------|-------------|-----|
| S2 | Redis-backed HTTP request metrics middleware | ASGI middleware with Redis sorted sets (sliding window), path normalization, excluded admin paths, insufficient data null handling. | 3.5h |
| S3 | DB pool stats + Pipeline stats query service | SQLAlchemy pool.status(), PipelineRun/Watermark query service (get_latest_run, get_watermarks, get_run_history, get_failed_tickers). | 3h |
| S4 | LoginAttempt audit trail + purge task | New model + migration 021 + auth router hooks + purge_login_attempts Celery Beat task (90-day, batch delete). CCPA/GDPR compliant. | 2.5h |
| S5 | PipelineRun step_durations + total_duration | Migration 022 (separate from 021). Add step_durations JSONB + total_duration_seconds. Atomic JSONB merge via record_step_duration(). Instrument nightly chain. | 1.5h |
| S6 | TokenBudget status + Celery + Langfuse health checks | Health check implementations: Celery (inspect.ping + llen + PipelineRun inference), Langfuse (auth probe + local DB trace count), TokenBudget (usage % per model). All cached. | 2h |

### Sprint 3 — API Endpoints

| # | Summary | Description | Est |
|---|---------|-------------|-----|
| S7 | Command center aggregate endpoint (4 zones) | GET /admin/command-center — asyncio.gather with per-zone timeout, degraded_zones, 10s server-side cache, _meta.assembly_ms. Pydantic response schemas. | 4h |
| S8 | 3 drill-down endpoints (API traffic, LLM, Pipeline) | GET /admin/command-center/{api-traffic,llm,pipeline} — detailed data for L2 expansion. Admin-gated. No auto-poll. | 3h |

### Sprint 4 — Frontend

| # | Summary | Description | Est |
|---|---------|-------------|-----|
| S9 | Frontend L1 — 4 zone panels + page | CommandCenterPage, SystemHealthPanel, ApiTrafficPanel, LlmOperationsPanel, PipelinePanel, StatusDot, GaugeBar, MetricCard, LastRefreshedIndicator, DegradedBadge. useCommandCenter hook (15s poll, refetchOnWindowFocus). Admin sidebar nav link. | 6h |
| S10 | Frontend L2 — 3 drill-down sheets | DrillDownSheet wrapper (manual Refresh, Copy JSON), ApiTrafficDetail, LlmDetail, PipelineDetail. Recharts charts. | 4h |

### All subtasks start "To Do". Sprint 1 subtasks are blockers for Sprint 2+.
