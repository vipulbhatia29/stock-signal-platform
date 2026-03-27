# KAN-190: Observability Completeness — Design Spec

**JIRA:** KAN-190 (under Epic KAN-189)
**Phase:** 8A
**Estimated effort:** ~8h (8 stories)
**Branch:** `feat/KAN-190-observability-gaps`

---

## 1. Problem Statement

The observability subsystem (Phase 6B) established the infrastructure — `LLMCallLog`, `ToolExecutionLog`, `ObservabilityCollector`, admin endpoints — but five critical data gaps remain:

| Gap | Impact |
|-----|--------|
| `cost_usd` never populated on `LLMCallLog` | Cannot track per-query or aggregate LLM spend |
| `cache_hit` always `False` on `ToolExecutionLog` | Cache hit rate analytics are meaningless |
| No `agent_type` on log tables | Cannot attribute costs or latency to agent types |
| `fallback_rate` not computable | Cannot detect provider degradation in real-time |
| No per-query cost endpoint | Cannot answer "what did this query cost?" |

Additionally, three **structural blind spots** exist:

1. **Anthropic provider** has zero collector instrumentation — escalation calls are invisible
2. **OpenAI provider** has zero collector instrumentation — same blind spot
3. **Groq provider** has inline instrumentation (`self._collector`) that won't extend to new providers — adding a provider means remembering to copy-paste 13 lines of boilerplate
4. **Cross-provider cascades** (Groq fails → Anthropic handles) are never recorded — `LLMClient.chat()` catch block logs a warning but never calls `collector.record_cascade()`

These gaps are prerequisites for Phase 8B (ReAct loop) and Phase 8D (dynamic concurrency controller).

---

## 2. Goals

1. Every LLM call (Groq, Anthropic, OpenAI) produces an `LLMCallLog` row with `cost_usd`
2. Every tool execution (cached or not) produces a `ToolExecutionLog` row with `cache_hit`
3. Both log tables carry `agent_type` for attribution
4. Cross-provider cascades recorded (not just intra-Groq model cascades)
5. `ObservabilityCollector` exposes `fallback_rate_last_60s()` for real-time health
6. Admin API supports per-query cost breakdown
7. Adding a new LLM provider automatically gets observability — zero boilerplate

---

## 3. Non-Goals

- Frontend cost dashboard (Phase 9)
- Historical backfill of `cost_usd` on existing rows
- Langfuse integration (KAN-162, separate ticket)
- Alerting on cost thresholds
- OpenAI wiring in `main.py` (provider is instrumented but not constructed — separate config story)

---

## 4. ReAct-Awareness: What Survives Phase 8B

Phase 8B (KAN-189 Step 1) replaces Plan→Execute→Synthesize with a ReAct reason⇄act loop. This spec is designed so **90% of the work is permanent infrastructure** that ReAct consumes, not replaces.

| Component | Survives ReAct? | Notes |
|-----------|----------------|-------|
| `LLMProvider` base class + all providers | **YES** | ReAct still calls providers |
| `ObservabilityCollector` + `fallback_rate` | **YES** | ReAct's concurrency controller depends on this |
| `LLMCallLog` / `ToolExecutionLog` + migration | **YES** | Schema is permanent |
| ContextVars (`agent_type`, etc.) | **YES** | Execution-path-agnostic |
| `LLMClient` cross-provider cascade recording | **YES** | LLMClient survives ReAct |
| Admin endpoints + per-query cost | **YES** | Pure read layer |
| **`executor.py` cache-hit instrumentation** | **NO (~5 lines)** | Executor replaced by ReAct act node |

**Design principle:** Keep executor instrumentation minimal. Don't create abstractions — the ~5 lines of cache-hit logging will be re-done in 8B's act node.

### Forward-compatible columns in migration 016

