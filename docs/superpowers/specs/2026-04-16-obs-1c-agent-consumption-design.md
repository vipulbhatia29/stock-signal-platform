# Sub-Spec 1c — Agent Consumption + Admin UI

**Parent:** [Master Architecture Spec](./2026-04-16-obs-master-design.md)
**Date:** 2026-04-16
**Status:** Draft — awaiting PM review
**Estimate:** ~6-8 days across 6 PRs
**Prerequisites:** [Sub-Spec 1a](./2026-04-16-obs-1a-foundations-design.md) + [Sub-Spec 1b](./2026-04-16-obs-1b-coverage-design.md) complete

---

## 1. Scope

With full coverage in place (1a + 1b), 1c productizes the substrate:

1. **13 MCP tools** for agent consumption (Claude Code today; autonomous agents later) — including the 9 agent-perspective gap closures
2. **CLI `health_report` script** — Markdown-output quick inspection tool
3. **Anomaly engine** — rule-based + statistical outlier detection; structured findings with remediation hints
4. **Admin UI 8 zones** at `/admin/observability` — operator dashboard
5. **JIRA draft integration** — "Create JIRA draft" button on findings

## 2. MCP Tools (Agent Consumption Surface)

All tools return structured JSON optimized for LLM parsing. All support `since` (relative: "1h", "24h", "7d") and `limit` (default 50, max 500). All return a standard envelope:

```json
{
  "tool": "get_recent_errors",
  "window": {"from": "2026-04-16T10:00:00Z", "to": "2026-04-16T11:00:00Z"},
  "result": {...},
  "meta": {"total_count": 152, "truncated": true, "schema_version": "v1"}
}
```

**Tool implementations:** `backend/observability/mcp/*.py`, registered via FastMCP at `backend/mcp_server/observability_tools.py`.

### 2.1 The 13 tools

| # | Tool | Purpose | Key params |
|---|---|---|---|
| 1 | `describe_observability_schema()` | Self-describing schema — tables, enums, event types, tool manifest, schema version. Called at session start by agents. | (none) |
| 2 | `get_platform_health(window_min=60)` | System-wide health snapshot — per-subsystem status, open anomalies, SLA breaches | `window_min` |
| 3 | `get_trace(trace_id)` | Full cross-layer reconstruction as a span tree. HTTP → auth → DB → cache → external → LLM → tools → response. | `trace_id` |
| 4 | `get_recent_errors(subsystem?, severity?, user_id?, ticker?, since?, limit?)` | Filtered error stream — `api_error_log` + `external_api_call_log` errors + tool errors + celery failures + frontend errors — unified view | filters |
| 5 | `get_anomalies(status=open, since?, severity?, attribution_layer?)` | Open findings from anomaly engine, ranked by severity × recency | filters |
| 6 | `get_external_api_stats(provider, window_min?, compare_to="prior_window")` | Per-provider: call count, success rate, error breakdown, cost, rate-limit events + comparison window | provider, `window_min`, `compare_to` |
| 7 | `get_dq_findings(severity?, check?, ticker?, since?)` | DQ scanner findings, historical | filters |
| 8 | `diagnose_pipeline(pipeline_name, recent_n=5)` | Deep dive on one pipeline: recent runs, failure pattern, watermark, ticker success distribution | name |
| 9 | `get_slow_queries(since?, min_duration_ms=500, query_hash?, compare_to="7d_baseline")` | Slow queries, grouped by `query_hash`; optional baseline comparison | filters |
| 10 | `get_cost_breakdown(window=7d, by="provider"|"model"|"tier"|"user", compare_to?)` | LLM cost trends + outliers | dims |
| 11 | `search_errors(query, since?, limit?)` | Full-text search across `error_message`, `stack_signature`, `finding.title` | query |
| 12 | `get_deploys(since?)` | Recent deploys — git SHA, PR, author, migrations, duration, outcome | filters |
| 13 | `get_observability_health()` | Self-observability: last-write timestamp per table, batch-flush failure rate, ingestion queue depth, spool size, retention compliance | (none) |

### 2.2 Tool design principles (closes agent-perspective gaps from review)

