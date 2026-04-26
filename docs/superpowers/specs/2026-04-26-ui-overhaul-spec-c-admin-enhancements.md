# Spec C: Admin Page Enhancements

**Epic:** KAN-400 (UI Overhaul)
**Story:** KAN-513
**Date:** 2026-04-26
**Scope:** 3 admin features — Forecast Health panel, System Health drill-down, Audit Log viewer
**Estimated effort:** ~1.5 days, 1 PR (~300 lines)

---

## Context

Session 134 gap analysis identified 11 backend features without frontend UI. Spec A (stock detail, KAN-511) and Spec B (dashboard/screener, KAN-512) are shipped. This spec covers admin-facing enhancements where backend endpoints already exist but have no frontend.

**Deferred to separate stories (context preserved in JIRA):**
- KAN-521: Backtesting Dashboard (E-2, ~2-3 days, full admin page)
- KAN-522: LLM Admin Console (E-3, ~2-3 days, 11 endpoints)
- KAN-523: Command Center 4 missing panels (E-10/11/12/13, ~5 days, need backend collectors)

**In-scope items** are those where the backend is already complete and the frontend change is bounded:

---

## Feature 1: Forecast Health Panel (Command Center)

### What it answers
"Are our forecast models healthy and is sentiment data coverage adequate?"

### Data source
- Already included in `useCommandCenter()` aggregate response — **no new API call needed**
- Hook: `frontend/src/hooks/use-command-center.ts:12-20`
- Backend: `_get_forecast_health_safe()` at `backend/observability/routers/command_center.py:402-447`

### Response schema (backend already returns this)

**`ForecastHealthZone`** (`backend/schemas/command_center.py:139-154`):
```
backtest_health_pct: float     # % of model versions with direction_accuracy >= 60%
models_passing: int            # count of passing models
models_total: int              # total model count
sentiment_coverage_pct: float  # % of active tickers with sentiment in last 7 days
tickers_with_sentiment: int    # count with recent sentiment
tickers_total: int             # total active ticker count
```

### Frontend gap
- `ForecastHealthZone` type is **missing** from `frontend/src/types/command-center.ts:128`
- `CommandCenterResponse` interface does **not** include `forecast_health` field
- No panel component exists

### Component: `forecast-health-panel.tsx`

**Location:** `frontend/src/components/command-center/forecast-health-panel.tsx`

**Layout** (follows existing panel pattern from `system-health-panel.tsx`):
```
┌─────────────────────────────────────────────┐
│ Forecast Health                    [●] Live │
├─────────────────────────────────────────────┤
│                                             │
│  Backtest Accuracy        Sentiment Coverage│
│  ┌──────────────┐         ┌───────────────┐ │
│  │  ██████ 73%  │         │  █████ 85%    │ │
│  │  11/15 pass  │         │  42/50 tickers│ │
│  └──────────────┘         └───────────────┘ │
│                                             │
│  Color thresholds:                          │
│  ≥ 80% green, 60-79% amber, < 60% red      │
│                                             │
└─────────────────────────────────────────────┘
```

**Design weight:** Light — 2 metric cards in a horizontal layout. No charts. Matches the compact panel style used by all 4 existing CC panels.

### Color thresholds
Use a shared utility or reuse `GaugeBar` component at `frontend/src/components/command-center/gauge-bar.tsx` for threshold-based coloring. Thresholds: >= 80% green, 60-79% amber, < 60% red.

### Changes required
1. Add `ForecastHealthZone` interface to `frontend/src/types/command-center.ts`
2. Add `forecast_health: ForecastHealthZone | null` to `CommandCenterResponse`
3. Create `forecast-health-panel.tsx` (~50 lines)
4. Add to CC page grid (5th panel, full-width on mobile, half-width on lg)

**Note:** The backend already returns `forecast_health` in the aggregate response (`backend/schemas/command_center.py:172`). TypeScript currently silently drops the field because the frontend type omits it. The change is purely additive type definitions.

### Testing
- Jest test: renders both metric cards with correct values
- Jest test: color thresholds (green/amber/red) for both metrics
- Jest test: null/loading state

---

