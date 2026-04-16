# Sub-Spec 1a — Observability Foundations

**Parent:** [Master Architecture Spec](./2026-04-16-obs-master-design.md)
**Date:** 2026-04-16
**Status:** Draft — awaiting PM review
**Estimate:** ~9-10 days across 5 PRs
**Prerequisites:** None (this is the foundation)

---

## 1. Scope

This sub-epic establishes the primitives every other observability work depends on:

1. **`ObservabilityClient` SDK** — single emission abstraction; pluggable target; buffered async flush; disk spool on overflow
2. **Canonical `trace_id` + propagation** — HTTP middleware generates, ContextVar propagates, Celery headers carry across workers, `parent_span_id` for causality
3. **Structured JSON logging** — `structlog` configured at app startup; all loggers emit JSON to stdout with canonical fields
4. **External API instrumentation** — `ObservedHttpClient` wrapping 10 providers; single `external_api_call_log` table consolidates every outbound call
5. **Observability schema + retention** — new `observability.*` Postgres schema; retention policies for all obs tables (including existing ones)
6. **SDK refactor of existing emitters** — route direct-DB-write emissions through the SDK (migrate `ObservabilityCollector`, `_write_login_attempt`, `dq_scan`, `@tracked_task`)

## 2. Deliverables

### 2.1 `ObservabilityClient` SDK

**File:** `backend/observability/client.py`

**Interface:**

```python
class ObservabilityClient:
    def __init__(self, target: ObservabilityTarget, buffer: EventBuffer):
        ...

    async def emit(self, event_type: EventType, payload: ObsEventBase) -> None:
        """Non-blocking. Buffered. Never raises on target failure."""

    def emit_sync(self, event_type: EventType, payload: ObsEventBase) -> None:
        """For sync contexts (middleware, Celery signals). Same semantics."""

    async def flush(self, timeout_s: float = 5.0) -> None:
        """Explicit flush — called at shutdown + before long-running tests."""

    async def health(self) -> ClientHealth:
        """For self-observability — last success, queue depth, spool size, target status."""
```

**Behavior:**
- Events buffered in bounded `asyncio.Queue` (default size: 10,000)
- Flush task runs every `flush_interval_ms` (default 500ms) — batch passes to target
- On target failure: if `OBS_SPOOL_ENABLED=true`, overflow to append-only JSONL spool in `OBS_SPOOL_DIR`; else drop with structured metric log
- Reclaim task runs every 30s: replays spooled events when target recovers
- Hard Rule: emit never raises; failures logged but silent to caller

**Kill switch (incident response):** `OBS_ENABLED=true|false` env var (default `true`). When `false`: `emit()` / `emit_sync()` are no-ops; middleware, decorators, and wrappers short-circuit. Documented playbook: if observability is itself misbehaving (DB overload, flush loop pathology), set `OBS_ENABLED=false` and restart app; re-enable after fix.

**Spool configuration:** `OBS_SPOOL_ENABLED=true|false` (default `true` in prod, `false` in dev/tests), `OBS_SPOOL_DIR` (default `/var/tmp/obs-spool/`), `OBS_SPOOL_MAX_SIZE_MB=100` per worker. If disabled, events drop on queue overflow; emit a `obs_event_dropped` metric + structured log with count.

**Initialization:** Single global instance created in `backend/main.py` lifespan and exposed via `app.state.obs_client`. Celery workers get their own instance at worker_ready signal.

**Tests required:**
- Unit: emit success path, queue overflow → spool, spool replay, concurrent emissions (asyncio.gather)
- Integration: full round-trip emit → target → DB row
- Chaos: target down → spool grows → target up → spool drains

### 2.2 Pluggable `ObservabilityTarget`

**File:** `backend/observability/targets/`

**Abstract:**

```python
class ObservabilityTarget(Protocol):
    async def send_batch(self, events: list[ObsEventEnvelope]) -> BatchResult:
        ...

    async def health(self) -> TargetHealth:
        ...
```

