# Platform Operations Command Center — Technical Specification

**Date:** 2026-03-31
**Epic:** KAN-233 (rescoped from "Admin Dashboard" to "Command Center")
**Phase:** B.5 BU-7 → expanded scope
**Status:** Revised — expert panel findings incorporated
**Review:** Fowler (architecture), Nygard (ops/reliability), Senior Ops TL (execution)

---

## 1. Overview

### 1.1 What

A nuclear-reactor-style operations dashboard providing a single pane of glass for the entire Stock Signal Platform. Every subsystem — API layer, LLM/Agent, data pipeline, database, Redis, MCP, forecasting, auth, alerts, and chat — is visible in one screen with drill-down capability.

### 1.2 Why

- **Operator visibility:** The platform has 24 agent tools, a 9-step nightly pipeline, a 3-tier LLM cascade, and 18 router groups — but no unified view of system health.
- **Cost control:** LLM spend is growing. Need real-time cost burn rate and budget exhaustion visibility.
- **SaaS readiness:** Before multi-user launch, operators need to monitor pipeline health, cache effectiveness, auth patterns, and alert generation without SSH-ing into the server.
- **Microservice preparation:** Consolidating observability code into a bounded `backend/observability/` package enables future extraction into an independent service.

### 1.3 Who

Admin users only (gated by `require_admin()`). Regular users continue to see `/observability` (their own query analytics). The command center is at `/admin/command-center`.

### 1.4 Phased Delivery

**MVP (Phase 1):** 4 core zones — System Health, API Traffic, LLM Operations, Pipeline. These are the highest-ops-value, most-frequently-checked subsystems.

**Phase 2:** 4 additional zones — Cache, Chat & Agent, Auth & Security, Alerts & Forecasting. Added after MVP is validated.

This split reduces Phase 1 to ~22h (4 sessions) and cuts the partial-failure surface of the aggregate endpoint in half.

---

## 2. Architecture Decision: Observability Package Extraction

### 2.1 Current State

Instrumentation code is scattered across 4 packages:

| File | Current Location | Responsibility |
|------|-----------------|----------------|
| `observability.py` | `backend/agents/` | ObservabilityCollector — in-memory metrics + DB write dispatch |
| `observability_writer.py` | `backend/agents/` | Fire-and-forget async DB writer |
| `token_budget.py` | `backend/agents/` | Redis sorted-set sliding windows (TPM/RPM/TPD/RPD) |
| `langfuse_service.py` | `backend/services/` | Langfuse SDK wrapper (trace/span/generation) |
| `observability_queries.py` | `backend/services/` | Query service for observability endpoints |
| `cache.py` | `backend/services/` | CacheService (3-tier namespace, TTL tiers) |
| `logs.py` | `backend/models/` | LLMCallLog, ToolExecutionLog models |
| `request_context.py` | `backend/` | ContextVars (user_id, session_id, query_id, agent_type, agent_instance_id) |
| `admin.py` | `backend/routers/` | 11 admin endpoints |
| `observability.py` | `backend/routers/` | 7 user-facing observability endpoints |
| `health.py` | `backend/routers/` | System health check |

### 2.2 Target State

```
backend/observability/
├── __init__.py               # Package init, re-exports for backward compat
├── collector.py              # ObservabilityCollector (from agents/observability.py)
├── writer.py                 # Fire-and-forget writer (from agents/observability_writer.py)
├── token_budget.py           # TokenBudget (from agents/token_budget.py)
├── langfuse.py               # Langfuse wrapper (from services/langfuse_service.py)
├── queries.py                # Query service (from services/observability_queries.py)
├── context.py                # ContextVars (from request_context.py)
├── models.py                 # LLMCallLog, ToolExecutionLog (from models/logs.py)
├── metrics/
│   ├── __init__.py
│   ├── http_middleware.py    # NEW: ASGI middleware for request metrics
│   ├── cache_stats.py        # NEW: Cache hit/miss counters on CacheService
│   ├── db_pool.py             # NEW: SQLAlchemy pool event listeners
│   ├── redis_stats.py         # NEW: Redis INFO + key stats
│   └── pipeline_stats.py     # NEW: PipelineRun/Watermark query service
└── routers/
    ├── __init__.py
    ├── admin.py               # Existing admin endpoints (from routers/admin.py)
    ├── health.py              # Health check (from routers/health.py)
    ├── user_observability.py  # User-facing endpoints (from routers/observability.py)
    └── command_center.py      # NEW: Command center aggregate endpoints
```

### 2.3 Migration Strategy

**Split into two sub-stories for reduced blast radius:**

