# Platform Observability Infrastructure — Master Architecture Spec

**Date:** 2026-04-16
**Status:** Draft — awaiting PM review
**Epic:** KAN-TBD (to be filed)
**Owner:** Agent-authored, PM-reviewed
**Sub-specs:**
- [1a — Foundations](./2026-04-16-obs-1a-foundations-design.md)
- [1b — Coverage Completion](./2026-04-16-obs-1b-coverage-design.md)
- [1c — Agent Consumption + Admin UI](./2026-04-16-obs-1c-agent-consumption-design.md)

---

## 1. Problem Statement

The platform currently has **partial observability**: ~7 structured emission points exist (`pipeline_runs`, `llm_call_log`, `tool_execution_log`, `login_attempts`, `dq_check_history`, `ticker_ingestion_state`, HTTP metrics in Redis), but critical layers are dark — external API calls (yfinance/Finnhub/EDGAR/FRED/Google News/OpenAI/Anthropic/Groq/Resend/Google OAuth) log exceptions as free text; HTTP requests are aggregated-only with no per-request row; the rate-limiter falls back to permissive on Redis outage *without emitting* an event; DB slow queries are invisible; frontend errors never reach the backend; retention is unbounded on most obs tables.

This Epic builds the observability substrate that:

1. **Captures every layer with structured, queryable events** — HTTP, auth, DB, cache, external APIs, LLM, agents, Celery, frontend. Nothing logs to stderr that an operator needs to read later.
2. **Correlates events end-to-end via a single canonical `trace_id`** — one user action produces one trace spanning every downstream call across every layer.
3. **Serves two first-class consumers from day one:** a human operator via a rich admin dashboard, AND an LLM agent (Claude Code today, autonomous maintenance agents later) via MCP tools + structured JSON responses.
4. **Is architected for eventual microservice extraction** — a single `ObservabilityClient` SDK is the only coupling point; Postgres schema + Redis namespace isolated; internal module with zero upward dependencies on application services.

## 2. Core Principles

### 2.1 Coverage contract (non-negotiable)

Every HTTP request, every DB query, every Redis call, every Celery task, every external API call, every LLM call, every tool execution, every agent reasoning step — ALL emit structured events.

**Enforcement:** Semgrep rules (see Sub-spec 1b) fail CI if a new call site lands uninstrumented. Instrumentation is automatic where possible (middleware, decorators, shared wrappers) to keep ceremony low.

### 2.2 Agent-consumable by design

Every schema, enum, and API is designed so an LLM agent can parse it without fuzzy matching. Structured fields over free-text strings. Enum everything that's enumerable. Stack signatures on errors. Remediation hints on findings. Self-describing schema via `describe_observability_schema()` tool.

### 2.3 Single emission abstraction (the SDK)

No application code writes directly to observability tables. Every emission goes through `ObservabilityClient.emit(event_type, payload)`. The client has a pluggable target — today an internal HTTP endpoint, tomorrow an external service or Kafka topic. Application code never changes when we extract the service.

### 2.4 Extractable from day one

The observability module lives in `backend/observability/` with zero upward dependencies on `backend.services`, `backend.routers`, or `backend.agents`. Database tables live in a separate `observability.*` Postgres schema. Redis keys use `obs:*` prefix. Extraction is a config change, not a rewrite.

### 2.5 Non-blocking, durable emissions

Event emissions are async + buffered + never block application code. If the ingestion target is down, events can overflow to an append-only disk spool per worker and replay on recovery. Spool is configurable (`OBS_SPOOL_ENABLED`) — default ON in prod, OFF in dev/tests.

### 2.6 Kill switch (incident-response primitive)

`OBS_ENABLED=true|false` env var (default `true`). When `false`: all emission calls become no-ops — middleware short-circuits, decorators skip, wrappers pass through. **Non-negotiable:** if the observability layer itself ever misbehaves (DB flooded, flush loop pathology, target unreachable + spool full), operators can turn it off in one config change without touching application code. Application behavior is unchanged whether `OBS_ENABLED` is true or false.

### 2.7 Target architecture (monolith-optimal, extraction-ready)

The `ObservabilityTarget` Protocol is the extraction seam. Current implementations:

- **`DirectTarget`** — writes directly to Postgres via SQLAlchemy session. **Default for monolith** because self-HTTP-POST per event at 10k events/sec is prohibitive.
- **`InternalHTTPTarget`** — POST to `/obs/v1/events` on the same app. Used in integration tests + for validating the HTTP ingestion path won't bit-rot before extraction.
- `MemoryTarget` — in-process (tests).
- *Future:* `ExternalHTTPTarget`, `KafkaTarget`.

When we extract observability to a microservice, the only change is swapping `DirectTarget` → `ExternalHTTPTarget(base_url=obs.svc.internal)`. SDK interface is stable; application code never changes.