**Implementations (in this sub-epic):**
- **`DirectTarget`** — writes directly to Postgres via SQLAlchemy async session. **Default for monolith.** Bypasses HTTP serialization overhead (critical: at 10k+ events/sec, self-HTTP-POST per event is prohibitive). Couples only the target implementation to the DB schema; the SDK interface stays stable.
- `InternalHTTPTarget` — POST to `/obs/v1/events` on the same app. Used for integration tests to exercise the HTTP ingestion path. Also the default when transitioning to microservice (target URL becomes external).
- `MemoryTarget` — in-process queue; for unit tests.

**Future (not in scope):** `ExternalHTTPTarget` (microservice extraction), `KafkaTarget` (high-scale).

**Config:**
- `OBS_TARGET_TYPE=direct|internal_http|memory` (default `direct` in prod, `memory` in tests)
- `OBS_TARGET_URL` (used by `internal_http` + future external — not set for `direct`)

**Why `DirectTarget` default:** Self-HTTP-POST in-monolith adds serialization + localhost networking overhead per event. At steady-state ~1000 req/s with ~10 events/request = 10k events/sec POSTs to self. `DirectTarget` cuts latency to µs-range DB batch inserts. The extraction seam is the `ObservabilityTarget` Protocol — swapping to `ExternalHTTPTarget` at extraction time is a single config change; the SDK interface and application code stay identical.

**Integration test coverage:** Both `DirectTarget` and `InternalHTTPTarget` exercised in integration tests — ensures the HTTP ingestion path works and doesn't bit-rot before extraction.

**Ingest endpoint:** `InternalHTTPTarget` (and future `ExternalHTTPTarget`) POST to `/obs/v1/events`. Endpoint implementation IS part of this sub-epic (see §2.2b below).

### 2.2b Ingestion Endpoint (was missing from original PR plan — added)

**File:** `backend/observability/routers/ingest.py`

**Endpoint:** `POST /obs/v1/events`
- Body: `IngestBatch { events: list[ObsEventEnvelope], schema_version: str }`
- Max batch size: 500 events, 1MB JSON
- Rate-limited at ingest (prevent DoS): 1000 batches/min per source IP
- Returns: `202 Accepted` on write-queued; `422` on schema mismatch; `503` on target DB down
- Auth: service-internal only — uses `X-Obs-Secret` header validated against `OBS_INGEST_SECRET` env var (prevents external abuse). For `DirectTarget` users this endpoint is unused.

**Implementation:**
- Validates events against Pydantic schema v1
- Passes to `EventWriter` service (routing by event_type to appropriate repository)
- Writes via async transaction; failures bubble up as 503 (client retries from spool)

### 2.3 Trace ID + propagation

**Files:**
- `backend/middleware/trace_id.py` — new FastAPI middleware (top of stack)
- `backend/observability/context.py` — extend existing ContextVars with `trace_id`, `span_id`, `parent_span_id`
- `backend/tasks/celery_trace_propagation.py` — Celery signals for header carry

**HTTP middleware:**
- Check for `X-Trace-Id` header on incoming request
- If present and valid UUIDv7: adopt it (supports external callers continuing a trace)
- Else: generate new UUIDv7
- Set ContextVars for request lifetime
- Inject `X-Trace-Id` into response headers
- **CORS:** Add `X-Trace-Id` to `Access-Control-Expose-Headers` in the existing CORS middleware config so the frontend can actually read it (browsers block reading response headers not explicitly exposed). Required for frontend error reporting to carry trace_id.

**Dependencies:** UUIDv7 is not in Python stdlib. Add `uuid-utils` (actively maintained, Rust-backed, ~100ns generation) to `pyproject.toml`.

**Celery propagation:**
- `before_task_publish` signal: read `trace_id` + `span_id` from ContextVar, inject into task headers
- `task_prerun` signal: read from headers, set ContextVars; generate new `span_id` with parent = incoming `span_id`
- `task_postrun` signal: clear ContextVars

**Span lifecycle helper:**

```python
@asynccontextmanager
async def span(name: str, **attrs) -> AsyncIterator[Span]:
    """Creates child span. parent_span_id = current span."""
    ...
```

Used by instrumentation wrappers (DB, cache, external API) to create child spans automatically.

