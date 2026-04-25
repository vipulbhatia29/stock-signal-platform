# Observability Integration Test Suite — Spec

**Date:** 2026-04-25
**Epic:** Observability Suite Validation
**Status:** Draft
**Depends on:** Epic KAN-457 (Platform Observability Infrastructure — COMPLETE)

---

## 1. Purpose

Validate that the 22 PRs comprising the observability suite (sub-epics 1a, 1b, 1c) integrate correctly as a system. Unit tests (71 files) cover individual components in isolation; this effort proves the **end-to-end paths** work when composed.

**Deliverables:**
1. Integration test suite (~25-29 tests across 6 files)
2. Unit test coverage audit (gaps filed as JIRA tickets)
3. Traceability matrix mapping features → tests → coverage status

## 2. Scope

### In scope
- Integration tests for 8 critical paths (SDK pipeline, trace propagation, anomaly lifecycle, admin endpoints, MCP tools, retention)
- Unit test audit across 9 coverage dimensions
- Traceability matrix: obs features → test coverage
- 5-persona expert review of the plan

### Out of scope
- Fixing unit test gaps (filed as separate tickets)
- Frontend E2E tests for admin dashboard (blocked on KAN-400 UI Overhaul)
- Performance/load testing of the obs pipeline
- Testing against InternalHTTPTarget (microservice extraction path — future work)

## 3. Prerequisites & Dependencies

### Infrastructure prerequisites (already in place)
- **Testcontainers Postgres** — `tests/conftest.py` starts `timescale/timescaledb:latest-pg16` container (session-scoped). The `_setup_database` fixture already runs `CREATE SCHEMA IF NOT EXISTS observability` and `Base.metadata.create_all`.
- **Schema truncation** — the `client` fixture truncates all tables (including `observability.*`) between tests via qualified `TRUNCATE ... CASCADE`.
- **`OBS_TARGET_TYPE=memory`** — root conftest sets this for unit tests. Integration tests will override to `direct` to test the real write path.
- **CI compatibility** — `tests/integration/conftest.py` overrides `db_url` to read `DATABASE_URL` from env (CI service containers). New tests inherit this.

### Dependencies (must be built as part of this effort)
| Dependency | Why needed | Effort |
|---|---|---|
| **Obs model factories** (factory-boy) | No factories exist for any of the 22 observability models. Tests need `RequestLogFactory`, `FindingLogFactory`, `AuthEventLogFactory`, `ExternalApiCallFactory`, `CeleryWorkerHeartbeatFactory` (minimum 5). | ~80 lines |
| **`obs_client` fixture** | Real `ObservabilityClient` with `DirectTarget` pointed at test DB (override `OBS_TARGET_TYPE=direct`). Must `await client.start()` / `await client.stop()` around tests. | ~30 lines |
| **`obs_session` fixture** | Async session scoped to `observability` schema for direct row assertions. May reuse existing `db_session` if schema-qualified queries work. | ~10 lines |
| **`seeded_obs_data` fixture** | Composite fixture that populates multiple obs tables using factories. Returns `dict[str, list[Row]]` for assertions. | ~50 lines |
| **Admin user fixture** | Some admin endpoints require `is_admin=True`. Existing `auth_headers` may not grant admin. Need `admin_auth_headers` fixture. | ~15 lines |

### External dependencies (no action needed)
| Dependency | Status |
|---|---|
| Epic KAN-457 (Observability Infrastructure) | COMPLETE — all 22 PRs merged |
| `observability` schema + 22 models | Shipped in migrations 030-040 |
| Anomaly engine + 14 rules | Shipped in 1c PR1-PR2 |
| MCP tools (13) | Shipped in 1c PR3 |
| Admin endpoints (8) | Shipped in 1c PR5 |
| JIRA draft endpoint | Shipped in 1c PR7 |

### Ordering constraints
1. Factories + fixtures must be built **first** (other tests depend on them)
2. `test_sdk_pipeline.py` should be implemented before `test_trace_propagation.py` (validates the base emit path that trace tests build on)
3. `test_admin_endpoints.py` and `test_mcp_tools.py` can be parallelized (independent)
4. `test_retention.py` is independent of all others
5. Unit audit happens **after** integration tests are written (the audit may reference integration coverage)

