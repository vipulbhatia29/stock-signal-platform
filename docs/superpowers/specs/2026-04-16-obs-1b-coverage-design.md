# Sub-Spec 1b — Coverage Completion

**Parent:** [Master Architecture Spec](./2026-04-16-obs-master-design.md)
**Date:** 2026-04-16
**Status:** Draft — awaiting PM review
**Estimate:** ~8-10 days across 7 PRs
**Prerequisites:** [Sub-Spec 1a](./2026-04-16-obs-1a-foundations-design.md) complete (SDK + trace_id + external API log)

---

## 1. Scope

With 1a establishing primitives, 1b completes coverage for every remaining layer. After 1b, every application operation emits a structured event correlated by `trace_id`.

Layers completed in this sub-epic:
- **HTTP** — per-request row, error log, 5xx capture, environment snapshot
- **Auth** — JWT verification failure log, OAuth event log, email send log, CSRF metrics, existing `login_attempts` enriched with `trace_id`
- **DB** — slow-query log, pool event log, schema migration log, deadlock detection
- **Cache** — cache operation log (sampled), rate-limiter event log
- **Celery** — worker heartbeat, beat schedule drift, queue depth, `retry_count` wiring
- **Agent** — intent classification log, termination reason enum, provider health snapshots, agent reasoning log
- **Frontend** — beacon API + `frontend_error_log`
- **Deploy** — GitHub Actions hook → `deploy_events` table
- **Coverage** — Semgrep rules + CI gate

## 2. Deliverables

### 2.1 HTTP layer

**New tables:**

```sql
CREATE TABLE observability.request_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID NOT NULL,
    span_id UUID NOT NULL,
    user_id UUID,
    session_id UUID,

    method TEXT NOT NULL,
    path TEXT NOT NULL,           -- normalized (UUIDs → {id}, tickers → {ticker})
    raw_path TEXT NOT NULL,       -- original for debugging
    status_code INT NOT NULL,
    latency_ms INT NOT NULL,
    request_bytes INT,
    response_bytes INT,

    ip_address INET,
    user_agent TEXT,
    referer TEXT,

    environment_snapshot JSONB,   -- feature flags, active LLM model config, rate limiter state, git SHA (capped ~1KB)

    env TEXT NOT NULL,
    git_sha TEXT
);

SELECT create_hypertable('observability.request_log', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ON observability.request_log (trace_id);
CREATE INDEX ON observability.request_log (user_id, ts DESC);
CREATE INDEX ON observability.request_log (status_code, ts DESC) WHERE status_code >= 400;
CREATE INDEX ON observability.request_log (path, ts DESC);

CREATE TABLE observability.api_error_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID NOT NULL,
    span_id UUID NOT NULL,
    request_log_id UUID REFERENCES observability.request_log(id),
    user_id UUID,

    status_code INT NOT NULL,
    error_type TEXT NOT NULL,         -- enum: validation|auth|permission|not_found|rate_limit|domain|internal_server
    error_reason TEXT,                -- enum per error_type
    error_message TEXT,               -- short human-readable
    stack_signature TEXT,
    stack_hash CHAR(64),
    stack_trace TEXT,                 -- only for 5xx; truncated
    exception_class TEXT,             -- e.g., ValueError, HTTPException

    env TEXT NOT NULL,
    git_sha TEXT
);

SELECT create_hypertable('observability.api_error_log', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ON observability.api_error_log (trace_id);
CREATE INDEX ON observability.api_error_log (status_code, ts DESC);
CREATE INDEX ON observability.api_error_log (stack_hash);
```

**Retention:** `request_log` 30 days; `api_error_log` 90 days.

**Implementation:**
- Extend trace_id middleware from 1a to ALSO write `request_log` row on response
- New exception middleware catches unhandled exceptions (including 5xx) → writes `api_error_log` with full stack
- `environment_snapshot` captured at request start from a per-request collector (feature flags, LLM model config version, rate limiter states)

**Replaces:** Existing `HttpMetricsCollector` (Redis-aggregated) stays for real-time percentiles on dashboard; `request_log` is authoritative historical record.

### 2.2 Auth layer

**New tables:**