**Tests required:**
- Middleware generates UUIDv7 when no header; adopts existing
- Celery task receives trace_id + new span_id with correct parent
- Nested async calls inherit correct parent
- Failure paths: missing ContextVar doesn't crash

### 2.4 Structured JSON logging

**File:** `backend/core/logging.py` (new)

**Setup:** `structlog` configured at app startup (and Celery worker startup).

**Canonical fields on every log line:**
- `timestamp` (ISO-8601 UTC)
- `level` (DEBUG|INFO|WARNING|ERROR|CRITICAL)
- `logger` (module name)
- `message` (human-readable)
- `trace_id` (from ContextVar, nullable)
- `span_id` (from ContextVar, nullable)
- `user_id` (from ContextVar, nullable)
- `env`, `git_sha` (from config)
- Any `extra={}` fields passed to logger

**Output format:** NDJSON to stdout; Docker/k8s collects natively.

**Replaces:** ad-hoc `logger.info(..., extra={...})` scattered through codebase. No forced migration — existing calls continue to work; new emissions go through structlog.

**Disabled in pytest:** Structured logging verbose; tests disable via fixture to keep output readable.

### 2.5 External API instrumentation — the biggest piece

**Problem:** yfinance, Finnhub, EDGAR, FRED, Google News, OpenAI, Anthropic, Groq, Resend, Google OAuth are all called via `httpx` (or SDKs using httpx). Errors are free-text today. We need structured emission for every outbound call.

**File:** `backend/observability/instrumentation/external_api.py`

**`ObservedHttpClient` wrapper:**

```python
class ObservedHttpClient:
    """httpx.AsyncClient drop-in that emits external_api_call_log for every call."""

    def __init__(self, provider: ExternalProvider, **httpx_kwargs):
        self._provider = provider
        self._client = httpx.AsyncClient(**httpx_kwargs)

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        with obs_span(name=f"external_api.{self._provider}", provider=self._provider, url=url):
            start = time.monotonic()
            try:
                resp = await self._client.request(method, url, **kwargs)
                latency_ms = int((time.monotonic() - start) * 1000)
                await self._emit_call_log(
                    provider=self._provider,
                    endpoint=self._normalize_endpoint(url),
                    method=method,
                    status_code=resp.status_code,
                    error_reason=self._classify(resp),
                    latency_ms=latency_ms,
                    request_bytes=len(kwargs.get("content", b"") or b""),
                    response_bytes=len(resp.content),
                    rate_limit_headers=self._parse_rate_limit_headers(resp),
                    cost_usd=None,  # populated by LLM providers externally
                )
                return resp
            except httpx.HTTPError as e:
                # log + re-raise
                ...
```

**Integration points:**
- `backend/services/stock_data.py` — yfinance calls (yfinance uses `requests`; wrap at session level)
- `backend/services/news/finnhub_provider.py`
- `backend/services/news/edgar_provider.py`
- `backend/services/news/fed_provider.py`
- `backend/services/news/google_provider.py`
- `backend/agents/providers/openai.py`
- `backend/agents/providers/anthropic.py`
- `backend/agents/providers/groq.py`
- `backend/services/email.py` (Resend)
- `backend/services/google_oauth.py`

**Migration pattern per provider:** Replace `httpx.AsyncClient()` instantiation with `ObservedHttpClient(provider=ExternalProvider.FINNHUB)`. No other code changes.

**Yfinance quirk:** uses `requests` (sync). Wrap at the `yfinance.Ticker` / `yfinance.download` boundary via a custom session passed to yfinance. Emits via sync `emit_sync`.

### 2.6 New tables: `external_api_call_log` + `rate_limiter_event`

**External API call log schema:**