## 4. Data Strategy

**Principle: real SDK + real DB + mocked externals.**

| Tier | What | How |
|---|---|---|
| **Real (no mocks)** | ObservabilityClient, EventBuffer, DirectTarget, event writers, DB inserts, admin query endpoints, MCP tool functions, anomaly rules, retention tasks | Testcontainers Postgres with `observability` schema |
| **Triggered (synthetic requests)** | HTTP middleware, auth instrumentation, trace_id propagation | Real HTTP requests to FastAPI test app via `async_client` |
| **Mocked (boundaries only)** | JIRA REST API, external providers (yfinance/Finnhub), Celery Beat clock | `unittest.mock.patch` / `respx` at the HTTP boundary |

**Rationale:** The observability pipeline is the system under test — it must be real. Only the things it *observes* (external APIs, JIRA) get mocked. This avoids the Session 103 anti-pattern where mocked tests passed but real SQL bugs and wrong call sites went undetected.

## 5. Test Organization

All new tests in `tests/integration/observability/` alongside existing files.

### 4.1 `test_sdk_pipeline.py` — SDK Emission → DB Persistence

Proves: emit → buffer → flush → DirectTarget → type-specific writer → correct DB table.

| # | Test | Event type(s) | Assertion |
|---|---|---|---|
| 1 | `test_emit_request_log_persists` | `REQUEST_LOG` | Row exists in `request_log` with correct fields |
| 2 | `test_emit_auth_event_persists` | `AUTH_EVENT` | Row exists in `auth_event_log` |
| 3 | `test_emit_external_api_call_persists` | `EXTERNAL_API_CALL` | Row exists in `external_api_call` |
| 4 | `test_emit_agent_intent_persists` | `AGENT_INTENT` | Row exists in `agent_intent_log` |
| 5 | `test_emit_mixed_batch_routes_correctly` | 4+ different types | Each row lands in correct table |
| 6 | `test_obs_disabled_no_writes` | Any | `OBS_ENABLED=False` → no rows written |
| 7 | `test_buffer_overflow_spools_to_disk` | Burst > buffer size | Spool file created, events recover on next flush |

### 4.2 `test_trace_propagation.py` — Cross-Layer Trace Correlation

Proves: trace_id generated/adopted by middleware flows through all downstream emitters.

| # | Test | Trigger | Assertion |
|---|---|---|---|
| 1 | `test_trace_id_adopted_from_header` | HTTP request with `X-Trace-Id` | `request_log.trace_id` matches header value |
| 2 | `test_trace_id_generated_when_missing` | HTTP request without header | Response has `X-Trace-Id`, `request_log` has same value |
| 3 | `test_trace_id_spans_multiple_tables` | Request triggering DB + external API obs events | Same `trace_id` in `request_log`, `slow_query_log`, `external_api_call` |
| 4 | `test_span_hierarchy_coherent` | Request with nested spans | `parent_span_id` chain is valid (no orphans, no cycles) |

### 4.3 `test_anomaly_lifecycle.py` — Detection → Persistence → Action

Proves: anomaly rules evaluate real data, findings persist with dedup, JIRA draft works.

| # | Test | Setup | Assertion |
|---|---|---|---|
| 1 | `test_http_5xx_rule_creates_finding` | Seed `request_log` with 5xx rows above threshold | `finding_log` has finding with `kind=http_5xx_elevated`, `status=open` |
| 2 | `test_worker_heartbeat_rule_creates_finding` | Seed `celery_worker_heartbeat` with stale timestamps | Finding with `kind=worker_heartbeat_missing` |
| 3 | `test_finding_dedup_no_duplicates` | Run `run_anomaly_scan()` twice (separate invocations) on same bad data | Only 1 finding (dedup_key match) |
| 4 | `test_jira_draft_updates_finding` | Create finding → POST `/findings/{id}/jira-draft` (JIRA API mocked) | `finding.jira_ticket_key` set, mock called with correct payload |

### 4.4 `test_admin_endpoints.py` — Query Endpoints Against Real Data

Proves: admin API returns correct shapes from real obs data.

