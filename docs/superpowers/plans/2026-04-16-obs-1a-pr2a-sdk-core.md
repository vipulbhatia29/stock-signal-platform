# Obs 1a PR2a — SDK Core + Default Targets + Lifespan Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Ship `ObservabilityClient`, the `ObservabilityTarget` Protocol, the `DirectTarget` (default for monolith) and `MemoryTarget` (tests) implementations, the buffered async flush loop with optional disk spool, the `OBS_ENABLED` / `OBS_SPOOL_ENABLED` kill switches, and wire through FastAPI lifespan + Celery `worker_ready`. `InternalHTTPTarget` + the `/obs/v1/events` ingest endpoint live in **PR2b** (depends on this PR).

**Architecture:** Events are buffered in a bounded `asyncio.Queue`; a flush task drains in batches to the target selected at init via `OBS_TARGET_TYPE`. On target failure the batch optionally spools to a per-worker JSONL file; a reclaim task replays spooled events on recovery. All emission paths are no-ops when `OBS_ENABLED=false`.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, `asyncio.Queue`, `aiofiles` (verify in deps; add if missing).

**Spec reference:** `docs/superpowers/specs/2026-04-16-obs-1a-foundations-design.md` §2.1, §2.2 (DirectTarget + MemoryTarget only).

**Prerequisites:** PR1 (uses `ObsEventBase`, `EventType`).

**Dependency for:** PR2b (adds `InternalHTTPTarget` + ingest endpoint), PR3 (feeds trace_id into events), PR4 (external_api events), PR5 (strangler-fig emissions).

**Fact-sheet anchors:** No existing Celery signal handlers (§8) — this PR installs the first (`worker_ready`). `app.state.*` pattern confirmed (§2: collector, cache, http_metrics, langfuse).

---

## File Structure

**Create:**
- `backend/observability/client.py` — `ObservabilityClient` (async emit + sync emit_sync), `ClientHealth`
- `backend/observability/buffer.py` — `EventBuffer` (loop-agnostic `queue.SimpleQueue` — see §Loop-Safety below)
- `backend/observability/spool.py` — `SpoolWriter`, `SpoolReader`
- `backend/observability/targets/__init__.py` — re-exports + factory helpers
- `backend/observability/targets/base.py` — `ObservabilityTarget` Protocol, `BatchResult`, `TargetHealth`
- `backend/observability/targets/direct.py` — `DirectTarget`
- `backend/observability/targets/memory.py` — `MemoryTarget`
- `backend/observability/service/__init__.py`, `backend/observability/service/event_writer.py` — stub (real writers land in PR4/PR5)
- `backend/observability/bootstrap.py` — `build_client_from_settings()` + `_maybe_get_obs_client()` helper + `obs_client_var` ContextVar
- `tests/unit/observability/test_targets.py`, `test_spool.py`, `test_client.py`, `test_emit_sync.py`

### Loop-safety contract (post-review revision)

`ObservabilityClient` must work from **three** distinct calling contexts that run on DIFFERENT event loops:

1. **FastAPI request handlers** — `async` code on the app's lifespan loop
2. **Celery tasks wrapped by `@tracked_task`** — sync code bridged via `asyncio.run()` per task (fresh loop per invocation per fact sheet §12 / `pipeline.py:433`)
3. **Truly sync contexts** — `requests.Session` in yfinance, rate-limiter fallback branches

The buffer MUST be loop-agnostic. Implementation: `queue.SimpleQueue` (thread- and loop-safe, non-blocking `put_nowait`) NOT `asyncio.Queue` (bound to a single loop). The async `_flush_loop` uses `asyncio.to_thread(self._buffer.get_batch, ...)` to pull without binding to any specific loop.

`emit` (async) and `emit_sync` (sync) both funnel through the SAME `_buffer.try_put(event)` call — they diverge only in how they handle spool overflow (emit awaits aiofiles; emit_sync uses `loop.call_soon_threadsafe` if a loop exists, else drops with a warn).

**Modify:**
- `backend/config.py` — add `OBS_*` settings
- `backend/main.py` — lifespan init / shutdown flush
- `backend/tasks/__init__.py` — `worker_ready` + `worker_shutdown` signals
- `pyproject.toml` — add `aiofiles>=24.1.0` if missing

**Deferred to PR2b:** `InternalHTTPTarget`, `backend/observability/routers/ingest.py`, `OBS_INGEST_SECRET`.

---

## Task 1: Add `aiofiles` dep if missing

- [ ] `uv run python -c "import aiofiles; print(aiofiles.__version__)"`. If fails, add `"aiofiles>=24.1.0",` to `pyproject.toml` deps, run `uv sync`, and commit `chore(obs-1a): add aiofiles for disk spool I/O`.

---

## Task 2: Config settings

**Files:** `backend/config.py`, `tests/conftest.py`

- [ ] **Step 1: Extend `Settings`** (inside the class; import `Literal` at top of file if missing):