```sql
CREATE TABLE observability.external_api_call_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID NOT NULL,
    span_id UUID NOT NULL,
    parent_span_id UUID,
    user_id UUID,

    provider TEXT NOT NULL,  -- enum: yfinance|finnhub|edgar|fred|google_news|openai|anthropic|groq|resend|google_oauth
    endpoint TEXT NOT NULL,  -- normalized (path without query params)
    method TEXT NOT NULL,    -- enum: GET|POST|PUT|DELETE
    status_code INT,
    error_reason TEXT,       -- enum: rate_limit_429|server_error_5xx|client_error_4xx|timeout|connection_refused|malformed_response|auth_failure|circuit_open

    latency_ms INT NOT NULL,
    request_bytes INT,
    response_bytes INT,
    retry_count INT DEFAULT 0,
    cost_usd NUMERIC(12, 6),

    rate_limit_remaining INT,
    rate_limit_reset_ts TIMESTAMPTZ,
    rate_limit_headers JSONB,

    stack_signature TEXT,
    stack_hash CHAR(64),

    env TEXT NOT NULL,
    git_sha TEXT
);

SELECT create_hypertable('observability.external_api_call_log', 'ts', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ON observability.external_api_call_log (trace_id);
CREATE INDEX ON observability.external_api_call_log (provider, ts DESC);
CREATE INDEX ON observability.external_api_call_log (error_reason, ts DESC) WHERE error_reason IS NOT NULL;
```

**Retention:** 30 days (`drop_chunks()` compatible).
**Compression:** after 7 days (segmentby=provider).