To avoid a second migration when 8B/9A land, migration 016 also adds:
- `loop_step: Integer, nullable=True` — populated by ReAct in 8B (unused until then)
- `agent_instance_id: UUID, nullable=True` — populated by multi-agent fan-out in 9A (unused until then)

Zero cost now, saves a migration later.

---

## 5. Architecture: Provider Base Class Observability

### Current State (instrumentation copy-pasted per provider)

```
LLMClient.chat()                              [no cascade recording in catch block]
  → GroqProvider.chat()                       [self._collector — 13 lines inline]
  → AnthropicProvider.chat()                  [zero instrumentation]
  → OpenAIProvider.chat()                     [zero instrumentation]
```

### Target State (instrumentation on base class + LLMClient)

```
LLMClient.chat()                              [records cross-provider cascades]
  → provider.chat()                           [calls self._record_success / self._record_cascade]
    → LLMProvider._record_success()           [base class: cost calc + collector call]
    → LLMProvider._record_cascade()           [base class: collector call]
    → LLMProvider._compute_cost()             [base class: pricing lookup]
```

### Two instrumentation layers

| Layer | What it records | Where |
|-------|----------------|-------|
| **Intra-provider** (model cascade) | Groq: llama-70b → llama-8b → gemma failures + success | Inside `GroqProvider.chat()` via `self._record_success/cascade()` |
| **Cross-provider** (provider cascade) | Groq fails entirely → Anthropic takes over | Inside `LLMClient.chat()` catch block via `collector.record_cascade()` |

Without the cross-provider layer, `fallback_rate_last_60s()` only sees Groq intra-model failures — Anthropic escalations are invisible.

### Provider Instrumentation Methods (on `LLMProvider`)

```python
class LLMProvider(ABC):
    collector: ObservabilityCollector | None = None
    pricing: dict[str, tuple[float, float]] | None = None  # model → (cost_per_1k_input, cost_per_1k_output)

    def _compute_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
        """Compute cost in USD from token counts and pricing config."""
        if not self.pricing or model not in self.pricing:
            return None
        cost_input, cost_output = self.pricing[model]
        return (prompt_tokens / 1000) * cost_input + (completion_tokens / 1000) * cost_output

    async def _record_success(
        self, model: str, latency_ms: int,
        prompt_tokens: int, completion_tokens: int,
        tier: str = "",
    ) -> None:
        """Record a successful LLM call with cost. Called by subclass after API response."""
        if not self.collector:
            return
        cost = self._compute_cost(model, prompt_tokens, completion_tokens)
        await self.collector.record_request(
            model=model, provider=self.name, tier=tier,
            latency_ms=latency_ms, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, cost_usd=cost,
        )

    async def _record_cascade(self, from_model: str, reason: str, tier: str = "") -> None:
        """Record a cascade/failure event. Called by subclass on error or budget skip."""
        if not self.collector:
            return
        await self.collector.record_cascade(
            from_model=from_model, reason=reason, provider=self.name, tier=tier,
        )
```

**Key refactor:** `GroqProvider` currently stores collector as `self._collector` (private). This is **removed** — Groq uses `self.collector` from the base class. All 13 lines of inline collector calls in `GroqProvider.chat()` are replaced with `await self._record_success(...)` / `await self._record_cascade(...)`.

### `tier` passthrough

Currently `tier=""` is hardcoded on all Groq collector calls — the provider doesn't know which tier called it. Fix: `_record_success` and `_record_cascade` accept an optional `tier` param. `LLMClient.chat()` passes tier info to the provider by setting `provider._current_tier = tier` before calling `provider.chat()`, or the provider methods accept `tier` as a param.

**Note:** Tier semantics will evolve in ReAct (no separate planner/synthesizer tiers). The param is still useful for categorizing LLM call purpose.

### LLMClient Cross-Provider Cascade Recording

