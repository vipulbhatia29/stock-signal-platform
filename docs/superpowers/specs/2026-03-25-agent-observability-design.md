# Agent Observability — Design Spec

**Date**: 2026-03-25
**Phase**: 6B
**Status**: Draft
**Depends on**: LLM Factory & Cascade (Phase 6A)
**Blocks**: Testing Infrastructure spec (Phase 6C)

---

## 1. Problem Statement

We have `LLMCallLog` and `ToolExecutionLog` tables (created in migrations 008 + 010, TimescaleDB hypertables) but **nothing writes to them**. We cannot answer:

- "How much did LLM calls cost today?"
- "Which model is failing most?"
- "What's our escalation rate to Anthropic?"
- "Which tools are slowest?"

Reference: aset-platform's `ObservabilityCollector` tracks per-model requests, cascade events, compression triggers, tier health classification, and latency percentiles — all in real-time with batched persistence.

---

## 2. Event Types

### 2.1 LLM Request Events

Written by `LLMClient` / `GroqProvider` after every LLM call (success or cascade failure).

| Field | Source | Existing Column? |
|---|---|---|
| `session_id` | Chat request context | Yes (`chat_session` FK) |
| `message_id` | After message persistence | Yes (`chat_message` FK) |
| `provider` | `provider.name` | Yes |
| `model` | Actual model that responded | Yes |
| `prompt_tokens` | `response.prompt_tokens` | Yes |
| `completion_tokens` | `response.completion_tokens` | Yes |
| `cost_usd` | Computed: tokens × `llm_model_config.cost_per_1k_*` | Yes |
| `latency_ms` | `time.monotonic()` wall clock | Yes |
| `tool_calls_requested` | Tool calls from response (JSONB) | Yes |
| `error` | Error message if cascade failure | Yes |
| `tier` | `"planner"` / `"synthesizer"` | Yes |
| `query_id` | Request-scoped UUID | Yes |

### 2.2 Cascade Events

Written by `GroqProvider` when skipping a model. Stored as LLMCallLog entries with `error` populated.

| Field | Value |
|---|---|
| `provider` | "groq" |
| `model` | The model that was skipped |
| `error` | Reason: `"budget_exhausted"`, `"tool_call_failure"`, `"server_error"`, `"rate_limit"`, `"connection_error"` |
| `cost_usd` | 0.0 (no tokens consumed) |
| `tier` | Tier that triggered the cascade |

### 2.3 Tool Execution Events

Written by the executor after each tool call in `graph_v2.py` → `execute_node()`.

| Field | Source | Existing Column? |
|---|---|---|
| `session_id` | Chat request context | Yes |
| `message_id` | Current message | Yes |
| `tool_name` | Tool that was executed | Yes |
| `params` | Input params (JSONB) | Yes |
| `result_size_bytes` | `len(json.dumps(result))` | Yes |
| `latency_ms` | Wall clock of tool execution | Yes |
| `cache_hit` | False (future: Redis cache) | Yes |
| `status` | `"ok"` / `"error"` | Yes |
| `error` | Error message if failed | Yes |
| `query_id` | Same request-scoped UUID | Yes |

---

## 2.4 Request Context Flow

`session_id`, `message_id`, and `query_id` must flow from the chat router down to the provider and collector. We use **ContextVars** (already established: `current_user_id` ContextVar exists in `chat.py`).

New ContextVars in `backend/agents/context.py`:
```python
from contextvars import ContextVar
import uuid

current_query_id: ContextVar[uuid.UUID | None] = ContextVar("current_query_id", default=None)
current_session_id: ContextVar[uuid.UUID | None] = ContextVar("current_session_id", default=None)
```

Set by `chat_stream()` in `chat.py` before streaming begins. Read by `ObservabilityCollector.record_request()` and `record_cascade()`. No changes to `LLMProvider.chat()` or `LLMClient.chat()` signatures.

---

## 3. In-Memory Real-Time Metrics

New module: `backend/agents/observability.py`

### 3.1 ObservabilityCollector

Async-safe singleton (uses `asyncio.Lock`) tracking:

| Metric | Structure | Purpose |
|---|---|---|
| `requests_by_model` | `dict[str, int]` | Cumulative request count per model |
| `requests_per_minute` | `dict[str, deque]` (60s window) | Current RPM per model |
| `cascade_count` | `int` | Total cascade events |
| `cascade_log` | `deque(maxlen=1000)` | Last 1000 cascade events |
| `cascades_by_model` | `dict[str, int]` | Per-model cascade count |
| `failures_by_model` | `dict[str, deque]` (5-min window) | Recent failures for health |
| `successes_by_model` | `dict[str, deque]` (5-min window) | Recent successes for health |
| `latency_by_model` | `dict[str, deque(maxlen=100)]` | Recent latencies for p50/p95 |
| `disabled_tiers` | `set[str]` | Manually disabled models |

### 3.2 Tier Health Classification

Based on failures in a 5-minute sliding window:

| Recent Failures (5 min) | Status | Meaning |
|---|---|---|
| 0 | `healthy` | Normal |
| 1–3 | `degraded` | Intermittent issues |
| 4+ | `down` | Consistently failing |
| manually toggled | `disabled` | Admin disabled via API |

### 3.3 API

```python
collector = ObservabilityCollector()

# After successful LLM call:
collector.record_request(model, provider, tier, latency_ms, prompt_tokens, completion_tokens)

# After cascade skip:
collector.record_cascade(from_model, reason, provider, tier)

# Admin queries:
stats = collector.get_stats()          # requests, cascades, RPM, recent log
health = collector.get_tier_health()   # per-model health + latency
```

---

## 4. DB Write Path

### 4.1 Strategy: Fire-and-Forget Async Insert

LLM and tool execution events are written asynchronously. A logging failure must **never** block the user's request.

```python
async def _log_llm_call(self, event: dict) -> None:
    try:
        async with async_session_factory() as db:
            db.add(LLMCallLog(**event))
            await db.commit()
    except Exception:
        logger.warning("Failed to log LLM call", exc_info=True)
```

### 4.2 Batching (Optional Optimization)

If write volume is high, batch events in a `deque` buffer and flush every 30 seconds via an async background task (similar to aset's `_FLUSH_INTERVAL`). For our current volume (single user, ~2 LLM calls per chat query), individual inserts are fine. Batching can be added later.

### 4.3 Shutdown Flush

On app shutdown (FastAPI lifespan `yield`), flush any buffered events synchronously to avoid data loss.

---

## 5. Admin API Endpoints

Router: `backend/routers/admin.py` (created in Phase 6A with LLM model config endpoints — add observability endpoints to the existing router)

| Endpoint | Method | Auth | Response |
|---|---|---|---|
| `GET /admin/llm-metrics` | GET | superuser | `{requests_by_model, cascade_count, rpm_by_model, cascade_log (last 50)}` |
| `GET /admin/tier-health` | GET | superuser | `{tiers: [{model, status, failures_5m, successes_5m, cascade_count, latency: {avg_ms, p95_ms}}], summary: {total, healthy, degraded, down, disabled}}` |
| `POST /admin/tier-toggle` | POST | superuser | Enable/disable a model at runtime. Body: `{model: str, enabled: bool}` |
| `GET /admin/llm-usage` | GET | superuser | Aggregated from `llm_call_log`: `{total_requests, total_cost_usd, avg_latency_ms, models: [{model, provider, request_count, estimated_cost_usd}], escalation_rate}` |

### 5.1 Escalation Rate

The most important cascade health metric (per research):

```sql
SELECT
    COUNT(*) FILTER (WHERE provider = 'anthropic') * 100.0 / COUNT(*) AS escalation_pct
FROM llm_call_log
WHERE created_at > now() - interval '24 hours'
  AND error IS NULL;
```

If this creeps above 10%, something is wrong with Groq availability or our budget is exhausted.

---

## 6. Dashboard API (Data Only)

`GET /api/v1/dashboard/llm-usage` — available to authenticated users (not just superuser).

Returns:

```json
{
  "total_requests_30d": 1234,
  "total_cost_usd_30d": 2.45,
  "avg_latency_ms": 340,
  "models": [
    {"model": "llama-3.3-70b", "provider": "groq", "request_count": 900, "cost_usd": 0.0},
    {"model": "claude-sonnet-4-6", "provider": "anthropic", "request_count": 34, "cost_usd": 2.45}
  ],
  "escalation_rate": 0.028
}
```

**No frontend widget in this spec** — just the API. Frontend can be built later.

---

## 7. Files Changed

| Action | File |
|---|---|
| **Create** | `backend/agents/observability.py` |
| **Modify** | `backend/agents/providers/groq.py` (add `collector.record_request/cascade` calls) |
| **Modify** | `backend/agents/llm_client.py` (pass collector, record on success/failure) |
| **Modify** | `backend/agents/graph_v2.py` (record tool execution in `execute_node`) |
| **Modify** | `backend/routers/admin.py` (add metrics, tier-health, tier-toggle, llm-usage endpoints) |
| **Modify** | `backend/main.py` (instantiate `ObservabilityCollector`, inject into providers/client) |

---

## 8. Success Criteria

- [ ] Every LLM call (success + cascade) writes to `llm_call_log`
- [ ] Every tool execution writes to `tool_execution_log`
- [ ] `GET /admin/llm-metrics` returns real-time cascade stats
- [ ] `GET /admin/tier-health` shows per-model health with latency
- [ ] `POST /admin/tier-toggle` disables/enables a model at runtime
- [ ] `GET /admin/llm-usage` returns 30-day cost and escalation rate
- [ ] Logging failures never block user requests
- [ ] All existing tests pass (observability is additive, not breaking)

---

## 9. Out of Scope

- Frontend dashboard widget for LLM usage → future UI work
- Alerting on escalation rate → future ops work
- Iceberg/analytics persistence → we use TimescaleDB (already set up)
- Compression event tracking → not needed for our architecture