**Rate limiter event schema (grouped here because it's tightly coupled to external API flow):**

```sql
CREATE TABLE observability.rate_limiter_event (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    trace_id UUID,
    span_id UUID,

    limiter_name TEXT NOT NULL,       -- enum: yfinance|finnhub|edgar|fred|google_news|openai|anthropic|groq|api_ingest_ticker|api_bulk_upload
    action TEXT NOT NULL,             -- enum: acquired|timeout|fallback_permissive|rejected
    wait_time_ms INT,
    tokens_remaining INT,
    reason_if_fallback TEXT,          -- enum: redis_down|noscript_recovery_failed|lua_error|unknown

    env TEXT NOT NULL,
    git_sha TEXT
);

CREATE INDEX ON observability.rate_limiter_event (limiter_name, action, ts DESC);
```

**Retention:** 30 days.

**Implementation:** `backend/services/rate_limiter.py` — at every `acquire()` call site + fallback path, emit `rate_limiter_event`. **Critical fix:** closes silent-data-risk gap #5 from audit (rate-limiter permissive-fallback was unobservable).

### 2.7 Existing emitter refactor (strangler-fig pattern for safe rollback)

Route existing direct-DB-write emissions through the SDK, keeping the legacy code path behind a feature flag for 2 weeks so rollback is a config change, not a revert.

| Current | Refactored |
|---|---|
| `ObservabilityCollector.record_request()` → direct `LLMCallLog` insert | → `obs_client.emit(EventType.LLM_CALL, payload)` |
| `ObservabilityCollector.record_tool_execution()` → direct `ToolExecutionLog` insert | → `obs_client.emit(EventType.TOOL_EXECUTION, payload)` |
| `_write_login_attempt` → direct `LoginAttempt` insert | → `obs_client.emit(EventType.LOGIN_ATTEMPT, payload)` |
| `dq_scan_task` → direct `DqCheckHistory` insert | → `obs_client.emit(EventType.DQ_FINDING, payload)` |
| `@tracked_task` → direct `PipelineRun` insert/update | Keep direct UPDATEs for state rows (too awkward for fire-and-forget SDK); add companion `PIPELINE_LIFECYCLE` events for every state transition. |

**Rollback safety (strangler-fig):**
- `OBS_LEGACY_DIRECT_WRITES=true|false` env var (default `true` at PR5 merge). When `true`, legacy direct-write code path continues to execute *in addition to* the SDK emission. Dual-write phase.
- PR5 merges with legacy + SDK both active — verified equivalent DB rows via contract tests.
- After 2 weeks of green production (per `feedback_ci_guard_checklist` promotion pattern), flip `OBS_LEGACY_DIRECT_WRITES=false`; emissions go only through SDK.
- After 1 more week green, separate cleanup PR deletes the legacy code path entirely.
- If anything breaks during the dual-write phase, flip the flag — emissions continue through legacy path while SDK path is fixed.

**Backwards compat:** Event schemas mirror existing table columns; no downstream consumer change needed.

**Tests:** Before/after contract tests — emissions produce equivalent DB rows via each path; dual-write validated.

### 2.8 Retention policies

**New:**

| Table | Policy | Mechanism |
|---|---|---|
| `observability.external_api_call_log` | 30 days | `drop_chunks()` daily at 03:50 ET |
| (all future 1b tables — defined in 1b spec) | per-table | same pattern |

**Updated (existing tables):**

| Table | Current | Proposed |
|---|---|---|
| `llm_call_log` | None (unbounded) | 30 days `drop_chunks()` |
| `tool_execution_log` | None (unbounded) | 30 days `drop_chunks()` |
| `pipeline_runs` | None (unbounded) | 90 days DELETE WHERE started_at < now() - 90d |
| `dq_check_history` | None (unbounded) | 90 days DELETE |
| `in_app_alerts` | Read alerts only >90d | Keep as-is |
| `ticker_ingestion_state` | N/A (state) | N/A |
| `login_attempts` | None | 90 days |

**Implementation:** Extend `backend/tasks/retention.py` with new purge tasks; beat entries added.

### 2.9 `describe_observability_schema()` MCP tool

**Purpose:** Agents (me) call this at session start to know the current schema. Returns:

- Table list with row counts + retention policy
- Enum registry (ErrorReason values per layer, etc.)
- Event type list with Pydantic schema
- Tool manifest (will populate in 1c)
- Schema version

**File:** `backend/observability/mcp/describe_schema.py`

**Note:** Skeleton in 1a; full MCP tool suite in 1c.

## 3. Data Model Summary

| Table | New in 1a? | Notes |
|---|---|---|
| `observability.external_api_call_log` | ✅ new | Consolidates 10 providers |
| `observability.rate_limiter_event` | ✅ new | Rate-limiter actions incl. permissive fallback (closes silent-data-risk gap) |
| `observability.schema_versions` | ✅ new | Tracks current schema version for `describe_observability_schema()` |

**No other new tables in 1a.** 1b introduces request_log, api_error_log, slow_query_log, etc.

## 4. Out of Scope for 1a (handled in 1b/1c)

- HTTP per-request row (`request_log`) → 1b
- API error log (`api_error_log`) → 1b
- DB slow-query log, pool events, migration log → 1b
- Cache + rate-limiter events → 1b
- Celery heartbeat, beat drift, queue depth → 1b
- Agent intent log, termination reasons, reasoning log → 1b
- Frontend beacon → 1b
- Deploy events → 1b
- Semgrep coverage rules → 1b
- Admin UI zones → 1c
- Anomaly engine → 1c
- Most MCP tools → 1c

## 5. PR Breakdown

Each PR ≤500 lines per Hard Rule #12.

| PR | Scope | Est. lines |
|---|---|---|
| **PR1** | `observability.*` Postgres schema migration; `schema_versions` table; `ObsEventBase` Pydantic models + `EventType` enum; `uuid-utils` dep added | ~250 |
| **PR2** | `ObservabilityClient` SDK + `DirectTarget` (default) + `InternalHTTPTarget` + `MemoryTarget` + buffered flush + optional disk spool + `/obs/v1/events` ingest endpoint + `OBS_ENABLED` / `OBS_SPOOL_ENABLED` kill switches; unit + integration tests | ~500 |
| **PR3** | trace_id middleware (incl. CORS expose-headers fix) + Celery propagation + ContextVar extension + `span()` helper; structured JSON logging (structlog) | ~400 |
| **PR4** | `ObservedHttpClient` + `external_api_call_log` + `rate_limiter_event` tables + integrate 10 providers; rate-limiter emission on permissive fallback; retention policies for new + existing tables | ~500 |
| **PR5** | SDK refactor of existing emitters (LLM/tool/login/DQ) with `OBS_LEGACY_DIRECT_WRITES` feature flag for strangler-fig rollback; contract tests | ~450 |

Each PR green in CI before merge; cumulative review.

## 6. Acceptance Criteria (1a-level)

- [ ] `ObservabilityClient.emit()` benchmarked at <2ms p95 in unit tests (via `DirectTarget`)
- [ ] `InternalHTTPTarget` integration test: events POSTed and persisted correctly
- [ ] Optional disk spool → replay tested: target down 60s, spool grows; target up; spool drains to 0 within 2 min
- [ ] `OBS_ENABLED=false` kill switch verified: no DB writes, no middleware overhead, app functions normally
- [ ] `OBS_SPOOL_ENABLED=false` verified: overflow drops events with structured metric log
- [ ] Every HTTP request has a `trace_id` in response headers; frontend can read it (CORS expose-headers configured); same `trace_id` appears on any LLM/tool calls triggered by that request
- [ ] Celery task picked up from beat carries `trace_id` from the scheduled-by context (or generates new root if scheduled)
- [ ] `external_api_call_log` receives rows for every call through all 10 providers (verified via integration test that hits each provider once)
- [ ] Rate-limiter permissive fallback emits `rate_limiter_event` row with `reason_if_fallback` enum
- [ ] `describe_observability_schema()` MCP tool returns current schema
- [ ] Retention policies active; verified by inspecting hypertable chunk expiration
- [ ] Existing LLM/tool/login/DQ emissions route through SDK (with `OBS_LEGACY_DIRECT_WRITES=true` dual-write mode); contract tests confirm equivalent DB state on both paths
- [ ] Zero new Semgrep violations

## 7. Risks

| Risk | Mitigation |
|---|---|
| yfinance `requests`-based — hard to wrap | Use `requests.Session` + session mount with custom transport; verify via integration test |
| `@tracked_task` uses UPDATE semantics — awkward to route through fire-and-forget SDK | Keep direct UPDATEs for state rows; emit companion events for lifecycle transitions |
| Disk spool grows unbounded if target never recovers | Cap spool size at 100MB/worker; drop oldest on overflow (logged with count) |
| `trace_id` not always available (e.g., beat-triggered tasks) | Allow `trace_id = None` root span; beat generates new root trace |
| Structured JSON logging breaks existing log-parsing tools | No external log parsers currently; migration is additive |

## 8. Files Touched (estimate)

New:
- `backend/observability/client.py`, `backend/observability/targets/{internal_http,memory}.py`
- `backend/observability/instrumentation/{external_api,celery}.py`
- `backend/observability/schema/v1.py`, `backend/observability/models/external_api_call.py`, `backend/observability/models/schema_versions.py`
- `backend/observability/routers/ingest.py`
- `backend/observability/mcp/describe_schema.py`
- `backend/middleware/trace_id.py`
- `backend/core/logging.py`
- `backend/migrations/versions/030_observability_schema.py`

Modified:
- `backend/main.py` (lifespan — init SDK, structured logging)
- `backend/services/stock_data.py`, all `backend/services/news/*_provider.py`, `backend/agents/providers/*.py`, `backend/services/email.py`, `backend/services/google_oauth.py` (use `ObservedHttpClient`)
- `backend/observability/collector.py` (route through SDK instead of direct write)
- `backend/routers/auth/_helpers.py` (login attempts through SDK)
- `backend/tasks/dq_scan.py` (findings through SDK)
- `backend/tasks/retention.py` (new purge tasks + beat entries)
- `backend/observability/context.py` (add trace_id, span_id, parent_span_id)

## 9. Testing Strategy

- **Unit:** `tests/unit/observability/test_client.py`, `test_targets.py`, `test_trace_id.py`, `test_external_api_wrapper.py`, `test_retention.py`
- **Integration:** `tests/api/observability/test_ingest_endpoint.py` — full emit round trip
- **Contract:** before/after tests for existing emitters (LLM/tool/login/DQ) — DB state equivalent
- **Chaos:** target-down simulation (via `MemoryTarget` with configurable failure mode) — spool + replay works
- **Performance:** benchmark SDK overhead <2ms p95

## 10. Rollout

- Merge PR1-PR4 in sequence on `develop` branch
- Observe ingestion for 48h (new external_api_call_log populated; no app-side errors)
- Merge PR5 (emitter refactor) — contract tests guard
- Promote to `main` when green for 1 week on `develop`

---

**Next:** [Sub-Spec 1b — Coverage Completion](./2026-04-16-obs-1b-coverage-design.md)