```python
# LLMClient.chat() — in the catch block (line ~186)
except Exception as e:
    provider.health.consecutive_failures += 1
    provider.health.last_failure = datetime.now(timezone.utc)
    errors.append((provider.name, e))
    # NEW: record cross-provider cascade
    if self._collector:
        await self._collector.record_cascade(
            from_model=provider.name,  # provider-level, not model-level
            reason=str(type(e).__name__),
            provider=provider.name,
            tier=tier or "",
        )
```

`LLMClient` needs a `_collector` reference. Injected in `main.py` at construction: `LLMClient(providers=providers, collector=collector)`.

### Pricing Injection (main.py)

```python
# After building tier_configs and providers:
pricing = {
    mc.model_name: (mc.cost_per_1k_input, mc.cost_per_1k_output)
    for tier_models in tier_configs.values()
    for mc in tier_models
}
for provider in providers:
    provider.collector = collector
    provider.pricing = pricing
```

This replaces the current pattern of passing `collector=collector` only to `GroqProvider.__init__`.

---

## 6. Schema Changes

### 6.1 New Columns (Migration 016)

Both `llm_call_log` and `tool_execution_log` get:

```sql
-- Agent attribution
ALTER TABLE llm_call_log ADD COLUMN agent_type VARCHAR(20);
ALTER TABLE llm_call_log ADD COLUMN agent_instance_id UUID;
CREATE INDEX ix_llm_call_log_agent_type ON llm_call_log (agent_type);

ALTER TABLE tool_execution_log ADD COLUMN agent_type VARCHAR(20);
ALTER TABLE tool_execution_log ADD COLUMN agent_instance_id UUID;
CREATE INDEX ix_tool_execution_log_agent_type ON tool_execution_log (agent_type);

-- Forward-compatible: ReAct loop step (Phase 8B)
ALTER TABLE llm_call_log ADD COLUMN loop_step INTEGER;
ALTER TABLE tool_execution_log ADD COLUMN loop_step INTEGER;
```

All columns nullable (no default needed). **Hand-written migration** — do NOT use autogenerate (TimescaleDB hypertable gotcha: autogenerate falsely drops hypertable indexes).

### 6.2 Existing Columns (no migration needed)

- `llm_call_log.cost_usd` — already `Numeric(10,6), nullable=True`. Just needs population.
- `tool_execution_log.cache_hit` — already `Boolean, default=False`. Just needs population.

---

## 7. ContextVar Propagation for agent_type

### Flow

```
POST /chat/stream (chat.py)
  → reads body.agent_type (or ChatSession.agent_type)
  → sets current_agent_type ContextVar
  → graph executes (planner → executor → synthesizer)
    → GroqProvider._record_success() fires
      → collector.record_request() — writer reads current_agent_type from ContextVar
    → executor records tool calls
      → collector.record_tool_execution() — writer reads current_agent_type from ContextVar
```

### New ContextVars

```python
# backend/request_context.py
current_agent_type: ContextVar[str | None] = ContextVar("current_agent_type", default=None)
current_agent_instance_id: ContextVar[str | None] = ContextVar("current_agent_instance_id", default=None)
```

Set in `chat.py` before streaming begins. Reset in `finally` block (same pattern as existing `current_session_id` / `current_query_id`).

**Non-chat callers** (Celery, MCP direct): ContextVars default to `None` — nullable columns handle this gracefully.

---

## 8. Cache Hit Logging

### Current Behavior (executor.py, line ~209)

```python
cached = await cache.get(cache_key)
if cached:
    cached_data = json.loads(cached)
    results.append(cached_data)
    tool_calls += 1
    if on_step: ...
    continue  # SKIPS collector.record_tool_execution() entirely
```

### Target Behavior

```python
cached = await cache.get(cache_key)
if cached:
    cached_data = json.loads(cached)
    results.append(cached_data)
    tool_calls += 1
    # NEW: record cache hit
    if collector:
        await collector.record_tool_execution(
            tool_name=tool_name, latency_ms=0, status="success",
            result_size_bytes=len(cached), cache_hit=True,
        )
    if on_step: ...
    continue
```

