# Obs 1a PR2b — Ingest Endpoint + InternalHTTPTarget

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Add `InternalHTTPTarget` and the `POST /obs/v1/events` ingestion endpoint so the HTTP ingestion path can be exercised in integration tests and stays validated ahead of microservice extraction. Extend `bootstrap.build_client_from_settings()` with the `internal_http` branch and the `OBS_INGEST_SECRET` / `OBS_TARGET_URL` settings.

**Architecture:** Adds a third target implementation that `httpx.post`s a batch to `/obs/v1/events`. The endpoint validates the `X-Obs-Secret` header, schema version, and batch size, then delegates to `event_writer.write_batch`. Used in integration tests; also the transition path at extraction time (the only change at extraction is swapping `OBS_TARGET_URL` to the external service host).

**Tech Stack:** FastAPI, httpx, Pydantic v2.

**Spec reference:** `docs/superpowers/specs/2026-04-16-obs-1a-foundations-design.md` §2.2 (InternalHTTPTarget), §2.2b (ingest endpoint).

**Prerequisites:** PR1 (schema), PR2a (SDK + targets base).

**Dependency for:** PR3-PR5 do not depend on this, but they can consume it in integration tests.

**Fact-sheet anchors:** Router mount pattern uses `/api/v1/*` for application routes (§2); the ingest endpoint uses `/obs/v1/events` (no `/api/v1` prefix) to match spec §2.2b. CORS is configured on `settings.cors_origins_list` (§2) — ingest endpoint is service-internal so CORS is not a factor.

---

## File Structure

**Create:**
- `backend/observability/targets/internal_http.py` — `InternalHTTPTarget`
- `backend/observability/routers/__init__.py`, `backend/observability/routers/ingest.py` — `POST /obs/v1/events`
- `tests/api/observability/__init__.py` (empty)
- `tests/api/observability/test_ingest_endpoint.py`
- Append to `tests/unit/observability/test_targets.py` — InternalHTTPTarget unit tests

**Modify:**
- `backend/config.py` — extend `OBS_TARGET_TYPE` Literal to include `"internal_http"`; add `OBS_TARGET_URL`, `OBS_INGEST_SECRET`
- `backend/observability/bootstrap.py` — branch on `internal_http`
- `backend/observability/targets/__init__.py` — re-export `InternalHTTPTarget`
- `backend/main.py` — register the ingest router

---

## Task 1: Config additions

**Files:** `backend/config.py`

- [ ] **Step 1:** Change the `OBS_TARGET_TYPE` Literal in the `Settings` class:

```python
    OBS_TARGET_TYPE: Literal["direct", "memory", "internal_http"] = Field(
        "direct", description="Target adapter — direct DB write (default), self-HTTP, or memory (tests)"
    )
    OBS_TARGET_URL: str | None = Field(
        None, description="Base URL for internal_http / future external_http target. "
                          "Required when OBS_TARGET_TYPE=internal_http."
    )
    OBS_INGEST_SECRET: str | None = Field(
        None, description="Shared secret for POST /obs/v1/events X-Obs-Secret header. "
                          "Required when OBS_TARGET_TYPE=internal_http; set via env in prod."
    )
```

- [ ] **Step 2:** Smoke-test: `uv run python -c "from backend.config import settings; print(settings.OBS_TARGET_URL, settings.OBS_INGEST_SECRET)"` — should print `None None` unless set.
- [ ] **Step 3:** Commit: `feat(obs-1a): extend OBS_TARGET_TYPE with internal_http option`.

---

## Task 2: `InternalHTTPTarget`

**Files:** `backend/observability/targets/internal_http.py`, append to `tests/unit/observability/test_targets.py`, `backend/observability/targets/__init__.py`

- [ ] **Step 1: Failing test** — append:

```python
import httpx
from backend.observability.targets.internal_http import InternalHTTPTarget


class _StubTransport(httpx.MockTransport):
    def __init__(self, status: int = 202):
        self._status = status
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(self._status, json={"accepted": 1})


@pytest.mark.asyncio
async def test_internal_http_target_sends_batch():
    transport = _StubTransport(status=202)
    client = httpx.AsyncClient(transport=transport)
    target = InternalHTTPTarget(
        base_url="http://localhost:8181", secret="s3cret", client=client,
    )
    result = await target.send_batch([_event()])
    assert result.sent == 1
    assert target.last_error is None  # exposed via health()
    assert transport.last_request.headers.get("X-Obs-Secret") == "s3cret"
    assert transport.last_request.url.path == "/obs/v1/events"


@pytest.mark.asyncio
async def test_internal_http_target_handles_5xx():
    transport = _StubTransport(status=503)
    target = InternalHTTPTarget(
        base_url="http://localhost:8181", secret="s3cret",
        client=httpx.AsyncClient(transport=transport),
    )
    result = await target.send_batch([_event(), _event()])
    assert result.failed == 2
    assert result.error == "status_503"


@pytest.mark.asyncio
async def test_internal_http_target_handles_connection_error():
    async def _raise(request):
        raise httpx.ConnectError("refused")

    target = InternalHTTPTarget(
        base_url="http://localhost:8181", secret="s3cret",
        client=httpx.AsyncClient(transport=httpx.MockTransport(_raise)),
    )
    result = await target.send_batch([_event()])
    assert result.failed == 1
    assert result.error == "ConnectError"
```

- [ ] **Step 2:** Run — FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# backend/observability/targets/internal_http.py
"""POST events to `/obs/v1/events` on the same app (or future external host)."""
from __future__ import annotations
import httpx
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.targets.base import BatchResult, TargetHealth