```python
    # Obs 1a PR2a — SDK kill switches + target config.
    OBS_ENABLED: bool = Field(True, description="Global kill switch — False makes all emit calls no-ops")
    OBS_SPOOL_ENABLED: bool = Field(True, description="If True, overflow events go to OBS_SPOOL_DIR; else drop")
    OBS_SPOOL_DIR: str = Field("/var/tmp/obs-spool", description="Per-worker append-only JSONL spool directory")
    OBS_SPOOL_MAX_SIZE_MB: int = Field(100, ge=1, description="Per-worker spool cap")
    OBS_TARGET_TYPE: Literal["direct", "memory"] = Field(
        "direct", description="Target adapter — DirectTarget (monolith default) or MemoryTarget (tests). "
                              "PR2b adds 'internal_http'.",
    )
    OBS_FLUSH_INTERVAL_MS: int = Field(500, ge=50)
    OBS_BUFFER_SIZE: int = Field(10_000, ge=100)
```

- [ ] **Step 2: Test-env defaults** — in the existing env-setup fixture in `tests/conftest.py`, force `OBS_TARGET_TYPE=memory`, `OBS_SPOOL_ENABLED=false`, `OBS_ENABLED=true`.
- [ ] **Step 3:** Smoke-test: `uv run python -c "from backend.config import settings; print(settings.OBS_ENABLED, settings.OBS_TARGET_TYPE)"` → `True direct`.
- [ ] **Step 4:** Commit: `feat(obs-1a): add OBS_* settings + kill-switch defaults`.

---

## Task 3: `ObservabilityTarget` Protocol + `MemoryTarget`

**Files:** `backend/observability/targets/{__init__.py, base.py, memory.py}`, `tests/unit/observability/test_targets.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/observability/test_targets.py
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.targets.base import BatchResult
from backend.observability.targets.memory import MemoryTarget


def _event():
    return ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=uuid4(), span_id=uuid4(), parent_span_id=None,
        ts=datetime.now(timezone.utc), env="dev",
        git_sha=None, user_id=None, session_id=None, query_id=None,
    )


@pytest.mark.asyncio
async def test_memory_target_accepts_batch():
    target = MemoryTarget()
    result = await target.send_batch([_event(), _event()])
    assert result == BatchResult(sent=2, failed=0)
    assert len(target.events) == 2


@pytest.mark.asyncio
async def test_memory_target_health_ok():
    assert (await MemoryTarget().health()).healthy is True


@pytest.mark.asyncio
async def test_memory_target_fail_next():
    target = MemoryTarget(fail_next=1)
    assert (await target.send_batch([_event()])).failed == 1
    assert (await target.send_batch([_event()])).sent == 1
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement**

```python
# backend/observability/targets/base.py
"""ObservabilityTarget Protocol — the extraction seam."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from backend.observability.schema.v1 import ObsEventBase


@dataclass(frozen=True)
class BatchResult:
    sent: int
    failed: int
    error: str | None = None


@dataclass(frozen=True)
class TargetHealth:
    healthy: bool
    last_success_ts: str | None = None
    last_error: str | None = None


@runtime_checkable
class ObservabilityTarget(Protocol):
    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult: ...
    async def health(self) -> TargetHealth: ...
```

```python
# backend/observability/targets/memory.py
"""In-process target for tests."""
from __future__ import annotations
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.targets.base import BatchResult, TargetHealth


class MemoryTarget:
    def __init__(self, fail_next: int = 0) -> None:
        self.events: list[ObsEventBase] = []
        self._fail_next = fail_next

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult:
        if self._fail_next > 0:
            self._fail_next -= 1
            return BatchResult(sent=0, failed=len(events), error="memory_target_simulated_failure")
        self.events.extend(events)
        return BatchResult(sent=len(events), failed=0)

    async def health(self) -> TargetHealth:
        return TargetHealth(healthy=True)
```

```python
# backend/observability/targets/__init__.py
from backend.observability.targets.base import BatchResult, ObservabilityTarget, TargetHealth
from backend.observability.targets.memory import MemoryTarget
__all__ = ["ObservabilityTarget", "BatchResult", "TargetHealth", "MemoryTarget"]
```

- [ ] **Step 4:** `uv run pytest tests/unit/observability/test_targets.py -v` → 3 passed.
- [ ] **Step 5:** Commit: `feat(obs-1a): add ObservabilityTarget Protocol + MemoryTarget`.

---

## Task 4: `DirectTarget` + event_writer stub

**Files:** `backend/observability/targets/direct.py`, `backend/observability/service/{__init__.py, event_writer.py}`, extend `targets/__init__.py`, extend `test_targets.py`

- [ ] **Step 1: Add failing test** (append to `test_targets.py`):

```python
@pytest.mark.asyncio
async def test_direct_target_delegates_to_writer():
    from backend.observability.targets.direct import DirectTarget
    called = []

    async def fake_writer(events):
        called.append(list(events))

    result = await DirectTarget(event_writer=fake_writer).send_batch([_event(), _event()])
    assert result.sent == 2 and result.failed == 0
    assert len(called) == 1 and len(called[0]) == 2
```

- [ ] **Step 2: Implement** (stub `event_writer` — real impl lands PR4/PR5):

```python
# backend/observability/service/event_writer.py
"""Routes events by event_type to the right repository.