| Agent gap | Closure |
|---|---|
| A1 Self-describing schema | Tool 1 (`describe_observability_schema`) |
| A2 Stack traces on errors | `request_log.stack_signature` + `api_error_log.stack_trace` + same on tool/external errors — returned by tools 3, 4 |
| A3 Deploy events table | Tool 12 (`get_deploys`) + `deploy_events` table from 1b |
| A4 Window comparison | `compare_to` param on tools 6, 9, 10 |
| A5 User-scoped filtering | `user_id?` on tool 4; could be added to others if needed |
| A6 Parent_span_id causality | `get_trace` (tool 3) returns tree structure, not flat list |
| A7 Agent reasoning capture | `agent_reasoning_log` from 1b exposed via `get_trace` span detail |
| A8 Environment snapshot | `request_log.environment_snapshot` JSONB returned by `get_trace` on root span |
| A9 Self-observability | Tool 13 (`get_observability_health`) |

### 2.3 Example MCP responses

**`get_trace("abc-123")` returns a tree:**

```json
{
  "trace_id": "abc-123",
  "root_span": {
    "span_id": "s1",
    "kind": "http",
    "path": "/api/v1/portfolios/P1",
    "method": "GET",
    "status_code": 200,
    "latency_ms": 4200,
    "user_id": "u1",
    "environment_snapshot": {...},
    "children": [
      {
        "span_id": "s2",
        "kind": "auth.jwt_verify",
        "latency_ms": 3,
        "children": []
      },
      {
        "span_id": "s3",
        "kind": "db.query",
        "query_hash": "abc",
        "duration_ms": 2200,
        "source_file": "backend/services/portfolio.py",
        "source_line": 245,
        "children": []
      },
      {
        "span_id": "s4",
        "kind": "external_api",
        "provider": "yfinance",
        "status_code": 429,
        "error_reason": "rate_limit_429",
        "latency_ms": 180,
        "retry_count": 2,
        "children": []
      }
    ]
  }
}
```

The agent sees exactly where time was spent, what failed, where to look in code.

**`get_anomalies()` returns findings with actionable hints:**

```json
{
  "findings": [
    {
      "id": "f-42",
      "kind": "external_api_error_rate_elevated",
      "attribution_layer": "external_api",
      "severity": "warning",
      "status": "open",
      "opened_at": "2026-04-16T10:15:00Z",
      "title": "yfinance 429 rate elevated",
      "evidence": {
        "provider": "yfinance",
        "error_count_1h": 47,
        "baseline_1h": 2,
        "sigma": 8.3
      },
      "remediation_hint": "Check yfinance rate-limiter state in Redis (obs:rate_limiter:yfinance). Consider raising token bucket capacity from 30 to 50, or increasing burst interval. Cross-reference deploy_events for recent rate-limiter changes.",
      "related_traces": ["trace-123", "trace-456"],
      "suggested_jira_fields": {
        "type": "Bug",
        "priority": "Medium",
        "labels": ["external-api", "rate-limit", "yfinance"]
      }
    }
  ]
}
```

The `suggested_jira_fields` pre-populate the "Create JIRA draft" button.

## 3. CLI `health_report`

**File:** `scripts/health_report.py`

**Usage:**

```bash
# Full platform sweep — Markdown for copy-paste
uv run python -m scripts.health_report --since=1h

# Focused
uv run python -m scripts.health_report --layer=external_api --provider=yfinance --since=24h
uv run python -m scripts.health_report --trace=abc-123
uv run python -m scripts.health_report --anomalies
uv run python -m scripts.health_report --json    # machine-readable variant
```

**Output (Markdown default):** tuned for me to parse + paste into chat. Short. Anomaly-first.

