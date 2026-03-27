# KAN-190: Observability Completeness — Implementation Plan

**Spec:** `docs/superpowers/specs/2026-03-27-observability-completeness-design.md`
**JIRA:** KAN-190 (under Epic KAN-189)
**Branch:** `feat/KAN-190-observability-gaps`
**Estimated effort:** ~8h (8 stories, serial execution)

---

## Execution Order & Dependencies

```
S1 (migration + models)
  ↓
S2 (collector + writer interface)
  ↓
S3 (provider base class)  ←  core refactor, everything else depends on this
  ↓
S4 (Groq refactor)  }
S5 (Anthropic + OpenAI instrumentation)  }  can parallelize after S3
S6 (LLMClient cross-provider cascade)  }
  ↓
S7 (executor cache-hit + ContextVars + chat wiring + main.py)
  ↓
S8 (admin endpoint + fallback_rate + integration verification)
```

---

## S1: Migration 016 + Model Columns

**JIRA Subtask:** KAN-190-S1 — Add agent_type, agent_instance_id, loop_step to log tables
**Estimate:** 30min
**Depends on:** Nothing

### Files

| File | Action |
|------|--------|
| `backend/models/logs.py` | Add 3 columns to `LLMCallLog` + 3 columns to `ToolExecutionLog` |
| `alembic/versions/*_016_add_observability_columns.py` | Hand-written migration (NO autogenerate) |

### Changes — `backend/models/logs.py`