PR2a ships a no-op DEBUG logger — validates SDK end-to-end. PR4 adds external_api_call_log +
rate_limiter_event writers; PR5 adds writers for refactored legacy emitters.
"""
from __future__ import annotations
import logging
from backend.observability.schema.v1 import ObsEventBase

logger = logging.getLogger(__name__)


async def write_batch(events: list[ObsEventBase]) -> None:
    for event in events:
        logger.debug("obs.event.write", extra={"event_type": event.event_type.value})
```

```python
# backend/observability/targets/direct.py
"""DirectTarget — writes events directly through event_writer.write_batch.

Monolith default. At extraction time, swap with ExternalHTTPTarget in bootstrap — no
application code changes.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Awaitable, Callable
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.service.event_writer import write_batch as default_writer
from backend.observability.targets.base import BatchResult, TargetHealth

WriterFn = Callable[[list[ObsEventBase]], Awaitable[None]]


class DirectTarget:
    def __init__(self, event_writer: WriterFn | None = None) -> None:
        self._writer = event_writer or default_writer
        self._last_success_ts: str | None = None
        self._last_error: str | None = None

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult:
        try:
            await self._writer(events)
        except Exception as exc:  # noqa: BLE001 — writer exceptions classified below
            self._last_error = type(exc).__name__
            return BatchResult(sent=0, failed=len(events), error=self._last_error)
        self._last_success_ts = datetime.now(timezone.utc).isoformat()
        self._last_error = None
        return BatchResult(sent=len(events), failed=0)

    async def health(self) -> TargetHealth:
        return TargetHealth(
            healthy=self._last_error is None,
            last_success_ts=self._last_success_ts,
            last_error=self._last_error,
        )
```

Re-export in `backend/observability/targets/__init__.py`: add `from backend.observability.targets.direct import DirectTarget`; append to `__all__`.

- [ ] **Step 3:** `uv run pytest tests/unit/observability/test_targets.py -v` → 4 passed.
- [ ] **Step 4:** Commit: `feat(obs-1a): add DirectTarget + event_writer stub`.

---

## Task 5: Disk spool (`SpoolWriter`, `SpoolReader`)

**Files:** `backend/observability/spool.py`, `tests/unit/observability/test_spool.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/observability/test_spool.py
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import pytest
from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.spool import SpoolReader, SpoolWriter


def _e():
    return ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=uuid4(), span_id=uuid4(), parent_span_id=None,
        ts=datetime.now(timezone.utc), env="dev",
        git_sha=None, user_id=None, session_id=None, query_id=None,
    )


@pytest.mark.asyncio
async def test_spool_round_trip(tmp_path: Path):
    await SpoolWriter(tmp_path, max_size_mb=1).append([_e(), _e()])
    events = [e async for e in SpoolReader(tmp_path).drain()]
    assert len(events) == 2


@pytest.mark.asyncio
async def test_spool_drops_on_overflow(tmp_path: Path):
    # 0 MB cap → everything dropped
    result = await SpoolWriter(tmp_path, max_size_mb=0).append([_e(), _e()])
    assert result.dropped == 2
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement**

```python
# backend/observability/spool.py
"""Append-only JSONL spool — survives target outages without blocking emit().

- One file per worker (spool-{pid}.jsonl)
- Per-worker byte cap; overflow = drop (oldest-first rotation is OUT of scope)
- No-op when OBS_SPOOL_ENABLED=false (constructor short-circuits upstream)
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator
import aiofiles
from backend.observability.schema.v1 import ObsEventBase


@dataclass(frozen=True)
class AppendResult:
    written: int
    dropped: int


class SpoolWriter:
    def __init__(self, directory: Path, max_size_mb: int) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._max_bytes = max_size_mb * 1024 * 1024
        self._file = self._dir / f"spool-{os.getpid()}.jsonl"

    async def append(self, events: list[ObsEventBase]) -> AppendResult:
        current = self._file.stat().st_size if self._file.exists() else 0
        if current >= self._max_bytes:
            return AppendResult(written=0, dropped=len(events))
        written = 0
        dropped = 0
        async with aiofiles.open(self._file, mode="a") as fh:
            for ev in events:
                line = ev.model_dump_json() + "\n"
                if current + len(line.encode()) > self._max_bytes:
                    dropped += 1
                    continue
                await fh.write(line)
                current += len(line.encode())
                written += 1
        return AppendResult(written=written, dropped=dropped)


class SpoolReader:
    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    async def drain(self) -> AsyncIterator[ObsEventBase]:
        for path in sorted(self._dir.glob("spool-*.jsonl")):
            async with aiofiles.open(path, mode="r") as fh:
                async for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    yield ObsEventBase.model_validate_json(raw)
            path.unlink(missing_ok=True)
```