```markdown
# Platform Health — last 1h

## 🟢 Status: Healthy (2 warnings)

## Open Anomalies (2)
1. **yfinance 429 rate elevated** [warning] — 47 errors (baseline 2, 8.3σ). See trace-123.
2. **Slow queries >2s on /portfolio/*** [info] — 3 distinct query_hash, likely missing index.

## Recent Errors (12 in 1h)
- api_error_log: 9 rows (7× 401 unauthorized, 2× 500 internal)
- external_api: 47 yfinance 429s
- celery: 0 failures
- frontend: 3 network_error rows

## Pipeline Health
- nightly_price_refresh: last success 2h ago ✅
- news_ingest: last success 6min ago ✅
- model_retrain: last success 48h ago ✅ (weekly cadence)

## External APIs (24h)
| Provider | Calls | Success | p95 lat | Errors | Cost |
|---|---|---|---|---|---|
| yfinance | 1,240 | 96.2% | 450ms | 47 (429) | $0.00 |
| openai | 312 | 99.4% | 890ms | 2 (timeout) | $0.37 |
| finnhub | 204 | 100% | 310ms | 0 | $0.00 |
```

Shares the same data source as MCP tools; different formatter.

## 4. Anomaly Engine

**File:** `backend/observability/anomaly/`

**Architecture:** Celery beat task running every 5 minutes. Reads obs tables. Writes findings to `finding_log`. Critical findings create `in_app_alerts` with dedup (already existing mechanism).

**Detection modes:**

### 4.1 Rule-based (ship first)

**Execution model:** Rules run in parallel via `asyncio.gather` with a `Semaphore(4)` to bound DB-pool pressure (12 rules × SQL-heavy queries across 7d of data could saturate the pool if unbounded). Each rule also has an individual `asyncio.wait_for(rule_fn(), timeout=30s)` wrapper — a stuck rule doesn't block the others.

Deterministic, tunable rules. 12 initial rules:

1. **External API error-rate spike** — provider error rate > 10% or > 3σ above 7-day baseline
2. **LLM cost spike** — daily spend > 3× rolling 7-day median
3. **Slow query regression** — query_hash p95 latency > 2× 7-day baseline
4. **DB pool exhaustion** — `db_pool_event` with `event_type=exhausted` in last 5min
5. **Rate-limiter permissive fallback** — any `rate_limiter_event.action=fallback_permissive` in last 5min (always a finding)
6. **Watermark staleness** — pipeline watermark older than expected cadence × 2
7. **Worker heartbeat missing** — no `celery_worker_heartbeat` from a known worker for >90s
8. **Beat schedule drift** — any `beat_schedule_run.drift_seconds > 300` in last hour
9. **5xx rate elevated** — `api_error_log` 5xx count > 5 in 5min
10. **Frontend error burst** — `frontend_error_log` count > 20 in 5min for same `error_type`
11. **DQ critical findings** — any `dq_check_history.severity=critical` in last run
12. **Agent decline rate elevated** — `agent_intent_log.decline_reason` count > 10% of queries in last 1h

Each rule:
- Config-driven thresholds (adjustable without code change)
- Produces a structured `finding_log` row with evidence + remediation hint
- Dedups via `(kind, attribution_layer, primary_entity)` key — same finding doesn't spam

### 4.2 Statistical (behind flag, ship after rules)

Flag: `ANOMALY_STATISTICAL_ENABLED` (default false initially).

- Rolling z-score on select metrics (latencies, costs, error rates)
- Change-point detection on time series (CUSUM or similar lightweight algo)
- Outputs `finding.kind = statistical_*` categories

Ship rules first, gather 2-4 weeks of baseline data, enable statistical after thresholds are proven.

### 4.3 `finding_log` table

```sql
CREATE TABLE observability.finding_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ,

    kind TEXT NOT NULL,               -- enum: external_api_error_rate|llm_cost_spike|slow_query_regression|db_pool_exhaustion|rate_limiter_fallback|watermark_stale|worker_heartbeat_missing|beat_drift|http_5xx_elevated|frontend_error_burst|dq_critical|agent_decline_elevated|statistical_latency|statistical_cost
    attribution_layer TEXT NOT NULL,  -- enum from master spec
    severity TEXT NOT NULL,           -- enum: info|warning|error|critical
    status TEXT NOT NULL,             -- enum: open|acknowledged|resolved|suppressed
    title TEXT NOT NULL,              -- short human summary
    evidence JSONB NOT NULL,          -- structured proof
    remediation_hint TEXT,            -- actionable guidance for agent/operator
    related_traces UUID[],            -- up to 5 sample trace_ids

    acknowledged_by UUID,             -- user_id
    acknowledged_at TIMESTAMPTZ,
    resolved_by UUID,
    resolved_at TIMESTAMPTZ,
    suppressed_until TIMESTAMPTZ,
    suppression_reason TEXT,

    dedup_key TEXT NOT NULL,          -- for preventing duplicates
    jira_ticket_key TEXT,             -- populated when JIRA draft created + filed
    env TEXT NOT NULL
);

CREATE INDEX ON observability.finding_log (status, severity, opened_at DESC);
CREATE INDEX ON observability.finding_log (dedup_key, status);
CREATE INDEX ON observability.finding_log (attribution_layer, kind, opened_at DESC);
```