- **S1a:** Move `agents/observability.py`, `agents/observability_writer.py`, `agents/token_budget.py` → `observability/collector.py`, `observability/writer.py`, `observability/token_budget.py`. These have the most contained import graph (primarily `agents/` and `routers/`). Ship S1a, run full test suite.
- **S1b:** Move `request_context.py`, `services/langfuse_service.py`, `services/observability_queries.py`, `models/logs.py`, `routers/admin.py`, `routers/observability.py`, `routers/health.py` → new locations. `request_context.py` has the widest blast radius (15+ importers across 6 packages).

**Migration rules:**
- Zero logic changes. All 1787 tests must pass after each sub-story.
- Old import paths get re-export shims. Shims remain for **at least one full release cycle** — not removed in follow-up.
- `backend/models/logs.py` keeps an import of the models from the new location (Alembic discovery requires models in `backend/models/__init__.py`).
- **S1 merges as its own PR** and is a gate before any Story 2+ work begins. Not just "first story" — an explicit merge gate.

**Verification checklist (after each sub-story):**
1. `uv run pytest tests/ -v --tb=short` — 0 failures
2. `uv run alembic check` — no false migration drift (Alembic falsely detects table drops when import chains change)
3. Grep all test files for patch targets referencing moved modules — update any `@patch("backend.agents.observability.xxx")` patterns
4. Verify shims work: `python -c "from backend.agents.observability import ObservabilityCollector"` in fresh interpreter
5. Verify Celery worker starts and loads modules correctly (lazy imports in `try/except` blocks are the highest-risk pattern)

---

## 3. Backend Instrumentation — New Metrics

### 3.1 HTTP Request Metrics Middleware

**File:** `backend/observability/metrics/http_middleware.py`

ASGI middleware that wraps every request and records metrics to **Redis** (multi-worker safe).

| Metric | Type | Storage |
|--------|------|---------|
| `request_count` | Counter | Redis INCRBY, keyed by `(method, path_template, status_code)` |
| `request_latency_ms` | Sliding window | Redis sorted set (same pattern as TokenBudget) |
| `error_count` | Counter | Redis INCRBY, subset where status >= 400 |
| `active_requests` | Gauge | Per-process atomic int (this metric is inherently per-worker; documented as such) |

**Why Redis, not in-memory:** The codebase already solved multi-worker metrics correctly with `TokenBudget` (Redis sorted sets + Lua scripts). In-memory counters would return 1/N traffic under multi-worker Uvicorn. Redis counters add ~1ms per request — negligible.

**Sliding window (not periodic reset):** Latency data uses a 5-minute sliding window via Redis sorted sets. Old entries age out continuously — no cliff-edge reset, no false zeros. The frontend always sees metrics based on the last 5 minutes of data regardless of when it polls.

**Insufficient data handling:** If the window contains fewer than 20 requests, percentiles return `null` (not misleading values from 3 data points). `error_rate_pct` returns `null` when `request_count == 0`.

**Path normalization:** Replace path params with placeholders (`/api/v1/stocks/AAPL/prices` → `/api/v1/stocks/{ticker}/prices`) using FastAPI's route matching.

**Excluded paths:** `/api/v1/admin/command-center*` and `/api/v1/health` are excluded from metrics collection. The command center must not inflate its own latency percentiles.

**No external dependencies.** Uses Redis (already available). No Prometheus client library.

### 3.2 Cache Hit/Miss Tracking

**File:** `backend/observability/metrics/cache_stats.py`

Add **monotonically increasing counters** to `CacheService.get()` and `CacheService.set()`:

```python
class CacheStats:
    hits: int          # monotonic, never reset
    misses: int        # monotonic, never reset
    sets: int          # monotonic, never reset
    deletes: int       # monotonic, never reset
    errors: int        # monotonic, never reset
    hits_by_namespace: dict[str, int]   # monotonic per namespace
    misses_by_namespace: dict[str, int] # monotonic per namespace
```

**Why monotonic (not reset-on-read):** Reset-on-read is not safe with multiple consumers (two admin tabs = second tab sees zeros). The frontend computes rates by diffing consecutive snapshots: `rate = (current - previous) / interval`. This is idempotent, safe for multiple consumers, and survives missed polls. 64-bit counters at 10K ops/sec last 58 million years.

Exposed via `CacheService.get_stats() -> CacheStats`.

### 3.3 Database Pool Statistics

**File:** `backend/observability/metrics/db_pool.py`

SQLAlchemy provides `pool.status()` which returns pool size, checked-out connections, and overflow. Add event listeners:

```python
@event.listens_for(engine.sync_engine, "checkout")
@event.listens_for(engine.sync_engine, "checkin")
```

Track: `pool_size`, `checked_out`, `overflow`, `checkout_wait_ms` (P95).