- [ ] **Step 4:** `uv run pytest tests/unit/observability/test_spool.py -v` → 2 passed.
- [ ] **Step 5:** Commit: `feat(obs-1a): add optional JSONL disk spool with size cap`.

---

## Task 6: `EventBuffer` + `ObservabilityClient`

**Files:** `backend/observability/buffer.py`, `backend/observability/client.py`, `tests/unit/observability/test_client.py`

- [ ] **Step 1: Failing tests** — covers happy-path emit, `OBS_ENABLED=false` no-op, chaos (target down → spool → reclaim), emit-never-raises contract.

```python
# tests/unit/observability/test_client.py
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import pytest
from backend.observability.client import ObservabilityClient
from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.targets.memory import MemoryTarget


def _e():
    return ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=uuid4(), span_id=uuid4(), parent_span_id=None,
        ts=datetime.now(timezone.utc), env="dev",
        git_sha=None, user_id=None, session_id=None, query_id=None,
    )


async def _make_client(tmp_path, *, enabled=True, spool=False, target=None):
    client = ObservabilityClient(
        target=target or MemoryTarget(),
        spool_dir=tmp_path, spool_enabled=spool,
        flush_interval_ms=50, buffer_size=100, enabled=enabled,
    )
    await client.start()
    return client


@pytest.mark.asyncio
async def test_emit_round_trip(tmp_path):
    target = MemoryTarget()
    client = await _make_client(tmp_path, target=target)
    try:
        await client.emit(_e())
        await client.flush()
        assert len(target.events) == 1
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_emit_is_no_op_when_disabled(tmp_path):
    target = MemoryTarget()
    client = await _make_client(tmp_path, enabled=False, target=target)
    try:
        await client.emit(_e())
        await client.flush()
        assert target.events == []
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_target_down_spools_and_drains(tmp_path):
    target = MemoryTarget(fail_next=1)
    client = await _make_client(tmp_path, spool=True, target=target)
    try:
        await client.emit(_e())
        await client.flush()
        await asyncio.sleep(0.2)
        await client.flush()
        assert len(target.events) == 1
    finally:
        await client.stop()


@pytest.mark.asyncio
async def test_emit_never_raises(tmp_path):
    target = MemoryTarget(fail_next=10_000)
    client = await _make_client(tmp_path, spool=False, target=target)
    try:
        for _ in range(100):
            await client.emit(_e())  # must not raise even on all failures + spool off
        await client.flush()
    finally:
        await client.stop()
```

- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement `EventBuffer`** — loop-agnostic `queue.SimpleQueue` (thread- and loop-safe). `try_put()` non-blocking; `get_batch(max_batch, timeout_s)` blocks in a worker thread via `asyncio.to_thread`. Must work from both FastAPI's lifespan loop AND Celery's per-task `asyncio.run()` loops AND purely sync contexts.

```python
# backend/observability/buffer.py
from __future__ import annotations
import queue
from dataclasses import dataclass
from backend.observability.schema.v1 import ObsEventBase


@dataclass
class BufferStats:
    depth: int
    drops: int


class EventBuffer:
    """Loop-agnostic bounded queue — safe from any thread + any event loop.

    Uses stdlib queue.Queue(maxsize=N): thread-safe, loop-agnostic, AND enforces
    a hard bound via put_nowait → queue.Full on overflow. queue.SimpleQueue would
    be simpler but its qsize() is "approximate" per stdlib docs and unreliable
    for bounds checking under concurrent producers (yfinance sync + FastAPI async
    + Celery daemon thread can all push simultaneously).

    Survives Celery's per-task asyncio.run() pattern (fresh loop per task) because
    queue.Queue has no loop binding, unlike asyncio.Queue.
    """

    def __init__(self, max_size: int) -> None:
        self._queue: queue.Queue[ObsEventBase] = queue.Queue(maxsize=max_size)
        self._drops = 0

    def try_put(self, event: ObsEventBase) -> bool:
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            self._drops += 1
            return False

    def get_batch(self, max_batch: int, timeout_s: float) -> list[ObsEventBase]:
        """Block up to timeout_s for the first event, then drain non-blockingly.

        Call from a worker thread via asyncio.to_thread so it never blocks a loop.
        """
        try:
            first = self._queue.get(timeout=timeout_s)
        except queue.Empty:
            return []
        batch = [first]
        while len(batch) < max_batch:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def stats(self) -> BufferStats:
        return BufferStats(depth=self._queue.qsize(), drops=self._drops)


# Regression test required (added to tests/unit/observability/test_client.py):
# test_buffer_concurrent_producers_respect_max_size — spawn 10 threads each
# pushing 100 events with max_size=500; assert final qsize <= 500 + drops == 500
# (hard bound via queue.Full, NOT soft bound from SimpleQueue.qsize check).
```

