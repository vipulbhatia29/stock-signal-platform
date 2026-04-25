# UI Assessment Gaps (Session 134, 2026-04-25)

## Backend Features Without Frontend UI

### HIGH VALUE — Priority 1
1. **Backtesting Dashboard** — 4 endpoints (`/backtests/run`, `/{ticker}`, `/{ticker}/history`, `/summary/all`), zero frontend. Core alpha feature.
2. **LLM Admin Console** — 11 endpoints (`/observability/llm/models`, `/tier-health`, `/tier/toggle`, `/usage`, `/chat-sessions`, `/chat-stats`, `/query-cost`, `/metrics`, `/reload`, `/models/{id}`, `/chat-sessions/{id}`), zero frontend. Cost control critical for production.
3. **Stock Intelligence Display** — `/stocks/{ticker}/intelligence` (insider trades, EPS revisions, earnings dates, upgrades/downgrades). Hook exists (`use-stocks.ts`), NO component renders it.

### MEDIUM VALUE — Priority 2
4. **Audit Log Viewer** — `/admin/pipelines/audit-log` endpoint, no admin UI.
5. **Task Status Monitor** — `/tasks/{task_id}/status` for Celery progress, no UI.
6. **Forecast Component Breakdown** — `/portfolio/{id}/forecast/components` (Prophet per-ticker), no hook or UI.
7. **Sentiment Article Browser** — `/sentiment/articles`, no frontend.
8. **Forecast Health in Command Center** — `/admin/command-center/forecast-health` endpoint exists, no hook/panel.

### LOW VALUE — Priority 3
9. **System Health drill-down** — Command Center panel has no "View Details" (other 3 panels do).
10. **Individual Pipeline Task Trigger** — `/admin/pipelines/tasks/{id}` not exposed in Pipeline Control UI.
11. **Ingestion Health Dashboard** — `/admin/pipelines/ingestion-health` not shown.

## Command Center Prototype Gaps (4 of 8 panels not shipped)

HTML prototype at `command-center-prototype.html` shows 8-panel layout. Only 4 shipped:

| Panel | Status | Gap |
|---|---|---|
| System Health | **Shipped** | Minor (hit rate, migration head) |
| API Traffic | **Shipped** | Minor (sparkline, P50/P99 in main) |
| LLM Operations | **Shipped** | Minor (provider tabs) |
| Nightly Pipeline | **Shipped** | Minor (step-level timings) |
| **Cache Performance** | **NOT SHIPPED** | Hit rate donut, namespaces, memory — zero code |
| **Chat & Agent** | **NOT SHIPPED** | Messages/hr, tool calls, feedback, top tools — zero code |
| **Auth & Security** | **NOT SHIPPED** | Active users, login %, failed logins, rate limits — zero code |
| **Alerts & Forecasting** | **Partial** | Backend `forecast_health` exists, no React component. Alerts zone missing entirely. |

Backend obs tables contain the data (auth_event_log, cache_operation_log, agent_intent_log) — needs collector functions + React components + types.

Estimated effort: ~44h for all 4 missing panels.

## UI Bugs Fixed (Session 134)
- `pipeline_runs.trace_id` + `celery_task_id` columns added (was causing 500s on admin obs)
- Nested `<button>` in Pipeline Control → `<div role="button">`
- Breadcrumb showing "Dashboard" on all admin pages → 5 new routes added

## Lighthouse Coverage Gaps
- Only 5 pages covered (Dashboard, Screener, Portfolio, Login, Register)
- Missing: Sectors, Account, Observability, Admin Obs, Admin Pipelines, Command Center, Stock Detail

## E2E Coverage Gaps (before Session 134 additions)
- 8/16 pages had ZERO E2E coverage
- Session 134 added 6 new test files covering: Sectors, Account, Admin Obs, Admin Pipelines, User Obs, Auth links