## 3. Architecture

### 3.1 Data flow

```
Application code
    │
    │ emits via
    ▼
ObservabilityClient SDK (in-process)
    │ (async buffer, optional disk spool on overflow)
    ▼
Pluggable Target (the extraction seam):
    ├─ DirectTarget (monolith default — direct DB write via SQLAlchemy)
    ├─ InternalHTTPTarget (POST to our own /obs/v1/events; used in integration tests)
    ├─ ExternalHTTPTarget (future: POST to separate service)
    ├─ KafkaTarget (future: high-scale)
    └─ MemoryTarget (tests)
    │
    ├──── DirectTarget ────────────┐
    │                              │
    ▼                              ▼
Ingestion API                EventWriter (validates + routes by event_type)
(backend/observability/             │
 routers/ingest.py) ──────────────► │
    │                              │
    ▼                              ▼
EventWriter                  Repositories (raw SQL isolated here)
    │                              │
    └──────────────┬───────────────┘
                   ▼
Postgres: observability.* schema (time-partitioned hypertables)
Redis:    obs:* namespace (hot metrics, percentiles, counters)
```

### 3.2 Module boundaries

```
backend/
├── observability/                 ← self-contained module
│   ├── client.py                  ← SDK (imported by everyone)
│   ├── targets/                   ← Internal / External / Kafka / Memory
│   ├── instrumentation/           ← middleware + decorators + wrappers
│   │   ├── http.py
│   │   ├── db.py                  (SQLAlchemy event hooks)
│   │   ├── cache.py               (Redis wrapper)
│   │   ├── external_api.py        (HTTPX wrapper for 10 providers)
│   │   ├── celery.py              (Celery signals)
│   │   └── agent.py               (agent/LLM hooks)
│   ├── schema/
│   │   └── v1.py                  ← Pydantic event models (versioned contract)
│   ├── models/                    ← SQLAlchemy models (observability.*)
│   ├── repositories/              ← SQL repositories
│   ├── service/                   ← event writer, query service, anomaly engine
│   ├── routers/                   ← ingest + query HTTP endpoints
│   ├── anomaly/                   ← beat-scheduled anomaly detection
│   └── mcp/                       ← MCP tool definitions
│
└── (all other modules)            ← import only backend.observability.client
```

**Dependency rule:** `backend.observability` depends on `backend.core` (DB pool, config) only. It does not import from `backend.services`, `backend.routers`, or `backend.agents`. One-way flow.

### 3.3 Database schema isolation

All observability tables live in `observability.*` Postgres schema. Migration scope clean: `pg_dump --schema=observability` produces a standalone dump.

Existing observability-adjacent tables currently in `public.*` (`pipeline_runs`, `llm_call_log`, `tool_execution_log`, `dq_check_history`, `in_app_alerts`, `login_attempts`, `ticker_ingestion_state`) stay in `public.*` for this Epic. A future cleanup PR can migrate them once extraction is actually planned.

### 3.4 Redis namespace

All observability Redis keys prefixed `obs:*` — `obs:metrics:http:*`, `obs:workers:heartbeat:*`, `obs:anomaly:findings:*`. Extractable to a separate Redis instance by config flip.

### 3.5 The canonical `trace_id`

- Generated at HTTP entry point (UUIDv7 — time-orderable) by new middleware
- Propagated via `ContextVar` through the async call stack
- Injected into `X-Trace-Id` response header (frontend includes it in error reports)
- Copied into Celery task headers when tasks are dispatched
- Read from task headers into ContextVar at task start
- Stored on every single event row in every obs table

One user action produces one `trace_id` that appears on every event generated downstream. Trace tree view (UI + MCP) reconstructs the full journey.

### 3.6 Parent span linking (causality)

Every event row has `parent_span_id` (nullable UUID). Spans form a tree, not a flat list. Example: a tool execution span has the HTTP request span as parent; a DB query span has the tool execution span as parent. Enables answering "what caused this slow query" rather than just "these things co-occurred."

## 4. Shared Data Contracts

### 4.1 Pydantic event models (schema v1)

All events pass through a versioned Pydantic model. Additive evolution only — new fields added, never renamed or removed without a v2 bump.

Baseline fields present on every event:

```python
class ObsEventBase(BaseModel):
    event_type: Literal[...]           # enum of all known types
    trace_id: UUID                     # canonical trace
    span_id: UUID                      # unique per emission
    parent_span_id: UUID | None        # causality link
    ts: datetime                       # tz-aware UTC, UUIDv7 derives from here
    env: Literal["dev", "staging", "prod"]
    git_sha: str | None                # runtime git SHA
    user_id: UUID | None               # request user
    session_id: UUID | None            # chat session
    query_id: UUID | None              # agent query
```

### 4.2 Enum standards