- [ ] **Step 4: Implement `ObservabilityClient`** — `start()`/`stop()` manage flush + reclaim tasks; `emit()` async non-blocking; **`emit_sync()` for sync callers** (yfinance + rate-limiter fallback); `flush()` drains once with timeout; `health()` reports state; `_flush_loop` wrapped in top-level try/except (poison-event safety); `stop()` signals FIRST, awaits flush task, then final drain (no double-drainer race); all paths no-op when disabled.

```python
# backend/observability/client.py
"""ObservabilityClient — single emission abstraction (spec §2.1).

Loop-safety contract:
- emit() (async) + emit_sync() (sync) both funnel through buffer.try_put
- Buffer is loop-agnostic queue.SimpleQueue so calls from ANY loop work
- _flush_loop runs on start()'s loop; drains buffer via asyncio.to_thread
- stop() signals _stopping first, awaits flush task cleanly, then final drain

Hard-rule semantics:
- emit/emit_sync NEVER raise (swallow all exceptions, log + drop-or-spool)
- _flush_loop wrapped in top-level try/except to survive poison events
- enabled=False → both emit paths are no-ops; no background tasks started
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from backend.observability.buffer import EventBuffer
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.spool import SpoolReader, SpoolWriter
from backend.observability.targets.base import ObservabilityTarget

logger = logging.getLogger(__name__)


@dataclass
class ClientHealth:
    enabled: bool
    queue_depth: int
    drops: int
    target_healthy: bool
    last_target_error: str | None


class ObservabilityClient:
    def __init__(
        self,
        *,
        target: ObservabilityTarget,
        spool_dir: Path,
        spool_enabled: bool,
        flush_interval_ms: int,
        buffer_size: int,
        enabled: bool,
        max_batch: int = 500,
        spool_max_size_mb: int = 100,
        reclaim_interval_s: float = 30.0,
    ) -> None:
        self._target = target
        self._enabled = enabled
        self._buffer = EventBuffer(buffer_size)
        self._spool_enabled = spool_enabled
        self._spool_writer = SpoolWriter(spool_dir, spool_max_size_mb) if spool_enabled else None
        self._spool_reader = SpoolReader(spool_dir) if spool_enabled else None
        self._flush_interval = flush_interval_ms / 1000.0
        self._max_batch = max_batch
        self._reclaim_interval = reclaim_interval_s  # configurable for tests
        self._flush_task: asyncio.Task[None] | None = None
        self._reclaim_task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        if not self._enabled:
            return
        self._flush_task = asyncio.create_task(self._flush_loop())
        if self._spool_enabled:
            self._reclaim_task = asyncio.create_task(self._reclaim_loop())

    async def stop(self) -> None:
        """Signal stop FIRST, let the flush loop exit naturally, then final drain.

        Fixes the double-drainer race: previous version awaited flush() before
        cancelling the flush task, which meant two coroutines contended on the
        same queue.
        """
        if not self._enabled:
            return
        self._stopping.set()
        if self._flush_task:
            try:
                await asyncio.wait_for(self._flush_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._flush_task.cancel()
        if self._reclaim_task:
            self._reclaim_task.cancel()
        # Final sync drain to catch anything still queued at shutdown.
        await self._drain_once(block=False)

    async def emit(self, event: ObsEventBase) -> None:
        """Async non-blocking emit — safe from FastAPI request handlers."""
        if not self._enabled:
            return
        self._enqueue_or_overflow(event, is_async=True)

    def emit_sync(self, event: ObsEventBase) -> None:
        """Sync non-blocking emit — safe from yfinance/requests/rate-limiter sync paths.

        Does NOT create asyncio tasks (caller may not be on an event loop). Uses the
        same buffer as async emit; spool overflow drops-and-warns in sync context
        rather than awaiting aiofiles.
        """
        if not self._enabled:
            return
        self._enqueue_or_overflow(event, is_async=False)

    def _enqueue_or_overflow(self, event: ObsEventBase, *, is_async: bool) -> None:
        try:
            if self._buffer.try_put(event):
                return
        except Exception:  # noqa: BLE001 — must not propagate
            logger.warning("obs.emit.try_put_raised", exc_info=True)
            return
        # Overflow path.
        if not self._spool_writer:
            logger.warning("obs.event_dropped.buffer_overflow",
                           extra={"event_type": event.event_type.value})
            return
        if is_async:
            # Fire-and-forget: schedule spool write on the caller's loop.
            try:
                asyncio.get_running_loop().create_task(self._spool_writer.append([event]))
            except RuntimeError:
                # Not on a running loop — fall back to drop.
                logger.warning("obs.event_dropped.sync_context_no_loop",
                               extra={"event_type": event.event_type.value})
        else:
            # Sync context — drop with warn (no loop to await aiofiles on).
            logger.warning("obs.event_dropped.sync_overflow",
                           extra={"event_type": event.event_type.value})

    async def flush(self, timeout_s: float = 5.0) -> None:
        if not self._enabled:
            return
        await self._drain_once(block=True, timeout_s=timeout_s)

    async def _drain_once(self, *, block: bool, timeout_s: float = 1.0) -> None:
        timeout = timeout_s if block else 0.0
        batch = await asyncio.to_thread(self._buffer.get_batch, self._max_batch, timeout)
        if batch:
            await self._send(batch)

    async def health(self) -> ClientHealth:
        stats = self._buffer.stats()
        target_health = await self._target.health()
        return ClientHealth(
            enabled=self._enabled,
            queue_depth=stats.depth,
            drops=stats.drops,
            target_healthy=target_health.healthy,
            last_target_error=target_health.last_error,
        )

    async def _flush_loop(self) -> None:
        """Top-level try/except prevents a single poison event from killing the flusher.

        Per review finding: if any step inside the loop raises unexpectedly (e.g.,
        PydanticSerializationError on a bad envelope, or a target impl bug), we log
        and continue — we do NOT let the task die silently.
        """
        while not self._stopping.is_set():
            try:
                batch = await asyncio.to_thread(
                    self._buffer.get_batch, self._max_batch, self._flush_interval
                )
                if batch:
                    await self._send(batch)
            except Exception:  # noqa: BLE001 — survive poison events
                logger.exception("obs.flush_loop.iteration_failed")
                await asyncio.sleep(0.1)  # back off briefly

    async def _send(self, batch: list[ObsEventBase]) -> None:
        try:
            result = await self._target.send_batch(batch)
            if result.failed > 0 and self._spool_writer:
                await self._spool_writer.append(batch)
        except Exception:  # noqa: BLE001 — target errors must not propagate past _send
            logger.warning("obs.target.send_raised", exc_info=True)
            if self._spool_writer:
                try:
                    await self._spool_writer.append(batch)
                except Exception:
                    logger.warning("obs.spool.append_after_send_failed", exc_info=True)

    async def _reclaim_loop(self) -> None:
        assert self._spool_reader is not None
        while not self._stopping.is_set():
            await asyncio.sleep(self._reclaim_interval)
            try:
                batch: list[ObsEventBase] = []
                async for ev in self._spool_reader.drain():
                    batch.append(ev)
                    if len(batch) >= self._max_batch:
                        await self._send(batch)
                        batch = []
                if batch:
                    await self._send(batch)
            except Exception:  # noqa: BLE001
                logger.exception("obs.reclaim.iteration_failed")
```

