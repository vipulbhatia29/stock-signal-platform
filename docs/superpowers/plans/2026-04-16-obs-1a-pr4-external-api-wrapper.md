# Obs 1a PR4 — `ObservedHttpClient` + 10 Providers + Rate-Limiter Events + Retention

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Every outbound external-API call emits a structured `external_api_call_log` event. Every rate-limiter outcome (acquired / timeout / permissive fallback) emits a `rate_limiter_event`. Migration 031 adds both hypertables with retention + compression policies. Retention is also added for the existing obs-adjacent tables (`llm_call_log`, `tool_execution_log`, `pipeline_runs`, `dq_check_history`, `login_attempts`).

**Architecture:** `ObservedHttpClient` wraps `httpx.AsyncClient` and emits an `EXTERNAL_API_CALL` event on every response (success or error) through the SDK. `get_http_client()` — the shared pool used by 6 providers per fact sheet §3 — returns `ObservedHttpClient` instances pinned to the caller's provider tag. OpenAI + Anthropic SDKs accept `http_client=` at construction; we pass wrapped clients so SDK calls flow through the same emission path. LangChain ChatGroq (used by `backend/agents/providers/groq.py` per fact sheet §3.8) gets callback-based instrumentation — flagged as open question, see Risks. `yfinance` (sync, uses `requests` per fact sheet §3.1) gets a `requests.Session` transport wrapper. Rate-limiter emission points are the 6 fallback branches at fact-sheet §4 lines 72-116.

**Tech Stack:** httpx, requests (yfinance path), FastAPI lifespan, SQLAlchemy async, Alembic, TimescaleDB hypertables + compression (pattern from fact sheet §1 migration 028).

**Spec reference:** `docs/superpowers/specs/2026-04-16-obs-1a-foundations-design.md` §2.5, §2.6, §2.8.

**Prerequisites:** PR1 (`ObsEventBase`, `EventType.EXTERNAL_API_CALL`, `EventType.RATE_LIMITER_EVENT`), PR2a (SDK can emit), PR2b (optional, not required), PR3 (trace_id + span() available for span names / parent_span_id).