**Retention:** 180 days.

### 4.4 Auto-close semantics

Findings auto-close when the condition clears:

- Rule re-evaluates every 5 min
- If rule returns false for 3 consecutive checks (15 min), finding transitions to `resolved` with `resolved_at=now()`
- Tracked as "auto-resolved" in evidence log

## 5. Admin UI — `/admin/observability`

**Route:** `frontend/src/app/(authenticated)/admin/observability/`

**8 Zones** as described in brainstorm. Auto-refresh every 15s. All zones gated to `admin` role.

### Zone 1: System Health Strip (always visible)

Horizontal strip at top. Each subsystem rendered as a pill with color + quick stat.

| Pill | Healthy | Degraded | Failing |
|---|---|---|---|
| DB | "< 50ms p95" | "50-200ms" | ">200ms or error" |
| Redis | "< 5ms ping" | "5-50ms" | ">50ms or error" |
| Celery | "N workers alive, Q depth = K" | "workers down OR Q depth high" | "no workers OR Q>1000" |
| MCP | "subprocess alive" | "fallback mode" | "down" |
| Langfuse | "connected" | (N/A) | "disabled" |
| yfinance | "success rate 24h" | "90-95%" | "<90%" |
| openai | (same) | (same) | (same) |
| (all 10 external APIs) | | | |

Click a pill → drill-down sheet with latency trend + recent errors.

### Zone 2: Live Error Stream (center-left)

Ticker-tape-style table of last 50 errors across all layers. Each row:

- Timestamp (relative: "2m ago")
- Layer pill (colored by layer)
- Severity badge
- Short message (truncated; expand on hover)
- Trace icon → clicking opens Trace Explorer (Zone 4)

Filters: layer, severity, time range, endpoint, user_id, trace_id search box.

### Zone 3: Anomaly Findings (center-right)

Card list of open findings. Each card:

- Severity badge (colored border)
- Title
- Layer pill
- Opened-at relative time
- Evidence summary (2-3 key numbers)
- Remediation hint (first 150 chars)
- Action row: `[Ack]` `[Suppress 1h]` `[Open trace]` `[Create JIRA draft]`

Filters: severity, layer, kind, status (default: open only).

### Zone 4: Trace Explorer (bottom, accordion)

Input: paste `trace_id` OR click any error/finding that has associated trace. Renders:

- Timeline waterfall — spans plotted on horizontal time axis (like Chrome devtools)
- Each span: duration bar colored by kind (http/auth/db/cache/external/llm/tool)
- Click span → detail panel: full span fields, errors, source_file:line, stack
- Copy trace_id button
- "Open in isolated view" → full-page trace explorer

This is the killer feature — the thing you'll use most when debugging.

### Zone 5: External API Dashboard (tab)

Grid — one row per provider. Columns: call count (24h), success rate, p95 latency, total cost, rate-limit events, recent errors (top 3 messages). Click provider → time-series charts + recent-error list + cost trend.

### Zone 6: Cost + Budget (tab)

- LLM cost trends by provider/model/tier (line chart, 30d)
- Token budget utilization per tier (gauges)
- Cost anomaly callouts ("Today's spend is 3x yesterday's")
- Top 10 most expensive queries (clickable → Trace Explorer)

### Zone 7: Pipeline Health (tab)

