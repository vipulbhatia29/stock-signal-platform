# Obs 1a PR5 — Strangler-Fig Refactor of Existing Emitters

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Route the 4 existing direct-DB-write emitters (`ObservabilityCollector.record_request`, `ObservabilityCollector.record_tool_execution`, `_write_login_attempt`, `dq_scan` direct insert) through the SDK. Emit companion `PIPELINE_LIFECYCLE` events for every `@tracked_task` state transition (keeping the existing UPDATE semantics intact — see Risks). Dual-write is controlled by `OBS_LEGACY_DIRECT_WRITES` (default `true` at merge, flipped to `false` after 2 weeks of green production per the strangler-fig pattern in spec §2.7).

**Architecture:** Each refactored emitter gains a pair of calls: the legacy direct-DB write runs only when `OBS_LEGACY_DIRECT_WRITES=true`; an `obs_client.emit(event)` runs unconditionally (no-op when `OBS_ENABLED=false`). Contract tests assert that DB state is equivalent on both paths — the legacy row and the SDK-derived row (written by PR4's `event_writer`) contain the same values for the fields they both capture.

**Tech Stack:** Python feature flag via `settings.OBS_LEGACY_DIRECT_WRITES`; existing pytest fixtures for DB state assertions; SDK from PR2a; event writers from PR4.

**Spec reference:** `docs/superpowers/specs/2026-04-16-obs-1a-foundations-design.md` §2.7.

**Prerequisites:** PR1 (schema), PR2a (SDK), PR3 (trace_id for event envelopes), PR4 (event writers for each EventType).

**Dependency for:** Future 1b Coverage work assumes all emissions flow through SDK; PR5 is the last 1a PR before we flip the switch.

**Fact-sheet anchors:** §5 enumerates all 4 strangler-fig targets with file:line. §5.5 shows `@tracked_task` at `backend/tasks/pipeline.py:412-521` — the UPDATE lifecycle at `start_run/complete_run` (lines 485, 516) must stay intact. §6 lists 11 test files asserting on existing emission behavior — they must all stay green. §7: existing emitters live in `backend/observability/collector.py` (280 lines) and `backend/observability/writer.py` (82 lines); `_write_login_attempt` is in `backend/routers/auth/_helpers.py:129-151`; `dq_scan` direct insert at `backend/tasks/dq_scan.py:52-59`.

---

## File Structure

**Create:**
- `backend/observability/service/legacy_emitters_writer.py` — real `event_writer.write_batch` branch for `LLM_CALL`, `TOOL_EXECUTION`, `LOGIN_ATTEMPT`, `DQ_FINDING`, `PIPELINE_LIFECYCLE`
- `backend/observability/schema/legacy_events.py` — event subclasses for each legacy emitter (Pydantic models)
- `tests/unit/observability/test_strangler_fig_contract.py` — per-emitter contract tests (legacy path produces same DB state as SDK path)

**Modify:**
- `backend/config.py` — add `OBS_LEGACY_DIRECT_WRITES: bool = Field(True, ...)`
- `backend/observability/collector.py` — `record_request` + `record_tool_execution` guard legacy path behind flag; emit through SDK
- `backend/routers/auth/_helpers.py` — `_write_login_attempt` guard legacy path; emit through SDK
- `backend/tasks/dq_scan.py` — dual-write for `DqCheckHistory` rows
- `backend/tasks/pipeline.py` — `@tracked_task` emits `PIPELINE_LIFECYCLE` event alongside existing UPDATE calls (keep UPDATE regardless of flag — state rows, not events)
- `backend/observability/service/event_writer.py` — route the 5 legacy event types to `legacy_emitters_writer`

**NOT modified** (by design):
- The 11 existing test files listed in fact sheet §6 — they still pass because legacy direct writes remain active
- `backend/observability/writer.py` — kept as-is; delete is a separate cleanup PR after the flag is flipped off

---

## Task 1: Config flag

**Files:** `backend/config.py`

- [ ] **Step 1:** Add to `Settings`:

```python
    OBS_LEGACY_DIRECT_WRITES: bool = Field(
        True,
        description="Strangler-fig flag — when True, legacy direct-DB writes run alongside "
                    "SDK emissions. Flip to False after 2 weeks of green production. See spec §2.7.",
    )
```

- [ ] **Step 2:** Commit: `feat(obs-1a): add OBS_LEGACY_DIRECT_WRITES strangler-fig flag`.

---

## Task 2: Event subclasses for legacy emitters

**Files:** `backend/observability/schema/legacy_events.py`, update `backend/observability/schema/__init__.py`

- [ ] **Step 1: Failing test** — roundtrip each subclass through JSON; assert required fields present:

```python
# tests/unit/observability/test_legacy_events.py
from backend.observability.schema.legacy_events import (
    LLMCallEvent, ToolExecutionEvent, LoginAttemptEvent,
    DqFindingEvent, PipelineLifecycleEvent,
)
# Construct minimal valid instances for each; assert model_dump_json() round-trips.
```

- [ ] **Step 2: Implement** — each subclass inherits `ObsEventBase` (PR1). Payload fields mirror the columns fact sheet §5 shows for each direct-write target:

```python
# backend/observability/schema/legacy_events.py
from __future__ import annotations
from typing import Literal
from uuid import UUID
from backend.observability.schema.v1 import EventType, ObsEventBase


class LLMCallEvent(ObsEventBase):
    event_type: Literal[EventType.LLM_CALL] = EventType.LLM_CALL
    model: str
    provider: str
    tier: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float | None = None
    loop_step: int | None = None
    status: str = "completed"
    langfuse_trace_id: UUID | str | None = None


class ToolExecutionEvent(ObsEventBase):
    event_type: Literal[EventType.TOOL_EXECUTION] = EventType.TOOL_EXECUTION
    tool_name: str
    latency_ms: int
    status: str
    result_size_bytes: int | None = None
    error: str | None = None  # safe message only — NO str(exc)
    cache_hit: bool = False
    loop_step: int | None = None


class LoginAttemptEvent(ObsEventBase):
    event_type: Literal[EventType.LOGIN_ATTEMPT] = EventType.LOGIN_ATTEMPT
    email: str
    success: bool
    ip_address: str
    user_agent: str
    failure_reason: str | None = None
    method: Literal["password", "oauth_google", "oauth_other"] = "password"


class DqFindingEvent(ObsEventBase):
    event_type: Literal[EventType.DQ_FINDING] = EventType.DQ_FINDING
    check_name: str
    severity: Literal["info", "warning", "error", "critical"]
    ticker: str | None = None
    message: str
    metadata: dict | None = None


class PipelineLifecycleEvent(ObsEventBase):
    event_type: Literal[EventType.PIPELINE_LIFECYCLE] = EventType.PIPELINE_LIFECYCLE
    pipeline_name: str
    transition: Literal["started", "succeeded", "failed", "no_op", "partial"]
    run_id: UUID
    trigger: str
    celery_task_id: str | None = None
    duration_s: float | None = None
    tickers_total: int | None = None
    tickers_succeeded: int | None = None
    tickers_failed: int | None = None
```

- [ ] **Step 3:** `uv run pytest tests/unit/observability/test_legacy_events.py -v` → all green.
- [ ] **Step 4:** Commit: `feat(obs-1a): add Pydantic event subclasses for legacy emitters`.

---

## Task 3: Route `record_request` through SDK

**Files:** `backend/observability/collector.py`, extend `tests/unit/observability/test_strangler_fig_contract.py`

- [ ] **Step 1: Contract test**

```python
# tests/unit/observability/test_strangler_fig_contract.py
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_record_request_legacy_and_sdk_produce_equivalent_rows(
    db_session, app_obs_client, monkeypatch,
):
    """Dual-write mode: legacy LLMCallLog row AND SDK-emitted event exist after record_request."""
    monkeypatch.setattr("backend.config.settings.OBS_LEGACY_DIRECT_WRITES", True)

    from backend.observability.collector import ObservabilityCollector
    collector = app_obs_client.state.collector  # set by lifespan
    await collector.record_request(
        model="gpt-4o", provider="openai", tier="primary",
        latency_ms=123, prompt_tokens=50, completion_tokens=10, cost_usd=0.001,
    )
    await app_obs_client.flush()

    # Legacy row — exactly one new llm_call_log row (legacy path wrote it; SDK writer
    # no-ops per Task 8 dedup invariant).
    row_count = (await db_session.execute(text(
        "SELECT COUNT(*) FROM llm_call_log WHERE model='gpt-4o' AND latency_ms=123"
    ))).scalar()
    assert row_count == 1  # exactly one — no duplicates from dual-write
    # SDK target (MemoryTarget in test harness) captured the event envelope.
    target = app_obs_client.state.obs_client._target  # MemoryTarget injected by test fixture
    llm_events = [e for e in target.events if e.event_type.value == "llm_call"]
    assert len(llm_events) == 1
    assert llm_events[0].model == "gpt-4o"
    assert llm_events[0].latency_ms == 123


@pytest.mark.asyncio
async def test_record_request_sdk_only_when_flag_off(db_session, app_obs_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.OBS_LEGACY_DIRECT_WRITES", False)
    from backend.observability.collector import ObservabilityCollector
    collector = app_obs_client.state.collector
    initial_count = (await db_session.execute(text("SELECT COUNT(*) FROM llm_call_log"))).scalar()
    await collector.record_request(
        model="gpt-4o", provider="openai", tier="primary",
        latency_ms=100, prompt_tokens=5, completion_tokens=5,
    )
    await app_obs_client.flush()
    # No new legacy row.
    new_count = (await db_session.execute(text("SELECT COUNT(*) FROM llm_call_log"))).scalar()
    assert new_count == initial_count
```

- [ ] **Step 2: Modify `ObservabilityCollector.record_request`** — fact sheet §5.1 shows current body at lines 52-83 emits via `self._db_writer` → `writer.write_event("llm_call", {...})`. Wrap behind flag + capture flag state at emit time (dedup-race fix):

```python
# collector.py — modify record_request
from datetime import datetime, timezone
from uuid import UUID
from uuid_utils import uuid7
from backend.config import settings
from backend.observability.bootstrap import _maybe_get_obs_client  # defined in PR2a
from backend.observability.context import current_trace_id, current_span_id
from backend.observability.schema.legacy_events import LLMCallEvent
from backend.observability.schema.v1 import EventType

async def record_request(
    self, model, provider, tier, latency_ms, prompt_tokens, completion_tokens,
    cost_usd=None, loop_step=None, status="completed", langfuse_trace_id=None,
) -> None:
    wrote_via_legacy = settings.OBS_LEGACY_DIRECT_WRITES  # snapshot NOW, not at write time
    if wrote_via_legacy and self._db_writer:
        asyncio.create_task(self._safe_db_write("llm_call", {...}))  # existing body unchanged

    # SDK emission — always runs (no-op when OBS_ENABLED=false).
    obs_client = _maybe_get_obs_client()  # from backend.observability.bootstrap
    if obs_client is not None:
        event = LLMCallEvent(
            event_type=EventType.LLM_CALL,
            trace_id=current_trace_id() or UUID(bytes=uuid7().bytes),
            span_id=UUID(bytes=uuid7().bytes),
            parent_span_id=current_span_id(),
            ts=datetime.now(timezone.utc),
            env=settings.APP_ENV if hasattr(settings, "APP_ENV") else "dev",
            git_sha=None, user_id=None, session_id=None, query_id=None,
            wrote_via_legacy=wrote_via_legacy,  # ← captured snapshot (Task 8 dedup invariant)
            model=model, provider=provider, tier=tier,
            latency_ms=latency_ms, prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens, cost_usd=cost_usd,
            loop_step=loop_step, status=status,
            langfuse_trace_id=langfuse_trace_id,
        )
        await obs_client.emit(event)
```

**Pattern for Tasks 4-6:** same three-step shape — (a) snapshot `wrote_via_legacy=settings.OBS_LEGACY_DIRECT_WRITES` at top; (b) gate legacy write behind that snapshot; (c) construct event with `wrote_via_legacy=wrote_via_legacy` and emit via `_maybe_get_obs_client()`.

- [ ] **Step 3:** `uv run pytest tests/unit/observability/test_strangler_fig_contract.py -v` → contract tests pass on both flag values.
- [ ] **Step 4:** Commit: `feat(obs-1a): route record_request through SDK (strangler-fig)`.

---

## Task 4: Route `record_tool_execution` through SDK

**Files:** `backend/observability/collector.py`, append to contract test

- [ ] **Step 1:** Same pattern as Task 3. Flag-guard the legacy `asyncio.create_task(self._safe_db_write("tool_execution", ...))` (fact sheet §5.2 shows lines 133-149). Emit a `ToolExecutionEvent` unconditionally.
- [ ] **Step 2:** Extend contract test with `test_record_tool_execution_legacy_and_sdk_equivalent` + `test_record_tool_execution_sdk_only_when_flag_off`.
- [ ] **Step 3:** Commit: `feat(obs-1a): route record_tool_execution through SDK`.

---

## Task 5: Route `_write_login_attempt` through SDK

**Files:** `backend/routers/auth/_helpers.py`, append to contract test

- [ ] **Step 1:** Fact sheet §5.3 shows lines 129-151 do `db.add(LoginAttempt(...)); await db.commit()`. Wrap behind flag:

```python
async def _write_login_attempt(...) -> None:
    if settings.OBS_LEGACY_DIRECT_WRITES:
        # existing body — db.add + commit — unchanged
        ...
    obs_client = _maybe_get_obs_client()
    if obs_client is not None:
        event = LoginAttemptEvent(
            # envelope fields as Task 3 pattern
            email=email, success=success, ip_address=ip_address,
            user_agent=user_agent, failure_reason=failure_reason, method=method,
        )
        await obs_client.emit(event)
```

- [ ] **Step 2:** Contract test: both paths write equivalent rows (legacy `LoginAttempt` table + SDK-written row). Assert `ip_address` is NOT full-text in the SDK row (PII redaction is a 1b concern, but we can at least confirm the event carries it now — 1b will add redaction at ingestion).
- [ ] **Step 3:** Commit: `feat(obs-1a): route login attempts through SDK`.

---

## Task 6: Route `dq_scan` direct insert through SDK

**Files:** `backend/tasks/dq_scan.py`, append to contract test

- [ ] **Step 1:** Fact sheet §5.4 shows the loop at lines 52-59: `db.add(DqCheckHistory(...))`. Wrap behind flag; emit one `DqFindingEvent` per finding.

```python
async def _persist_findings(findings: list[dict]) -> None:
    if settings.OBS_LEGACY_DIRECT_WRITES:
        async with async_session_factory() as db:
            for f in findings:
                db.add(DqCheckHistory(check_name=f["check"], severity=f["severity"],
                                      ticker=f.get("ticker"), message=f["message"],
                                      metadata_=f.get("metadata")))
            await db.commit()
    obs_client = _maybe_get_obs_client()
    if obs_client is not None:
        for f in findings:
            await obs_client.emit(DqFindingEvent(
                # envelope as above pattern
                check_name=f["check"], severity=f["severity"],
                ticker=f.get("ticker"), message=f["message"], metadata=f.get("metadata"),
            ))
```

- [ ] **Step 2:** Contract test mirrors Task 3 pattern.
- [ ] **Step 3:** Commit: `feat(obs-1a): route dq_scan findings through SDK`.

---

## Task 7: `@tracked_task` — companion `PIPELINE_LIFECYCLE` events

**Files:** `backend/tasks/pipeline.py`, `tests/unit/tasks/test_tracked_task_events.py`

Fact sheet §5.5 + §12 documents the current behavior: `start_run()` INSERT, `record_ticker_*()` UPDATEs, `complete_run()` UPDATE. **We keep all UPDATEs** — state rows stay direct-writes regardless of the flag. We ADD lifecycle events on each state transition:

- [ ] **Step 1: Failing test** — every `@tracked_task` invocation produces exactly one `started` event + one terminal event (`succeeded` / `failed` / `no_op` / `partial`):

```python
# tests/unit/tasks/test_tracked_task_events.py
@pytest.mark.asyncio
async def test_tracked_task_emits_started_and_terminal(app_obs_client):
    # Invoke a minimal task decorated with @tracked_task; assert target.events has
    # exactly [PIPELINE_LIFECYCLE(started), PIPELINE_LIFECYCLE(succeeded)].
    ...


@pytest.mark.asyncio
async def test_tracked_task_emits_failed_on_exception(app_obs_client):
    # Task raises; assert second event is transition='failed'.
    ...
```

- [ ] **Step 2:** Modify `tracked_task` decorator at `backend/tasks/pipeline.py:412-521`.

**Important — use `emit_sync`, not `await emit()`:** per review finding (CRITICAL), `@tracked_task` runs inside `asyncio.run()` (fact sheet §12, `pipeline.py:433`). That loop is DIFFERENT from the persistent obs-client loop created in `worker_ready`. Calling `await obs_client.emit(...)` would attempt to put into a buffer that was bound on a different loop → race-conditions. `emit_sync` uses the thread-safe `queue.SimpleQueue` directly, so it's safe from ANY loop AND from sync Celery contexts. Also wrap each emission in a try/except so an emission bug never masks the real task failure:

```python
from backend.observability.bootstrap import _maybe_get_obs_client

# At start (around line 485):
run_id = await runner.start_run(...)  # existing — keep
obs_client = _maybe_get_obs_client()
if obs_client is not None:
    try:
        obs_client.emit_sync(PipelineLifecycleEvent(
            # envelope fields (trace_id/span_id/ts/env per Task 3 pattern)
            pipeline_name=pipeline_name, transition="started",
            run_id=run_id, trigger=trigger,
            celery_task_id=_current_celery_task_id(),
            wrote_via_legacy=settings.OBS_LEGACY_DIRECT_WRITES,  # task 8 dedup
        ))
    except Exception:  # noqa: BLE001 — emission bug must never mask real task failure
        logger.warning("obs.pipeline_lifecycle.started_emit_raised", exc_info=True)

# At terminal (complete_run + exception paths around lines 491-517):
# After runner.complete_run(run_id), look up its final status and emit.
# NOTE: if `runner.get_status(run_id)` does not exist (fact sheet §5.5 only
# documents start_run / record_ticker_* / complete_run), add a small helper method
# to PipelineRunner: `async def get_status(run_id) -> str` that reads the row;
# OR refactor complete_run to RETURN the classified status. See PR5 Task 7 Risks.
final_status = await runner.get_status(run_id)
if obs_client is not None:
    try:
        obs_client.emit_sync(PipelineLifecycleEvent(
            pipeline_name=pipeline_name, transition=final_status,
            run_id=run_id, trigger=trigger,
            celery_task_id=_current_celery_task_id(),
            duration_s=<measured>, tickers_total=..., tickers_succeeded=..., tickers_failed=...,
            wrote_via_legacy=settings.OBS_LEGACY_DIRECT_WRITES,
        ))
    except Exception:  # noqa: BLE001
        logger.warning("obs.pipeline_lifecycle.terminal_emit_raised", exc_info=True)
```

Crucially — **the UPDATE to `pipeline_runs` stays unchanged**. `OBS_LEGACY_DIRECT_WRITES` does NOT gate the state-row writes. Only the _event_ is gated by the SDK's own `OBS_ENABLED` flag (the `_maybe_get_obs_client()` returns None when disabled).

### BLOCKING prerequisite (NOT optional) — Task 7a: Verify + add `PipelineRunner.get_status` before emission logic

**This is a hard blocker.** Do NOT dispatch the Task 7 subagent until this prerequisite commit lands. Fact sheet §5.5 + §12 enumerate `start_run` / `record_ticker_success` / `record_ticker_failure` / `complete_run` on `PipelineRunner` — `get_status` was assumed to exist but is unverified.

- [ ] **Step 1: Grep verification**

```bash
grep -rn "def get_status\|async def get_status" /Users/sigmoid/Documents/projects/stockanalysis/stock-signal-platform/backend/tasks/pipeline.py
```

If zero hits → proceed to Step 2. If the method exists → note its signature + proceed directly to Task 7.

- [ ] **Step 2: Prerequisite commit — add the method with a planned signature (NO fabrication)**

Signature (plan exactly, do not mutate):

```python
# Inside PipelineRunner class in backend/tasks/pipeline.py
async def get_status(self, run_id: UUID) -> Literal["succeeded", "failed", "no_op", "partial"]:
    """Read classified terminal status for a completed pipeline run.

    Used by @tracked_task decorator to emit PIPELINE_LIFECYCLE terminal events
    with the same status classification as complete_run(). Raises LookupError if
    the run_id is unknown or not yet complete.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(PipelineRun.status).where(PipelineRun.id == run_id)
        )
        status = result.scalar_one_or_none()
    if status is None:
        raise LookupError(f"pipeline run {run_id} not found")
    if status not in ("succeeded", "failed", "no_op", "partial"):
        raise ValueError(f"unexpected status {status!r} for run {run_id}")
    return status
```

Test: `tests/unit/pipeline/test_pipeline_runner.py` — `test_get_status_returns_classified_terminal` (seed a run with each status, assert correct return) + `test_get_status_raises_on_unknown_run_id`.

- [ ] **Step 3:** Commit: `feat(obs-1a): add PipelineRunner.get_status for PIPELINE_LIFECYCLE emissions`.

Only after Step 3 commits → proceed to Task 7.

**Pre-merge gate:** before dispatching a subagent for Task 7 emission logic, verify `PipelineRunner.get_status` exists via the grep above. If it does not, STOP and run Task 7a first.

- [ ] **Step 3:** Ensure the 11 fact-sheet §6 test files still pass — `test_pipeline_runner_decorator.py`, `test_pipeline_infra.py`, `test_pipeline_stats.py`, `test_nightly_chain.py`, etc. The decorator's UPDATE semantics are preserved.
- [ ] **Step 4:** Commit: `feat(obs-1a): emit PIPELINE_LIFECYCLE events alongside @tracked_task UPDATEs`.

---

## Task 8: Route the 5 legacy event types through `event_writer` (with spool-replay dedup)

**Files:** `backend/observability/service/legacy_emitters_writer.py`, update `backend/observability/service/event_writer.py`, update `backend/observability/schema/legacy_events.py` (add `wrote_via_legacy` field)

- [ ] **Step 1:** Each of `LLM_CALL`, `TOOL_EXECUTION`, `LOGIN_ATTEMPT`, `DQ_FINDING`, `PIPELINE_LIFECYCLE` gets a writer that inserts into the SAME existing table (`llm_call_log`, `tool_execution_log`, `login_attempts`, `dq_check_history`, `pipeline_runs`) rather than a new `observability.*` table.

Rationale: spec §3.3 — existing observability-adjacent tables stay in `public.*` for this Epic. During dual-write we MUST guarantee **one row per event, never two, never zero**.

### Dedup invariant (post-review fix for spool-replay race)

Per review (CRITICAL finding): the naive "check `settings.OBS_LEGACY_DIRECT_WRITES` at write time" pattern is **wrong** because the SDK's spool can persist events emitted during flag=true, then replay them after operators flip flag=false → `persist_llm_call` reads the CURRENT (false) flag and inserts, but the legacy path ALREADY wrote the row two hours ago → duplicate.

**Fix:** capture the flag value at **emit time** into the event envelope via a new `wrote_via_legacy: bool` field. The writer decides based on the event's captured snapshot, not the current setting. Spool-replay preserves the original decision.

Add to `backend/observability/schema/legacy_events.py` — put on the common base subclass (all 5 inherit):

```python
class _LegacyStranglerFigMixin(BaseModel):
    """Mixin for PR5 strangler-fig events — captures dual-write decision at emit time."""
    wrote_via_legacy: bool  # snapshot of OBS_LEGACY_DIRECT_WRITES at emit, NOT read later


class LLMCallEvent(ObsEventBase, _LegacyStranglerFigMixin):
    # ...existing fields...

# Apply to: LLMCallEvent, ToolExecutionEvent, LoginAttemptEvent, DqFindingEvent, PipelineLifecycleEvent
```

Every emitter sets `wrote_via_legacy=settings.OBS_LEGACY_DIRECT_WRITES` at the `obs_client.emit(event)` call site. (Tasks 3-7 of this PR must be updated to populate this field when constructing the event.)

### Writer short-circuit on the captured snapshot

```python
# backend/observability/service/legacy_emitters_writer.py
async def persist_llm_call(event: LLMCallEvent) -> None:
    if event.wrote_via_legacy:
        return  # legacy path wrote this row at emit time; skip to avoid duplicate
    # insert into llm_call_log — same columns as collector._safe_db_write("llm_call", ...)
```

**Invariant:** dual-write = one row per event. If `wrote_via_legacy=True`, legacy wrote it (writer skips). If `wrote_via_legacy=False`, legacy skipped (writer inserts). Flag state at **emit time** decides — spool-replay is safe.

### Tests

Add a spool-replay regression test:

```python
@pytest.mark.asyncio
async def test_spool_replay_after_flag_flip_does_not_duplicate(db_session, tmp_path):
    """Emit with flag=True → spooled event carries wrote_via_legacy=True → replay is no-op."""
    # 1. Set flag=True, call collector.record_request → legacy writes row, SDK emits event with wrote_via_legacy=True
    # 2. Simulate spool overflow: stop client, inspect spool file, verify event has wrote_via_legacy=True
    # 3. Set flag=False; reclaim loop replays from spool
    # 4. Assert llm_call_log still has ONE row, not TWO
```

- [ ] **Step 2:** Extend `event_writer.write_batch` to dispatch on event_type:

```python
async def write_batch(events):
    for event in events:
        if isinstance(event, LLMCallEvent):
            await persist_llm_call(event)
        elif isinstance(event, ToolExecutionEvent):
            await persist_tool_execution(event)
        # ... etc. ExternalApiCallLog + RateLimiterEvent branches from PR4 stay
```

- [ ] **Step 3:** Contract test — verify ONE row per event across both flag settings (no duplicates, no drops).
- [ ] **Step 4:** Commit: `feat(obs-1a): legacy_emitters_writer — flag-gated dedup between legacy and SDK writes`.

---

## Full-suite sanity + lint + smoke

- [ ] `uv run pytest tests/unit/ tests/api/ -q --tb=short` → all 11 fact-sheet §6 tests still green; +10 contract tests new.
- [ ] `uv run ruff check --fix backend/ tests/`
- [ ] `uv run ruff format backend/ tests/`
- [ ] Manual validation: set `OBS_LEGACY_DIRECT_WRITES=false` in a dev env; run the full nightly chain; verify `llm_call_log` / `tool_execution_log` / `login_attempts` / `dq_check_history` / `pipeline_runs` still populate via SDK path only.

---

## Acceptance Criteria (PR5)

- [x] `OBS_LEGACY_DIRECT_WRITES=true` (default): 4 emitters dual-write; row in legacy table; SDK writer skips to avoid duplicate; SDK event still flows for downstream consumers
- [x] `OBS_LEGACY_DIRECT_WRITES=false`: 4 emitters emit only via SDK; row appears via `legacy_emitters_writer`; legacy code paths short-circuit
- [x] `@tracked_task` emits PIPELINE_LIFECYCLE events on every state transition; existing UPDATE semantics unchanged
- [x] All 11 fact-sheet §6 test files still pass unchanged
- [x] +10 new contract tests (2 per emitter + tracked_task lifecycle pair)
- [x] Zero regressions in full unit + API suite

---

## Risks

| Risk | Mitigation |
|---|---|
| Dual-write window produces inconsistent DB state if SDK writer has a bug | Contract tests assert equivalence at EVERY emitter boundary; flag flip only happens after 2 weeks of green production |
| `@tracked_task` emission inside a Celery task forces an asyncio.run bridge that conflicts with existing tracer | Use existing `asyncio.run()` pattern from `task_tracer.py` (fact sheet §12); emission is fire-and-forget so it slots cleanly into the existing asyncio bridge |
| `_maybe_get_obs_client()` returns None in some code paths (e.g., non-request contexts that still call the collector) | Early-exit silently — same semantics as OBS_ENABLED=false; test coverage for "no client attached" |
| State-row UPDATEs in `@tracked_task` drift away from event payload fields | Contract test: every PIPELINE_LIFECYCLE event has matching row in `pipeline_runs` with the same `status`, `started_at`, `completed_at` |
| Flag flip reveals subtle column-mapping bug in `legacy_emitters_writer` | Stage the flip: flip in dev for 24h, then staging 48h, then prod; revert = set flag back to true (rows resume flowing through legacy path) |
| Future cleanup PR (delete legacy code) accidentally deletes useful helpers | Cleanup is a separate PR 2 weeks after the flag flip; reviewers get a full diff |
| Duplicate PIPELINE_LIFECYCLE events on Celery retries | Celery retries re-run the task; each retry emits its own started/terminal pair — correct behavior (retry visibility); `celery_task_id` aggregates them |

---

## Commit Sequence

1. `feat(obs-1a): add OBS_LEGACY_DIRECT_WRITES strangler-fig flag`
2. `feat(obs-1a): add Pydantic event subclasses for legacy emitters`
3. `feat(obs-1a): route record_request through SDK (strangler-fig)`
4. `feat(obs-1a): route record_tool_execution through SDK`
5. `feat(obs-1a): route login attempts through SDK`
6. `feat(obs-1a): route dq_scan findings through SDK`
7. `feat(obs-1a): emit PIPELINE_LIFECYCLE events alongside @tracked_task UPDATEs`
8. `feat(obs-1a): legacy_emitters_writer — flag-gated dedup between legacy and SDK writes`

PR body references: spec §2.7, §3.3; KAN-458, KAN-464; fact-sheet §5 (emitter file:line inventory), §6 (11 must-stay-green tests), §12 (@tracked_task UPDATE semantics).

---

## Post-PR5 rollout (not in this PR)

Per spec §2.7, after PR5 merges:
1. 2 weeks of green production with `OBS_LEGACY_DIRECT_WRITES=true` (dual-write validates SDK path without risk)
2. Flip flag to `false` in a follow-up PR; observe another week
3. Cleanup PR: delete `ObservabilityCollector._safe_db_write`, `backend/observability/writer.py`, direct-insert code in `_write_login_attempt` / `dq_scan`; simplify `@tracked_task` to read `PIPELINE_LIFECYCLE` events from SDK for dashboards

1a is complete when step 1 starts (PR5 merged + dual-write mode running). The flag-flip and cleanup are tracked as 1b tickets.