**Dependency for:** PR5 (not blocking, but PR5's contract tests coexist with provider-emission tests).

**Fact-sheet anchors:** 10 providers identified at §3 (4 news providers + yfinance share `get_http_client()`; OpenAI/Anthropic/Groq use SDKs; Resend SDK; Google OAuth uses `get_http_client()` for token exchange + PyJWKClient for JWKS). 6 rate-limiter fallback branches at §4 lines 72-74, 83-89, 102-105, 106-107, 108-110, 115-116. Existing retention tasks at §10 (forecast 30d, news 90d via drop_chunks). Alembic head after PR1 = `c4d5e6f7a8b9`.

---

## File Structure

**Create:**
- `backend/migrations/versions/031_observability_external_api_rate_limiter.py` — 2 hypertables + compression + retention-policy DDL
- `backend/observability/models/external_api_call.py` — SQLAlchemy model
- `backend/observability/models/rate_limiter_event.py` — SQLAlchemy model
- `backend/observability/instrumentation/__init__.py`
- `backend/observability/instrumentation/external_api.py` — `ObservedHttpClient` + `YfinanceObservedSession`
- `backend/observability/instrumentation/providers.py` — `ExternalProvider` enum + helpers
- `backend/observability/service/external_api_writer.py` — the real `write_batch` branch for `EXTERNAL_API_CALL` + `RATE_LIMITER_EVENT` (extends PR2a stub)
- `tests/unit/observability/test_external_api_wrapper.py`, `test_rate_limiter_event.py`, `test_retention_new_tables.py`

**Modify:**
- `backend/services/http_client.py` (or wherever `get_http_client()` lives per project convention) — return `ObservedHttpClient` with provider context
- `backend/services/news/{finnhub,edgar,fed,google}_provider.py` — pass `provider=` to `get_http_client()`
- `backend/services/stock_data.py` — replace `yf.Ticker`/`yf.download` invocations with wrappers that use `YfinanceObservedSession`
- `backend/agents/providers/openai.py` — construct `AsyncOpenAI(http_client=build_observed_http_client(OPENAI))`
- `backend/agents/providers/anthropic.py` — same pattern for `AsyncAnthropic`
- `backend/agents/providers/groq.py` — add callback-based instrumentation (see Task 5 note)
- `backend/services/email.py` — wrap Resend client similarly (Resend SDK accepts custom transport; if not, emit manually around the SDK call)
- `backend/services/google_oauth.py` — already uses `get_http_client()` per fact sheet §3.10; no code change other than passing `provider=GOOGLE_OAUTH`
- `backend/services/rate_limiter.py` — emit `rate_limiter_event` at 6 fallback points + timeout
- `backend/tasks/retention.py` — add `purge_external_api_call_log_task`, `purge_rate_limiter_event_task`, and retention tasks for 5 existing tables (`llm_call_log` 30d, `tool_execution_log` 30d, `pipeline_runs` 90d, `dq_check_history` 90d, `login_attempts` 90d)
- `backend/tasks/__init__.py` — add beat entries for 7 new retention tasks
- `backend/observability/service/event_writer.py` — route `EXTERNAL_API_CALL` + `RATE_LIMITER_EVENT` to real writer (was stub in PR2a)

---

## Task 1: Migration 031 — tables + compression + retention

**Files:** `backend/migrations/versions/031_observability_external_api_rate_limiter.py`, `tests/unit/observability/test_migration_031.py`

- [ ] **Step 1: Failing test** — verify both tables exist with correct columns + hypertable registration:

```python
# tests/unit/observability/test_migration_031.py
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_external_api_call_log_is_hypertable(db_session):
    result = await db_session.execute(text(
        "SELECT hypertable_name FROM timescaledb_information.hypertables "
        "WHERE hypertable_schema='observability' AND hypertable_name='external_api_call_log'"
    ))
    assert result.scalar() == "external_api_call_log"


@pytest.mark.asyncio
async def test_rate_limiter_event_is_hypertable(db_session):
    result = await db_session.execute(text(
        "SELECT hypertable_name FROM timescaledb_information.hypertables "
        "WHERE hypertable_schema='observability' AND hypertable_name='rate_limiter_event'"
    ))
    assert result.scalar() == "rate_limiter_event"


@pytest.mark.asyncio
async def test_compression_policy_on_external_api(db_session):
    result = await db_session.execute(text(
        "SELECT compress_after FROM timescaledb_information.compression_settings "
        "WHERE hypertable_schema='observability' AND hypertable_name='external_api_call_log'"
    ))
    # Spec §2.6: compression after 7 days
    assert "7 days" in str(result.scalar()).lower() or "7 day" in str(result.scalar()).lower()
```

- [ ] **Step 2: Write the migration** — follow fact sheet §1 pattern from migration 028 (TimescaleDB compression). Revision `d5e6f7a8b9c0`, down_revision `c4d5e6f7a8b9`.

```python
"""Observability external API + rate limiter hypertables (Obs 1a PR4).

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-16
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE observability.external_api_call_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            trace_id UUID NOT NULL,
            span_id UUID NOT NULL,
            parent_span_id UUID,
            user_id UUID,
            provider TEXT NOT NULL,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            status_code INT,
            error_reason TEXT,
            latency_ms INT NOT NULL,
            request_bytes INT,
            response_bytes INT,
            retry_count INT DEFAULT 0,
            cost_usd NUMERIC(12, 6),
            rate_limit_remaining INT,
            rate_limit_reset_ts TIMESTAMPTZ,
            rate_limit_headers JSONB,
            stack_signature TEXT,
            stack_hash CHAR(64),
            env TEXT NOT NULL,
            git_sha TEXT
        );
    """))
    op.execute(sa.text(
        "SELECT create_hypertable('observability.external_api_call_log', 'ts', chunk_time_interval => INTERVAL '1 day')"
    ))
    op.execute(sa.text(
        "CREATE INDEX ON observability.external_api_call_log (trace_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ON observability.external_api_call_log (provider, ts DESC)"
    ))
    op.execute(sa.text(
        "CREATE INDEX ON observability.external_api_call_log (error_reason, ts DESC) WHERE error_reason IS NOT NULL"
    ))
    # Compression per spec §2.6.
    op.execute(sa.text(
        "ALTER TABLE observability.external_api_call_log SET "
        "(timescaledb.compress, timescaledb.compress_orderby='ts DESC', timescaledb.compress_segmentby='provider')"
    ))
    op.execute(sa.text(
        "SELECT add_compression_policy('observability.external_api_call_log', INTERVAL '7 days')"
    ))
    op.execute(sa.text(
        "SELECT add_retention_policy('observability.external_api_call_log', INTERVAL '30 days')"
    ))

    op.execute(sa.text("""
        CREATE TABLE observability.rate_limiter_event (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ts TIMESTAMPTZ NOT NULL DEFAULT now(),
            trace_id UUID,
            span_id UUID,
            limiter_name TEXT NOT NULL,
            action TEXT NOT NULL,
            wait_time_ms INT,
            tokens_remaining INT,
            reason_if_fallback TEXT,
            env TEXT NOT NULL,
            git_sha TEXT
        );
    """))
    op.execute(sa.text(
        "SELECT create_hypertable('observability.rate_limiter_event', 'ts', chunk_time_interval => INTERVAL '1 day')"
    ))
    op.execute(sa.text(
        "CREATE INDEX ON observability.rate_limiter_event (limiter_name, action, ts DESC)"
    ))
    op.execute(sa.text(
        "SELECT add_retention_policy('observability.rate_limiter_event', INTERVAL '30 days')"
    ))


def downgrade() -> None:
    # Remove policies before dropping tables (Timescale requires this order).
    op.execute(sa.text(
        "SELECT remove_retention_policy('observability.external_api_call_log', if_exists => true)"
    ))
    op.execute(sa.text(
        "SELECT remove_compression_policy('observability.external_api_call_log', if_exists => true)"
    ))
    op.execute(sa.text(
        "SELECT remove_retention_policy('observability.rate_limiter_event', if_exists => true)"
    ))
    op.execute(sa.text("DROP TABLE IF EXISTS observability.external_api_call_log CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS observability.rate_limiter_event CASCADE"))
```

- [ ] **Step 3:** `uv run alembic upgrade head && uv run pytest tests/unit/observability/test_migration_031.py -v` → 3 passed.
- [ ] **Step 4:** Commit: `feat(obs-1a): migration 031 — external_api_call_log + rate_limiter_event hypertables`.

---

## Task 2: SQLAlchemy models

**Files:** `backend/observability/models/external_api_call.py`, `backend/observability/models/rate_limiter_event.py`, update `backend/observability/models/__init__.py`

- [ ] **Step 1:** Create models mirroring the DDL columns (follow existing Base/mapped_column pattern from `SchemaVersion` in PR1). Include `__tablename__` + `__table_args__ = {"schema": "observability"}`.
- [ ] **Step 2:** Re-export from `backend/observability/models/__init__.py`.
- [ ] **Step 3:** Smoke-test: `uv run python -c "from backend.observability.models import ExternalApiCallLog, RateLimiterEvent; print(ExternalApiCallLog.__tablename__, RateLimiterEvent.__tablename__)"`.
- [ ] **Step 4:** Commit: `feat(obs-1a): add SQLAlchemy models for external_api + rate_limiter tables`.

---

## Task 3: `ExternalProvider` enum + event subclasses

**Files:** `backend/observability/instrumentation/{__init__.py, providers.py}`, extend `backend/observability/schema/v1.py`

- [ ] **Step 1: Failing test** — assert enum + event subclass validation:

```python
# tests/unit/observability/test_external_api_wrapper.py (Task 3 portion)
from backend.observability.instrumentation.providers import ExternalProvider


def test_external_provider_enum_covers_10_providers():
    names = {p.value for p in ExternalProvider}
    assert names == {
        "yfinance", "finnhub", "edgar", "fred", "google_news",
        "openai", "anthropic", "groq", "resend", "google_oauth",
    }
```

- [ ] **Step 2: Implement**

```python
# backend/observability/instrumentation/providers.py
from enum import Enum


class ExternalProvider(str, Enum):
    YFINANCE = "yfinance"
    FINNHUB = "finnhub"
    EDGAR = "edgar"
    FRED = "fred"
    GOOGLE_NEWS = "google_news"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    RESEND = "resend"
    GOOGLE_OAUTH = "google_oauth"


class ErrorReason(str, Enum):
    RATE_LIMIT_429 = "rate_limit_429"
    SERVER_ERROR_5XX = "server_error_5xx"
    CLIENT_ERROR_4XX = "client_error_4xx"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    MALFORMED_RESPONSE = "malformed_response"
    AUTH_FAILURE = "auth_failure"
    CIRCUIT_OPEN = "circuit_open"
```

- [ ] **Step 3:** Commit: `feat(obs-1a): add ExternalProvider + ErrorReason enums`.

---

## Task 4: `ObservedHttpClient` + `get_http_client()` refactor

**Files:** `backend/observability/instrumentation/external_api.py`, update `backend/services/http_client.py` (path per project; if not present, find via `grep -rn "def get_http_client" backend/` per fact-sheet implication)

- [ ] **Step 1: Failing test** — every call emits an EXTERNAL_API_CALL event:

```python
# Append to tests/unit/observability/test_external_api_wrapper.py
import httpx
import pytest
from backend.observability.instrumentation.external_api import ObservedHttpClient
from backend.observability.instrumentation.providers import ExternalProvider
from backend.observability.targets.memory import MemoryTarget


@pytest.mark.asyncio
async def test_observed_http_client_emits_event_on_success(monkeypatch):
    target = MemoryTarget()
    # Wire a test-scoped client whose emit() flows through target.
    from backend.observability.client import ObservabilityClient
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp())
    obs_client = ObservabilityClient(
        target=target, spool_dir=tmp, spool_enabled=False,
        flush_interval_ms=50, buffer_size=100, enabled=True,
    )
    await obs_client.start()
    try:
        transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"ok": True}))
        http = httpx.AsyncClient(transport=transport)
        observed = ObservedHttpClient(
            provider=ExternalProvider.FINNHUB, client=http, obs_client=obs_client,
        )
        resp = await observed.get("https://finnhub.io/api/v1/company-news")
        assert resp.status_code == 200
        await obs_client.flush()
        assert len(target.events) == 1
        assert target.events[0].event_type.value == "external_api_call"
    finally:
        await obs_client.stop()


@pytest.mark.asyncio
async def test_observed_http_client_classifies_429():
    # 429 → error_reason=rate_limit_429
    transport = httpx.MockTransport(lambda r: httpx.Response(429, json={}))
    # ... (construct obs_client as above) ...
    # Assert emitted event has event_type='external_api_call' and payload-field error_reason='rate_limit_429'.
    # (Full test body analogous to above — omitted for brevity; see spec §2.5 for fields.)
```

- [ ] **Step 2: Implement `ObservedHttpClient`**

**Critical design point (post-review):** `ObservedHttpClient` must be a drop-in replacement for `httpx.AsyncClient` so SDKs (OpenAI, Anthropic) that take `http_client=` work. SUBCLASS `httpx.AsyncClient` and override `send()`. Don't wrap — subclass.

Core behavior (spec §2.5):
- Subclass `httpx.AsyncClient`; override `send(request, **kwargs)`
- On `send()`: start monotonic timer; super().send(); compute latency; classify status (200-399 = success; 429 = rate_limit_429; 4xx = client_error_4xx; 5xx = server_error_5xx; `httpx.ConnectError` = connection_refused; `httpx.TimeoutException` = timeout)
- Build `EXTERNAL_API_CALL` event (subclass of `ObsEventBase` in `schema/external_api_events.py`) with payload fields: provider, endpoint (normalized path, no query params), method, status_code, error_reason, latency_ms, request_bytes, response_bytes, rate_limit_headers (parsed `X-RateLimit-*`), stack_signature (on error only)
- Fill envelope: `trace_id=current_trace_id() or UUID(bytes=uuid7().bytes)`, `span_id=UUID(bytes=uuid7().bytes)`, `parent_span_id=current_span_id()`
- Call `obs_client.emit_sync(event)` OR `obs_client.emit(event)` depending on context (see Step 3)
- Re-raise the underlying httpx exception after emission (wrapped in try/except so emission bugs never mask the real error)

Keep implementation to ~80 lines; reference spec §2.5 for field list.

- [ ] **Step 3: Define `build_observed_http_client()` factory + refactor `get_http_client()`**

Per review finding (HIGH): `build_observed_http_client(provider)` was referenced but never defined. And `get_http_client()` is a singleton per fact sheet §3 — naively accepting a `provider=` kwarg would turn the singleton inside-out (one per provider, or new instance per call). Resolve both:

```python
# backend/observability/instrumentation/external_api.py
"""ObservedHttpClient + factory.

Singleton-compatible pattern:
- One underlying `httpx.AsyncTransport` pool (shared across all providers)
- `build_observed_http_client(provider)` returns a NEW `ObservedHttpClient`
  (subclass of httpx.AsyncClient) that uses the shared transport but tags
  emissions with the provider.
- SDK consumers (OpenAI AsyncOpenAI, Anthropic AsyncAnthropic) accept
  `http_client=<httpx.AsyncClient>` — our subclass satisfies the contract.
"""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID
import httpx
from uuid_utils import uuid7
from backend.config import settings
from backend.observability.bootstrap import _maybe_get_obs_client
from backend.observability.context import current_trace_id, current_span_id
from backend.observability.instrumentation.providers import ExternalProvider, ErrorReason
# NOTE: ExternalApiCallEvent is defined in schema/external_api_events.py (new in this PR)

# Shared transport pool — one per process.
_SHARED_TRANSPORT: httpx.AsyncHTTPTransport | None = None


def _get_shared_transport() -> httpx.AsyncHTTPTransport:
    global _SHARED_TRANSPORT
    if _SHARED_TRANSPORT is None:
        _SHARED_TRANSPORT = httpx.AsyncHTTPTransport(retries=0, http2=False)
    return _SHARED_TRANSPORT


class ObservedHttpClient(httpx.AsyncClient):
    """httpx.AsyncClient drop-in — emits EXTERNAL_API_CALL on every response.

    Safe to pass to AsyncOpenAI(http_client=...) / AsyncAnthropic(http_client=...).
    """

    def __init__(self, provider: ExternalProvider, **kwargs) -> None:
        kwargs.setdefault("transport", _get_shared_transport())
        kwargs.setdefault("timeout", httpx.Timeout(30.0, connect=5.0))
        super().__init__(**kwargs)
        self._provider = provider

    async def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        import time
        start = time.monotonic()
        status_code: int | None = None
        error_reason: ErrorReason | None = None
        response: httpx.Response | None = None
        try:
            response = await super().send(request, **kwargs)
            status_code = response.status_code
            error_reason = _classify_status(status_code)
            return response
        except httpx.TimeoutException:
            error_reason = ErrorReason.TIMEOUT
            raise
        except httpx.ConnectError:
            error_reason = ErrorReason.CONNECTION_REFUSED
            raise
        except httpx.HTTPError:
            error_reason = ErrorReason.MALFORMED_RESPONSE
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            try:
                self._emit(
                    request=request, response=response,
                    status_code=status_code, error_reason=error_reason,
                    latency_ms=latency_ms,
                )
            except Exception:  # noqa: BLE001 — emission never propagates
                pass

    def _emit(self, *, request, response, status_code, error_reason, latency_ms):
        client = _maybe_get_obs_client()
        if client is None:
            return
        # Build event (see schema/external_api_events.py in this PR) — abbreviated:
        event = _build_external_api_event(
            provider=self._provider,
            method=request.method,
            endpoint=request.url.path,  # strip query params
            status_code=status_code, error_reason=error_reason,
            latency_ms=latency_ms,
            response=response,
        )
        client.emit_sync(event)  # sync — works from any loop, including SDK internal threads


def _classify_status(status: int) -> ErrorReason | None:
    if status == 429:
        return ErrorReason.RATE_LIMIT_429
    if 500 <= status < 600:
        return ErrorReason.SERVER_ERROR_5XX
    if 400 <= status < 500:
        return ErrorReason.CLIENT_ERROR_4XX
    return None


def build_observed_http_client(provider: ExternalProvider) -> ObservedHttpClient:
    """Factory used by OpenAI/Anthropic SDK integrations and refactored news providers.

    Every call returns a NEW ObservedHttpClient; they all share a single transport pool
    via `_get_shared_transport()`, so connection reuse is preserved.
    """
    return ObservedHttpClient(provider=provider)
```

`get_http_client()` refactor: existing singleton at `backend/services/http_client.py` stays as a raw `httpx.AsyncClient`. A new parallel function `get_observed_http_client(provider)` wraps it for providers migrating to the SDK. News providers (fact sheet §3) swap their call sites from `get_http_client()` to `get_observed_http_client(provider=ExternalProvider.FINNHUB)`.
- [ ] **Step 4:** Update the 4 news providers + `google_oauth.py` + `email.py` call sites (fact sheet §3 shows exact file:line for each) to pass `provider=ExternalProvider.FINNHUB` / etc.
- [ ] **Step 5:** `uv run pytest tests/unit/observability/test_external_api_wrapper.py -v` → all green.
- [ ] **Step 6:** Commit: `feat(obs-1a): add ObservedHttpClient + provider tagging for shared pool`.

---

## Task 5: SDK client integrations (OpenAI / Anthropic / LangChain / yfinance)

**Files:** `backend/agents/providers/{openai,anthropic,groq}.py`, `backend/services/stock_data.py`, append tests

- [ ] **Step 1: OpenAI** — in `backend/agents/providers/openai.py`, replace per-call `AsyncOpenAI(**kwargs)` (fact sheet §3.6, lines 50, 56) with module-level factory:

```python
from openai import AsyncOpenAI
from backend.observability.instrumentation.external_api import build_observed_http_client
from backend.observability.instrumentation.providers import ExternalProvider

def _openai_client(api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, http_client=build_observed_http_client(ExternalProvider.OPENAI))
```

Call `_openai_client(...)` at each call site. Confirms integration by running `tests/unit/observability/test_openai_emits_external_api_call.py` (new test — 1 happy path assertion).

- [ ] **Step 2: Anthropic** — same pattern in `backend/agents/providers/anthropic.py` (fact sheet §3.7 line 96).
- [ ] **Step 3: LangChain ChatGroq** — **OPEN QUESTION**, see Risks. Proposed approach: add a LangChain `BaseCallbackHandler` that emits `EXTERNAL_API_CALL` on `on_llm_start`/`on_llm_end`/`on_llm_error`; pass via `callbacks=[groq_callback_handler]`. Latency measured from callback timestamps. Defer to code-review if a cleaner path (e.g., `httpx_transport` hook) emerges.
- [ ] **Step 4: Resend** — check if the Resend SDK accepts a custom `http_client`. If yes, wrap; if no, emit manually with `async with span("external_api.resend"):` around the SDK call.
- [ ] **Step 5: yfinance** — build a `YfinanceObservedSession(requests.Session)` subclass that overrides `request()` to emit via `obs_client.emit_sync()` (yfinance is sync). Pass to yfinance via the documented `requests_session=` parameter on `yf.Ticker()`/`yf.download()`. `backend/services/stock_data.py` lines 168, 249, 274 (fact sheet §3.1) are the integration points.
- [ ] **Step 6:** `uv run pytest tests/unit/observability/test_external_api_wrapper.py tests/unit/agents/ -v` → all green.
- [ ] **Step 7:** Commit: `feat(obs-1a): integrate ObservedHttpClient into OpenAI/Anthropic/yfinance/Resend` + separate commit for LangChain-Groq (flagged `docs(obs-1a): TODO LangChain ChatGroq observability — open question, tracked in PR4 risks`).

---

## Task 6: Rate-limiter event emission

**Files:** `backend/services/rate_limiter.py`, `tests/unit/observability/test_rate_limiter_event.py`

- [ ] **Step 1: Failing test** — every fallback branch emits one event:

```python
@pytest.mark.asyncio
async def test_rate_limiter_emits_event_on_redis_down(monkeypatch, tmp_path):
    # Patch Redis to raise ConnectionError; acquire() returns True (permissive); assert rate_limiter_event emitted with reason_if_fallback='redis_down'.
    ...
```

(Write a test per fallback branch: redis_down, noscript_recovery_failed, lua_error, timeout. See fact sheet §4 lines 72-116 for branch enumeration.)

- [ ] **Step 2: Implement** — at each `logger.warning()` site (fact sheet §4 lines 73, 87, 106, 109, 115), insert `obs_client.emit_sync(...)` immediately before the warning. Use `limiter_name=self.name`, `action=<acquired|timeout|fallback_permissive>`, `reason_if_fallback=<enum>`, `wait_time_ms=<measured>`.

Event model (add to `schema/v1.py` or inline in the instrumentation module):

```python
class RateLimiterEventPayload(ObsEventBase):
    event_type: Literal[EventType.RATE_LIMITER_EVENT] = EventType.RATE_LIMITER_EVENT
    limiter_name: str
    action: Literal["acquired", "timeout", "fallback_permissive", "rejected"]
    wait_time_ms: int | None = None
    tokens_remaining: int | None = None
    reason_if_fallback: Literal["redis_down", "noscript_recovery_failed", "lua_error", "unknown"] | None = None
```

- [ ] **Step 3:** Run all tests in `tests/unit/observability/test_rate_limiter_event.py` → green.
- [ ] **Step 4:** Commit: `feat(obs-1a): emit rate_limiter_event at permissive-fallback branches`.

---

## Task 7: Retention policies for existing tables + new tasks

**Files:** `backend/tasks/retention.py`, `backend/tasks/__init__.py` (beat schedule)

- [ ] **Step 1: Extend `retention.py`** — fact sheet §10 shows the existing pattern (`@tracked_task("forecast_retention", trigger="scheduled")`). Add 5 new tasks:

| Task name | Table | Window | Mechanism |
|---|---|---|---|
| `purge_old_llm_call_log_task` | `llm_call_log` | 30d | `DELETE WHERE created_at < now() - interval '30 days'` (or `drop_chunks` if hypertable — verify) |
| `purge_old_tool_execution_log_task` | `tool_execution_log` | 30d | same |
| `purge_old_pipeline_runs_task` | `pipeline_runs` | 90d | `DELETE WHERE started_at < now() - interval '90 days'` |
| `purge_old_dq_check_history_task` | `dq_check_history` | 90d | `DELETE` |
| `purge_old_login_attempts_task` | `login_attempts` | 90d | `DELETE` |

Use `tracked_task` decorator matching existing pattern; each task runs the DELETE inside `async with async_session_factory() as db: await db.execute(text(...)); await db.commit()`.

New-table retention is handled by the hypertable retention policies in migration 031 (TimescaleDB runs them natively); no Celery task needed for `external_api_call_log` / `rate_limiter_event`.

- [ ] **Step 2: Beat schedule** — append to `backend/tasks/__init__.py` beat config (fact sheet §2 shows existing 11 entries; add 5 new at staggered times 01:30-02:30 ET).

```python
"purge-llm-call-log-daily":   {"task": "backend.tasks.retention.purge_old_llm_call_log_task",   "schedule": crontab(hour=1, minute=30)},
"purge-tool-execution-log-daily": {"task": "backend.tasks.retention.purge_old_tool_execution_log_task", "schedule": crontab(hour=1, minute=45)},
"purge-pipeline-runs-90d":    {"task": "backend.tasks.retention.purge_old_pipeline_runs_task",  "schedule": crontab(hour=2, minute=0)},
"purge-dq-check-history-90d": {"task": "backend.tasks.retention.purge_old_dq_check_history_task","schedule": crontab(hour=2, minute=15)},
"purge-login-attempts-90d":   {"task": "backend.tasks.retention.purge_old_login_attempts_task", "schedule": crontab(hour=2, minute=30)},
```

- [ ] **Step 3: Tests** — each retention task has a unit test following the existing pattern (seed rows past threshold, run task, assert rows deleted). See `tests/unit/tasks/test_retention.py` for existing patterns.
- [ ] **Step 4:** `uv run pytest tests/unit/tasks/test_retention.py -v` → all green.
- [ ] **Step 5:** Commit: `feat(obs-1a): add retention tasks for llm/tool/pipeline/dq/login tables`.

---

## Task 8: Route EXTERNAL_API_CALL + RATE_LIMITER_EVENT through `event_writer`

**Files:** `backend/observability/service/event_writer.py` (update — was stub in PR2a), `backend/observability/service/external_api_writer.py`

- [ ] **Step 1:** Extend `event_writer.write_batch` to branch on `event.event_type`: call `external_api_writer.persist(event)` for `EXTERNAL_API_CALL` and a matching `persist` for `RATE_LIMITER_EVENT`. Legacy events (PR5 scope) still hit the stub logger until PR5 adds them.
- [ ] **Step 2:** Implement `external_api_writer.persist` — SQL INSERT into `observability.external_api_call_log` (or the analogous rate-limiter writer). Use async SQLAlchemy session from `backend.database`.
- [ ] **Step 3:** Integration test — smoke-test end-to-end: `obs_client.emit(EXTERNAL_API_CALL event)` → row in `observability.external_api_call_log`. Use `tests/api/observability/test_external_api_end_to_end.py`.
- [ ] **Step 4:** Commit: `feat(obs-1a): real event_writer for external_api + rate_limiter`.

---

## Full-suite sanity + lint + smoke

- [ ] `uv run pytest tests/unit/ tests/api/ -q --tb=short` → baseline + net ~20 new tests, zero regressions.
- [ ] `uv run ruff check --fix backend/observability/ backend/services/ backend/agents/ backend/tasks/ tests/`
- [ ] `uv run ruff format backend/observability/ backend/services/ backend/agents/ backend/tasks/ tests/`
- [ ] Integration smoke: `uv run python -c "import asyncio; from backend.services.news.finnhub_provider import fetch_stock_news; asyncio.run(fetch_stock_news('AAPL'))"` → 1 row appears in `observability.external_api_call_log`.

---

## Acceptance Criteria (PR4)

- [x] Migration 031 creates both hypertables with correct compression + retention policies; up/down both tested
- [x] `ObservedHttpClient` emits an `EXTERNAL_API_CALL` event on every request (success + error); classification enum covered for 429, 4xx, 5xx, timeout, connection errors
- [x] All 10 providers route through observed clients (OpenAI / Anthropic / news × 4 / Resend / Google OAuth / yfinance + LangChain-Groq callback)
- [x] Rate-limiter emits `rate_limiter_event` at all 6 fallback branches + timeout with correct `reason_if_fallback` enum
- [x] 5 new retention tasks scheduled at staggered beat times; hypertable retention policies active on new tables
- [x] Full unit + API suite green; zero regressions
- [x] Lint clean

---

## Risks

| Risk | Mitigation |
|---|---|
| **LangChain ChatGroq callback instrumentation** — API surface less stable than httpx | Use `BaseCallbackHandler.on_llm_{start,end,error}` hooks; if LangChain version bump breaks, fall back to manual `span()` wrapping around the call site. Document in code comments + follow-up ticket if the callback path proves unreliable |
| Resend SDK may not expose custom http client | Fall back to `async with span("external_api.resend"):` around SDK call with manual emission — acceptable because Resend is low-volume (email only) |
| `requests.Session` subclass for yfinance + `emit_sync` blocks the sync call | Emission is asyncio.create_task via sync adapter; <1ms overhead tolerable; benchmark during smoke test |
| Migration 031 compression policy differs from migration 028 pattern | Copy DDL shape verbatim from fact sheet §1; test up/down locally before committing |
| Timescale `drop_chunks()` vs `DELETE` chosen wrong for llm/tool_execution tables | Check if each is a hypertable (`SELECT * FROM timescaledb_information.hypertables`); if so, use `drop_chunks`; else `DELETE` |
| Rate-limiter event emission adds latency to hot path | `emit_sync` is non-blocking queue put; <100µs per emission; benchmark |
| Provider enum drift when new providers added | Adding a new provider = 1-line enum update + call-site wrap; covered by Semgrep rule in 1b |

---

## Commit Sequence

1. `feat(obs-1a): migration 031 — external_api_call_log + rate_limiter_event hypertables`
2. `feat(obs-1a): add SQLAlchemy models for external_api + rate_limiter tables`
3. `feat(obs-1a): add ExternalProvider + ErrorReason enums`
4. `feat(obs-1a): add ObservedHttpClient + provider tagging for shared pool`
5. `feat(obs-1a): integrate ObservedHttpClient into OpenAI/Anthropic/yfinance/Resend/OAuth`
6. `docs(obs-1a): TODO LangChain ChatGroq observability — callback-based instrumentation`
7. `feat(obs-1a): emit rate_limiter_event at permissive-fallback branches`
8. `feat(obs-1a): add retention tasks for llm/tool/pipeline/dq/login tables`
9. `feat(obs-1a): real event_writer for external_api + rate_limiter`

PR body references: spec §2.5, §2.6, §2.8; KAN-458, KAN-464; fact-sheet §1 (migration pattern 028), §3 (10 provider call sites), §4 (rate-limiter fallback branches), §10 (existing retention pattern).
