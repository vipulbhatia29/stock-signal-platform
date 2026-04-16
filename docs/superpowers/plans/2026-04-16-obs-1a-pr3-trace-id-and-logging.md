# Obs 1a PR3 — Canonical `trace_id` + Celery Propagation + Structured JSON Logging

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Every HTTP request gets a canonical UUIDv7 `trace_id`. It propagates via `ContextVar` through the async call stack, via Celery task headers across workers, appears in the `X-Trace-Id` response header, and is injected into every structured log line. CORS is updated so the frontend can read it. The `span()` async contextmanager builds causality trees via `parent_span_id`.

**Architecture:** A `TraceIdMiddleware` sits outside `ErrorHandlerMiddleware` so errors carry trace_id. Three Celery signals (`before_task_publish`, `task_prerun`, `task_postrun`) read/write trace_id to task headers. `structlog` is configured once at app + worker startup; processors inject `trace_id`/`span_id`/`user_id` from ContextVars on every log record.

**Tech Stack:** FastAPI middleware, `contextvars`, Celery signals, `structlog` (already in deps), `uuid-utils` (PR1).

**Spec reference:** `docs/superpowers/specs/2026-04-16-obs-1a-foundations-design.md` §2.3, §2.4, §3.5, §3.6.

**Prerequisites:** PR1 (uuid-utils), PR2a (SDK ready for events that carry trace_id).

**Dependency for:** PR4 (external API spans need trace_id), PR5 (legacy-emitter events carry trace_id).

**Fact-sheet anchors:** Middleware order outer→inner: ErrorHandler, CORS, CSRF, HttpMetrics (§2). CORS `expose_headers` NOT set (§2) — must be added. Zero existing Celery signal handlers (§8). `structlog` already in deps, not initialized (§9, §11). `backend/observability/context.py` already has ContextVars for session_id, query_id, agent_type, agent_instance_id (§7) — extend with trace_id fields.

---

## File Structure

**Create:**
- `backend/middleware/trace_id.py` — `TraceIdMiddleware`
- `backend/observability/span.py` — `span()` async contextmanager
- `backend/tasks/celery_trace_propagation.py` — `before_task_publish` / `task_prerun` / `task_postrun` handlers
- `backend/core/logging.py` — `configure_structlog()` function
- `tests/unit/observability/test_trace_id.py` — middleware + span + ContextVar behavior
- `tests/unit/tasks/test_celery_trace_propagation.py` — signal behavior via Celery test-runner
- `tests/unit/core/test_logging.py` — structlog enricher behavior