```sql
CREATE TABLE observability.auth_event_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,                    -- nullable; beat-triggered auth (rare) may not have trace
    span_id UUID,
    user_id UUID,                     -- nullable for pre-auth events

    event_type TEXT NOT NULL,         -- enum: jwt_verify_failure|token_refresh|logout|email_verify_attempt|password_reset_request|password_reset_complete|session_terminated|revocation_applied
    outcome TEXT NOT NULL,            -- enum: success|failure
    failure_reason TEXT,              -- enum: expired|malformed|revoked|wrong_type|not_found|rate_limited|invalid_token

    ip_address INET,
    user_agent TEXT,
    method TEXT,                      -- request method, if applicable
    path TEXT,                        -- request path, if applicable

    metadata JSONB,                   -- event-specific context (small)
    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.auth_event_log (user_id, ts DESC);
CREATE INDEX ON observability.auth_event_log (event_type, outcome, ts DESC);
CREATE INDEX ON observability.auth_event_log (trace_id) WHERE trace_id IS NOT NULL;

CREATE TABLE observability.oauth_event_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,
    user_id UUID,

    provider TEXT NOT NULL,           -- enum: google (extensible)
    action TEXT NOT NULL,             -- enum: auth_start|code_exchange|token_refresh|revoke|link_existing|conflict_detected
    status TEXT NOT NULL,             -- enum: success|failure
    error_reason TEXT,                -- enum: invalid_state|invalid_code|network_error|provider_error|user_cancelled|email_mismatch
    attempt_number INT,
    metadata JSONB,

    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.oauth_event_log (user_id, ts DESC);
CREATE INDEX ON observability.oauth_event_log (provider, status, ts DESC);

CREATE TABLE observability.email_send_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,
    user_id UUID,

    recipient_hash CHAR(64) NOT NULL, -- SHA256 of email (PII protection)
    email_type TEXT NOT NULL,         -- enum: verification|password_reset|deletion_confirmation|welcome|digest
    status TEXT NOT NULL,             -- enum: sent|failed|bounced
    error_reason TEXT,                -- enum: provider_down|rate_limited|invalid_recipient|timeout|unknown
    resend_message_id TEXT,

    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.email_send_log (user_id, ts DESC);
CREATE INDEX ON observability.email_send_log (status, ts DESC);
```

**Retention:** 90 days for all three.

**Enhancements to existing:** `login_attempts` gets `trace_id`, `span_id` columns (ALTER TABLE + backfill).

### 2.3 DB layer

**New tables:**

```sql
CREATE TABLE observability.slow_query_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,
    span_id UUID,
    parent_span_id UUID,

    query_text TEXT NOT NULL,         -- normalized (literals → $1, $2)
    query_hash CHAR(64) NOT NULL,     -- SHA256 of normalized query
    duration_ms INT NOT NULL,
    rows_affected INT,

    source_file TEXT,                 -- captured from stack
    source_line INT,
    stack_signature TEXT,

    env TEXT NOT NULL,
    git_sha TEXT
);

SELECT create_hypertable('observability.slow_query_log', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ON observability.slow_query_log (query_hash, ts DESC);
CREATE INDEX ON observability.slow_query_log (duration_ms DESC, ts DESC);
CREATE INDEX ON observability.slow_query_log (trace_id) WHERE trace_id IS NOT NULL;

CREATE TABLE observability.db_pool_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL,         -- enum: exhausted|recovered|slow_checkout|connection_error
    pool_size INT NOT NULL,
    checked_out INT NOT NULL,
    overflow INT NOT NULL,
    duration_ms INT,                  -- how long exhausted
    stack_signature TEXT,

    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.db_pool_event (ts DESC);
CREATE INDEX ON observability.db_pool_event (event_type, ts DESC);

CREATE TABLE observability.schema_migration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    migration_id TEXT NOT NULL,       -- e.g., "030_observability_schema"
    version TEXT NOT NULL,             -- Alembic revision
    status TEXT NOT NULL,             -- enum: pending|running|success|failed|rolled_back
    duration_ms INT,
    error_message TEXT,
    error_reason TEXT,                -- enum: constraint_violation|timeout|manual_abort|dependency_missing|sql_error
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ,
    env TEXT NOT NULL,
    deployed_by TEXT,                 -- github actor
    git_sha TEXT
);

CREATE INDEX ON observability.schema_migration_log (ts DESC);
```