## Feature 2: System Health Drill-Down

### What it answers
"What's the detailed status of each infrastructure component?"

### Data source
- Already in `useCommandCenter()` response → `system_health` zone
- No new backend endpoint needed — drill-down shows the same data in expanded format

**Pattern deviation note:** Unlike other CC panels (API Traffic, LLM, Pipeline) which use `useCommandCenterDrillDown<T>(zone, enabled)` to fetch richer data from a separate drill-down endpoint, System Health drill-down reuses the aggregate data because the aggregate already contains per-service details. A backend drill-down endpoint may be added later if richer metrics (connection pool history, slow-query counts) are needed.

### Current system health data (from `SystemHealthZone`)

**`SystemHealthZone`** full field list per sub-type:
```
database: { healthy, latency_ms, pool_active, pool_size, pool_overflow, migration_head }
redis: { healthy, latency_ms, memory_used_mb, memory_max_mb, total_keys }
mcp: { healthy, tool_count, mode, restarts, uptime_seconds }
celery: { workers, queued, beat_active }
langfuse: { connected, traces_today, spans_today }
```

### Component: System Health drill-down content

**Location:** Extend `system-health-panel.tsx` with a "View Details" button + `DrillDownSheet`

**Layout** (follows `drill-down-sheet.tsx` pattern used by API Traffic, LLM, Pipeline panels):
```
┌─────────────────────────────────────────────┐
│ System Health Details              [×] Close│
├─────────────────────────────────────────────┤
│                                             │
│ Database                           ● Healthy│
│   Latency: 2.3ms                            │
│   Connection Pool: 3/10 active (0 overflow) │
│   Migration Head: e0f1a2b3c4d5              │
│                                             │
│ Redis                              ● Healthy│
│   Latency: 0.8ms                            │
│   Memory: 45 / 256 MB                       │
│   Keys: 1,247                               │
│                                             │
│ MCP Server                         ● Healthy│
│   Tools: 25 registered (stdio)              │
│   Uptime: 4h 23m (0 restarts)              │
│                                             │
│ Celery                             ● Active │
│   Workers: 2 | Queued: 0                    │
│   Beat: Active                              │
│                                             │
│ Langfuse                       ● Connected  │
│   Traces: 147 | Spans: 892                  │
│                                             │
└─────────────────────────────────────────────┘
```

**Design weight:** Light — text list with status indicators. No charts.

### Changes required
1. Add "View Details" button with `aria-expanded={detailOpen}` to `system-health-panel.tsx`
2. Add `DrillDownSheet` with expanded service details showing ALL fields (~50 lines)
3. No new hook or type needed — data already available

### Testing
- Jest test: "View Details" button click opens sheet
- Jest test: all 5 services rendered with all fields and correct status indicators
- Jest test: unhealthy service shows red indicator
- Jest test: `pool_overflow > 0` highlighted as warning

---

## Feature 3: Audit Log Viewer

### What it answers
"What admin actions have been performed on the platform?"

### Data source
- Backend: `GET /api/v1/admin/pipelines/audit-log` at `backend/routers/admin_pipelines.py:625-678`
- Query params: `action` (optional filter), `limit` (default 50, max 200), `offset` (default 0)
- Auth: admin-only (checked via `get_current_user`)

### Response schema

**`AuditLogResponse`** (`backend/schemas/admin_pipeline.py:141-159`):
```
total: int                    # total entries matching filter
limit: int                    # page size
offset: int                   # current offset
entries: list[AuditLogEntry]
  - id: str (UUID)
  - user_id: str (UUID)
  - action: str               # trigger_group, cache_clear, trigger_task, etc.
  - target: str | None         # group name, cache pattern, task name
  - metadata: dict | None      # failure_mode, keys_deleted, etc.
  - created_at: str (ISO 8601)
```

### Component: Audit Log section on Admin Pipelines page

**Location:** New section below existing Cache Controls on `frontend/src/app/(authenticated)/admin/pipelines/page.tsx`