Table: every pipeline with last-run status, watermark age, next expected run, red/amber/green. Beat drift readout. Click pipeline → pipeline detail (historical runs + step durations).

### Zone 8: DQ Scanner (tab)

Trend per check over 30 days. Recent critical findings. Manual "run now" button (triggers `dq_scan_task`).

### 5.1 Implementation notes

- Shadcn components extended with project design system (`architecture/frontend-design-system`)
- Recharts for time-series (per project convention; disable animations per Playwright gotcha)
- TanStack Query with 15s polling + stale-while-revalidate
- No websockets (polling is simpler; 15s is fine for operator use)
- **Query REST endpoints (ship in PR5a, before UI):**
  - `GET /api/v1/observability/admin/kpis` — Zone 1 (system health)
  - `GET /api/v1/observability/admin/errors` — Zone 2 (error stream, filterable)
  - `GET /api/v1/observability/admin/findings` — Zone 3
  - `GET /api/v1/observability/admin/trace/{trace_id}` — Zone 4
  - `GET /api/v1/observability/admin/externals` — Zone 5
  - `GET /api/v1/observability/admin/costs` — Zone 6
  - `GET /api/v1/observability/admin/pipelines` — Zone 7
  - `GET /api/v1/observability/admin/dq` — Zone 8
  - All admin-role-gated via existing `require_admin()` dependency
  - Internally delegate to the same `ObservabilityQueryService` that MCP tools use — single source of truth for query logic

## 6. JIRA Draft Integration

**Purpose:** When operator clicks "Create JIRA draft" on a finding, a pre-filled ticket opens.

**Implementation:**

- Backend endpoint: `POST /api/v1/observability/findings/{finding_id}/jira-draft`
- Uses existing Atlassian MCP integration to create an issue with:
  - Title: finding.title
  - Description: evidence (pretty-printed) + remediation_hint + related_traces (as links) + observability query to reproduce
  - Labels: from `suggested_jira_fields.labels`
  - Priority: from finding.severity
  - Reporter: current admin user
- Returns JIRA ticket URL
- Updates `finding_log.jira_ticket_key`

**Operator approval flow:** Button creates the JIRA issue in status "To Do" with tag `obs-generated`. Operator reviews and refines.

**NOT in scope:** automatic filing without approval. Operator always clicks.

## 7. Out of Scope

- Automatic agent fix-and-ship loop (future epic — requires approval + tests + hypothesis-driven remediation)
- External observability export (Datadog/Honeycomb integration) — YAGNI
- User-facing trace explorer for regular users — admin only
- Alerting to email/Slack — in-app alerts sufficient
- Log-line-level full-text search (ElasticSearch-style) — finding search + structured queries cover needs

## 8. PR Breakdown

| PR | Scope | Est. lines |
|---|---|---|
| **PR1** | `finding_log` table + anomaly engine framework (parallel execution + per-rule timeout) + 6 rules + beat schedule | ~450 |
| **PR2** | Remaining 6 anomaly rules + dedup + auto-close | ~300 |
| **PR3** | 13 MCP tools + `backend/observability/mcp/` module + FastMCP registration | ~500 |
| **PR4** | CLI `scripts/health_report.py` + tests | ~300 |
| **PR5a** | **Admin query REST endpoints** (`/api/v1/observability/admin/{kpis,errors,findings,trace,externals,costs,pipelines,dq}`) — the data layer the UI consumes | ~400 |
| **PR5b** | Admin UI zones 1-4 (health strip, error stream, findings, trace explorer) — depends on PR5a endpoints | ~500 |
| **PR6** | Admin UI zones 5-8 (external APIs, cost, pipelines, DQ) + JIRA draft integration | ~500 |

## 9. Acceptance Criteria (1c-level)