**Retention:** `slow_query_log` 30d; `db_pool_event` 90d; `schema_migration_log` 365d (compliance-adjacent).

**Implementation:**
- SQLAlchemy `before_execute`/`after_execute` event hooks — write `slow_query_log` when duration > 500ms
- Connection pool events (via SQLAlchemy `PoolEvents.connect`, `checkout`, `checkin`, `close_detached`) — write `db_pool_event` on exhaustion/recovery
- `backend/migrations/env.py` — wrap migration execution; emit `schema_migration_log` on each migration

**Query normalization:** parameterized queries converted to canonical form (literals replaced with placeholders), hashed for grouping.

### 2.4 Cache layer

**New tables:**

```sql
CREATE TABLE observability.cache_operation_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,
    span_id UUID,

    operation TEXT NOT NULL,          -- enum: get|set|delete|scan|mget|mset|expire
    key_pattern TEXT NOT NULL,        -- redacted (user:{id}:profile → user:*:profile)
    hit BOOLEAN,                      -- nullable for non-get operations
    latency_ms INT NOT NULL,
    value_bytes INT,                  -- for set operations
    ttl_seconds INT,                  -- for set operations
    error_reason TEXT,                -- enum: connection_error|timeout|nokey|script_not_cached|oom

    env TEXT NOT NULL,
    git_sha TEXT
);

SELECT create_hypertable('observability.cache_operation_log', 'ts', chunk_time_interval => INTERVAL '6 hours');
CREATE INDEX ON observability.cache_operation_log (key_pattern, operation, ts DESC);
CREATE INDEX ON observability.cache_operation_log (error_reason, ts DESC) WHERE error_reason IS NOT NULL;

-- rate_limiter_event table defined in sub-spec 1a (moved there to group with external API work).
-- 1b cache layer only adds cache_operation_log.
```

**Retention:** `cache_operation_log` 7 days (sampled at 1% for non-error ops; 100% for errors).

**Implementation:**
- Extend `backend/services/cache.py` with observation hooks: every GET/SET/DELETE wrapped with latency timer + sample decision (random < 0.01) + error capture

### 2.5 Celery layer

**New tables:**

```sql
CREATE TABLE observability.celery_worker_heartbeat (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    worker_name TEXT NOT NULL,
    hostname TEXT NOT NULL,
    status TEXT NOT NULL,             -- enum: alive|draining|shutdown
    tasks_in_flight INT,
    queue_names TEXT[],               -- queues this worker consumes from
    uptime_seconds INT,
    memory_mb INT,
    env TEXT NOT NULL,
    git_sha TEXT
);

SELECT create_hypertable('observability.celery_worker_heartbeat', 'ts', chunk_time_interval => INTERVAL '1 hour');
CREATE INDEX ON observability.celery_worker_heartbeat (worker_name, ts DESC);

CREATE TABLE observability.beat_schedule_run (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    task_name TEXT NOT NULL,
    scheduled_time TIMESTAMPTZ NOT NULL,
    actual_start_time TIMESTAMPTZ,
    drift_seconds INT,                 -- actual - scheduled
    outcome TEXT,                      -- enum: dispatched|skipped|error
    error_reason TEXT,
    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.beat_schedule_run (task_name, ts DESC);
CREATE INDEX ON observability.beat_schedule_run (drift_seconds DESC) WHERE drift_seconds > 30;

CREATE TABLE observability.celery_queue_depth (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    queue_name TEXT NOT NULL,
    depth INT NOT NULL,
    oldest_task_age_seconds INT,
    env TEXT NOT NULL
);

SELECT create_hypertable('observability.celery_queue_depth', 'ts', chunk_time_interval => INTERVAL '1 hour');
CREATE INDEX ON observability.celery_queue_depth (queue_name, ts DESC);
```

**Retention:** Heartbeat 7 days; beat_schedule_run 90 days; queue_depth 7 days.