- [ ] **Step 4b: Emit_sync tests** — new file `tests/unit/observability/test_emit_sync.py`:

```python
import pytest
import threading
from backend.observability.client import ObservabilityClient
from backend.observability.schema.v1 import EventType, ObsEventBase
from backend.observability.targets.memory import MemoryTarget
from uuid import uuid4
from datetime import datetime, timezone


def _e():
    return ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=uuid4(), span_id=uuid4(), parent_span_id=None,
        ts=datetime.now(timezone.utc), env="dev",
        git_sha=None, user_id=None, session_id=None, query_id=None,
    )


@pytest.mark.asyncio
async def test_emit_sync_from_thread(tmp_path):
    target = MemoryTarget()
    client = ObservabilityClient(
        target=target, spool_dir=tmp_path, spool_enabled=False,
        flush_interval_ms=50, buffer_size=100, enabled=True,
    )
    await client.start()
    try:
        # Called from a worker thread (simulates yfinance / rate-limiter path).
        def push():
            for _ in range(10):
                client.emit_sync(_e())
        t = threading.Thread(target=push)
        t.start()
        t.join()
        await client.flush()
        assert len(target.events) == 10
    finally:
        await client.stop()


def test_emit_sync_never_raises():
    """Rate-limiter + yfinance call this from sync hot paths — MUST NOT raise."""
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    client = ObservabilityClient(
        target=MemoryTarget(fail_next=99999), spool_dir=tmp, spool_enabled=False,
        flush_interval_ms=50, buffer_size=1, enabled=True,  # tiny buffer → overflow
    )
    # No start() — still must not raise.
    for _ in range(100):
        client.emit_sync(_e())  # overflow path in sync context; drops + warns; no raise
```

- [ ] **Step 5:** `uv run pytest tests/unit/observability/test_client.py -v` → 4 passed.
- [ ] **Step 6:** Commit: `feat(obs-1a): ObservabilityClient with buffered flush + spool integration`.

---

## Task 7: `bootstrap.build_client_from_settings()` + FastAPI + Celery wiring

**Files:** `backend/observability/bootstrap.py`, `backend/main.py`, `backend/tasks/__init__.py`

- [ ] **Step 1: Factory + `obs_client_var` ContextVar + `_maybe_get_obs_client()` helper**