| # | Test | Endpoint | Assertion |
|---|---|---|---|
| 1 | `test_kpis_returns_all_subsystems` | `GET /kpis` | All subsystem keys present, status values are valid enums |
| 2 | `test_errors_filters_by_subsystem` | `GET /errors?subsystem=HTTP` | Only HTTP-layer errors returned |
| 3 | `test_findings_ranked_by_severity` | `GET /findings` | CRITICAL before WARNING before INFO |
| 4 | `test_acknowledge_transitions_status` | `PATCH /findings/{id}/acknowledge` | Status changes `open` → `acknowledged` |
| 5 | `test_suppress_sets_ttl` | `PATCH /findings/{id}/suppress` | Status → `suppressed`, `suppressed_until` set |
| 6 | `test_admin_auth_required` | All admin endpoints without auth | 401/403 response |

### 4.5 `test_mcp_tools.py` — Agent Consumption Contract

Proves: MCP tool functions return correct structures from real data.

| # | Test | Tool | Assertion |
|---|---|---|---|
| 1 | `test_platform_health_structure` | `get_platform_health()` | Per-subsystem status dict, all layers present |
| 2 | `test_get_trace_reconstructs_span_tree` | `get_trace(trace_id)` | Span tree with correct parent-child relationships |
| 3 | `test_get_anomalies_matches_findings` | `get_anomalies()` | Results match `finding_log` rows, severity-ranked |
| 4 | `test_search_errors_text_match` | `search_errors("timeout")` | Returns errors containing "timeout" |
| 5 | `test_obs_health_self_report` | `get_observability_health()` | Reports SDK client status, last-write timestamp |

### 4.6 `test_retention.py` — Data Lifecycle Correctness

Proves: retention tasks delete old data correctly, hypertable vs regular table distinction works.

| # | Test | Table type | Assertion |
|---|---|---|---|
| 1 | `test_hypertable_retention_drops_chunks` | `request_log` (hypertable, 30d) | Old chunks dropped, recent data survives |
| 2 | `test_regular_table_retention_deletes_rows` | `auth_event_log` (regular, 90d) | Old rows deleted, recent rows survive |
| 3 | `test_retention_days_match_policy` | All 22 tables (parametrized) | Each table's retention task uses the declared retention period |

## 6. Fixtures

### New fixtures (in `tests/integration/observability/conftest.py`)

```python
@pytest.fixture
async def obs_client(db_session):
    """Real ObservabilityClient with DirectTarget pointed at test DB."""
    ...

@pytest.fixture
async def obs_session(db_engine):
    """Async session scoped to observability schema."""
    ...

@pytest.fixture
async def seeded_obs_data(obs_session):
    """Populate multiple obs tables with realistic factory-built data.
    Returns dict of {table_name: [inserted_rows]} for assertions.
    """
    ...

@pytest.fixture
async def seeded_findings(obs_session):
    """Seed finding_log with findings at various statuses/severities."""
    ...
```

### Reused fixtures
- `async_client` — httpx AsyncClient for endpoint tests
- `auth_headers` — admin JWT for authenticated requests
- `db_session` / `db_engine` — from testcontainers conftest

## 7. CI Integration

New integration tests run automatically in both CI pipelines — **no CI config changes needed**.

### Existing CI coverage for `tests/integration/`