**Layout:**
```
┌──────────────────────────────────────────────────────┐
│ Audit Log                            [Filter ▼]      │
├──────────────────────────────────────────────────────┤
│ Time         │ Action        │ Target     │ Details  │
│──────────────┼───────────────┼────────────┼──────────│
│ 2m ago       │ cache_clear   │ signals:*  │ 42 keys  │
│ 15m ago      │ trigger_group │ nightly    │ —        │
│ 1h ago       │ trigger_task  │ ingest_all │ —        │
│ ...          │               │            │          │
├──────────────────────────────────────────────────────┤
│ Showing 1-50 of 127             [← Prev] [Next →]   │
└──────────────────────────────────────────────────────┘
```

**Design weight:** Medium — data table with pagination and optional action filter dropdown.

### Action filter values
The action filter uses a static list derived from known admin actions (no enumeration endpoint):
- `trigger_group` — pipeline group trigger
- `trigger_task` — single task trigger
- `cache_clear` — cache pattern clear
- `cache_clear_all` — full cache clear

An "All" option shows all actions. If new action types are added backend-side, the filter list needs updating.

### Changes required
1. Add `AuditLogEntry` and `AuditLogResponse` types to `frontend/src/types/api.ts`
2. Add `useAuditLog(action?, limit, offset)` hook to `frontend/src/hooks/use-admin-pipelines.ts`
3. Create `audit-log-table.tsx` component (~80 lines)
4. Add to admin pipelines page below cache controls

### Testing
- Jest test: renders table with entries
- Jest test: pagination (prev/next buttons, disabled states)
- Jest test: action filter dropdown with all known values
- Jest test: empty state (no entries)
- Jest test: relative time formatting

---

## Dropped: Task Status Polling (E-5)

**Originally scoped as Feature 4, removed during spec review.**

**Reason:** Neither `TriggerGroupResponse` nor `TriggerTaskResponse` returns a `task_id` field. Group triggers use `asyncio.create_task()` (not Celery), so the `/tasks/{task_id}/status` endpoint wouldn't work for groups. The existing `useActiveRun()` hook already provides group-level progress polling. Implementing task-level polling requires backend schema changes (adding `task_id` to response models), which contradicts this spec's "frontend-only" scope.

**Deferred to:** A future story that pairs the backend schema change with the frontend badge. Context captured in KAN-523 description.

---

## PR Strategy

**1 PR** (~300 lines):
- 3 features, 2 new components, 1 modified component, 1 hook addition, 2 type additions
- Branch: `feat/KAN-513-admin-enhancements`
- All frontend-only — no backend changes

### File change estimate

| Change Type | Files | Lines |
|-------------|-------|-------|
| New components | 2 (`forecast-health-panel.tsx`, `audit-log-table.tsx`) | ~130 |
| Modified component | 1 (`system-health-panel.tsx` — add drill-down) | ~50 |
| Type additions | 2 (`command-center.ts`, `api.ts`) | ~30 |
| Hook additions | 1 (`use-admin-pipelines.ts`) | ~15 |
| Page wiring | 2 (`command-center/page.tsx`, `pipelines/page.tsx`) | ~15 |
| Tests | 3 test files | ~80 |
| **Total** | **~11 files** | **~320 lines** |

---

## Testing Strategy

- **Jest unit tests** for all 3 features (render, interaction, edge cases)
- **No E2E needed in this PR** — KAN-504 covers E2E for all A+B+C specs
- **No backend tests** — all endpoints already tested, no backend changes
- Follow existing mock patterns from `frontend/src/__tests__/`

---

## Dependencies

- None on other specs — all backend endpoints exist
- KAN-504 (E2E tests) should run after this spec ships

## Deferred items (with JIRA tickets)

| Item | JIRA | Reason |
|------|------|--------|
| Backtesting Dashboard (E-2) | KAN-521 | Full admin page, ~300 lines, needs own story |
| LLM Admin Console (E-3) | KAN-522 | 11 endpoints, ~400 lines, may need own Epic |
| 4 CC panels (E-10/11/12/13) | KAN-523 | Need backend collectors + schemas, ~5 days |
| Task Status Polling (E-5) | — | Needs backend schema change (`task_id` in trigger responses); group triggers use asyncio not Celery |