**`pg_stat_statements` deferred** — requires DBA-level extension verification. Not in MVP scope.

### 3.4 Redis Statistics

**File:** `backend/observability/metrics/redis_stats.py`

Call `Redis.info('memory')` and `Redis.info('keyspace')` periodically (every 30s, cached):

| Metric | Source |
|--------|--------|
| `used_memory_bytes` | `INFO memory` |
| `used_memory_human` | `INFO memory` |
| `maxmemory` | `INFO memory` |
| `fragmentation_ratio` | `INFO memory` |
| `db_keys` | `INFO keyspace` |
| `evicted_keys` | `INFO stats` |
| `blocked_clients` | `INFO clients` |

**Namespace key counts:** Pre-computed via Redis counter keys (`__meta:ns:{namespace}:count`), incremented on `CacheService.set()`, decremented on `CacheService.delete()`. **No SCAN in production** — SCAN with patterns on 12K+ keys can block Redis for production traffic. Accept approximate counts (TTL expiry won't decrement counters; periodically reconcile via a nightly task if accuracy matters).

### 3.5 Pipeline Statistics

**File:** `backend/observability/metrics/pipeline_stats.py`

Query service for existing `PipelineRun` and `PipelineWatermark` models (data exists, just no API):

| Query | Returns |
|-------|---------|
| `get_latest_runs(n=5)` | Last N runs per pipeline_name with status, duration, ticker counts |
| `get_watermarks()` | All watermarks with gap detection |
| `get_run_history(days=7)` | Run timeline for trend charts |
| `get_failed_tickers(run_id)` | Error details from `error_summary` JSONB |
| `get_step_durations(run_id)` | Per-step timing from `step_durations` JSONB |

### 3.6 Auth Audit Trail

**New model:** `LoginAttempt`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | PK |
| `timestamp` | DateTime | Indexed |
| `user_id` | UUID FK, nullable | NULL for failed attempts with unknown email |
| `email` | String(255) | Attempted email |
| `ip_address` | String(45) | IPv4 or IPv6 |
| `user_agent` | String(500) | Browser/client |
| `success` | Boolean | |
| `failure_reason` | String(50), nullable | "invalid_password", "account_disabled", "rate_limited" |

**Write points:** `POST /auth/login` (success + failure), `POST /auth/register` (success).

**Data retention:** 90-day auto-purge via `purge_login_attempts` Celery Beat task (runs daily at 3:00 AM ET). Batch deletes (1000 rows per iteration with `LIMIT`) to avoid long-running transactions. This is specced here, not deferred — compliance requires implementation with the model.

**IP-to-geo:** Explicitly out of scope. No geolocation resolution. Raw IP stored only for brute force detection and audit trail.

**Privacy compliance:** IP addresses are PII under both GDPR and CCPA/US state privacy laws. The 90-day retention + auto-purge satisfies both frameworks. If operating in EU, add a privacy notice reference.

### 3.7 Alert Analytics (Phase 2)

New query functions on existing `InAppAlert` model:

| Function | Returns |
|----------|---------|
| `get_alert_stats(hours=24)` | Total, by severity, by type, dedup suppressed count |
| `get_alert_timeline(days=7)` | Hourly alert generation counts |
| `get_unread_by_user()` | Per-user unread counts (admin view) |

### 3.8 Chat Analytics (Phase 2)

New query functions on existing `ChatSession` and `ChatMessage` models:

| Function | Returns |
|----------|---------|
| `get_chat_throughput(hours=24)` | Messages per hour, total sessions |
| `get_response_time_stats()` | P50, P95, P99 from `ChatMessage.latency_ms` |
| `get_tool_usage_stats(hours=24)` | Tool call counts from `ToolExecutionLog`, grouped by tool_name |
| `get_feedback_stats(hours=24)` | Thumbs up/down counts, ratio |
| `get_decline_breakdown(hours=24)` | Decline reasons from `ChatMessage` where declined |

### 3.9 Forecast Model Health (Phase 2)

New query functions on existing `ModelVersion` and `ForecastResult` models:

| Function | Returns |
|----------|---------|
| `get_model_health()` | Per-model: age, is_active, MAPE from metrics JSONB, staleness flag |
| `get_forecast_accuracy(horizons=[30,90])` | Hit rate by horizon from evaluated ForecastResults |
| `get_drift_status()` | Last drift check timestamp, any active drift alerts |
| `get_retrain_queue()` | Tickers queued for retrain |

---

## 4. Database Changes

### 4.1 New Model: `LoginAttempt` (Migration 021)

See §3.6 for schema. Not a hypertable (low volume). Index on `(timestamp, success)` for dashboard queries.

### 4.2 New Columns on `PipelineRun` (Migration 022 — separate from 021)

| Column | Type | Notes |
|--------|------|-------|
| `step_durations` | JSONB, nullable | `{"cache_invalidation": 0.3, "price_refresh": 252.0, ...}` |
| `total_duration_seconds` | Float, nullable | Wall-clock seconds for entire run |

**Write path:** Add `record_step_duration(run_id, step_name, duration_seconds)` to `PipelineRunner` — uses atomic JSONB merge: `SET step_durations = COALESCE(step_durations, '{}'::jsonb) || '{"step_name": 1.23}'::jsonb`. Each pipeline step calls this independently — no race conditions, no monolithic write at `complete_run()`. `total_duration_seconds` computed from `completed_at - started_at` at `complete_run()`.

---

## 5. Command Center API

### 5.1 Aggregate Endpoint

**`GET /api/v1/admin/command-center`**

Returns the L1 dashboard payload in a single call. Frontend polls this every 15 seconds.

**Execution strategy — `asyncio.gather()` with per-zone circuit breakers:**

```python
async def get_command_center(db: AsyncSession, redis: Redis) -> CommandCenterResponse:
    zones = await asyncio.gather(
        _collect_zone("system_health", _get_system_health(db, redis), timeout=3),
        _collect_zone("api_traffic", _get_api_traffic(redis), timeout=3),
        _collect_zone("llm_operations", _get_llm_operations(db, redis), timeout=3),
        _collect_zone("pipeline", _get_pipeline(db), timeout=3),
        return_exceptions=True,  # never let one zone kill the whole response
    )
    # Each zone returns data or {"status": "unavailable", "error": "..."}
```

**Per-zone independence:** If Redis is down, the `api_traffic` and `llm_operations.token_budgets` zones degrade to `"status": "unavailable"` while `pipeline` and `system_health.database` continue working. The response includes `"degraded_zones": ["cache", "api_traffic"]` at the top level. The frontend dims unavailable zones with a warning badge.

**Server-side cache (10 seconds):** The aggregate response is cached in Redis with a 10-second TTL. Multiple admin tabs or concurrent polls within the same 10s window share a single computation. This eliminates N×10 DB query amplification. Cache key: `admin:command_center:aggregate`.

**Self-monitoring:** The response includes a `"_meta": {"assembly_ms": 142}` field. If assembly exceeds 2 seconds, a warning is logged. The frontend displays `assembly_ms` in a tooltip on the top bar.

**MVP Phase 1 response (4 zones):**

```json
{
  "timestamp": "2026-03-31T14:23:00Z",
  "_meta": { "assembly_ms": 142, "degraded_zones": [] },
  "system_health": {
    "status": "ok",
    "database": { "healthy": true, "latency_ms": 2, "pool_active": 3, "pool_size": 5, "pool_overflow": 0, "migration_head": "021" },
    "redis": { "healthy": true, "latency_ms": 1, "memory_used_mb": 45, "memory_max_mb": 256, "total_keys": 12340, "cache_hit_rate": 0.78 },
    "mcp": { "healthy": true, "mode": "stdio", "tool_count": 24, "restarts": 0, "uptime_seconds": 15780 },
    "celery": { "workers": 3, "queued": 0, "beat_active": true },
    "langfuse": { "connected": true, "traces_today": 247, "spans_today": 1830 }
  },
  "api_traffic": {
    "window_seconds": 300,
    "sample_count": 1847,
    "rps_avg": 18.4,
    "latency_p50_ms": 45,
    "latency_p95_ms": 120,
    "latency_p99_ms": 450,
    "error_rate_pct": 0.3,
    "total_requests_today": 2340,
    "total_errors_today": 7,
    "top_endpoints": [
      { "path": "/api/v1/stocks/signals/bulk", "count": 487, "avg_ms": 89, "errors": 2 }
    ]
  },
  "llm_operations": {
    "tiers": [
      { "name": "groq", "status": "healthy", "models": 3, "p95_ms": 340 },
      { "name": "anthropic", "status": "degraded", "models": 1, "p95_ms": 1200 },
      { "name": "openai", "status": "disabled", "models": 0, "p95_ms": null }
    ],
    "cost_today_usd": 2.47,
    "cost_yesterday_usd": 2.12,
    "cost_week_usd": 18.30,
    "cascade_rate_pct": 2.1,
    "token_budgets": [
      { "model": "llama-3.3-70b-versatile", "tpm_used_pct": 34, "rpm_used_pct": 22 }
    ]
  },
  "pipeline": {
    "last_run": {
      "started_at": "2026-03-30T21:30:00-04:00",
      "status": "success",
      "total_duration_seconds": 612,
      "tickers_succeeded": 487,
      "tickers_failed": 3,
      "step_durations": { "cache_invalidation": 0.3, "price_refresh": 252.0 }
    },
    "watermarks": [
      { "pipeline": "price_refresh", "last_date": "2026-03-30", "status": "ok" }
    ],
    "next_run_at": "2026-03-31T21:30:00-04:00"
  }
}
```

**Phase 2 additions** (added to the same endpoint when implemented):

```json
{
  "cache": {
    "hit_rate_pct": 78, "total_hits": 9625, "total_misses": 2715,
    "namespaces": [{ "name": "app:signals", "keys": 340 }],
    "memory_used_mb": 45, "memory_max_mb": 256
  },
  "chat": {
    "messages_per_hour": 34, "avg_response_ms": 3200, "p95_response_ms": 8400,
    "tool_calls_today": 1247, "feedback_positive_pct": 89,
    "active_sessions": 4, "top_tools": [{ "name": "get_stock_price", "count": 312 }]
  },
  "auth": {
    "active_users_24h": 12, "login_success_rate_pct": 98.5,
    "login_failed_24h": 7, "token_refreshes_per_hour": 45, "rate_limit_hits_24h": 3
  },
  "alerts": {
    "generated_today": 14, "by_severity": { "critical": 2, "warning": 5, "info": 7 },
    "dedup_suppressed_today": 23, "unread_total": 9
  },
  "forecasting": {
    "models_fresh": 3, "models_stale": 1, "models_drifting": 0,
    "accuracy_30d_pct": 72, "accuracy_90d_pct": 68, "vix_regime": "normal"
  }
}
```

### 5.2 Drill-Down Endpoints

Each zone has a dedicated detail endpoint for L2 expansion:

**MVP (Phase 1):**

| Endpoint | Returns |
|----------|---------|
| `GET /admin/command-center/api-traffic?hours=24` | Full endpoint table, latency histogram, error log |
| `GET /admin/command-center/llm?hours=24` | Per-model cost chart data, cascade log, token consumption |
| `GET /admin/command-center/pipeline?days=7` | Run history, failed tickers, step duration trends |

**Phase 2:**

| Endpoint | Returns |
|----------|---------|
| `GET /admin/command-center/cache` | Per-namespace TTL stats, eviction timeline |
| `GET /admin/command-center/chat?hours=24` | Throughput chart, agent distribution, decline breakdown |
| `GET /admin/command-center/auth?hours=24` | Login attempt log, session inventory |
| `GET /admin/command-center/alerts?days=7` | Alert timeline, per-type breakdown |
| `GET /admin/command-center/forecasting` | Model details, accuracy by sector, retrain queue |

All endpoints require admin role. All return JSON with Pydantic response models.

**Drill-downs do NOT auto-poll.** Fetched once on user click. Manual "Refresh" button in the drill-down sheet. Avoids doubling DB load during incident investigation.

### 5.3 Polling Strategy

- **L1 aggregate:** Poll every 15 seconds via TanStack Query `refetchInterval`. Server-side cached for 10s.
- **L2 drill-downs:** Fetched on-demand. Manual refresh only. Cached client-side for 30 seconds.
- **Tab focus:** `refetchOnWindowFocus: true` — immediate refetch when browser tab regains focus (eliminates stale-data-on-return after background tab throttling).
- **No WebSocket.** Polling is simpler, sufficient for admin use, and avoids infrastructure complexity.

### 5.4 Celery Health Check Implementation

**Mechanism:**
- **Worker count:** `celery.control.inspect().ping()` wrapped in `asyncio.to_thread()` with 2-second timeout. Returns count of responding workers. Timeout returns `null` (unknown), not `0`.
- **Queue depth:** `redis.llen('celery')` — fast Redis call, no Celery broker overhead.
- **Beat active:** Inferred from `PipelineRun` table — if the most recent scheduled run started within the expected window (e.g., nightly chain ran within last 26 hours), beat is presumed active.
- **Cached for 30 seconds** — `inspect.ping()` is a broadcast to all workers and should not run on every 15s poll.

### 5.5 Langfuse Health Check Implementation

**Mechanism:**
- **Connected:** Lightweight health probe — `langfuse_service.client.auth_check()` with 2-second timeout, cached for 60 seconds. Current `self.enabled` flag only reflects initialization, not live connectivity.
- **traces_today:** Query local `llm_call_log` table for today's rows where `langfuse_trace_id IS NOT NULL`. Does NOT call Langfuse API (no such endpoint exists). This counts traces we sent, not traces Langfuse received — good enough for dashboard purposes.
- **spans_today:** Same approach — count `tool_execution_log` rows with today's timestamp.

---

## 6. Frontend Design

### 6.1 Route

`/admin/command-center` — protected by admin role check. Redirect non-admins to dashboard.

### 6.2 Layout

**MVP (Phase 1) — 3-column grid:**

| Col 1 (280px) | Col 2 (1fr) | Col 3 (1fr) |
|---|---|---|
| System Health (spans 2 rows) | API Traffic | LLM Operations |
| | Pipeline (spans 2 cols) | |

**Phase 2 — expand to 4-column grid:**

| Col 1 (280px) | Col 2 (1fr) | Col 3 (1fr) | Col 4 (260px) |
|---|---|---|---|
| System Health (spans 3 rows) | API Traffic | LLM Operations | Cache (spans 2 rows) |
| | Pipeline | Chat & Agent | |
| | Auth & Security | Alerts & Forecasting (spans 2 cols) | |

### 6.3 Components

**MVP (Phase 1):**

| Component | Data Source | Refresh |
|-----------|------------|---------|
| `CommandCenterPage` | Orchestrates polling, manages drill-down state | 15s poll |
| `SystemHealthPanel` | `system_health` from aggregate | Auto |
| `ApiTrafficPanel` | `api_traffic` + drill-down | Auto + on-demand |
| `LlmOperationsPanel` | `llm_operations` + drill-down | Auto + on-demand |
| `PipelinePanel` | `pipeline` + drill-down | Auto + on-demand |
| `StatusDot` | Pulsing health indicator (green/yellow/red) | CSS animation |
| `GaugeBar` | Horizontal fill bar with percentage | Props |
| `MiniSparkline` | SVG sparkline for trends (reuse existing `sparkline.tsx`) | Props |
| `MetricCard` | Label + big number + subtitle | Props |
| `DrillDownSheet` | Slide-out panel for L2 detail, manual Refresh button | On click |
| `LastRefreshedIndicator` | "Last refreshed: Xs ago" — yellow at >30s, red at >60s | Timer |
| `DegradedZoneBadge` | Warning badge on zones in `degraded_zones` array | Props |

**Phase 2 adds:** `CachePanel`, `ChatPanel`, `AuthPanel`, `AlertsForecastPanel`.

### 6.4 Design System

Inherits existing navy dark theme:
- `--color-bg-primary`, `--color-bg-card`, `--color-border` from existing CSS variables
- Sora font for headings, JetBrains Mono for metrics
- Cyan accent for primary metrics, green/yellow/red for health states
- No light mode (admin tool, always dark)

### 6.5 Hooks

| Hook | Purpose |
|------|---------|
| `useCommandCenter()` | Polls aggregate endpoint every 15s, `refetchOnWindowFocus: true`, returns typed state |
| `useCommandCenterDrillDown(zone)` | Fetches drill-down data on demand, caches 30s, manual refresh via `refetch()` |

### 6.6 UX Details

- **Per-zone `data_as_of` timestamp:** Each zone card shows when its data was last computed (from `_meta.assembly_ms` and server timestamp). Independent of poll cycle.
- **Copy as JSON:** Each zone has a "Copy JSON" button in the drill-down sheet for incident reports.
- **Cost comparison:** LLM zone shows `cost_today` vs `cost_yesterday` with a delta indicator (green arrow down = cheaper, red arrow up = more expensive).
- **Insufficient data states:** When sliding window has < 20 samples, metric cards show "—" instead of misleading numbers.

---

## 7. Scope & Non-Scope

### In Scope — MVP (Phase 1)

- Package extraction S1a + S1b (pure refactor, merged independently)
- HTTP request metrics middleware (Redis-backed, sliding window)
- DB pool stats exposure
- Pipeline status endpoints (using existing models) + step_durations write path
- TokenBudget status exposure
- Celery + Langfuse health check implementations
- LoginAttempt model + migration + purge task
- L1 aggregate endpoint (4 zones) with `asyncio.gather()` + per-zone circuit breakers + 10s server-side cache
- 3 L2 drill-down endpoints (API traffic, LLM, Pipeline)
- Frontend command center page with 4 zone panels + drill-downs
- `LastRefreshedIndicator`, `DegradedZoneBadge` UI components

### In Scope — Phase 2

- Cache hit/miss monotonic counters
- Redis stats (INFO-based, pre-computed namespace counts)
- Chat analytics queries
- Alert analytics queries
- Forecast model health queries
- 5 additional drill-down endpoints
- 4 additional frontend zone panels

### Out of Scope (deferred beyond Phase 2)

- **OpenTelemetry / Prometheus:** Not needed for MVP. Can add exporters later.
- **Structured logging (structlog):** Installed but unwired. Separate initiative.
- **Frontend RUM (Sentry, Web Vitals):** Would add a "Frontend Performance" zone later.
- **Real-time WebSocket updates:** Polling is sufficient for admin use.
- **Celery Flower integration:** Use our own metrics.
- **`pg_stat_statements` slow query log:** Requires DBA-level extension verification.
- **LLM model config inline editing:** Already exists in admin endpoints.
- **Alerting rules / thresholds:** Document thresholds (see §7.1) but don't implement automated alerts yet.
- **IP-to-geolocation resolution:** Explicitly out of scope.

### 7.1 Documented Alerting Thresholds (for future implementation)

These are the "what does bad look like" reference for operators. Not automated in MVP, but documented so the ops team knows what to watch:

| Metric | Threshold | Meaning |
|--------|-----------|---------|
| `pipeline.last_run.status` | `failed` for 2 consecutive runs | Nightly pipeline broken |
| `llm_operations.cascade_rate_pct` | > 10% sustained 15 min | LLM tier failing over excessively |
| `auth.login_failed_24h` | > 50 | Potential brute force |
| `cache.hit_rate_pct` | < 50% sustained 30 min | Cache eviction storm |
| `system_health.database.pool_active` | == pool_size | Connection pool exhaustion |
| `api_traffic.error_rate_pct` | > 5% sustained 5 min | Systemic API errors |
| `_meta.assembly_ms` | > 2000 | Command center itself is slow |

---

## 8. Security Considerations

- All command center endpoints require `require_admin()`.
- `LoginAttempt` stores IP addresses — PII under GDPR and CCPA. 90-day retention enforced by `purge_login_attempts` Celery Beat task (specified in §3.6, not deferred). IP-to-geo explicitly out of scope.
- Cache stats and Redis INFO do not expose sensitive data (no key values, only counts and sizes).
- HTTP middleware must NOT log request/response bodies — only method, path template, status, latency.
- Token budget percentages are safe to expose (no absolute limits visible to non-admins).
- Admin paths excluded from HTTP metrics to prevent self-referential data inflation.

---

## 9. Testing Strategy

| Layer | Tests | Notes |
|-------|-------|-------|
| Package extraction S1a | Full test suite — 0 failures | Alembic check + shim smoke test |
| Package extraction S1b | Full test suite — 0 failures | Patch target grep + lazy import verification |
| HTTP middleware | 10-12 unit tests | Redis counter accuracy, sliding window, path normalization, excluded paths, insufficient data `null` return |
| DB pool stats | 3-4 unit tests | Event listener registration, stat collection |
| Pipeline stats | 6-8 unit tests | Query correctness, gap detection, step_durations JSONB merge |
| LoginAttempt | 5-6 unit + 3-4 API tests | Model CRUD, auth router hooks, purge task |
| TokenBudget exposure | 2-3 unit tests | Status endpoint, percentage computation |
| Aggregate endpoint | 6-8 API tests | Auth gate, response shape, **degraded mode (Redis down)**, **degraded mode (DB slow)**, server-side cache hit, `_meta.assembly_ms` |
| Drill-down endpoints | 6 API tests (2 per endpoint) | Auth gate, response shape |
| Celery health check | 3-4 unit tests | Async timeout, `null` on timeout, cache behavior |
| Langfuse health check | 2-3 unit tests | Probe timeout, traces_today from local DB |
| Frontend components | 8-12 Jest tests | Render, polling, drill-down, `LastRefreshedIndicator`, `DegradedZoneBadge`, `refetchOnWindowFocus` |
| **Total new tests (Phase 1)** | **~60-80** | |
| **Phase 2 additions** | **~30-40** | Cache stats, chat, alerts, forecast queries, 4 more panels |

---

## 10. Effort Estimate

### Phase 1 — MVP (4 zones)

| Story | Scope | Estimate |
|-------|-------|----------|
| S1a: Package extraction — agents/ | Move collector, writer, token_budget + shims | ~2.5h |
| S1b: Package extraction — services/routers/context | Move remaining files + wide import update | ~3h |
| **Gate: S1 PR merged, verified** | | |
| S2: HTTP middleware (Redis-backed) | Sliding window, path normalization, excluded paths | ~3.5h |
| S3: DB pool stats + pipeline stats | Pool listeners, PipelineRun query service, step_durations write path | ~3h |
| S4: Auth audit trail | LoginAttempt model, migration 021, router hooks, purge Celery task | ~2.5h |
| S5: PipelineRun columns | Migration 022, `record_step_duration()`, `complete_run()` update | ~1.5h |
| S6: TokenBudget + Celery + Langfuse health | Status endpoint, health check implementations | ~2h |
| S7: Aggregate endpoint | 4-zone assembly, `asyncio.gather()`, circuit breakers, server-side cache | ~4h |
| S8: Drill-down endpoints (3) | API traffic, LLM, Pipeline detail endpoints + schemas | ~3h |
| S9: Frontend L1 | 4 zone panels + hooks + page + StatusDot/GaugeBar/MetricCard/LastRefreshed | ~6h |
| S10: Frontend L2 drill-downs (3) | 3 drill-down sheets + detail components | ~4h |
| **Phase 1 Total** | | **~35h (5-6 sessions)** |

### Phase 2 — Remaining 4 zones

| Story | Scope | Estimate |
|-------|-------|----------|
| S11: Cache stats + Redis stats | Monotonic counters, namespace pre-computation, Redis INFO | ~3h |
| S12: Chat + Alert + Forecast analytics | Query services on existing models | ~3h |
| S13: Aggregate endpoint expansion | Add 4 zones to gather, 5 new drill-down endpoints | ~3h |
| S14: Frontend — 4 additional zone panels + drill-downs | Cache, Chat, Auth, Alerts/Forecast panels | ~6h |
| **Phase 2 Total** | | **~15h (2-3 sessions)** |

### Grand Total: ~50h (7-9 sessions)

---

## 11. Dependencies

- No external library additions required (Redis already available, no Prometheus/OTel).
- Frontend: no new npm packages (charts use Recharts + existing SVG sparkline component).

---

## 12. Migration from Prototype

The HTML prototype (`command-center-prototype.html`) serves as the visual reference. The production implementation:
- Uses React components (not raw HTML/Canvas)
- Uses TanStack Query for polling (not setInterval)
- Uses existing shadcn/ui primitives where applicable
- Uses Recharts for charts (consistent with rest of app)
- Inherits existing CSS variable system (not hardcoded colors)

The prototype file should be moved to `docs/superpowers/archive/` after the frontend is built.

---

## Appendix A: Expert Review Findings & Resolutions

| # | Finding | Source | Resolution |
|---|---------|--------|------------|
| C1 | In-memory HTTP metrics broken for multi-worker | All 3 | Redis-backed counters + sliding window (§3.1) |
| C2 | No per-zone circuit breakers | Nygard, Ops TL | `asyncio.gather(return_exceptions=True)` + `degraded_zones` (§5.1) |
| C3 | Aggregate endpoint needs parallelism + caching | All 3 | `asyncio.gather()` + 10s server-side cache (§5.1) |
| I1 | Cache stats reset-on-read loses data | Fowler, Nygard | Monotonic counters, frontend diffs (§3.2) |
| I2 | 5-min reset creates false zeros | Ops TL | Sliding window, `null` for insufficient data (§3.1) |
| I3 | LoginAttempt purge missing | Fowler, Nygard | Celery Beat task specced inline (§3.6) |
| I4 | Celery health unspecified | Nygard, Ops TL | `inspect.ping()` + `llen` + PipelineRun inference (§5.4) |
| I5 | Langfuse health stale | Nygard | Probe + local DB count (§5.5) |
| I6 | Redis SCAN blocks production | Nygard | Pre-computed counters, no SCAN (§3.4) |
| I7 | PipelineRunner write path unspecified | Nygard | Atomic JSONB merge per step (§4.2) |
| I8 | S1 must merge independently | Fowler, Ops TL | Explicit gate (§2.3) |
| I9 | Split S1 into two sub-stories | Ops TL | S1a + S1b (§2.3) |
| I10 | Migration bundles unrelated changes | Nygard | Split into 021 + 022 (§4) |
| I11 | Effort underestimated | Ops TL | Revised to ~50h total (§10) |
| I12 | pg_stat_statements in-scope AND out-of-scope | Fowler, Nygard | Removed from §3.3, deferred (§7) |
| I13 | CCPA compliance for IP storage | Fowler | Added to §3.6 and §8 |
| M1 | Browser tab backgrounding | Fowler | `refetchOnWindowFocus: true` (§5.3) |
| M2 | Command center inflates own metrics | Fowler | Excluded paths (§3.1) |
| M3 | Last refreshed indicator | Ops TL | `LastRefreshedIndicator` component (§6.3) |
| M4 | Cost baseline comparison | Ops TL | `cost_yesterday_usd` added (§5.1) |
| M5 | Drill-downs should not auto-poll | Ops TL | Manual Refresh only (§5.2) |
| M6 | Per-zone data_as_of timestamps | Ops TL | Added to UX details (§6.6) |
| M7 | Document alerting thresholds | Ops TL | §7.1 threshold reference table |
| — | MVP scoping suggestion | Ops TL | Phase 1 (4 zones) + Phase 2 (4 zones) split (§1.4) |