All error reasons, statuses, severities, attribution layers are enums. Adding an enum value requires a migration + Pydantic schema bump. Free-text `reason` fields are banned in new code (Semgrep rule enforces).

Key enums (full detail in sub-specs):

- `AttributionLayer`: `http` | `auth` | `db` | `cache` | `external_api` | `llm` | `agent` | `celery` | `frontend` | `anomaly_engine`
- `ErrorReason` (per layer): `rate_limit_429`, `server_error_5xx`, `client_error_4xx`, `timeout`, `connection_refused`, `malformed_response`, `auth_failure`, `circuit_open`, ... (per external API layer)
- `Severity`: `info` | `warning` | `error` | `critical`
- `FindingStatus`: `open` | `acknowledged` | `resolved` | `suppressed`
- `TerminationReason` (ReAct agent): `normal` | `max_iterations` | `wall_clock_timeout` | `zero_tool_calls` | `exception`

### 4.3 Timestamp standards

All timestamps: `DateTime(timezone=True)`, stored in UTC, initialized with `datetime.now(timezone.utc)`. Never `datetime.utcnow`. Enforced by Semgrep + CI.

### 4.4 Stack signatures

Every error row carries:
- `stack_signature`: top 5 frames as `"file.py:line"` joined by `→`
- `stack_hash`: SHA256 of full stack (for deduplication)
- `stack_trace`: full traceback text (nullable; populated for high-severity only, to bound storage)

Agents use `stack_signature` to jump to code; `stack_hash` to deduplicate recurring errors.

### 4.5 Environment snapshot

On `request_log` row (per HTTP request), an `environment_snapshot` JSONB column captures: active LLM model config version, feature flags active for this user, rate-limiter states at request start, git SHA. Bounded payload (~1KB max). Enables reproduction: an agent can re-create conditions at time of failure.

## 5. Sub-Epic Breakdown

| Sub-epic | Scope | Estimate | Ships first? |
|---|---|---|---|
| **1a — Foundations** | ObservabilityClient SDK with `DirectTarget` default + ingest endpoint + `OBS_ENABLED` / `OBS_SPOOL_ENABLED` kill switches, trace_id middleware + propagation + CORS header exposure, structured JSON logging, external API HTTPX wrapper + `external_api_call_log` + `rate_limiter_event`, retention policies, `observability.*` schema setup, strangler-fig refactor of existing emitters | ~9-10 days | ✅ Yes |
| **1b — Coverage Completion** | HTTP request_log + api_error_log + 5xx capture, auth/OAuth/email event logs, DB slow-query + pool + migration logs, cache event log, Celery worker heartbeat + beat drift + queue depth + retry_count wire, agent intent_log + termination_reason + provider_health_snapshot + agent_reasoning_log, frontend beacon + `frontend_error_log` (via `sendBeacon`), `deploy_events` hook with HMAC auth, PII redaction at ingestion, Semgrep coverage rules | ~8-10 days | After 1a |
| **1c — Agent Consumption + Admin UI** | 13 MCP tools (including 9 agent-perspective gap closures), CLI `health_report`, anomaly engine (parallel execution + per-rule timeout) + `finding_log`, admin REST query endpoints + 8-zone UI, JIRA-draft integration | ~6-8 days | After 1b |

**Why this order:** 1a establishes the primitives every other sub-epic uses (SDK, trace_id, external API log). Without 1a, 1b and 1c have nothing to build on. 1b completes the coverage so 1c has data to consume. 1c productizes the substrate for humans and agents.

**Mergeable independently:** Each sub-epic is independently reviewable and deployable. After 1a ships, the platform has trace-correlated external API logging. After 1b, full coverage. After 1c, the dashboard + MCP tools make it all actionable.

## 6. What's Auto-Generated vs What Needs Code

### Auto-generated today (reusable with minor refactor through the SDK)

| Current emission | Mechanism | Sub-epic |
|---|---|---|
| Pipeline task lifecycle | `@tracked_task` decorator | 1a refactor (route through SDK) |
| LLM calls | `ObservabilityCollector.record_request()` | 1a refactor |
| Tool executions | `ObservabilityCollector.record_tool_execution()` | 1a refactor |
| Login attempts | `_write_login_attempt()` | 1a refactor |
| DQ findings | `dq_scan_task` insert to `dq_check_history` | 1a refactor |
| HTTP metrics (aggregated) | `HttpMetricsCollector` Redis | Keep as-is |
| ticker_ingestion_state | `mark_stage_updated()` | Keep as-is (state, not event) |

### Needs new code

See sub-spec tables. ~14 new components across the 3 sub-epics.

## 7. Microservice Extraction Checklist (future)

When we decide to extract observability as a standalone service, the 9-step checklist:

1. Split repo — `backend/observability/` becomes new package/repo (`ssp-observability`)
2. Deploy new FastAPI service (same code, separately running)
3. App-side: swap `InternalHTTPTarget` → `ExternalHTTPTarget(base_url=obs.stocksignal.internal)` (one config line)
4. Dashboard: update base URL for query APIs
5. MCP tools: same URL swap
6. Database: `pg_dump --schema=observability` → restore to new DB; update connection string
7. Redis: move `obs:*` keys to new Redis or leave shared
8. Anomaly engine: moves to new service as scheduled worker
9. Deploy events hook: GitHub Actions points at new service URL

Days of work, not months. This Epic is the investment.

## 8. Out of Scope (YAGNI)

Explicit *not building now*:

- **OpenTelemetry exporters** — defer until microservice split or external integration needed
- **Prometheus `/metrics` endpoint** — our dashboard suffices; Prometheus adds ops burden
- **Sentry / external error tracking** — `frontend_error_log` + `api_error_log` cover it in-app
- **Log aggregators (Loki/Elastic)** — unneeded at current scale (<1GB/day)
- **Distributed tracing across microservices** — N/A (monolith)
- **Time-series databases beyond TimescaleDB** — hypertables are enough
- **Alerting via email/Slack/PagerDuty** — in-app alerts + JIRA draft workflow sufficient for now
- **User analytics (Mixpanel-style)** — separate concern; obs is operational not product-analytics
- **Automated agent fix-and-ship loop** — agents propose, humans approve; autonomous execution is future Epic

## 9. Risks + Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SDK abstraction adds latency | Low | Medium | Async buffered emissions; benchmark <5ms p95 overhead in 1a tests |
| Ingestion endpoint becomes bottleneck | Medium | High | Disk spool fallback + async batch flush; ingestion is separate router, can horizontally scale |
| Schema evolution breaks consumers | Low | High | Versioned Pydantic models (v1, v2); additive-only field changes |
| Retention deletes chunks we'd need for debugging | Medium | Medium | Policies are per-table + configurable; start conservative (30-90d) and tune |
| Semgrep coverage rules too aggressive | Medium | Low | Start advisory (warnings), promote to required after 2 weeks (per `feedback_ci_guard_checklist`) |
| Anomaly engine false positives swamp findings | High | Medium | Start rule-based (tunable); statistical outlier detection behind a flag |
| TimescaleDB hypertable migrations tricky | Medium | Medium | Existing compression patterns proven (migration 028); follow same conventions |
| MCP tool inventory grows uncontrollably | Medium | Low | Keep to 13 tools; `describe_observability_schema()` exposes schema instead of proliferating tools |

## 10. Acceptance Criteria (Epic-level)

Epic is Done when:

1. Every layer listed in §2.1 emits structured events for ≥99% of operations (measured by coverage Semgrep + integration tests)
2. A randomly selected user query can be fully reconstructed via `get_trace(trace_id)` — all HTTP/DB/cache/external/LLM/tool spans present and parent-linked
3. Admin UI 8 zones render with real data; auto-refresh works; drill-downs functional
4. All 13 MCP tools respond correctly to the benchmark queries in `tests/integration/observability/`
5. `/admin/observability` page reports `get_observability_health()` as green (all event streams within expected cadence)
6. Semgrep CI rules pass on main branch; coverage rules set to required (not advisory)
7. Retention policies active on all obs tables; table sizes stable over 7 days
8. Microservice extraction checklist validated via staging dry-run (optional but recommended)

## 11. Open Questions (for implementation discretion)

- **Sampling rates:** `cache_operation_log` at 1% sampling (errors always). `request_log` at 100% today; may sample to 10% if volume becomes an issue post-launch. Decision deferred to 1b.
- **Anomaly engine cadence:** default every 5 min; may tune per rule in 1c.
- **Disk spool location:** default `/var/tmp/obs-spool/` per worker; configurable via `OBS_SPOOL_DIR`. Details in 1a.
- **`provider_health_snapshot` cadence:** default every 60s; may tune. Details in 1b.
- **Semgrep rule aggressiveness:** advisory for 2 weeks, then required. Per existing `feedback_ci_guard_checklist` pattern.

## 12. References

- Observability audits (4 parallel agent reports, 2026-04-16 session) — captured to Obsidian
- `feedback_no_workarounds_fix_root_cause.md` — informs non-permissive fallback design
- `project_observability_differentiator.md` — product principle (user-facing transparency)
- `conventions/jira-sdlc-workflow.md` — Epic workflow
- `architecture/celery-patterns.md` — existing `@tracked_task` pattern
- `architecture/timescaledb-patterns.md` — hypertable + compression patterns

---

**Next step after PM approval:** Invoke `superpowers:writing-plans` skill on each sub-spec in sequence (1a first). Each sub-epic becomes its own plan + PR(s). Plans MUST stay ≤500 lines per Hard Rule #12; sub-epics may split into multiple PRs.