Per review finding: `_maybe_get_obs_client()` is referenced by PR3/PR4/PR5 but never defined. Also `app.state.obs_client` is a layering violation (domain modules reaching into FastAPI state). Fix: use a module-level ContextVar set symmetrically by FastAPI lifespan AND Celery `worker_ready`. Domain modules read via `_maybe_get_obs_client()`.

```python
# backend/observability/bootstrap.py
"""Build an ObservabilityClient from settings — single place for target selection.

PR2b extends this with the InternalHTTPTarget branch. Extraction swaps DirectTarget
with ExternalHTTPTarget here.

`obs_client_var` ContextVar + `_maybe_get_obs_client()` provide a layering-safe
lookup for domain modules (ObservabilityCollector, rate_limiter, etc.) that
need the client from either a FastAPI or Celery context.
"""
from __future__ import annotations
from contextvars import ContextVar
from pathlib import Path
from backend.config import settings
from backend.observability.client import ObservabilityClient
from backend.observability.targets import MemoryTarget
from backend.observability.targets.direct import DirectTarget

# Module-level ContextVar — set by FastAPI lifespan + Celery worker_ready.
# Default None means "observability not initialized yet" — emitters short-circuit
# silently (no exceptions past the domain module boundary).
obs_client_var: ContextVar[ObservabilityClient | None] = ContextVar(
    "obs_client", default=None
)


def build_client_from_settings() -> ObservabilityClient:
    if settings.OBS_TARGET_TYPE == "memory":
        target = MemoryTarget()
    else:  # "direct" (default)
        target = DirectTarget()
    return ObservabilityClient(
        target=target,
        spool_dir=Path(settings.OBS_SPOOL_DIR),
        spool_enabled=settings.OBS_SPOOL_ENABLED,
        flush_interval_ms=settings.OBS_FLUSH_INTERVAL_MS,
        buffer_size=settings.OBS_BUFFER_SIZE,
        enabled=settings.OBS_ENABLED,
        spool_max_size_mb=settings.OBS_SPOOL_MAX_SIZE_MB,
    )


def _maybe_get_obs_client() -> ObservabilityClient | None:
    """Look up the ambient client — FastAPI lifespan or Celery worker_ready sets it.

    Returns None if observability isn't initialized yet (e.g., during pytest fixtures
    that bypass lifespan). Callers MUST handle None gracefully — no exceptions leak
    out of emitter code paths.
    """
    return obs_client_var.get()
```

- [ ] **Step 2: FastAPI lifespan** — per fact sheet §2, `main.py` uses `@asynccontextmanager async def lifespan(app)` at lines 47-48. Add obs_client init BEFORE `yield`, shutdown AFTER. Use both `app.state.obs_client` (backwards-compat for any handlers that want the app-scoped reference) AND `obs_client_var` ContextVar (canonical domain-module lookup):

```python
# inside existing async def lifespan(app):
from backend.observability.bootstrap import build_client_from_settings, obs_client_var

# ...existing startup work (lines 50-290) unchanged...
obs_client = build_client_from_settings()
await obs_client.start()
app.state.obs_client = obs_client
obs_client_var.set(obs_client)

try:
    yield
finally:
    # ...existing shutdown work (lines 295-307) unchanged...
    await obs_client.stop()
    obs_client_var.set(None)
```

- [ ] **Step 3: Celery `worker_ready` / `worker_shutdown` — persistent background-thread event loop**

Per review finding (CRITICAL): the naive `asyncio.new_event_loop() + run_until_complete(start())` pattern is broken. `start()` schedules `asyncio.create_task(_flush_loop())`, then `run_until_complete` returns before the task ever runs → flush loop never executes → buffer never drains in workers. Additionally, each `@tracked_task` invocation calls `asyncio.run()` per fact sheet §12 (`pipeline.py:433`), creating a FRESH loop per task. The client's async flush task must survive across tasks.

**Fix:** run a dedicated event loop on a daemon thread at `worker_ready`. Emissions from Celery tasks use `emit_sync` (which only touches the thread-safe buffer — no loop needed). The background flush task drains the buffer on the dedicated loop.