**Implementation:**
- Celery signals: `worker_ready`, `worker_heartbeat` (Celery built-in), `worker_shutting_down` → write heartbeat rows
- `before_task_publish` for beat-scheduled tasks: compare scheduled vs actual → write `beat_schedule_run`
- Background task (every 60s): poll Redis queue lengths → write `celery_queue_depth`

**Dead-code fix:** `pipeline_runs.retry_count` — wire into `@tracked_task` so retries actually increment. Comes with a test.

### 2.6 Agent layer

**New tables:**

```sql
CREATE TABLE observability.agent_intent_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID NOT NULL,
    query_id UUID NOT NULL,
    user_id UUID,
    session_id UUID,

    intent TEXT NOT NULL,             -- enum: stock_analysis|portfolio_analysis|screener|forecast|news|compare|clarification_needed|out_of_scope|decline
    confidence NUMERIC(3, 2),          -- 0.00-1.00
    out_of_scope BOOLEAN NOT NULL,
    decline_reason TEXT,               -- enum: out_of_scope|safety|user_asked|insufficient_data|budget_exhausted
    query_text_hash CHAR(64),          -- for dedup / pattern detection

    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.agent_intent_log (query_id);
CREATE INDEX ON observability.agent_intent_log (intent, ts DESC);
CREATE INDEX ON observability.agent_intent_log (decline_reason, ts DESC) WHERE decline_reason IS NOT NULL;

CREATE TABLE observability.agent_reasoning_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID NOT NULL,
    query_id UUID NOT NULL,
    loop_step INT NOT NULL,

    reasoning_type TEXT NOT NULL,     -- enum: plan|reflect|synthesize|clarify|refuse
    content_summary TEXT,              -- first 500 chars of LLM output
    tool_calls_proposed JSONB,         -- what the LLM asked to do
    termination_reason TEXT,           -- enum: normal|max_iterations|wall_clock_timeout|zero_tool_calls|exception (populated on final step)

    env TEXT NOT NULL
);

CREATE INDEX ON observability.agent_reasoning_log (query_id, loop_step);
CREATE INDEX ON observability.agent_reasoning_log (termination_reason, ts DESC) WHERE termination_reason IS NOT NULL;

CREATE TABLE observability.provider_health_snapshot (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider TEXT NOT NULL,           -- enum: openai|anthropic|groq
    model TEXT,
    is_exhausted BOOLEAN NOT NULL,
    exhausted_until TIMESTAMPTZ,
    consecutive_failures INT,
    last_failure_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    requests_last_5m INT,
    errors_last_5m INT,
    avg_latency_ms_last_5m INT,
    env TEXT NOT NULL
);

SELECT create_hypertable('observability.provider_health_snapshot', 'ts', chunk_time_interval => INTERVAL '1 hour');
CREATE INDEX ON observability.provider_health_snapshot (provider, ts DESC);
```

**Retention:** `agent_intent_log` 30d; `agent_reasoning_log` 30d (bounded by LLM cost of the query anyway); `provider_health_snapshot` 30d.

**Implementation:**
- `backend/agents/intent_classifier.py` — emit `agent_intent_log` after classification
- `backend/agents/react_loop.py` — emit `agent_reasoning_log` per iteration; populate `termination_reason` on final step
- Background task every 60s: snapshot in-memory `ProviderHealth` state → `provider_health_snapshot`

### 2.7 Frontend

**New table:**

```sql
CREATE TABLE observability.frontend_error_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,                     -- from last API call's X-Trace-Id response header
    user_id UUID,                      -- nullable (errors before auth)

    error_type TEXT NOT NULL,          -- enum: unhandled_rejection|react_error_boundary|query_error|mutation_error|console_error|network_error
    error_message TEXT,
    error_stack TEXT,                  -- truncated
    page_route TEXT,                   -- Next.js route
    component_name TEXT,               -- from error boundary info
    user_agent TEXT,
    url TEXT,

    metadata JSONB,                    -- API status code if network error, etc.
    env TEXT NOT NULL,
    git_sha TEXT                       -- build SHA from Next.js env
);

CREATE INDEX ON observability.frontend_error_log (user_id, ts DESC);
CREATE INDEX ON observability.frontend_error_log (error_type, ts DESC);
CREATE INDEX ON observability.frontend_error_log (page_route, ts DESC);
```