- [ ] All 13 MCP tools return valid JSON matching documented schemas
- [ ] `describe_observability_schema()` matches actual DB schema (verified by test that queries `information_schema`)
- [ ] `get_trace(trace_id)` reconstructs span tree with parent-child linkage
- [ ] Anomaly engine produces findings for all 12 rules when conditions met (tested via fixtures)
- [ ] Finding auto-close works (3 negative checks → resolved)
- [ ] Dedup prevents >1 open finding per `dedup_key`
- [ ] CLI `health_report --since=1h` produces Markdown output in <3s
- [ ] Admin UI `/admin/observability` renders all 8 zones with real data from local dev
- [ ] "Create JIRA draft" creates issue with populated fields + returns URL
- [ ] Finding's `related_traces` link clickable in UI → opens Trace Explorer
- [ ] 15s auto-refresh works without flashing/jumping
- [ ] Playwright E2E: admin logs in, sees health zones, clicks an error, trace explorer opens

## 10. Risks

| Risk | Mitigation |
|---|---|
| Anomaly rules produce too many findings | Tune thresholds; dedup; auto-close; start conservative |
| Dashboard slow at scale | TimescaleDB indexes; aggregation queries pre-compute; Redis cache for zone data (10s TTL) |
| MCP tool response too large for LLM context | Default `limit=50`; truncation; pagination cursor |
| JIRA draft creates noise | Operator approves each; `obs-generated` label for sorting |
| Statistical anomaly detection noisy | Gated behind flag; ship rule-based first; enable statistical only after baseline collected |
| Trace explorer rendering heavy for large traces | Cap displayed spans at 500; "show more" pagination |

## 11. Files Touched (estimate)

New:
- `backend/observability/mcp/` — 13 MCP tool implementations
- `backend/mcp_server/observability_tools.py` — FastMCP registration
- `backend/observability/anomaly/` — engine + 12 rule files + config
- `backend/observability/models/finding_log.py`
- `backend/observability/routers/admin_dashboard.py` — query APIs for UI
- `backend/observability/services/jira_draft.py` — integration
- `backend/migrations/versions/032_finding_log.py`
- `scripts/health_report.py`
- `frontend/src/app/(authenticated)/admin/observability/` — 8 zones
- `frontend/src/hooks/use-observability-*.ts` — TanStack Query hooks
- `frontend/src/components/admin/observability/` — zone components

Modified:
- `backend/tasks/__init__.py` — add anomaly engine beat schedule
- `backend/mcp_server/server.py` — register observability tools
- `backend/observability/context.py` — surfaces schema version

## 12. Testing Strategy

- **Unit:** each anomaly rule tested with synthetic fixtures (positive + negative cases)
- **Unit:** each MCP tool tested with known data → expected JSON output
- **Integration:** CLI `health_report --since=1h` against seeded test DB
- **Playwright E2E:** login as admin, open `/admin/observability`, verify all 8 zones render, click an error, trace explorer opens, create JIRA draft
- **Contract:** `describe_observability_schema()` output matches `information_schema`
- **Performance:** MCP tool p95 <1s on local dev with 24h of data; dashboard queries p95 <500ms

## 13. Rollout

- PR1-PR2: anomaly engine, observe findings for 1 week on `develop` to tune thresholds
- PR3-PR4: MCP tools + CLI — immediately useful for debugging during PR5/PR6 development
- PR5-PR6: UI zones, Playwright smoke tests, admin role verification
- Demo to PM + walkthrough of common debugging scenarios

---

## 14. The Debugging Workflow (end state)

After 1c ships, this is the workflow:

**You notice something:** admin dashboard flashes red on yfinance pill.

**You ask me:** "yfinance seems off, what's happening?"

**I (in a single turn):**
1. `get_platform_health(60)` — confirm overall status
2. `get_external_api_stats(provider=yfinance, window_min=60, compare_to="prior_window")` — quantify
3. `get_anomalies(attribution_layer=external_api, status=open)` — any engine-flagged finding
4. `search_errors("yfinance 429", since=2h)` — recent incidents
5. Pick one failing trace: `get_trace(trace_id)` — see the full request path
6. Return: concrete diagnosis with file:line pointers to investigate, cost impact, suggested fix

**Total round trips with you:** 1. **Time to actionable insight:** ~10 seconds of MCP calls.

Compare to today: I'd ask you to grep logs, rerun things, paste output. Hours not seconds.

That's the payoff.

---

**Terminal step:** After PM approves all 4 specs, invoke `superpowers:writing-plans` skill starting with 1a.