Add to `LLMCallLog`:
```python
agent_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
agent_instance_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
loop_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Add identical 3 columns to `ToolExecutionLog`.

### Changes — Migration 016

Hand-write only. Template:
```python
def upgrade():
    op.add_column("llm_call_log", sa.Column("agent_type", sa.String(20), nullable=True))
    op.add_column("llm_call_log", sa.Column("agent_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("llm_call_log", sa.Column("loop_step", sa.Integer, nullable=True))
    op.create_index("ix_llm_call_log_agent_type", "llm_call_log", ["agent_type"])

    op.add_column("tool_execution_log", sa.Column("agent_type", sa.String(20), nullable=True))
    op.add_column("tool_execution_log", sa.Column("agent_instance_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tool_execution_log", sa.Column("loop_step", sa.Integer, nullable=True))
    op.create_index("ix_tool_execution_log_agent_type", "tool_execution_log", ["agent_type"])

def downgrade():
    op.drop_index("ix_tool_execution_log_agent_type")
    op.drop_column("tool_execution_log", "loop_step")
    op.drop_column("tool_execution_log", "agent_instance_id")
    op.drop_column("tool_execution_log", "agent_type")
    op.drop_index("ix_llm_call_log_agent_type")
    op.drop_column("llm_call_log", "loop_step")
    op.drop_column("llm_call_log", "agent_instance_id")
    op.drop_column("llm_call_log", "agent_type")
```

### Verification

```bash
uv run alembic upgrade head
uv run alembic current  # should show 016
uv run pytest tests/unit/ -q --tb=short  # no regression
```

### Done criteria
- `alembic current` shows 016
- Both tables have 3 new nullable columns
- All existing tests pass

---

## S2: Collector + Writer Interface Extensions

**JIRA Subtask:** KAN-190-S2 — Extend ObservabilityCollector and writer to accept new fields
**Estimate:** 45min
**Depends on:** S1

### Files

| File | Action |
|------|--------|
| `backend/agents/observability.py` | Add `cost_usd` param to `record_request`; add `cache_hit` param to `record_tool_execution`; add `fallback_rate_last_60s()` method |
| `backend/agents/observability_writer.py` | Wire `cost_usd`, `cache_hit`, `agent_type`, `agent_instance_id`, `loop_step` into row construction; import + read ContextVars |
| `backend/request_context.py` | Add `current_agent_type`, `current_agent_instance_id` ContextVars |
| `tests/unit/agents/test_observability.py` | +4 tests for `fallback_rate_last_60s` |
| `tests/unit/agents/test_observability_writer.py` | +3 tests for new field wiring |

### Changes — `backend/agents/observability.py`

1. `record_request()` — add `cost_usd: float | None = None` param. Pass through to `_safe_db_write` data dict.
2. `record_tool_execution()` — add `cache_hit: bool = False` param. Pass through to data dict.
3. Add `fallback_rate_last_60s()` method (from spec §9 — pure computation on existing deques).

### Changes — `backend/agents/observability_writer.py`

1. Import `current_agent_type`, `current_agent_instance_id` from `request_context`.
2. In `write_event()`, read both ContextVars (with `.get(None)` default).
3. `LLMCallLog(...)` constructor: add `cost_usd=data.get("cost_usd")`, `agent_type=agent_type`, `agent_instance_id=agent_instance_id`.
4. `ToolExecutionLog(...)` constructor: add `cache_hit=data.get("cache_hit", False)`, `agent_type=agent_type`, `agent_instance_id=agent_instance_id`.

### Changes — `backend/request_context.py`

```python
current_agent_type: ContextVar[str | None] = ContextVar("current_agent_type", default=None)
current_agent_instance_id: ContextVar[str | None] = ContextVar("current_agent_instance_id", default=None)
```

### Tests

**test_observability.py** — 4 new:
1. `test_fallback_rate_empty` — no data → 0.0
2. `test_fallback_rate_all_success` — only successes → 0.0
3. `test_fallback_rate_mixed` — 3 failures, 7 successes → 0.3
4. `test_fallback_rate_prunes_old` — entries older than 60s excluded

**test_observability_writer.py** — 3 new:
1. `test_write_llm_call_with_cost_usd` — cost_usd present on row
2. `test_write_tool_execution_with_cache_hit` — cache_hit=True on row
3. `test_write_with_agent_type_from_contextvar` — agent_type populated from ContextVar

### Verification

```bash
uv run pytest tests/unit/agents/test_observability.py tests/unit/agents/test_observability_writer.py -v
```

### Done criteria
- `record_request` accepts `cost_usd`; `record_tool_execution` accepts `cache_hit`
- Writer populates all new fields on DB rows
- `fallback_rate_last_60s()` returns correct values
- 7 new tests passing

---

## S3: Provider Base Class Instrumentation

**JIRA Subtask:** KAN-190-S3 — Add _record_success, _record_cascade, _compute_cost to LLMProvider
**Estimate:** 45min
**Depends on:** S2

### Files

| File | Action |
|------|--------|
| `backend/agents/llm_client.py` | Add `collector`, `pricing` attrs + 3 methods to `LLMProvider` ABC |
| `backend/agents/model_config.py` | Add `get_pricing_map()` to `ModelConfigLoader` |

### Changes — `backend/agents/llm_client.py`

Add to `LLMProvider` class body (after `health` attribute):

```python
collector: ObservabilityCollector | None = None
pricing: dict[str, tuple[float, float]] | None = None

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
    """Record a successful LLM call with cost."""
    if not self.collector:
        return
    cost = self._compute_cost(model, prompt_tokens, completion_tokens)
    await self.collector.record_request(
        model=model, provider=self.name, tier=tier,
        latency_ms=latency_ms, prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens, cost_usd=cost,
    )

async def _record_cascade(self, from_model: str, reason: str, tier: str = "") -> None:
    """Record a cascade/failure event."""
    if not self.collector:
        return
    await self.collector.record_cascade(
        from_model=from_model, reason=reason, provider=self.name, tier=tier,
    )
```

Import `ObservabilityCollector` with `TYPE_CHECKING` guard to avoid circular imports.

### Changes — `backend/agents/model_config.py`

Add to `ModelConfigLoader`:
```python
def get_pricing_map(self) -> dict[str, tuple[float, float]]:
    """Return model_name → (cost_per_1k_input, cost_per_1k_output) for all cached models."""
    return {
        mc.model_name: (mc.cost_per_1k_input, mc.cost_per_1k_output)
        for tier_models in self._cache.values()
        for mc in tier_models
    }
```

### Verification

```bash
uv run pytest tests/unit/agents/ -v --tb=short  # no regression
```

### Done criteria
- `LLMProvider` has `collector`, `pricing`, `_compute_cost`, `_record_success`, `_record_cascade`
- `ModelConfigLoader.get_pricing_map()` returns correct dict
- No regressions (base class additions don't break subclasses)

---

## S4: Groq Provider Refactor

**JIRA Subtask:** KAN-190-S4 — Migrate GroqProvider from inline collector to base class methods
**Estimate:** 45min
**Depends on:** S3

### Files

| File | Action |
|------|--------|
| `backend/agents/providers/groq.py` | Remove `self._collector`; use `self.collector` from base class; replace inline calls |
| `tests/unit/agents/test_groq_observability.py` | Modify 3 existing tests for base class pattern |

### Changes — `backend/agents/providers/groq.py`

1. **Remove** `collector: ObservabilityCollector | None = None` from `__init__` params.
2. **Remove** `self._collector = collector` assignment.
3. **Remove** `from backend.agents.observability import ObservabilityCollector` import.
4. In `chat()` success path (line ~125-134): replace 8 lines with:
   ```python
   latency_ms = int((time.monotonic() - start) * 1000)
   await self._record_success(
       model=model_name, latency_ms=latency_ms,
       prompt_tokens=result.prompt_tokens,
       completion_tokens=result.completion_tokens,
   )
   ```
5. In `chat()` budget-skip path (line ~109-116): replace with:
   ```python
   await self._record_cascade(from_model=model_name, reason="over_budget")
   ```
6. In `chat()` error path (line ~145-150): replace with:
   ```python
   await self._record_cascade(from_model=model_name, reason=error_type)
   ```

### Tests — `test_groq_observability.py`

Modify existing 3 tests:
1. Set `provider.collector = mock_collector` instead of passing `collector=` to constructor
2. Assert `mock_collector.record_request.called` (same behavior, different injection)
3. Verify `_collector` private attr no longer exists (grep check)

### Verification

```bash
uv run pytest tests/unit/agents/test_groq_observability.py -v
uv run pytest tests/unit/agents/ -v --tb=short  # full agent test suite
```

### Done criteria
- `GroqProvider` has no `self._collector` — only `self.collector` from base class
- All 3 existing Groq observability tests pass with new pattern
- `grep -r '_collector' backend/agents/providers/groq.py` returns nothing

---

## S5: Anthropic + OpenAI Provider Instrumentation

**JIRA Subtask:** KAN-190-S5 — Add observability to Anthropic and OpenAI providers
**Estimate:** 45min
**Depends on:** S3

### Files

| File | Action |
|------|--------|
| `backend/agents/providers/anthropic.py` | Add timing + `self._record_success()` |
| `backend/agents/providers/openai.py` | Add timing + `self._record_success()` |

### Changes — `backend/agents/providers/anthropic.py`

1. Add `import time` at top.
2. In `chat()`, wrap the API call with timing:
   ```python
   start = time.monotonic()
   response = await client.messages.create(**kwargs)
   latency_ms = int((time.monotonic() - start) * 1000)
   ```
3. After building `LLMResponse`, before returning:
   ```python
   await self._record_success(
       model=self._model, latency_ms=latency_ms,
       prompt_tokens=response.usage.input_tokens,
       completion_tokens=response.usage.output_tokens,
   )
   ```

### Changes — `backend/agents/providers/openai.py`

Same pattern:
1. Add `import time`.
2. Wrap API call with timing.
3. Call `self._record_success()` before returning.

### No new test files

These providers are tested indirectly via `test_llm_client.py` (S6) which verifies cross-provider cascade recording. Direct provider tests would need API mocking — defer to integration testing.

### Verification

```bash
uv run pytest tests/unit/agents/ -v --tb=short
```

### Done criteria
- Both providers call `self._record_success()` on every successful API call
- No `collector` references remain in either file (only base class `self._record_success`)

---

## S6: LLMClient Cross-Provider Cascade Recording

**JIRA Subtask:** KAN-190-S6 — Record provider-level cascades in LLMClient.chat()
**Estimate:** 45min
**Depends on:** S3

### Files

| File | Action |
|------|--------|
| `backend/agents/llm_client.py` | Add `collector` param to `LLMClient.__init__`; record cascade in catch block |
| `tests/unit/agents/test_llm_client.py` | NEW file — +3 tests |

### Changes — `backend/agents/llm_client.py`

1. `LLMClient.__init__` — add `collector: ObservabilityCollector | None = None` param. Store as `self._collector`.
2. In `chat()` catch block (line ~186-198), after `errors.append(...)`:
   ```python
   if self._collector:
       await self._collector.record_cascade(
           from_model=provider.name,
           reason=type(e).__name__,
           provider=provider.name,
           tier=tier or "",
       )
   ```

### Tests — `tests/unit/agents/test_llm_client.py` (NEW)

1. `test_cross_provider_cascade_recorded` — provider A fails, provider B succeeds → collector.record_cascade called once with provider A's name
2. `test_no_collector_no_error` — `collector=None` → no exception on cascade
3. `test_tier_passed_through_to_cascade` — tier="synthesizer" → cascade recorded with that tier

Use mock providers (`AsyncMock` for `chat()` — first raises, second returns `LLMResponse`).

### Verification

```bash
uv run pytest tests/unit/agents/test_llm_client.py -v
```

### Done criteria
- `LLMClient` records cross-provider cascades to collector
- 3 new tests passing
- `fallback_rate_last_60s()` now includes cross-provider failures

---

## S7: Executor Cache-Hit + ContextVars + Chat Wiring + main.py

**JIRA Subtask:** KAN-190-S7 — Wire cache_hit logging, ContextVars in chat router, pricing injection in main.py
**Estimate:** 1h
**Depends on:** S4, S5, S6

### Files

| File | Action |
|------|--------|
| `backend/agents/executor.py` | Log cache hits; pass `cache_hit=False` on normal path |
| `backend/routers/chat.py` | Set `current_agent_type` + `current_agent_instance_id` ContextVars |
| `backend/main.py` | Loop providers to set `.collector` + `.pricing`; pass `collector` to `LLMClient`; remove `collector=` from GroqProvider constructor |
| `tests/unit/agents/test_executor_observability.py` | +2 tests |

### Changes — `backend/agents/executor.py`

1. In cache-hit branch (line ~209-218), before `continue`:
   ```python
   if collector:
       await collector.record_tool_execution(
           tool_name=tool_name, latency_ms=0, status="success",
           result_size_bytes=len(cached), cache_hit=True,
       )
   ```
2. In existing `collector.record_tool_execution()` call (line ~249-256), add `cache_hit=False`.

### Changes — `backend/routers/chat.py`

In the streaming function, after setting `current_session_id` and `current_query_id`:
```python
from backend.request_context import current_agent_type, current_agent_instance_id
import uuid as uuid_mod

agent_type_token = current_agent_type.set(session.agent_type)
instance_id = str(uuid_mod.uuid4())
agent_instance_token = current_agent_instance_id.set(instance_id)
```

In the `finally` block:
```python
current_agent_type.reset(agent_type_token)
current_agent_instance_id.reset(agent_instance_token)
```

### Changes — `backend/main.py`

Replace current pattern:
```python
# BEFORE (line 137-146):
providers.append(GroqProvider(api_key=..., collector=collector))
providers.append(AnthropicProvider(api_key=...))
llm_client = LLMClient(providers=providers)

# AFTER:
providers.append(GroqProvider(api_key=..., token_budget=token_budget))  # no collector
providers.append(AnthropicProvider(api_key=...))

# Inject observability onto all providers
pricing = config_loader.get_pricing_map()
for provider in providers:
    provider.collector = collector
    provider.pricing = pricing

llm_client = LLMClient(providers=providers, collector=collector)
```

### Tests — `test_executor_observability.py`

1. `test_cache_hit_logged` — mock cache returns data → `collector.record_tool_execution` called with `cache_hit=True`, `latency_ms=0`
2. `test_cache_miss_logged_with_cache_hit_false` — normal execution → `cache_hit=False` in collector call

### Verification

```bash
uv run pytest tests/unit/agents/test_executor_observability.py -v
uv run pytest tests/unit/ -q --tb=short  # full suite
```

### Done criteria
- Cache hits produce `ToolExecutionLog` rows with `cache_hit=True`
- Normal tool calls have `cache_hit=False`
- Chat streaming sets agent ContextVars
- All providers get `collector` + `pricing` from main.py loop
- `LLMClient` has collector for cross-provider cascade recording

---

## S8: Admin Endpoint + Fallback Rate + Final Verification

**JIRA Subtask:** KAN-190-S8 — Per-query cost endpoint, fallback_rate in metrics, end-to-end verify
**Estimate:** 1h
**Depends on:** S7

### Files

| File | Action |
|------|--------|
| `backend/routers/admin.py` | New `GET /admin/observability/query/{query_id}/cost` endpoint; add `fallback_rate_60s` to existing llm-metrics |
| `tests/api/test_admin_observability.py` | +4 tests |

### Changes — `backend/routers/admin.py`

1. **Existing `get_llm_metrics`** — add `"fallback_rate_60s": collector.fallback_rate_last_60s()` to response dict.

2. **New endpoint:**
   ```python
   @router.get("/admin/observability/query/{query_id}/cost")
   async def get_query_cost(
       query_id: uuid.UUID,
       user: User = Depends(get_current_user),
       db: AsyncSession = Depends(get_async_session),
   ):
       _require_admin(user)
       # Query llm_call_log
       llm_result = await db.execute(
           select(LLMCallLog).where(LLMCallLog.query_id == query_id)
       )
       llm_rows = llm_result.scalars().all()

       # Query tool_execution_log
       tool_result = await db.execute(
           select(ToolExecutionLog).where(ToolExecutionLog.query_id == query_id)
       )
       tool_rows = tool_result.scalars().all()

       if not llm_rows and not tool_rows:
           raise HTTPException(status_code=404, detail="No data for query")

       # Build response (per spec §10)
       ...
   ```

### Tests — `test_admin_observability.py`

1. `test_query_cost_401_unauthenticated` — no token → 401
2. `test_query_cost_403_non_admin` — regular user → 403
3. `test_query_cost_404_unknown_query` — random UUID → 404
4. `test_query_cost_200` — seed LLMCallLog + ToolExecutionLog rows → returns breakdown

### Verification — Full Suite

```bash
uv run ruff check --fix backend/ tests/
uv run ruff format backend/ tests/
uv run pytest tests/unit/ -q --tb=short
uv run pytest tests/api/ -q --tb=short
```

### Done criteria
- `GET /admin/observability/llm-metrics` includes `fallback_rate_60s`
- `GET /admin/observability/query/{query_id}/cost` returns per-model + per-tool breakdown
- 4 new API tests passing
- Full test suite green
- `ruff` clean

---

## Summary

| Story | Description | Files | New Tests | Est |
|-------|-------------|-------|-----------|-----|
| S1 | Migration 016 + model columns | 2 | 0 | 30m |
| S2 | Collector + writer interface + ContextVars | 4 | 7 | 45m |
| S3 | Provider base class instrumentation | 2 | 0 | 45m |
| S4 | Groq provider refactor | 2 | 0 (modify 3) | 45m |
| S5 | Anthropic + OpenAI instrumentation | 2 | 0 | 45m |
| S6 | LLMClient cross-provider cascade | 2 | 3 | 45m |
| S7 | Executor + ContextVars + chat + main.py | 4 | 2 | 1h |
| S8 | Admin endpoint + fallback_rate + verify | 2 | 4 | 1h |
| **Total** | | **20 files** | **~19 tests** | **~7h** |

### Parallelization Opportunities

After S3 completes, S4/S5/S6 are independent and can run as parallel subagents in worktrees. S7 merges the results. S8 is the final integration + verification.

```
S1 → S2 → S3 → ┬─ S4 (Groq refactor)
                ├─ S5 (Anthropic + OpenAI)
                └─ S6 (LLMClient cascade)
                   ↓
                  S7 (wiring)
                   ↓
                  S8 (admin + verify)
```