**Retention:** 30 days.

**Implementation:**
- New endpoint: `POST /api/v1/observability/frontend-error` — accepts batched errors (list, up to 10/request, 1KB each)
- Rate-limited per user/session (10/min)
- Frontend hooks:
  - `window.addEventListener('error', ...)` + `'unhandledrejection'`
  - React error boundary wrapping top-level layout
  - TanStack Query `QueryClient` global `onError`
  - Errors batched client-side (5s window) and POSTed via `navigator.sendBeacon()` (survives page unload)
- Captures current `trace_id` from last received `X-Trace-Id` response header (nullable — non-API errors won't have one)

### 2.7b PII Redaction (applies to 1b-introduced tables)

Several new tables capture user-adjacent data that could contain PII. Redaction applied at ingestion:

| Table.column | PII risk | Redaction at ingestion |
|---|---|---|
| `request_log.raw_path` (query string) | URL query params may contain email, tokens, API keys | Query string scrubbed to enum-whitelisted params only (`page`, `limit`, `sort`, etc.). Unknown params replaced with `REDACTED`. Path itself kept. |
| `frontend_error_log.url` | Same risk | Same whitelist-based scrubbing |
| `frontend_error_log.error_message` | May include console.log PII | Regex-based redaction for common PII patterns (email, credit-card, JWT). Conservative — false positives OK. |
| `auth_event_log.user_agent` | Fingerprinting potential | Stored as-is (user_id already present; no incremental PII risk). Truncated to 500 chars. |
| `auth_event_log.ip_address` | PII | Stored as `INET` native type; retention policy (90d) bounds exposure |
| `email_send_log.recipient_hash` | Email is PII | Always SHA256-hashed at ingestion; raw email never stored |
| `frontend_error_log.error_stack` | May contain PII in closures | Truncated at 5KB; no other redaction (balance: stack traces are debug-critical) |

**Redaction utility:** `backend/observability/instrumentation/pii_redact.py` — shared functions `redact_url()`, `redact_message()`, `hash_email()`. Used by ingestion pipeline.

**Explicit opt-out:** `OBS_REDACT_PII=true|false` (default `true`). Can be disabled in dev for debugging; never in prod.

### 2.8 Deploy events

**New table:**

```sql
CREATE TABLE observability.deploy_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    git_sha CHAR(40) NOT NULL,
    branch TEXT NOT NULL,              -- develop|main|feature branch
    pr_number INT,
    author TEXT NOT NULL,
    commit_message TEXT,
    migrations_applied TEXT[],         -- list of migration IDs
    env TEXT NOT NULL,                 -- prod|staging|dev
    deploy_duration_seconds INT,
    status TEXT NOT NULL               -- enum: success|failed|rolled_back
);

CREATE INDEX ON observability.deploy_events (ts DESC);
CREATE INDEX ON observability.deploy_events (git_sha);
```

**Retention:** 365 days (low volume, high debug value).

**Implementation:**
- GitHub Actions workflow step posts to `/api/v1/observability/deploy-event` on successful deploy
- Run at the end of `ci-merge.yml` and `deploy.yml`

**Authentication (previously hand-wavy — made explicit):**
- Backend env var: `OBS_DEPLOY_WEBHOOK_SECRET` (min 32 bytes, generated via `secrets.token_urlsafe(32)`)
- Same value stored in GitHub Secrets
- GitHub Actions sends: `Authorization: Bearer ${{ secrets.OBS_DEPLOY_WEBHOOK_SECRET }}`
- Backend validates via `secrets.compare_digest()` (constant-time) before accepting payload; returns 401 on mismatch
- Also validates `X-GitHub-Event: deployment` header as secondary sanity check
- Rate-limited at 10/min per IP to prevent abuse even with leaked secret
- Endpoint logs all auth failures to `api_error_log` with `error_reason=auth_failure` — so secret leaks surface via anomaly detection

### 2.9 Semgrep coverage rules

**File:** `.semgrep/observability-rules.yml`

**Rules:**

1. **Ban `httpx.AsyncClient()` / `httpx.Client()` outside `backend/observability/instrumentation/external_api.py`** — must use `ObservedHttpClient`
2. **Ban `requests.get/post/...` anywhere outside the yfinance wrapper**
3. **Ban `datetime.utcnow()`** — use `datetime.now(timezone.utc)`
4. **Ban direct INSERT into observability tables** — must go through `ObservabilityClient.emit()`
5. **Require `@tracked_task` on all Celery tasks** in `backend/tasks/` (ban bare `@celery.task`)
6. **Ban `HTTPException` raise outside of router layer** — services raise `DomainError` subclasses
7. **Require `trace_id` parameter propagation in async helpers** calling external APIs (advisory)
8. **Ban free-text `error_reason` values** — must be enum member

**CI integration:** Extends `.semgrep/stock-signal-rules.yml`. Initially advisory (warnings only) for 2 weeks per existing `feedback_ci_guard_checklist` pattern; then promoted to required via `ci-gate`.

## 3. Data Model Summary

| Table | Purpose |
|---|---|
| `request_log` | Per-HTTP-request row |
| `api_error_log` | 4xx + 5xx errors with stack |
| `auth_event_log` | JWT/email-verify/password events |
| `oauth_event_log` | OAuth provider flows |
| `email_send_log` | Resend API calls |
| `slow_query_log` | DB queries >500ms |
| `db_pool_event` | Pool exhaustion/recovery |
| `schema_migration_log` | Alembic migrations |
| `cache_operation_log` | Redis ops (sampled) |
| `rate_limiter_event` | Token bucket events incl. permissive fallback |
| `celery_worker_heartbeat` | Worker liveness |
| `beat_schedule_run` | Beat drift tracking |
| `celery_queue_depth` | Queue backlog |
| `agent_intent_log` | Intent classification history |
| `agent_reasoning_log` | Per-iteration agent reasoning |
| `provider_health_snapshot` | LLM provider health (persisted) |
| `frontend_error_log` | Client-side errors |
| `deploy_events` | Deploys with git SHA |

Plus column additions to `login_attempts` (trace_id, span_id) and `pipeline_runs` (trace_id).

## 4. Out of Scope for 1b (handled in 1c)

- MCP tools → 1c
- CLI `health_report` → 1c
- Anomaly engine + `finding_log` → 1c
- Admin UI zones → 1c
- JIRA draft integration → 1c

## 5. PR Breakdown

| PR | Scope | Est. lines |
|---|---|---|
| **PR1** | HTTP layer: `request_log` + `api_error_log` + env snapshot + 5xx middleware | ~450 |
| **PR2** | Auth layer: `auth_event_log` + `oauth_event_log` + `email_send_log` + login_attempts trace_id | ~400 |
| **PR3** | DB + cache layer: slow_query + pool + migration + cache_operation + rate_limiter_event | ~500 |
| **PR4** | Celery layer: heartbeat + beat drift + queue depth + retry_count wire | ~350 |
| **PR5** | Agent layer: intent_log + reasoning_log + provider_health_snapshot | ~400 |
| **PR6** | Frontend: beacon endpoint + `frontend_error_log` + hooks; deploy_events + GitHub Actions | ~400 |
| **PR7** | Semgrep rules + CI gate + documentation | ~250 |

## 6. Acceptance Criteria (1b-level)

- [ ] Every HTTP request produces a `request_log` row; 4xx/5xx also produce `api_error_log` row
- [ ] 5xx responses include stack traces (not just 500 "Internal Server Error")
- [ ] JWT verification failures recorded with distinct `failure_reason` enum values (expired|malformed|revoked|wrong_type)
- [ ] Every OAuth code exchange produces an `oauth_event_log` row
- [ ] Every email send (`email_send_log`) records outcome + error reason
- [ ] SQLAlchemy queries >500ms appear in `slow_query_log` with source file:line
- [ ] Pool exhaustion events produce `db_pool_event` rows
- [ ] Every Alembic migration run (success or failure) produces `schema_migration_log`
- [ ] Rate-limiter permissive fallback emits `rate_limiter_event` with `reason_if_fallback` enum
- [ ] Celery worker heartbeat visible every ~30s per worker
- [ ] Beat task drift >30s produces `beat_schedule_run` rows flagged
- [ ] Agent query emits `agent_intent_log` + per-iteration `agent_reasoning_log` with termination_reason on final
- [ ] Provider health persisted every 60s across restarts (verified: kill worker → check `provider_health_snapshot` has pre-restart rows)
- [ ] Frontend error from test page appears in `frontend_error_log` within 5s with matching `trace_id`
- [ ] GitHub Actions deploy creates `deploy_events` row
- [ ] Semgrep rules enforced; any violation caught by `ci-pr.yml`

## 7. Risks

| Risk | Mitigation |
|---|---|
| `slow_query_log` high-cardinality floods the table | Duration threshold 500ms; `query_hash` enables dedup views |
| `cache_operation_log` at 100% volume would dominate ingestion | Sample at 1% for non-errors; 100% for errors |
| `environment_snapshot` JSONB bloats request_log | Cap at 1KB; exclude large feature-flag payloads |
| Frontend beacon floods backend during JS error storm | Per-user rate limit 10/min; batch 10/request |
| SQLAlchemy event hooks add latency | Benchmark; threshold filter before emit |
| Agent reasoning log grows too large | Only `content_summary` (500 chars); full LLM output already in `llm_call_log` |
| Celery queue depth polling hits Redis every 60s | Use `LLEN` (O(1)); negligible |
| Semgrep rules too aggressive at rollout | Advisory period (2 weeks) before required |

## 8. Files Touched (estimate)

New:
- `backend/observability/models/{request_log,api_error_log,auth_event_log,oauth_event_log,email_send_log,slow_query_log,db_pool_event,schema_migration_log,cache_operation_log,rate_limiter_event,celery_worker_heartbeat,beat_schedule_run,celery_queue_depth,agent_intent_log,agent_reasoning_log,provider_health_snapshot,frontend_error_log,deploy_events}.py`
- `backend/observability/instrumentation/{http,auth,db,cache,celery,agent}.py`
- `backend/observability/routers/frontend_errors.py`
- `backend/observability/routers/deploy_events.py`
- `backend/migrations/versions/031_obs_coverage_tables.py` (likely split into multiple migrations)
- `.semgrep/observability-rules.yml`
- `frontend/src/lib/observability-beacon.ts`
- `frontend/src/components/error-boundary.tsx` (if not already global)
- `.github/workflows/` additions for deploy_events hook

Modified:
- `backend/middleware/error_handler.py` — 5xx capture
- `backend/middleware/trace_id.py` — also write request_log
- `backend/routers/auth/*.py` — emit auth events
- `backend/services/oauth.py` — emit oauth events
- `backend/services/email.py` — emit email_send events
- `backend/database.py` — SQLAlchemy event hooks
- `backend/services/cache.py` — instrumentation hooks
- `backend/services/rate_limiter.py` — emit events on every action including fallback
- `backend/tasks/pipeline.py` — wire `retry_count`
- `backend/agents/intent_classifier.py`, `backend/agents/react_loop.py` — agent events
- `backend/migrations/env.py` — migration emission
- `frontend/src/lib/api.ts` — set trace_id context from response headers
- `frontend/src/app/providers.tsx` — global TanStack Query error handler

## 9. Testing Strategy

- **Unit:** per-instrumentation tests (HTTP middleware, SQLAlchemy hook, cache wrapper, Celery signals, agent emissions, frontend beacon handler)
- **Integration:** trace_id end-to-end tests — synthetic request → verify rows land in every expected table with correct trace_id
- **Contract:** existing login_attempts tests continue to pass after trace_id column added
- **Chaos:** Redis down → rate_limiter emits `fallback_permissive` events (not silent)
- **Coverage:** Semgrep CI passes; no direct-DB-write regressions

## 10. Rollout

- PR1-PR6 sequential on `develop`; observe obs-table growth + performance for 24h per PR
- PR7 (Semgrep) advisory for 14 days
- Promote Semgrep to required; close out 1b

---

**Next:** [Sub-Spec 1c — Agent Consumption + Admin UI](./2026-04-16-obs-1c-agent-consumption-design.md)