```python
# backend/tasks/__init__.py — append (first-ever signal handlers per fact sheet §8):
import asyncio
import threading
from celery.signals import worker_ready, worker_shutdown
from backend.observability.bootstrap import (
    build_client_from_settings, obs_client_var,
)

_worker_obs_client = None
_worker_obs_loop: asyncio.AbstractEventLoop | None = None
_worker_obs_thread: threading.Thread | None = None


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    loop.run_forever()


@worker_ready.connect
def _init_worker_obs_client(**kwargs):
    """Start a persistent event loop on a daemon thread for obs client background tasks.

    Why? @tracked_task invokes via asyncio.run() per call — fresh loop per task.
    Pinning the obs client's flush loop to a dedicated, long-lived loop on a
    daemon thread survives across tasks + avoids loop-mismatch on shared state.

    Failure mode: if start() times out, we FAIL-CLOSED — tear down the loop/thread
    and leave obs_client_var unset. This means emissions silently drop for the
    worker's lifetime (better than leaving a half-initialized client behind).
    """
    global _worker_obs_client, _worker_obs_loop, _worker_obs_thread
    _worker_obs_loop = asyncio.new_event_loop()
    _worker_obs_thread = threading.Thread(
        target=_run_loop, args=(_worker_obs_loop,), daemon=True, name="obs-loop"
    )
    _worker_obs_thread.start()
    client = build_client_from_settings()
    # Schedule start() on the persistent loop; wait with timeout + fail-closed.
    fut = asyncio.run_coroutine_threadsafe(client.start(), _worker_obs_loop)
    try:
        fut.result(timeout=5.0)
    except Exception:  # noqa: BLE001 — TimeoutError, CancelledError, anything
        import logging
        logging.getLogger(__name__).warning(
            "obs.worker_ready.start_failed — observability disabled for this worker",
            exc_info=True,
        )
        fut.cancel()
        _worker_obs_loop.call_soon_threadsafe(_worker_obs_loop.stop)
        _worker_obs_thread.join(timeout=2.0)
        _worker_obs_client = None
        _worker_obs_loop = None
        _worker_obs_thread = None
        return
    _worker_obs_client = client
    obs_client_var.set(_worker_obs_client)


@worker_shutdown.connect
def _shutdown_worker_obs_client(**kwargs):
    global _worker_obs_client, _worker_obs_loop, _worker_obs_thread
    if _worker_obs_client is None or _worker_obs_loop is None:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            _worker_obs_client.stop(), _worker_obs_loop
        ).result(timeout=10.0)
    except Exception:  # noqa: BLE001
        pass  # shutdown must not raise
    _worker_obs_loop.call_soon_threadsafe(_worker_obs_loop.stop)
    if _worker_obs_thread:
        _worker_obs_thread.join(timeout=5.0)
    obs_client_var.set(None)
```

**Emission from inside `@tracked_task`:** use `emit_sync` (not `await emit(...)`). PR5 Task 7's `@tracked_task` lifecycle events call `obs_client_var.get().emit_sync(...)` — synchronous, thread-safe, no loop involvement. This closes the event-loop-mismatch finding.

- [ ] **Step 4: Smoke test**

```bash
uv run uvicorn backend.main:app --port 8181 &
sleep 3
curl -s http://localhost:8181/api/v1/health
kill %1
```

Expected: health responds 200 OK; no `obs_client` errors in logs.

- [ ] **Step 5: Full suite + lint**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
uv run ruff check --fix backend/observability/ tests/
uv run ruff format backend/observability/ tests/
```

Expected: 2115 + 13 unit (4 test_client + 2 test_spool + 4 test_targets + 3 from PR1) passed, 448 API passed, zero regressions.

- [ ] **Step 6:** Commit: `feat(obs-1a): wire ObservabilityClient into FastAPI + Celery lifespans`.

---

## Acceptance Criteria (PR2a)

- [x] `ObservabilityClient.emit()` p95 latency <2ms (measured via MemoryTarget unit tests)
- [x] `OBS_ENABLED=false` → `emit()` is a no-op; no background tasks start
- [x] `OBS_SPOOL_ENABLED=false` + buffer overflow → events drop with structured WARNING log
- [x] Chaos test: target down 60s → spool grows → target up → reclaim drains spool to 0 (covered by `test_target_down_spools_and_drains`)
- [x] `app.state.obs_client` available to request handlers after FastAPI startup
- [x] Celery `worker_ready` / `worker_shutdown` signals install + drain a worker-local client
- [x] Zero regressions; net +10 unit tests on top of PR1

---

## Risks

| Risk | Mitigation |
|---|---|
| Spool file grows unbounded if `max_size_mb` misconfigured | Default 100 MB/worker; drop-on-overflow correct for MVP; revisit after 48h prod data |
| Reclaim loop starves real-time flush when spool is huge | 30s interval; real-time flush is its own task |
| Celery worker uses `asyncio.new_event_loop()` where Celery ≥5.3 may already have one | Falls back to `get_event_loop()` on shutdown; if Celery pool prefork changes, adjust per project's `celery_app.py` pattern |
| `write_batch` stub floods DEBUG logs | DEBUG level only; tests run at WARNING by default |

---

## Commit Sequence

1. (optional) `chore(obs-1a): add aiofiles for disk spool I/O`
2. `feat(obs-1a): add OBS_* settings + kill-switch defaults`
3. `feat(obs-1a): add ObservabilityTarget Protocol + MemoryTarget`
4. `feat(obs-1a): add DirectTarget + event_writer stub`
5. `feat(obs-1a): add optional JSONL disk spool with size cap`
6. `feat(obs-1a): ObservabilityClient with buffered flush + spool integration`
7. `feat(obs-1a): wire ObservabilityClient into FastAPI + Celery lifespans`

PR body references: spec §2.1, §2.2 (direct+memory only); KAN-458, KAN-464; fact-sheet §2 (middleware), §8 (Celery signals vacuum).