Non-cached path adds `cache_hit=False` explicitly to the existing `collector.record_tool_execution()` call.

**ReAct note:** This executor code is ~5 lines and will be re-done in Phase 8B's act node. Acceptable — not worth abstracting.

---

## 9. fallback_rate_last_60s()

### Implementation

Uses existing `_failures_windows` and `_successes_windows` deques on `ObservabilityCollector`. These are already maintained and pruned to a 60-second window.

```python
def fallback_rate_last_60s(self) -> float:
    """Fraction of LLM calls that resulted in cascade/failure in the last 60s.

    Includes both intra-provider cascades (Groq model→model) and
    cross-provider cascades (Groq→Anthropic) after LLMClient integration.
    """
    now = time.monotonic()
    total_failures = 0
    total_successes = 0
    for window in self._failures_windows.values():
        self._prune_window(window, now, _RPM_WINDOW_S)
        total_failures += len(window)
    for window in self._successes_windows.values():
        self._prune_window(window, now, _RPM_WINDOW_S)
        total_successes += len(window)
    total = total_failures + total_successes
    if total == 0:
        return 0.0
    return total_failures / total
```

Exposed via existing `GET /admin/observability/llm-metrics` (add `fallback_rate_60s` field to response dict).

---

## 10. Per-Query Cost Endpoint

### `GET /admin/observability/query/{query_id}/cost`

**Auth:** admin-only (same as all `/admin/*` endpoints).

**Response schema:**

```json
{
  "query_id": "uuid",
  "total_cost_usd": 0.0023,
  "total_prompt_tokens": 1200,
  "total_completion_tokens": 647,
  "llm_calls": [
    {
      "model": "llama-3.3-70b-versatile",
      "provider": "groq",
      "prompt_tokens": 1200,
      "completion_tokens": 500,
      "cost_usd": 0.0008,
      "latency_ms": 342,
      "agent_type": "stock"
    }
  ],
  "tool_calls": {
    "total": 4,
    "cache_hits": 1,
    "cache_hit_rate": 0.25,
    "total_latency_ms": 890,
    "by_tool": [
      {"tool_name": "get_stock_signals", "count": 2, "cache_hits": 1}
    ]
  }
}
```

**Query:** Two SQL queries — one on `llm_call_log`, one on `tool_execution_log`, both filtered by `query_id`. Returns 404 if no rows found.

---

## 11. File Change Map

### Source Files (13)

| File | Change | Lines ~est |
|------|--------|------------|
| `backend/agents/llm_client.py` | Add `collector`, `pricing`, `_compute_cost`, `_record_success`, `_record_cascade` to `LLMProvider` base class; add `_collector` to `LLMClient` for cross-provider cascades | +40 |
| `backend/agents/providers/groq.py` | Remove `self._collector` private attr; replace 13 lines of inline collector calls with `self._record_success()` / `self._record_cascade()` from base class | -15, +6 |
| `backend/agents/providers/anthropic.py` | Add `self._record_success()` after API call with timing | +10 |
| `backend/agents/providers/openai.py` | Add `self._record_success()` after API call with timing | +10 |
| `backend/agents/observability.py` | Add `cost_usd` param to `record_request`; `cache_hit` param to `record_tool_execution`; pass-through for `agent_type`/`agent_instance_id`/`loop_step` (read from ContextVars in writer); `fallback_rate_last_60s()` method | +25 |
| `backend/agents/observability_writer.py` | Wire `cost_usd`, `cache_hit`, `agent_type`, `agent_instance_id`, `loop_step` into model row construction; read agent ContextVars | +12 |
| `backend/agents/executor.py` | Log cache hits as rows (~5 lines); pass `cache_hit=False` on normal path | +8 |
| `backend/models/logs.py` | Add `agent_type`, `agent_instance_id`, `loop_step` columns to both models | +12 |
| `backend/request_context.py` | Add `current_agent_type`, `current_agent_instance_id` ContextVars | +4 |
| `backend/routers/chat.py` | Set agent ContextVars before streaming, reset in finally | +8 |
| `backend/routers/admin.py` | New `/admin/observability/query/{query_id}/cost` endpoint; add `fallback_rate_60s` to llm-metrics | +50 |
| `backend/main.py` | Loop providers to set `.collector` + `.pricing`; pass `collector` to `LLMClient`; remove `collector=collector` from GroqProvider constructor | +10, -2 |
| `backend/agents/model_config.py` | Add `get_pricing_map()` convenience method on `ModelConfigLoader` | +8 |