**Modify:**
- `backend/observability/context.py` — add `trace_id_var`, `span_id_var`, `parent_span_id_var` ContextVars + getters
- `backend/main.py` — register middleware (outside ErrorHandler per fact sheet §2); add `X-Trace-Id` to `CORSMiddleware(expose_headers=[...])`; call `configure_structlog()` at startup
- `backend/tasks/__init__.py` — import `celery_trace_propagation` so handlers register at import time; add `configure_structlog()` to `worker_ready` (alongside PR2a's `build_client_from_settings`)

---

## Task 1: Extend ContextVars + `span()` helper

**Files:** `backend/observability/context.py`, `backend/observability/span.py`, `tests/unit/observability/test_trace_id.py`

- [ ] **Step 1: Failing test** — ContextVar defaults + nested `span()`:

```python
# tests/unit/observability/test_trace_id.py (Task 1 tests only; Task 2-3 append)
from uuid import UUID
import pytest
from backend.observability.context import (
    current_trace_id, current_span_id, current_parent_span_id,
    trace_id_var, span_id_var, parent_span_id_var,
)
from backend.observability.span import span


def test_context_vars_default_none():
    assert current_trace_id() is None
    assert current_span_id() is None
    assert current_parent_span_id() is None


@pytest.mark.asyncio
async def test_span_sets_parent_link():
    root_trace = UUID("01234567-89ab-7def-8123-456789abcdef")
    trace_id_var.set(root_trace)
    try:
        async with span("outer") as outer:
            assert current_trace_id() == root_trace
            assert current_span_id() == outer.span_id
            assert current_parent_span_id() is None
            async with span("inner") as inner:
                assert inner.parent_span_id == outer.span_id
                assert current_span_id() == inner.span_id
            # after inner exits, current_span_id resumes outer
            assert current_span_id() == outer.span_id
    finally:
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)
```

- [ ] **Step 2: Implement**

Extend `backend/observability/context.py` by appending (the existing file has session/query/agent ContextVars per fact sheet §7):

```python
from contextvars import ContextVar
from uuid import UUID

trace_id_var: ContextVar[UUID | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[UUID | None] = ContextVar("span_id", default=None)
parent_span_id_var: ContextVar[UUID | None] = ContextVar("parent_span_id", default=None)


def current_trace_id() -> UUID | None:
    return trace_id_var.get()


def current_span_id() -> UUID | None:
    return span_id_var.get()


def current_parent_span_id() -> UUID | None:
    return parent_span_id_var.get()
```

Create `backend/observability/span.py`:

```python
"""`span()` async contextmanager — builds causality trees.

Each nested span inherits the ambient trace_id and sets its own UUIDv7 span_id;
parent_span_id = the span_id that was current on entry. On exit, ContextVars are
restored so siblings see the parent span_id, not the just-closed one.
"""
from __future__ import annotations
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator
from uuid import UUID
from uuid_utils import uuid7
from backend.observability.context import (
    parent_span_id_var, span_id_var, trace_id_var,
)


@dataclass(frozen=True)
class Span:
    name: str
    trace_id: UUID | None
    span_id: UUID
    parent_span_id: UUID | None


@asynccontextmanager
async def span(name: str) -> AsyncIterator[Span]:
    prev_span = span_id_var.get()
    prev_parent = parent_span_id_var.get()
    new_span = UUID(bytes=uuid7().bytes)
    span_tok = span_id_var.set(new_span)
    parent_tok = parent_span_id_var.set(prev_span)  # previous becomes parent
    try:
        yield Span(
            name=name,
            trace_id=trace_id_var.get(),
            span_id=new_span,
            parent_span_id=prev_span,
        )
    finally:
        span_id_var.reset(span_tok)
        parent_span_id_var.reset(parent_tok)
```

Note: `uuid_utils.uuid7()` returns a `uuid_utils.UUID` object; we cast to stdlib `UUID` via `.bytes` so Pydantic accepts it uniformly.

- [ ] **Step 3:** `uv run pytest tests/unit/observability/test_trace_id.py -v` → 2 passed.
- [ ] **Step 4:** Commit: `feat(obs-1a): add trace_id ContextVars + span() contextmanager`.

---

## Task 2: `TraceIdMiddleware` + CORS expose-headers

**Files:** `backend/middleware/trace_id.py`, `backend/main.py`, append to `test_trace_id.py`

- [ ] **Step 1: Failing test** — middleware generates new trace_id or adopts incoming header, injects into response, sets ContextVar during request lifetime:

```python
# append to tests/unit/observability/test_trace_id.py
import httpx
import pytest


@pytest.mark.asyncio
async def test_trace_id_middleware_generates_new(async_client):
    # No X-Trace-Id on request → middleware generates a UUIDv7.
    resp = await async_client.get("/api/v1/health")
    assert resp.status_code == 200
    trace = resp.headers.get("X-Trace-Id")
    assert trace is not None
    # UUIDv7 has "7" in the 13th hex position.
    assert trace[14] == "7"


@pytest.mark.asyncio
async def test_trace_id_middleware_adopts_incoming(async_client):
    incoming = "01234567-89ab-7def-8123-456789abcdef"
    resp = await async_client.get("/api/v1/health", headers={"X-Trace-Id": incoming})
    assert resp.headers["X-Trace-Id"] == incoming


@pytest.mark.asyncio
async def test_trace_id_middleware_rejects_malformed(async_client):
    # Garbage → generates new (does not echo untrusted input).
    resp = await async_client.get("/api/v1/health", headers={"X-Trace-Id": "not-a-uuid"})
    assert resp.status_code == 200
    assert resp.headers["X-Trace-Id"] != "not-a-uuid"


@pytest.mark.asyncio
async def test_cors_expose_headers_includes_trace_id(async_client):
    """Per spec §2.3 — frontend must be able to read X-Trace-Id.

    Preflight OPTIONS returns access-control-expose-headers with X-Trace-Id.
    """
    resp = await async_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    # On an actual GET, the header exposure shows up on the response.
    resp = await async_client.get(
        "/api/v1/health", headers={"Origin": "http://localhost:3000"}
    )
    expose = resp.headers.get("access-control-expose-headers", "")
    assert "X-Trace-Id" in expose or "x-trace-id" in expose.lower()
```

- [ ] **Step 2: Implement the middleware**

```python
# backend/middleware/trace_id.py
"""Generate-or-adopt a canonical trace_id on every HTTP request.

- Generates UUIDv7 if no valid X-Trace-Id header
- Adopts incoming X-Trace-Id if parseable as UUID (not strictly v7 — forward-compat)
- Sets ContextVars so downstream code + logs see it
- Injects X-Trace-Id into response headers
- MUST be registered OUTSIDE ErrorHandlerMiddleware so errors carry trace_id
"""
from __future__ import annotations
from uuid import UUID
from uuid_utils import uuid7
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from backend.observability.context import parent_span_id_var, span_id_var, trace_id_var


class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Trace-Id")
        trace_id: UUID | None = None
        if incoming:
            try:
                trace_id = UUID(incoming)
            except ValueError:
                trace_id = None
        if trace_id is None:
            trace_id = UUID(bytes=uuid7().bytes)

        trace_tok = trace_id_var.set(trace_id)
        span_tok = span_id_var.set(None)
        parent_tok = parent_span_id_var.set(None)
        try:
            response: Response = await call_next(request)
        finally:
            trace_id_var.reset(trace_tok)
            span_id_var.reset(span_tok)
            parent_span_id_var.reset(parent_tok)
        response.headers["X-Trace-Id"] = str(trace_id)
        return response
```

- [ ] **Step 3: Wire into `backend/main.py`** — per fact sheet §2, middleware is registered in registration order (outer-most LAST). Add `TraceIdMiddleware` AFTER `ErrorHandlerMiddleware` so it executes outermost:

```python
from backend.middleware.trace_id import TraceIdMiddleware

# ... existing middleware registrations unchanged ...
app.add_middleware(ErrorHandlerMiddleware)   # existing, line ~360
app.add_middleware(TraceIdMiddleware)         # NEW — outermost
```

- [ ] **Step 4: CORS expose-headers** — per fact sheet §2, CORS currently does not set `expose_headers`. Update `backend/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Trace-Id"],
    expose_headers=["X-Trace-Id"],
)
```

(`X-Trace-Id` added to both `allow_headers` and `expose_headers` — the frontend both sends it on continued traces and reads it off responses.)

- [ ] **Step 5:** `uv run pytest tests/unit/observability/test_trace_id.py -v` → all passed.
- [ ] **Step 6:** Commit: `feat(obs-1a): add TraceIdMiddleware + X-Trace-Id CORS exposure`.

---

## Task 3: Celery trace propagation

**Files:** `backend/tasks/celery_trace_propagation.py`, `backend/tasks/__init__.py`, `tests/unit/tasks/test_celery_trace_propagation.py`

- [ ] **Step 1: Failing test** — a publisher with a trace_id injects it into headers; a task picked up from the queue sets its own ContextVar to that trace_id; span_id becomes the first span under that trace. Use `celery.contrib.testing.worker.start_worker` or the project's existing Celery test pattern.

```python
# tests/unit/tasks/test_celery_trace_propagation.py
from uuid import UUID
import pytest
from backend.observability.context import current_trace_id, current_parent_span_id
from backend.tasks import celery_app


@celery_app.task(name="tests.obs_trace_probe")
def _probe_task():
    return {
        "trace_id": str(current_trace_id()) if current_trace_id() else None,
        "parent_span_id": str(current_parent_span_id()) if current_parent_span_id() else None,
    }


def test_publisher_injects_trace_header(monkeypatch):
    """before_task_publish reads ContextVar → injects into task headers."""
    from backend.observability.context import trace_id_var
    trace_id_var.set(UUID("01234567-89ab-7def-8123-456789abcdef"))
    try:
        async_result = _probe_task.apply_async()
        # async_result.headers is where Celery stores per-task headers
        # (project wires to carry 'obs_trace_id' key)
        assert async_result.headers.get("obs_trace_id") == "01234567-89ab-7def-8123-456789abcdef"
    finally:
        trace_id_var.set(None)


def test_consumer_reads_trace_header(celery_worker):
    """task_prerun reads headers → sets ContextVar; probe task returns observed values."""
    from backend.observability.context import trace_id_var
    trace_id_var.set(UUID("01234567-89ab-7def-8123-456789abcdef"))
    try:
        result = _probe_task.apply_async().get(timeout=5)
        assert result["trace_id"] == "01234567-89ab-7def-8123-456789abcdef"
    finally:
        trace_id_var.set(None)
```

(If project doesn't already have a `celery_worker` fixture, follow project convention for Celery tests — check `tests/conftest.py`. Fallback: use `apply_async(connection=...)` against a memory broker.)

- [ ] **Step 2:** Run → FAIL.

- [ ] **Step 3: Implement the signals — use token-reset pattern to prevent ContextVar leaks**

Per review finding (HIGH): the naive `trace_id_var.set(...)` at `task_prerun` + unconditional `.set(None)` at `task_postrun` leaks ContextVars across tasks if `task_prerun` raises (`.set(None)` never runs). Also ties us to specific thread affinity. Fix: capture `Token` objects at prerun on a module-level per-task-id dict; reset via tokens at postrun (survives exception in either handler).

```python
# backend/tasks/celery_trace_propagation.py
"""Celery signals that propagate trace_id + span_id across worker boundaries.

- before_task_publish: read ContextVar → write to task headers
- task_prerun: read headers → set ContextVars; store reset Tokens per task_id
- task_postrun: reset ContextVars via Tokens so a prerun exception can't leak
"""
from __future__ import annotations
import logging
from contextvars import Token
from uuid import UUID
from uuid_utils import uuid7
from celery.signals import before_task_publish, task_postrun, task_prerun

from backend.observability.context import (
    parent_span_id_var, span_id_var, trace_id_var,
)

logger = logging.getLogger(__name__)

_HEADER_TRACE_ID = "obs_trace_id"
_HEADER_SPAN_ID = "obs_parent_span_id"

# Per-task reset tokens — keyed by Celery task_id so overlapping tasks in the same
# worker thread (eventlet/gevent pools) don't step on each other's Tokens.
_TOKENS: dict[str, tuple[Token, Token, Token]] = {}


@before_task_publish.connect
def _inject_trace_headers(sender=None, headers=None, **_):
    if headers is None:
        return
    trace_id = trace_id_var.get()
    span_id = span_id_var.get()
    if trace_id is not None:
        headers[_HEADER_TRACE_ID] = str(trace_id)
    if span_id is not None:
        headers[_HEADER_SPAN_ID] = str(span_id)


@task_prerun.connect
def _adopt_trace_headers(task_id=None, task=None, **kwargs):
    req = getattr(task, "request", None)
    if req is None:
        return
    headers = getattr(req, "headers", {}) or {}
    trace_raw = headers.get(_HEADER_TRACE_ID)
    parent_raw = headers.get(_HEADER_SPAN_ID)
    trace_id = _parse(trace_raw)
    if trace_id is None:
        # Beat-triggered or publisher without trace → new root.
        trace_id = UUID(bytes=uuid7().bytes)

    # Set via tokens so postrun can reset even if a later handler raises.
    trace_tok = trace_id_var.set(trace_id)
    span_tok = span_id_var.set(UUID(bytes=uuid7().bytes))
    parent_tok = parent_span_id_var.set(_parse(parent_raw))
    if task_id is not None:
        _TOKENS[task_id] = (trace_tok, span_tok, parent_tok)


@task_postrun.connect
def _clear_trace(task_id=None, **_):
    tokens = _TOKENS.pop(task_id, None) if task_id is not None else None
    if tokens is None:
        # Fallback: set to None unconditionally. Handles the "prerun raised before
        # we stored tokens" case so the NEXT task on this context isn't polluted.
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)
        return
    trace_tok, span_tok, parent_tok = tokens
    try:
        trace_id_var.reset(trace_tok)
        span_id_var.reset(span_tok)
        parent_span_id_var.reset(parent_tok)
    except ValueError:
        # Token was created in a different Context (e.g., eventlet switch).
        # Fall back to unconditional set-None so the ambient context is cleared.
        logger.warning("obs.trace.token_reset_failed", extra={"task_id": task_id})
        trace_id_var.set(None)
        span_id_var.set(None)
        parent_span_id_var.set(None)


def _parse(raw: str | None) -> UUID | None:
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None
```

Import the module at Celery init so signals register:

```python
# backend/tasks/__init__.py (append after existing imports)
from backend.tasks import celery_trace_propagation  # noqa: F401 — signal handlers register on import
```

- [ ] **Step 4:** Run signal tests → all passed.
- [ ] **Step 5:** Commit: `feat(obs-1a): propagate trace_id through Celery task headers`.

---

## Task 4: Structured JSON logging via structlog

**Files:** `backend/core/logging.py`, `backend/main.py`, `backend/tasks/__init__.py`, `tests/unit/core/test_logging.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/core/test_logging.py
import io
import json
import logging
from uuid import UUID
import pytest
import structlog
from backend.core.logging import configure_structlog
from backend.observability.context import span_id_var, trace_id_var


@pytest.fixture
def log_buffer(monkeypatch) -> io.StringIO:
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    configure_structlog()
    yield buf


def test_log_line_is_json_with_trace_id(log_buffer):
    trace = UUID("01234567-89ab-7def-8123-456789abcdef")
    trace_id_var.set(trace)
    try:
        structlog.get_logger("test").info("hello", foo=1)
        line = log_buffer.getvalue().strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["event"] == "hello"
        assert payload["foo"] == 1
        assert payload["trace_id"] == str(trace)
        assert "timestamp" in payload
        assert payload["level"] == "info"
    finally:
        trace_id_var.set(None)


def test_log_line_omits_trace_id_when_absent(log_buffer):
    # Default is None; processor must drop the key rather than emit null.
    structlog.get_logger("test").info("no-trace")
    line = log_buffer.getvalue().strip().splitlines()[-1]
    payload = json.loads(line)
    assert "trace_id" not in payload
```

- [ ] **Step 2: Implement**

```python
# backend/core/logging.py
"""Structured JSON logging configuration — structlog.

Per spec §2.4 — canonical fields on every log line: timestamp (ISO-8601 UTC),
level, logger, message, trace_id (from ContextVar, nullable — omitted if None),
span_id, user_id, env, git_sha, plus any extra= kwargs.

Call configure_structlog() once at FastAPI startup and once at Celery worker_ready.
Test fixtures disable output for readability.
"""
from __future__ import annotations
import logging
import sys
import structlog
from structlog.contextvars import merge_contextvars
from backend.config import settings
from backend.observability.context import (
    current_span_id, current_trace_id,
)


def _inject_trace_context(logger, method_name, event_dict):
    tid = current_trace_id()
    sid = current_span_id()
    if tid is not None:
        event_dict["trace_id"] = str(tid)
    if sid is not None:
        event_dict["span_id"] = str(sid)
    return event_dict


def _inject_env(logger, method_name, event_dict):
    event_dict.setdefault("env", settings.APP_ENV if hasattr(settings, "APP_ENV") else "dev")
    return event_dict


def configure_structlog() -> None:
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=logging.INFO,
    )
    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _inject_trace_context,
            _inject_env,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
```

Wire it:

```python
# backend/main.py (in lifespan startup, near the top before any logger.info calls)
from backend.core.logging import configure_structlog
configure_structlog()

# backend/tasks/__init__.py — inside worker_ready handler (added in PR2a):
#   configure_structlog()  # BEFORE build_client_from_settings()
```

(Update the `worker_ready` handler from PR2a to call `configure_structlog()` first.)

- [ ] **Step 3:** `uv run pytest tests/unit/core/test_logging.py -v` → 2 passed.
- [ ] **Step 4:** Commit: `feat(obs-1a): configure structlog with trace_id/span_id enrichers`.

---

## Task 5: Full-suite sanity + lint + smoke

- [ ] `uv run pytest tests/unit/ tests/api/ -q --tb=short` → baseline + net ~8 new tests passed, zero regressions.
- [ ] `uv run ruff check --fix backend/middleware/ backend/observability/ backend/core/ backend/tasks/ tests/`
- [ ] `uv run ruff format backend/middleware/ backend/observability/ backend/core/ backend/tasks/ tests/`
- [ ] Smoke: `uv run uvicorn backend.main:app --port 8181 &` → `curl -si http://localhost:8181/api/v1/health | grep -i x-trace-id` → header present; logs on stdout are JSON with `trace_id` field.
- [ ] Celery smoke: `uv run celery -A backend.tasks worker --loglevel=INFO` → worker_ready handler fires; startup log lines are JSON.

---

## Acceptance Criteria (PR3)

- [x] Every response has a valid UUIDv7 `X-Trace-Id` header (per-test)
- [x] Incoming valid UUID `X-Trace-Id` is adopted; garbage is rejected and a new id generated
- [x] CORS `Access-Control-Expose-Headers` includes `X-Trace-Id`; frontend can read it
- [x] A task published from a trace-carrying context receives the trace_id in its headers
- [x] A task picked up by a worker sets `current_trace_id()` to the incoming header value
- [x] Beat-triggered tasks (no incoming trace) get a new root `trace_id`
- [x] Structlog logs emit NDJSON with `trace_id`, `span_id`, `timestamp`, `level` fields (trace_id omitted when ContextVar is None)
- [x] `span()` contextmanager correctly sets `parent_span_id` = previous span_id
- [x] Zero regressions to baseline test count

---

## Risks

| Risk | Mitigation |
|---|---|
| Middleware order wrong → trace_id missing on error responses | `TraceIdMiddleware` registered LAST so it wraps everything including ErrorHandlerMiddleware; verified in tests |
| Structlog output breaks an existing log-parsing tool | No external log parsers currently per fact sheet §9; migration is additive; existing `logger.info(...)` calls continue to work |
| Celery `task_prerun` handler leaks ContextVars across tasks in a shared event loop | `task_postrun` resets all three ContextVars unconditionally |
| `uuid_utils.uuid7()` returns a `uuid_utils.UUID` incompatible with stdlib in some contexts | Wrap via `UUID(bytes=uuid7().bytes)` — stdlib object from the start |
| Incoming `X-Trace-Id` from malicious client could be used to correlate sessions | Middleware adopts incoming only if it's a valid UUID; no trust assertion beyond that; PII redaction handled in 1b |

---

## Commit Sequence

1. `feat(obs-1a): add trace_id ContextVars + span() contextmanager`
2. `feat(obs-1a): add TraceIdMiddleware + X-Trace-Id CORS exposure`
3. `feat(obs-1a): propagate trace_id through Celery task headers`
4. `feat(obs-1a): configure structlog with trace_id/span_id enrichers`

PR body references: spec §2.3, §2.4, §3.5, §3.6; KAN-458, KAN-464; fact-sheet §2 (middleware order + CORS), §8 (Celery signal vacuum), §9 (structlog not initialized).