class InternalHTTPTarget:
    def __init__(
        self,
        base_url: str,
        secret: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = base_url.rstrip("/") + "/obs/v1/events"
        self._secret = secret
        self._client = client or httpx.AsyncClient(timeout=5.0)
        self.last_error: str | None = None

    async def send_batch(self, events: list[ObsEventBase]) -> BatchResult:
        payload = {
            "events": [e.model_dump(mode="json") for e in events],
            "schema_version": "v1",
        }
        try:
            resp = await self._client.post(
                self._url, json=payload, headers={"X-Obs-Secret": self._secret}
            )
        except httpx.HTTPError as exc:
            self.last_error = type(exc).__name__
            return BatchResult(sent=0, failed=len(events), error=self.last_error)
        if resp.status_code == 202:
            self.last_error = None
            return BatchResult(sent=len(events), failed=0)
        self.last_error = f"status_{resp.status_code}"
        return BatchResult(sent=0, failed=len(events), error=self.last_error)

    async def health(self) -> TargetHealth:
        return TargetHealth(healthy=self.last_error is None, last_error=self.last_error)
```

Re-export in `backend/observability/targets/__init__.py`:

```python
from backend.observability.targets.internal_http import InternalHTTPTarget
# append to __all__
```

- [ ] **Step 4:** `uv run pytest tests/unit/observability/test_targets.py -v` → all green.
- [ ] **Step 5:** Commit: `feat(obs-1a): add InternalHTTPTarget`.

---

## Task 3: `POST /obs/v1/events` endpoint

**Files:** `backend/observability/routers/__init__.py`, `backend/observability/routers/ingest.py`, `tests/api/observability/__init__.py`, `tests/api/observability/test_ingest_endpoint.py`, `backend/main.py`

- [ ] **Step 1: Failing integration test**

```python
# tests/api/observability/test_ingest_endpoint.py
"""POST /obs/v1/events — validates ingest-endpoint contract."""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from backend.observability.schema.v1 import EventType, ObsEventBase


def _payload():
    return ObsEventBase(
        event_type=EventType.LLM_CALL,
        trace_id=uuid4(), span_id=uuid4(), parent_span_id=None,
        ts=datetime.now(timezone.utc), env="dev",
        git_sha=None, user_id=None, session_id=None, query_id=None,
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_ingest_accepts_valid_batch(async_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await async_client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 202
    assert resp.json() == {"accepted": 1}


@pytest.mark.asyncio
async def test_ingest_rejects_missing_secret(async_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await async_client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_rejects_wrong_secret(async_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await async_client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_rejects_oversized_batch(async_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await async_client.post(
        "/obs/v1/events",
        json={"events": [_payload()] * 501, "schema_version": "v1"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_ingest_rejects_unsupported_schema_version(async_client, monkeypatch):
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "testsecret")
    resp = await async_client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v99"},
        headers={"X-Obs-Secret": "testsecret"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ingest_rejects_when_secret_unset(async_client, monkeypatch):
    """Safety: if secret is None, all requests are 401 (fail-closed)."""
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", None)
    resp = await async_client.post(
        "/obs/v1/events",
        json={"events": [_payload()], "schema_version": "v1"},
        headers={"X-Obs-Secret": "anything"},
    )
    assert resp.status_code == 401
```

- [ ] **Step 2:** Run — FAIL (route not found → 404).

- [ ] **Step 3: Implement the router**

```python
# backend/observability/routers/ingest.py
"""POST /obs/v1/events — ingest endpoint for InternalHTTPTarget / future ExternalHTTPTarget."""
from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel
from backend.config import settings
from backend.observability.schema.v1 import ObsEventBase
from backend.observability.service.event_writer import write_batch

router = APIRouter(tags=["observability-ingest"])

MAX_EVENTS_PER_BATCH = 500


class IngestBatch(BaseModel):
    events: list[ObsEventBase]
    schema_version: str


@router.post("/obs/v1/events", status_code=status.HTTP_202_ACCEPTED)
async def ingest_events(
    batch: IngestBatch,
    x_obs_secret: str | None = Header(default=None, alias="X-Obs-Secret"),
) -> dict[str, int]:
    # Fail-closed: no secret configured means no one can POST.
    if not settings.OBS_INGEST_SECRET or x_obs_secret != settings.OBS_INGEST_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Obs-Secret",
        )
    if len(batch.events) > MAX_EVENTS_PER_BATCH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"batch size {len(batch.events)} exceeds max {MAX_EVENTS_PER_BATCH}",
        )
    if batch.schema_version != "v1":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unsupported schema_version",
        )
    try:
        await write_batch(batch.events)
    except Exception:  # noqa: BLE001 — surface via 503 for client retry
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="event_writer_failure",
        )
    return {"accepted": len(batch.events)}
```

```python
# backend/observability/routers/__init__.py
from backend.observability.routers.ingest import router as ingest_router
__all__ = ["ingest_router"]
```

- [ ] **Step 4: Mount the router in `backend/main.py`** — no `/api/v1` prefix; matches spec §2.2b. **Also add `/obs/v1/events` to `csrf_exempt_paths` in the existing `CSRFMiddleware` registration** — per review finding (CRITICAL), without this every POST to the ingest endpoint returns 403 from CSRF before it ever reaches the auth check. CSRF is not applicable here because the endpoint uses a shared-secret header (`X-Obs-Secret`) for service-to-service auth, not cookie-based sessions.

```python
from backend.observability.routers import ingest_router  # top-of-file with other imports
# ...after existing app.include_router calls:
app.include_router(ingest_router)
```

Update the existing `app.add_middleware(CSRFMiddleware, csrf_exempt_paths={...})` call in `main.py:336-351` — add `"/obs/v1/events"` to the exempt set. Concrete change:

```python
app.add_middleware(
    CSRFMiddleware,
    csrf_exempt_paths={
        # ...existing exempt paths (auth, health, docs)...
        "/obs/v1/events",  # Obs 1a PR2b — X-Obs-Secret auth, not cookie-based
    },
)
```

Verify exempt by hitting the endpoint without a CSRF cookie: `test_ingest_rejects_missing_secret` above expects `401` (not `403`). If the test returns `403`, the exempt path wasn't applied.

- [ ] **Step 5:** `uv run pytest tests/api/observability/test_ingest_endpoint.py -v` → 6 passed.
- [ ] **Step 6:** Commit: `feat(obs-1a): add POST /obs/v1/events ingest endpoint`.

---

## Task 4: Extend `bootstrap.build_client_from_settings()` with `internal_http` branch

**Files:** `backend/observability/bootstrap.py`

- [ ] **Step 1:** Extend factory:

```python
from backend.observability.targets.internal_http import InternalHTTPTarget
# ...

def build_client_from_settings() -> ObservabilityClient:
    if settings.OBS_TARGET_TYPE == "memory":
        target = MemoryTarget()
    elif settings.OBS_TARGET_TYPE == "internal_http":
        if not settings.OBS_TARGET_URL or not settings.OBS_INGEST_SECRET:
            raise RuntimeError(
                "OBS_TARGET_TYPE=internal_http requires OBS_TARGET_URL + OBS_INGEST_SECRET"
            )
        target = InternalHTTPTarget(
            base_url=settings.OBS_TARGET_URL, secret=settings.OBS_INGEST_SECRET
        )
    else:  # "direct"
        target = DirectTarget()
    # ... existing ObservabilityClient construction unchanged
```

- [ ] **Step 2: Add a startup-config test** (append to `tests/unit/observability/test_client.py` or new `test_bootstrap.py`):

```python
@pytest.mark.asyncio
async def test_bootstrap_internal_http_requires_url_and_secret(monkeypatch):
    from backend.observability.bootstrap import build_client_from_settings
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_TYPE", "internal_http")
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_URL", None)
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", None)
    with pytest.raises(RuntimeError, match="OBS_TARGET_URL"):
        build_client_from_settings()


@pytest.mark.asyncio
async def test_bootstrap_internal_http_happy_path(monkeypatch, tmp_path):
    from backend.observability.bootstrap import build_client_from_settings
    from backend.observability.targets.internal_http import InternalHTTPTarget
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_TYPE", "internal_http")
    monkeypatch.setattr("backend.config.settings.OBS_TARGET_URL", "http://localhost:8181")
    monkeypatch.setattr("backend.config.settings.OBS_INGEST_SECRET", "s3cret")
    monkeypatch.setattr("backend.config.settings.OBS_SPOOL_ENABLED", False)
    monkeypatch.setattr("backend.config.settings.OBS_SPOOL_DIR", str(tmp_path))
    client = build_client_from_settings()
    assert isinstance(client._target, InternalHTTPTarget)  # internal access is ok in tests
```

- [ ] **Step 3:** `uv run pytest tests/unit/observability/ -v` → all green.
- [ ] **Step 4:** Commit: `feat(obs-1a): extend bootstrap with internal_http branch`.

---

## Task 5: Full-suite sanity + lint

- [ ] `uv run pytest tests/unit/ tests/api/ -q --tb=short` → +5 new unit tests + 6 new API tests on top of PR2a baseline; zero regressions.
- [ ] `uv run ruff check --fix backend/observability/ tests/`
- [ ] `uv run ruff format backend/observability/ tests/`
- [ ] `uv run ruff check backend/observability/ tests/` → 0 errors.
- [ ] Smoke test: `uv run uvicorn backend.main:app --port 8181 &` → `curl -s -X POST http://localhost:8181/obs/v1/events -H 'X-Obs-Secret: wrong' -d '{"events":[],"schema_version":"v1"}' -H 'Content-Type: application/json' -w '%{http_code}\n'` → `401`.

---

## Acceptance Criteria (PR2b)

- [x] `InternalHTTPTarget.send_batch()` sets `X-Obs-Secret` header and posts to `/obs/v1/events`
- [x] 5xx / connection-error / timeout responses classified as failures; `health().last_error` populated
- [x] `POST /obs/v1/events` returns 202 on valid batch, 401 without secret or with wrong secret, 413 on oversized batch, 422 on unsupported schema_version, 503 on writer failure
- [x] Endpoint is fail-closed when `OBS_INGEST_SECRET` is unset (all requests 401)
- [x] `bootstrap.build_client_from_settings()` raises `RuntimeError` when `internal_http` is selected without URL+secret
- [x] Zero regressions; net +5 unit / +6 API tests on top of PR2a
- [x] Lint clean

---

## Risks

| Risk | Mitigation |
|---|---|
| Production misconfiguration exposes ingest without secret | Endpoint fail-closes when secret unset; documented playbook: set secret before enabling `internal_http` |
| Constant-time secret comparison not used (timing attack) | Secrets are long random strings; a follow-up can swap to `secrets.compare_digest` if security review flags it |
| `InternalHTTPTarget` against self creates latency loop | Only used in integration tests + during microservice transition; DirectTarget remains monolith default |
| Ingest endpoint mounted without rate limit in PR2b | Acceptable because `OBS_INGEST_SECRET` + `X-Obs-Secret` blocks external abuse; explicit rate limiting (SlowAPI) can follow in 1b if production load warrants |

---

## Commit Sequence

1. `feat(obs-1a): extend OBS_TARGET_TYPE with internal_http option`
2. `feat(obs-1a): add InternalHTTPTarget`
3. `feat(obs-1a): add POST /obs/v1/events ingest endpoint`
4. `feat(obs-1a): extend bootstrap with internal_http branch`

PR body references: spec §2.2 (InternalHTTPTarget), §2.2b (ingest endpoint); KAN-458, KAN-464; fact-sheet §2 (router mount pattern).