| Pipeline | Trigger | Command | Env vars |
|---|---|---|---|
| `ci-pr.yml` | PR to `develop` or `main` | `uv run pytest tests/integration/ -v --tb=short -m integration` | `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `MCP_TOOLS=true`, `CI=true` |
| `ci-merge.yml` | Push to `develop` | `uv run pytest tests/integration/ -v --tb=short -m integration` | Same as above |

### What this means for new tests
- All new test files in `tests/integration/observability/` are **automatically discovered** by both pipelines
- Tests must be marked `@pytest.mark.integration` to match the `-m integration` filter
- CI uses real Postgres service container (not testcontainers) — `DATABASE_URL` from GitHub Actions Secrets
- `tests/integration/conftest.py` overrides `db_url` fixture to read `DATABASE_URL` env var in CI
- The `observability` schema is created by `_setup_database` in root conftest (runs in both local + CI)

### CI-specific considerations
- **No testcontainers in CI** — `CI=true` env var triggers `pytest.fail()` if testcontainers are invoked. Tests use service containers instead.
- **Sequential execution** — integration tests run without xdist (shared DB state)
- **Timeout** — no explicit timeout on integration job. Tests should complete in <60s total (obs queries are lightweight).
- **Path filter** — `ci-pr.yml` only runs backend tests when `tests/integration/**` changes (already in path filter list at line 31)

### Validation checklist (during implementation)
- [ ] All tests pass with `uv run pytest tests/integration/observability/ -v --tb=short -m integration`
- [ ] All tests pass with `DATABASE_URL` env var (simulating CI mode)
- [ ] No testcontainers imports in new test files (CI-safe)
- [ ] Total integration suite runtime stays under 60s

## 8. Unit Test Audit

The 5-persona review audits existing unit tests against 9 dimensions:

| Dimension | Expected | Audit question |
|---|---|---|
| 22 event types | Each has ≥1 serialization + validation test | Any event type without a test? |
| 22 DB models | Each has ≥1 create/read test | Any model untested? |
| 14 anomaly rules | Each has ≥1 "triggers" + ≥1 "doesn't trigger" test | Any rule with only happy path? |
| 13 MCP tools | Each has ≥1 test with realistic data | Any tool untested or empty-state only? |
| 14 emitter points | Each has ≥1 test asserting `emit_sync`/`emit` called | Any emitter with no mock assertion? |
| 8 admin endpoints | Each has auth + happy + error test | Missing auth guard test? |
| ContextVar guards | `_in_obs_write`, `_emitting_auth_event` recursion prevention tested | Guard missing or untested? |
| PII redaction | Redaction tested on PII-carrying event types | Any event type leaking PII? |
| 20+ retention tasks | Each task has ≥1 test | Any retention task untested? |

**Output:** Each gap → filed as a JIRA Task under the Epic with priority and effort estimate.

## 9. Traceability Matrix

Final deliverable mapping obs features (from 1a/1b/1c specs) to test coverage:

| Feature (from spec) | Integration test | Unit test file(s) | Status |
|---|---|---|---|
| SDK buffered emission | `test_sdk_pipeline::test_emit_*` | `test_client.py`, `test_buffer.py` | Covered |
| Trace propagation | `test_trace_propagation::*` | `test_trace_id.py` | Covered |
| HTTP request logging | `test_sdk_pipeline::test_emit_request_log` | `test_http_middleware.py` | Covered |
| Anomaly detection | `test_anomaly_lifecycle::*` | `anomaly/test_engine.py`, `anomaly/test_rules.py` | Covered |
| ... | ... | ... | ... |

(Full matrix produced during implementation, one row per feature from the 3 sub-epic specs.)

## 10. Review Plan

**5 personas, applied to the implementation plan (not this spec):**

| Persona | Focus |
|---|---|
| Backend Architect | SDK lifecycle, buffer/spool, target abstraction, middleware ordering, ContextVar guards |
| Test Engineer | Coverage gaps, test quality, missing edge cases, fixture design |
| DB/SQL Expert | Hypertable vs regular retention, schema integrity, index coverage |
| Reliability Engineer | Anomaly engine, finding lifecycle, fire-and-forget isolation, spool overflow |
| Full-Stack/API Contract | Admin response shapes, MCP tool output, trace reconstruction |

**Per review-scaling.md:** 5 personas is appropriate — this is cross-cutting infrastructure touching HTTP, auth, DB, cache, Celery, LLM, agents, frontend, and external APIs.

## 11. Constraints

- **PR ≤ 500 lines of diff** (Hard Rule #12)
- **Tests run sequentially** (integration tier — shared DB, no xdist)
- **Testcontainers for Postgres** (CI uses `CI_DATABASE_URL`)
- **No new migrations** — tests use existing `observability` schema
- **Factory-boy for test data** — new factories for obs models as needed
- **JIRA API always mocked** — never create real tickets in tests

## 12. Success Criteria

1. All ~25-28 integration tests pass locally and in CI
2. Unit audit identifies all gaps with JIRA tickets filed
3. Traceability matrix covers every feature from 1a/1b/1c specs
4. 5-persona review finds no CRITICAL issues in the plan
5. PR merged to develop with zero regressions