### Migration (1)

| File | Change |
|------|--------|
| `alembic/versions/*_016_add_observability_columns.py` | Hand-written: `agent_type`, `agent_instance_id`, `loop_step` on both tables + 2 indexes |

### Test Files (6)

| File | New/Modified Tests |
|------|-------------------|
| `tests/unit/agents/test_observability.py` | +4: `fallback_rate_last_60s` (empty, all success, mixed, pruning) |
| `tests/unit/agents/test_observability_writer.py` | +3: `cost_usd` wired, `cache_hit` wired, `agent_type` wired |
| `tests/unit/agents/test_groq_observability.py` | Modify 3: assert base class `_record_success`/`_record_cascade` calls instead of inline collector |
| `tests/unit/agents/test_executor_observability.py` | +2: cache hit logged with `cache_hit=True`, normal path logged with `cache_hit=False` |
| `tests/unit/agents/test_llm_client.py` | +3: cross-provider cascade records to collector; no collector = no error; tier passed through |
| `tests/api/test_admin_observability.py` | +4: query cost 200/401/403/404 |

**Estimated new tests: ~19**

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| TimescaleDB migration gotcha (autogenerate drops indexes) | Hand-write migration, no autogenerate |
| Groq provider refactor breaks existing cascade | Existing test_groq_observability.py validates; run before/after |
| `cost_usd = None` if model not in pricing map | Acceptable — nullable column, log a warning. Groq models always in DB; Anthropic/OpenAI may not be yet |
| ContextVar not set for non-chat callers (Celery, MCP) | Default to None — nullable columns handle this |
| Cache-hit rows increase ToolExecutionLog volume | Minimal — cache hits are fast, rows are small, hypertable handles scale |
| `self._collector` → `self.collector` name change in GroqProvider | Tests validate; grep for `_collector` post-refactor to ensure no stale references |
| executor.py changes are temporary (ReAct replaces executor) | Kept to ~5 lines — acceptable throwaway cost |

---

## 13. Dependencies

- **Prerequisite:** None — all work is independent of feature backlog
- **Blocks:** Phase 8B (ReAct loop needs `agent_type` + `loop_step` columns), Phase 8D (concurrency controller needs `fallback_rate`)
- **Housekeeping:** KAN-187 and KAN-188 are duplicates (both "intent-based tool filtering") — close one

---

## 14. Success Criteria

1. `cost_usd` populated on every LLM call row (Groq + Anthropic; OpenAI when wired)
2. Cross-provider cascades (Groq→Anthropic) visible in `llm_call_log`
3. `cache_hit=True` rows visible in `tool_execution_log` after cached tool calls
4. `agent_type` populated on all log rows during chat sessions
5. `fallback_rate_last_60s()` returns correct value including cross-provider cascades
6. `GET /admin/observability/query/{query_id}/cost` returns per-model + per-tool breakdown
7. All existing observability tests still pass (no regression)
8. ~19 new tests passing
9. Adding a new provider requires only `self._record_success()` call — zero other boilerplate
10. Migration 016 includes forward-compatible `loop_step` + `agent_instance_id` for Phase 8B/9A
