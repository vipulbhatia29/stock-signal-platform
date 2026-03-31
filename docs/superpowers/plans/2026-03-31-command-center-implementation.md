# Platform Operations Command Center — Implementation Plan (Phase 1 MVP)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a nuclear-reactor-style admin dashboard with 4 core zones (System Health, API Traffic, LLM Operations, Pipeline) providing unified platform observability.

**Architecture:** Extract observability code into `backend/observability/` bounded package. Add Redis-backed HTTP metrics middleware (sliding window). Aggregate endpoint assembles 4 zones via `asyncio.gather()` with per-zone circuit breakers and 10s server-side cache. Frontend polls every 15s with TanStack Query.

**Tech Stack:** FastAPI, Redis (metrics storage), SQLAlchemy (pool stats), Celery (health check), React, TanStack Query, Recharts, shadcn/ui

**Visual Reference:** `command-center-prototype.html` (open in browser for layout review during frontend tasks)

**Spec:** `docs/superpowers/specs/2026-03-31-command-center-design.md`

---

## Sprint Overview

| Sprint | Stories | Scope | Est. | Sessions |
|--------|---------|-------|------|----------|
| **Sprint 1** | S1a, S1b | Package extraction (MERGE GATE) | ~5.5h | 1 |
| **Sprint 2** | S2, S3, S4, S5, S6 | Backend instrumentation + data models | ~12.5h | 2 |
| **Sprint 3** | S7, S8 | Aggregate + drill-down endpoints | ~7h | 1 |
| **Sprint 4** | S9, S10 | Frontend L1 + L2 | ~10h | 2 |
| **Total** | 12 stories | | **~35h** | **5-6** |

**Sprint 1 is a merge gate.** PR must be merged and all tests green before Sprint 2 begins.

---

## Sprint 1: Package Extraction (MERGE GATE)

### Task 1: S1a — Move agents/ observability files

**Files:**
- Create: `backend/observability/__init__.py`
- Create: `backend/observability/collector.py` (content from `backend/agents/observability.py`)
- Create: `backend/observability/writer.py` (content from `backend/agents/observability_writer.py`)
- Create: `backend/observability/token_budget.py` (content from `backend/agents/token_budget.py`)
- Modify: `backend/agents/observability.py` → re-export shim
- Modify: `backend/agents/observability_writer.py` → re-export shim
- Modify: `backend/agents/token_budget.py` → re-export shim

- [ ] **Step 1: Create `backend/observability/` package**

```bash
mkdir -p backend/observability/metrics backend/observability/routers
touch backend/observability/__init__.py backend/observability/metrics/__init__.py backend/observability/routers/__init__.py
```

- [ ] **Step 2: Copy collector, writer, token_budget**

Copy the full content of each file to its new location:
- `backend/agents/observability.py` → `backend/observability/collector.py`
- `backend/agents/observability_writer.py` → `backend/observability/writer.py`
- `backend/agents/token_budget.py` → `backend/observability/token_budget.py`

Update internal imports within each copied file: any `from backend.agents.observability import` becomes `from backend.observability.collector import`, etc. Any `from backend.request_context import` stays unchanged (moved in S1b).

- [ ] **Step 3: Create re-export shims at old paths**

Replace `backend/agents/observability.py` with:
```python
"""Re-export shim — moved to backend.observability.collector."""
from backend.observability.collector import *  # noqa: F401,F403
from backend.observability.collector import ObservabilityCollector  # noqa: F401
```

Replace `backend/agents/observability_writer.py` with:
```python
"""Re-export shim — moved to backend.observability.writer."""
from backend.observability.writer import *  # noqa: F401,F403
```

Replace `backend/agents/token_budget.py` with:
```python
"""Re-export shim — moved to backend.observability.token_budget."""
from backend.observability.token_budget import *  # noqa: F401,F403
from backend.observability.token_budget import TokenBudget  # noqa: F401
```

- [ ] **Step 4: Update direct importers in agents/ package**

Grep for all files importing from the old paths:
```bash
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
```

Key files to check and update imports (prefer new paths):
- `backend/agents/llm_client.py` — imports `ObservabilityCollector`
- `backend/agents/react_loop.py` — imports `ObservabilityCollector`
- `backend/agents/graph.py` — may import collector
- `backend/main.py` — imports `TokenBudget`

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: All tests pass. If any fail, the shims aren't covering an import — fix by adding explicit re-exports.

- [ ] **Step 6: Verify shims work in fresh interpreter**

```bash
uv run python -c "from backend.agents.observability import ObservabilityCollector; print('OK')"
uv run python -c "from backend.agents.token_budget import TokenBudget; print('OK')"
uv run python -c "from backend.observability.collector import ObservabilityCollector; print('OK')"
```

- [ ] **Step 7: Commit S1a**

```bash
git add backend/observability/ backend/agents/observability.py backend/agents/observability_writer.py backend/agents/token_budget.py
git commit -m "refactor: extract observability collector, writer, token_budget to backend/observability/ (S1a)"
```

---

### Task 2: S1b — Move services/routers/context files

**Files:**
- Create: `backend/observability/context.py` (from `backend/request_context.py`)
- Create: `backend/observability/langfuse.py` (from `backend/services/langfuse_service.py`)
- Create: `backend/observability/queries.py` (from `backend/services/observability_queries.py`)
- Create: `backend/observability/models.py` (log models, re-exported from `backend/models/logs.py`)
- Create: `backend/observability/routers/admin.py` (from `backend/routers/admin.py`)
- Create: `backend/observability/routers/health.py` (from `backend/routers/health.py`)
- Create: `backend/observability/routers/user_observability.py` (from `backend/routers/observability.py`)
- Modify: all original files → re-export shims

- [ ] **Step 1: Copy context, langfuse, queries, models**

Copy files to new locations, update internal imports:
- `backend/request_context.py` → `backend/observability/context.py`
- `backend/services/langfuse_service.py` → `backend/observability/langfuse.py`
- `backend/services/observability_queries.py` → `backend/observability/queries.py`

For `backend/observability/models.py`, create a file that imports from `backend/models/logs.py` and re-exports:
```python
"""Observability log models — canonical imports from backend.models.logs.

Alembic model discovery requires these models to be importable via
backend/models/__init__.py, so the original file remains authoritative.
This module provides a convenient import path within the observability package.
"""
from backend.models.logs import LLMCallLog, ToolExecutionLog  # noqa: F401
```

**Important:** `backend/models/logs.py` stays as the source of truth (not a shim). Alembic needs it there.

- [ ] **Step 2: Create re-export shims at old paths**

Replace `backend/request_context.py` with:
```python
"""Re-export shim — moved to backend.observability.context."""
from backend.observability.context import *  # noqa: F401,F403
```

Replace `backend/services/langfuse_service.py` with:
```python
"""Re-export shim — moved to backend.observability.langfuse."""
from backend.observability.langfuse import *  # noqa: F401,F403
```

Replace `backend/services/observability_queries.py` with:
```python
"""Re-export shim — moved to backend.observability.queries."""
from backend.observability.queries import *  # noqa: F401,F403
```

- [ ] **Step 3: Copy router files**

- `backend/routers/admin.py` → `backend/observability/routers/admin.py`
- `backend/routers/health.py` → `backend/observability/routers/health.py`
- `backend/routers/observability.py` → `backend/observability/routers/user_observability.py`

Create shims at old paths that re-export the `router` object:
```python
"""Re-export shim — moved to backend.observability.routers.admin."""
from backend.observability.routers.admin import router  # noqa: F401
```

**Critical:** `backend/main.py` imports `from backend.routers import admin, health, observability` — these shims must expose the `router` attribute. Verify `main.py` still works.

- [ ] **Step 4: Update imports across the codebase**

The highest-risk file is `backend/request_context.py` — imported by 15+ files. Grep and update:
```bash
grep -rn "from backend.request_context import" backend/ --include="*.py" | head -20
grep -rn "from backend.request_context import" tests/ --include="*.py" | head -20
```

Update each to import from `backend.observability.context` (or rely on shim — shims work, but prefer new paths for files you're already touching).

- [ ] **Step 5: Update test patch targets**

Grep for test files that mock/patch moved modules:
```bash
grep -rn "backend.agents.observability" tests/ --include="*.py" | head -20
grep -rn "backend.services.langfuse_service" tests/ --include="*.py" | head -20
grep -rn "backend.request_context" tests/ --include="*.py" | head -20
grep -rn "backend.routers.admin" tests/ --include="*.py" | head -20
```

Update `@patch("backend.agents.observability.xxx")` → `@patch("backend.observability.collector.xxx")` etc. **Patch target must match the module where the name is looked up**, not where it was defined.

- [ ] **Step 6: Lint + full test suite**

```bash
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
uv run pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests pass.

- [ ] **Step 7: Alembic verification**

```bash
uv run alembic check
```

Expected: No pending migrations detected. If Alembic falsely detects table changes, the model import chain broke — fix `backend/models/__init__.py` to ensure `LLMCallLog` and `ToolExecutionLog` are still imported.

- [ ] **Step 8: Commit S1b**

```bash
git add -A
git commit -m "refactor: extract context, langfuse, queries, routers to backend/observability/ (S1b)"
```

- [ ] **Step 9: Open PR for Sprint 1 — MERGE GATE**

Branch: `feat/KAN-233-observability-extraction`
Target: `develop`
Title: `[KAN-233] S1: Observability package extraction`

**This PR must be merged before Sprint 2 begins.**

---

## Sprint 2: Backend Instrumentation

### Task 3: S2 — HTTP Request Metrics Middleware (Redis-backed)

**Files:**
- Create: `backend/observability/metrics/http_middleware.py`
- Create: `tests/unit/observability/test_http_middleware.py`
- Modify: `backend/main.py` (add middleware)

- [ ] **Step 1: Write failing tests for the middleware**

Create `tests/unit/observability/__init__.py` and `tests/unit/observability/test_http_middleware.py`:

```python
"""Tests for HTTP request metrics middleware."""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.metrics.http_middleware import (
    HttpMetricsCollector,
    HttpMetricsMiddleware,
    normalize_path,
)


class TestNormalizePath:
    def test_static_path(self):
        assert normalize_path("/api/v1/health") == "/api/v1/health"

    def test_uuid_param(self):
        result = normalize_path("/api/v1/chat/sessions/550e8400-e29b-41d4-a716-446655440000/messages")
        assert result == "/api/v1/chat/sessions/{id}/messages"

    def test_ticker_param(self):
        result = normalize_path("/api/v1/stocks/AAPL/prices")
        assert result == "/api/v1/stocks/{param}/prices"

    def test_excludes_admin_command_center(self):
        assert normalize_path("/api/v1/admin/command-center") is None

    def test_excludes_health(self):
        assert normalize_path("/api/v1/health") is None


class TestHttpMetricsCollector:
    @pytest.fixture
    def mock_redis(self):
        r = AsyncMock()
        r.pipeline.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
        r.pipeline.return_value.__aexit__ = AsyncMock(return_value=None)
        return r

    @pytest.fixture
    def collector(self, mock_redis):
        return HttpMetricsCollector(redis=mock_redis, window_seconds=300)

    @pytest.mark.asyncio
    async def test_record_request(self, collector, mock_redis):
        await collector.record("GET", "/api/v1/stocks/{param}/prices", 200, 45.0)
        # Should call Redis pipeline with INCRBY and ZADD
        assert mock_redis.pipeline.called

    @pytest.mark.asyncio
    async def test_get_stats_returns_null_for_insufficient_data(self, collector, mock_redis):
        # Mock Redis to return small sorted set (< 20 entries)
        mock_redis.zrangebyscore.return_value = [b"1:45.0"] * 5
        mock_redis.get.return_value = b"5"
        stats = await collector.get_stats()
        assert stats["latency_p50_ms"] is None  # insufficient data

    @pytest.mark.asyncio
    async def test_get_stats_computes_percentiles(self, collector, mock_redis):
        # Mock Redis to return enough data points (>= 20)
        latencies = [f"uuid{i}:{float(i * 10)}".encode() for i in range(30)]
        mock_redis.zrangebyscore.return_value = latencies
        mock_redis.get.return_value = b"30"
        stats = await collector.get_stats()
        assert stats["latency_p50_ms"] is not None
        assert stats["sample_count"] == 30
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/unit/observability/test_http_middleware.py -v
```

Expected: ImportError — module doesn't exist yet.

- [ ] **Step 3: Implement HttpMetricsCollector and middleware**

Create `backend/observability/metrics/http_middleware.py`:

```python
"""Redis-backed HTTP request metrics with sliding window.

Multi-worker safe. Uses Redis sorted sets (same pattern as TokenBudget).
Excluded paths: /admin/command-center, /health (self-referential).
"""
from __future__ import annotations

import logging
import re
import time
import uuid

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)
_NUMERIC_RE = re.compile(r"/\d+(?=/|$)")

_EXCLUDED_PREFIXES = ("/api/v1/admin/command-center", "/api/v1/health")

_KEY_PREFIX = "http_metrics"
_KEY_COUNT = f"{_KEY_PREFIX}:count"          # Hash: field=(method:path:status) value=count
_KEY_LATENCY = f"{_KEY_PREFIX}:latency"      # Sorted set: member=uuid:latency score=timestamp
_KEY_ERRORS = f"{_KEY_PREFIX}:errors"        # Hash: field=(method:path:status) value=count
_KEY_TODAY_COUNT = f"{_KEY_PREFIX}:today"     # Simple counter, reset at midnight
_KEY_TODAY_ERRORS = f"{_KEY_PREFIX}:today_err"


def normalize_path(path: str) -> str | None:
    """Normalize path by replacing params with placeholders. Returns None for excluded paths."""
    for prefix in _EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return None
    path = _UUID_RE.sub("{id}", path)
    path = _NUMERIC_RE.sub("/{num}", path)
    # Replace remaining path segments that look like tickers (2-5 uppercase letters)
    parts = path.split("/")
    normalized = []
    for part in parts:
        if re.match(r"^[A-Z]{1,5}$", part):
            normalized.append("{param}")
        else:
            normalized.append(part)
    return "/".join(normalized)


class HttpMetricsCollector:
    """Redis-backed request metrics with sliding window."""

    def __init__(self, redis: aioredis.Redis, window_seconds: int = 300) -> None:
        self._redis = redis
        self._window = window_seconds

    async def record(self, method: str, path: str, status: int, latency_ms: float) -> None:
        """Record a request. Fire-and-forget — errors logged, never raised."""
        try:
            now = time.time()
            field = f"{method}:{path}:{status}"
            member = f"{uuid.uuid4().hex[:12]}:{latency_ms:.1f}"

            async with self._redis.pipeline(transaction=False) as pipe:
                pipe.hincrby(_KEY_COUNT, field, 1)
                pipe.zadd(_KEY_LATENCY, {member: now})
                pipe.incr(_KEY_TODAY_COUNT)
                if status >= 400:
                    pipe.hincrby(_KEY_ERRORS, field, 1)
                    pipe.incr(_KEY_TODAY_ERRORS)
                # Prune entries older than window
                pipe.zremrangebyscore(_KEY_LATENCY, "-inf", now - self._window)
                await pipe.execute()
        except Exception:
            logger.debug("Failed to record HTTP metrics", exc_info=True)

    async def get_stats(self) -> dict:
        """Get current metrics snapshot for the aggregate endpoint."""
        try:
            now = time.time()
            cutoff = now - self._window

            # Get latency data points within window
            raw = await self._redis.zrangebyscore(
                _KEY_LATENCY, cutoff, "+inf", withscores=False
            )
            latencies = []
            for entry in raw:
                text = entry.decode() if isinstance(entry, bytes) else entry
                _, lat_str = text.rsplit(":", 1)
                latencies.append(float(lat_str))

            sample_count = len(latencies)
            elapsed = self._window  # always report full window

            # Percentiles — null if insufficient data
            if sample_count >= 20:
                latencies.sort()
                p50 = latencies[int(sample_count * 0.5)]
                p95 = latencies[int(sample_count * 0.95)]
                p99 = latencies[int(min(sample_count * 0.99, sample_count - 1))]
            else:
                p50 = p95 = p99 = None

            rps = sample_count / elapsed if elapsed > 0 else 0

            today_total = int(await self._redis.get(_KEY_TODAY_COUNT) or 0)
            today_errors = int(await self._redis.get(_KEY_TODAY_ERRORS) or 0)

            error_rate = None
            if sample_count > 0:
                # Count errors in window from hash
                all_fields = await self._redis.hgetall(_KEY_ERRORS)
                window_errors = sum(int(v) for v in all_fields.values()) if all_fields else 0
                error_rate = round((window_errors / max(today_total, 1)) * 100, 2)

            # Top endpoints
            all_counts = await self._redis.hgetall(_KEY_COUNT)
            endpoint_counts: dict[str, dict] = {}
            for field_bytes, count_bytes in (all_counts or {}).items():
                field = field_bytes.decode() if isinstance(field_bytes, bytes) else field_bytes
                parts = field.split(":")
                if len(parts) >= 3:
                    path = parts[1]
                    status = int(parts[2])
                    count = int(count_bytes)
                    if path not in endpoint_counts:
                        endpoint_counts[path] = {"path": path, "count": 0, "errors": 0}
                    endpoint_counts[path]["count"] += count
                    if status >= 400:
                        endpoint_counts[path]["errors"] += count

            top_endpoints = sorted(
                endpoint_counts.values(), key=lambda x: x["count"], reverse=True
            )[:10]

            return {
                "window_seconds": self._window,
                "sample_count": sample_count,
                "rps_avg": round(rps, 1),
                "latency_p50_ms": round(p50, 1) if p50 is not None else None,
                "latency_p95_ms": round(p95, 1) if p95 is not None else None,
                "latency_p99_ms": round(p99, 1) if p99 is not None else None,
                "error_rate_pct": error_rate,
                "total_requests_today": today_total,
                "total_errors_today": today_errors,
                "top_endpoints": top_endpoints,
            }
        except Exception:
            logger.warning("Failed to read HTTP metrics", exc_info=True)
            return {"status": "unavailable", "error": "Redis read failed"}


class HttpMetricsMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that records request metrics to Redis."""

    def __init__(self, app, collector: HttpMetricsCollector) -> None:
        super().__init__(app)
        self._collector = collector

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = normalize_path(request.url.path)
        if path is None:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        latency_ms = (time.monotonic() - start) * 1000

        # Fire and forget — don't await, don't block response
        import asyncio
        asyncio.create_task(
            self._collector.record(request.method, path, response.status_code, latency_ms)
        )
        return response
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/unit/observability/test_http_middleware.py -v
```

- [ ] **Step 5: Wire middleware into main.py**

In `backend/main.py`, after the CORS middleware block (~line 295), add:

```python
# --- HTTP Metrics Middleware ---
from backend.observability.metrics.http_middleware import HttpMetricsCollector, HttpMetricsMiddleware

if hasattr(app.state, "cache_redis") and app.state.cache_redis is not None:
    http_metrics = HttpMetricsCollector(redis=app.state.cache_redis)
    app.add_middleware(HttpMetricsMiddleware, collector=http_metrics)
    app.state.http_metrics = http_metrics
```

Note: `cache_redis` is set during lifespan startup. The middleware needs to be added conditionally or the collector initialized lazily. Check `main.py` lifespan for how Redis is initialized and wire accordingly.

- [ ] **Step 6: Lint + commit**

```bash
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
git add backend/observability/metrics/http_middleware.py tests/unit/observability/ backend/main.py
git commit -m "feat(observability): Redis-backed HTTP request metrics middleware (S2)"
```

---

### Task 4: S3 — DB Pool Stats + Pipeline Stats

**Files:**
- Create: `backend/observability/metrics/db_pool.py`
- Create: `backend/observability/metrics/pipeline_stats.py`
- Create: `tests/unit/observability/test_db_pool.py`
- Create: `tests/unit/observability/test_pipeline_stats.py`

- [ ] **Step 1: Implement DB pool stats collector**

Create `backend/observability/metrics/db_pool.py`:

```python
"""SQLAlchemy connection pool statistics collector."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def get_pool_stats(engine: AsyncEngine) -> dict:
    """Read current pool statistics from SQLAlchemy engine.

    Returns:
        Dict with pool_size, checked_out, overflow, pool_status.
    """
    try:
        pool = engine.pool
        return {
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "checked_in": pool.checkedin(),
            "pool_status": str(pool.status()),
        }
    except Exception:
        logger.warning("Failed to read DB pool stats", exc_info=True)
        return {"status": "unavailable", "error": "Pool stats unavailable"}
```

- [ ] **Step 2: Implement pipeline stats query service**

Create `backend/observability/metrics/pipeline_stats.py`:

```python
"""Pipeline run and watermark query service for command center."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.pipeline import PipelineRun, PipelineWatermark

logger = logging.getLogger(__name__)


async def get_latest_run(db: AsyncSession) -> dict | None:
    """Get the most recent pipeline run with status and ticker counts."""
    result = await db.execute(
        select(PipelineRun)
        .order_by(desc(PipelineRun.started_at))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None

    duration = None
    if run.completed_at and run.started_at:
        duration = (run.completed_at - run.started_at).total_seconds()

    return {
        "started_at": run.started_at.isoformat(),
        "status": run.status,
        "total_duration_seconds": duration,
        "tickers_succeeded": run.tickers_succeeded,
        "tickers_failed": run.tickers_failed,
        "tickers_total": run.tickers_total,
        "step_durations": getattr(run, "step_durations", None),
    }


async def get_watermarks(db: AsyncSession) -> list[dict]:
    """Get all pipeline watermarks with gap detection."""
    result = await db.execute(select(PipelineWatermark))
    watermarks = []
    for wm in result.scalars().all():
        watermarks.append({
            "pipeline": wm.pipeline_name,
            "last_date": wm.last_completed_date.isoformat(),
            "status": wm.status,
        })
    return watermarks


async def get_next_run_time() -> str:
    """Calculate next nightly pipeline run time (21:30 ET)."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("US/Eastern"))
    target = now.replace(hour=21, minute=30, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return target.isoformat()


async def get_run_history(db: AsyncSession, days: int = 7) -> list[dict]:
    """Get pipeline run history for the drill-down view."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.started_at >= cutoff)
        .order_by(desc(PipelineRun.started_at))
        .limit(50)
    )
    runs = []
    for run in result.scalars().all():
        duration = None
        if run.completed_at and run.started_at:
            duration = (run.completed_at - run.started_at).total_seconds()
        runs.append({
            "id": str(run.id),
            "pipeline_name": run.pipeline_name,
            "started_at": run.started_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "status": run.status,
            "total_duration_seconds": duration,
            "tickers_succeeded": run.tickers_succeeded,
            "tickers_failed": run.tickers_failed,
            "tickers_total": run.tickers_total,
            "error_summary": run.error_summary,
            "step_durations": getattr(run, "step_durations", None),
        })
    return runs


async def get_failed_tickers(db: AsyncSession, run_id: str) -> dict | None:
    """Get error details for a specific pipeline run."""
    import uuid as uuid_mod
    result = await db.execute(
        select(PipelineRun).where(PipelineRun.id == uuid_mod.UUID(run_id))
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None
    return {
        "run_id": str(run.id),
        "pipeline_name": run.pipeline_name,
        "tickers_failed": run.tickers_failed,
        "error_summary": run.error_summary or {},
    }
```

- [ ] **Step 3: Write tests for both modules**

Create `tests/unit/observability/test_pipeline_stats.py` with tests covering `get_latest_run`, `get_watermarks`, `get_next_run_time`. Use mock `AsyncSession`.

- [ ] **Step 4: Run tests + lint + commit**

```bash
uv run pytest tests/unit/observability/ -v
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
git add backend/observability/metrics/ tests/unit/observability/
git commit -m "feat(observability): DB pool stats + pipeline stats query service (S3)"
```

---

### Task 5: S4 — Auth Audit Trail (LoginAttempt model + migration + purge)

**Files:**
- Create: `backend/models/login_attempt.py`
- Create: `backend/migrations/versions/XXX_021_login_attempt.py`
- Create: `tests/unit/observability/test_login_attempt.py`
- Modify: `backend/models/__init__.py` (register model)
- Modify: `backend/routers/auth.py` (record attempts)
- Modify: `backend/tasks/__init__.py` (purge Beat schedule)

- [ ] **Step 1: Create LoginAttempt model**

Create `backend/models/login_attempt.py`:

```python
"""Login attempt audit trail for security monitoring."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base, UUIDPrimaryKeyMixin

import uuid


class LoginAttempt(UUIDPrimaryKeyMixin, Base):
    """Audit log of login attempts for brute force detection and compliance."""

    __tablename__ = "login_attempts"

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

- [ ] **Step 2: Register in models/__init__.py**

Add `from backend.models.login_attempt import LoginAttempt  # noqa: F401` to `backend/models/__init__.py`.

- [ ] **Step 3: Generate Alembic migration**

```bash
uv run alembic revision --autogenerate -m "021 add login_attempts table"
```

Review the generated migration — ensure it only creates the `login_attempts` table. Remove any false TimescaleDB index drops.

- [ ] **Step 4: Apply migration**

```bash
uv run alembic upgrade head
```

- [ ] **Step 5: Add recording to auth router**

In `backend/routers/auth.py`, add a helper function and call it from the login endpoint:

```python
async def _record_login_attempt(
    db: AsyncSession,
    email: str,
    success: bool,
    user_id: uuid.UUID | None,
    request: Request,
    failure_reason: str | None = None,
) -> None:
    """Fire-and-forget login attempt recording."""
    try:
        from backend.models.login_attempt import LoginAttempt
        attempt = LoginAttempt(
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            email=email,
            ip_address=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "")[:500],
            success=success,
            failure_reason=failure_reason,
        )
        db.add(attempt)
        await db.commit()
    except Exception:
        logger.debug("Failed to record login attempt", exc_info=True)
```

Call this in the login endpoint — after successful auth and in the failure branch.

- [ ] **Step 6: Create purge Celery task**

Create or add to an appropriate tasks file:

```python
@celery_app.task(name="backend.tasks.purge_login_attempts_task")
def purge_login_attempts_task():
    """Delete login attempts older than 90 days. Batch delete to avoid lock contention."""
    import asyncio
    asyncio.run(_purge_login_attempts_async())


async def _purge_login_attempts_async():
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete
    from backend.database import async_session_factory
    from backend.models.login_attempt import LoginAttempt

    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    async with async_session_factory() as session:
        while True:
            result = await session.execute(
                delete(LoginAttempt)
                .where(LoginAttempt.timestamp < cutoff)
                .execution_options(synchronize_session=False)
            )
            await session.commit()
            if result.rowcount == 0:
                break
            logger.info("Purged %d login attempts older than 90 days", result.rowcount)
```

Add to Beat schedule in `backend/tasks/__init__.py`:
```python
"purge-login-attempts-daily": {
    "task": "backend.tasks.purge_login_attempts_task",
    "schedule": crontab(hour=3, minute=0),  # 3 AM ET daily
},
```

- [ ] **Step 7: Write tests + lint + commit**

```bash
uv run pytest tests/unit/observability/test_login_attempt.py -v
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
git add backend/models/login_attempt.py backend/migrations/versions/ backend/routers/auth.py backend/tasks/ tests/
git commit -m "feat(observability): LoginAttempt audit trail with 90-day purge (S4)"
```

---

### Task 6: S5 — PipelineRun step_durations (Migration 022)

**Files:**
- Create: `backend/migrations/versions/XXX_022_pipeline_step_durations.py`
- Modify: `backend/models/pipeline.py` (add columns)
- Modify: `backend/tasks/pipeline.py` (add `record_step_duration`)
- Modify: `backend/tasks/market_data.py` (call `record_step_duration` per step)

- [ ] **Step 1: Add columns to PipelineRun model**

In `backend/models/pipeline.py`, add to `PipelineRun`:

```python
from sqlalchemy import Float
# ...existing columns...
step_durations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
total_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [ ] **Step 2: Generate + apply migration**

```bash
uv run alembic revision --autogenerate -m "022 add step_durations and total_duration to pipeline_runs"
uv run alembic upgrade head
```

Review migration — should only add 2 columns to `pipeline_runs`.

- [ ] **Step 3: Add `record_step_duration` to PipelineRunner**

In `backend/tasks/pipeline.py`, add method:

```python
async def record_step_duration(
    self, run_id: uuid.UUID, step_name: str, duration_seconds: float
) -> None:
    """Atomic JSONB merge — safe for concurrent step writes."""
    from sqlalchemy import text
    async with self._session_factory() as session:
        await session.execute(
            text("""
                UPDATE pipeline_runs
                SET step_durations = COALESCE(step_durations, '{}'::jsonb) || :step_json
                WHERE id = :run_id
            """),
            {
                "step_json": f'{{"{step_name}": {duration_seconds:.1f}}}',
                "run_id": str(run_id),
            },
        )
        await session.commit()
```

Update `complete_run()` to compute `total_duration_seconds` from `completed_at - started_at`.

- [ ] **Step 4: Instrument nightly chain steps with timing**

In `backend/tasks/market_data.py`, wrap each pipeline phase with `time.monotonic()` and call `record_step_duration()`.

- [ ] **Step 5: Tests + lint + commit**

```bash
uv run pytest tests/unit/ -v --tb=short -q
git add backend/models/pipeline.py backend/migrations/versions/ backend/tasks/
git commit -m "feat(observability): PipelineRun step_durations + total_duration (S5)"
```

---

### Task 7: S6 — TokenBudget Status + Celery + Langfuse Health

**Files:**
- Create: `backend/observability/metrics/health_checks.py`
- Create: `tests/unit/observability/test_health_checks.py`

- [ ] **Step 1: Implement health check collectors**

Create `backend/observability/metrics/health_checks.py`:

```python
"""Health check implementations for Celery, Langfuse, and TokenBudget status."""
from __future__ import annotations

import asyncio
import logging
import time

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Cached results to avoid expensive checks on every poll
_celery_cache: dict = {}
_celery_cache_time: float = 0
_CELERY_CACHE_TTL = 30  # seconds

_langfuse_cache: dict = {}
_langfuse_cache_time: float = 0
_LANGFUSE_CACHE_TTL = 60  # seconds


async def get_celery_health(redis: aioredis.Redis) -> dict:
    """Get Celery worker count, queue depth, and beat status."""
    global _celery_cache, _celery_cache_time
    now = time.time()
    if now - _celery_cache_time < _CELERY_CACHE_TTL:
        return _celery_cache

    try:
        # Queue depth from Redis (fast)
        queue_len = await redis.llen("celery") or 0

        # Worker count via celery inspect (blocking — run in thread)
        workers = None
        try:
            from backend.tasks import celery_app
            result = await asyncio.wait_for(
                asyncio.to_thread(lambda: celery_app.control.inspect(timeout=2).ping()),
                timeout=3,
            )
            workers = len(result) if result else 0
        except (asyncio.TimeoutError, Exception):
            workers = None  # unknown, not 0

        # Beat status inferred from last pipeline run recency
        beat_active = None
        try:
            from backend.database import async_session_factory
            from backend.models.pipeline import PipelineRun
            from sqlalchemy import select, desc
            from datetime import datetime, timedelta, timezone

            async with async_session_factory() as session:
                result = await session.execute(
                    select(PipelineRun.started_at)
                    .order_by(desc(PipelineRun.started_at))
                    .limit(1)
                )
                last_run = result.scalar_one_or_none()
                if last_run:
                    beat_active = (datetime.now(timezone.utc) - last_run) < timedelta(hours=26)
        except Exception:
            pass

        _celery_cache = {
            "workers": workers,
            "queued": queue_len,
            "beat_active": beat_active,
        }
        _celery_cache_time = now
        return _celery_cache
    except Exception:
        logger.warning("Failed to check Celery health", exc_info=True)
        return {"workers": None, "queued": None, "beat_active": None}


async def get_langfuse_health(langfuse_service) -> dict:
    """Check Langfuse connectivity and trace count from local DB."""
    global _langfuse_cache, _langfuse_cache_time
    now = time.time()
    if now - _langfuse_cache_time < _LANGFUSE_CACHE_TTL:
        return _langfuse_cache

    connected = False
    traces_today = 0
    spans_today = 0

    try:
        if langfuse_service and langfuse_service.enabled:
            # Lightweight probe
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(lambda: langfuse_service._client.auth_check()),
                    timeout=2,
                )
                connected = bool(result)
            except Exception:
                connected = False

            # Count from local DB
            from backend.database import async_session_factory
            from backend.models.logs import LLMCallLog, ToolExecutionLog
            from sqlalchemy import select, func
            from datetime import datetime, timezone

            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            async with async_session_factory() as session:
                trace_result = await session.execute(
                    select(func.count())
                    .select_from(LLMCallLog)
                    .where(
                        LLMCallLog.created_at >= today_start,
                        LLMCallLog.langfuse_trace_id.isnot(None),
                    )
                )
                traces_today = trace_result.scalar() or 0

                span_result = await session.execute(
                    select(func.count())
                    .select_from(ToolExecutionLog)
                    .where(ToolExecutionLog.created_at >= today_start)
                )
                spans_today = span_result.scalar() or 0
    except Exception:
        logger.warning("Failed to check Langfuse health", exc_info=True)

    _langfuse_cache = {
        "connected": connected,
        "traces_today": traces_today,
        "spans_today": spans_today,
    }
    _langfuse_cache_time = now
    return _langfuse_cache


async def get_token_budget_status(token_budget) -> list[dict]:
    """Get current budget utilization percentages per model."""
    if token_budget is None:
        return []
    try:
        budgets = []
        for model, limits in token_budget._limits.items():
            tpm_used = 0
            rpm_used = 0
            # Read current usage from Redis via can_afford logic
            # (reuse the Lua prune-and-sum script)
            if limits.get("tpm_limit"):
                tpm_used = await token_budget._get_usage(model, "minute_tokens")
                tpm_pct = round((tpm_used / limits["tpm_limit"]) * 100, 1) if limits["tpm_limit"] else 0
            else:
                tpm_pct = 0
            if limits.get("rpm_limit"):
                rpm_used = await token_budget._get_usage(model, "minute_requests")
                rpm_pct = round((rpm_used / limits["rpm_limit"]) * 100, 1) if limits["rpm_limit"] else 0
            else:
                rpm_pct = 0
            budgets.append({
                "model": model,
                "tpm_used_pct": tpm_pct,
                "rpm_used_pct": rpm_pct,
            })
        return budgets
    except Exception:
        logger.warning("Failed to read token budget status", exc_info=True)
        return []
```

Note: `token_budget._get_usage()` may not exist — check the actual `TokenBudget` class and adapt. The key insight is reusing the existing Lua `_LUA_PRUNE_AND_SUM` script to read current usage.

- [ ] **Step 2: Write tests**

Test each health check with mocked dependencies. Key tests:
- Celery timeout returns `workers: null` (not 0)
- Langfuse probe failure returns `connected: false`
- Token budget with no limits returns empty list
- Cache TTL prevents repeated calls

- [ ] **Step 3: Lint + commit**

```bash
uv run pytest tests/unit/observability/ -v
git add backend/observability/metrics/health_checks.py tests/unit/observability/
git commit -m "feat(observability): Celery, Langfuse, TokenBudget health checks (S6)"
```

---

## Sprint 3: API Endpoints

### Task 8: S7 — Aggregate Endpoint (4 zones)

**Files:**
- Create: `backend/observability/routers/command_center.py`
- Create: `backend/schemas/command_center.py`
- Create: `tests/api/test_command_center.py`
- Modify: `backend/main.py` (mount router)

- [ ] **Step 1: Create Pydantic response schemas**

Create `backend/schemas/command_center.py` with typed models for each zone:

```python
"""Command Center API response schemas."""
from __future__ import annotations
from pydantic import BaseModel


class DatabaseHealth(BaseModel):
    healthy: bool
    latency_ms: float
    pool_active: int
    pool_size: int
    pool_overflow: int
    migration_head: str | None = None

class RedisHealth(BaseModel):
    healthy: bool
    latency_ms: float
    memory_used_mb: float | None = None
    memory_max_mb: float | None = None
    total_keys: int | None = None

class McpHealth(BaseModel):
    healthy: bool
    mode: str
    tool_count: int
    restarts: int
    uptime_seconds: int | None = None

class CeleryHealth(BaseModel):
    workers: int | None = None
    queued: int | None = None
    beat_active: bool | None = None

class LangfuseHealth(BaseModel):
    connected: bool
    traces_today: int = 0
    spans_today: int = 0

class SystemHealthZone(BaseModel):
    status: str  # "ok" | "degraded"
    database: DatabaseHealth
    redis: RedisHealth
    mcp: McpHealth
    celery: CeleryHealth
    langfuse: LangfuseHealth

class ApiTrafficZone(BaseModel):
    window_seconds: int = 300
    sample_count: int = 0
    rps_avg: float = 0
    latency_p50_ms: float | None = None
    latency_p95_ms: float | None = None
    latency_p99_ms: float | None = None
    error_rate_pct: float | None = None
    total_requests_today: int = 0
    total_errors_today: int = 0
    top_endpoints: list[dict] = []

class TierHealth(BaseModel):
    name: str
    status: str  # "healthy" | "degraded" | "disabled"
    models: int
    p95_ms: float | None = None

class TokenBudgetStatus(BaseModel):
    model: str
    tpm_used_pct: float = 0
    rpm_used_pct: float = 0

class LlmOperationsZone(BaseModel):
    tiers: list[TierHealth] = []
    cost_today_usd: float = 0
    cost_yesterday_usd: float = 0
    cost_week_usd: float = 0
    cascade_rate_pct: float = 0
    token_budgets: list[TokenBudgetStatus] = []

class PipelineLastRun(BaseModel):
    started_at: str
    status: str
    total_duration_seconds: float | None = None
    tickers_succeeded: int = 0
    tickers_failed: int = 0
    step_durations: dict | None = None

class PipelineWatermarkStatus(BaseModel):
    pipeline: str
    last_date: str
    status: str

class PipelineZone(BaseModel):
    last_run: PipelineLastRun | None = None
    watermarks: list[PipelineWatermarkStatus] = []
    next_run_at: str | None = None

class CommandCenterMeta(BaseModel):
    assembly_ms: int = 0
    degraded_zones: list[str] = []

class CommandCenterResponse(BaseModel):
    timestamp: str
    _meta: CommandCenterMeta = CommandCenterMeta()
    system_health: SystemHealthZone | None = None
    api_traffic: ApiTrafficZone | None = None
    llm_operations: LlmOperationsZone | None = None
    pipeline: PipelineZone | None = None

    class Config:
        # Allow _meta field name
        fields = {"_meta": {"alias": "meta"}}
```

- [ ] **Step 2: Implement aggregate endpoint**

Create `backend/observability/routers/command_center.py`:

```python
"""Command Center aggregate endpoint with per-zone circuit breakers."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user, require_admin
from backend.models.user import User
from backend.schemas.command_center import (
    CommandCenterResponse,
    CommandCenterMeta,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/command-center", tags=["command-center"])

_CACHE_KEY = "admin:command_center:aggregate"
_CACHE_TTL = 10  # seconds


async def _collect_zone(name: str, coro, timeout: float = 3.0) -> tuple[str, dict | None]:
    """Run a zone collector with timeout. Returns (name, data_or_None)."""
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return (name, result)
    except asyncio.TimeoutError:
        logger.warning("Command center zone '%s' timed out after %.1fs", name, timeout)
        return (name, None)
    except Exception:
        logger.warning("Command center zone '%s' failed", name, exc_info=True)
        return (name, None)


@router.get(
    "",
    summary="Command Center aggregate dashboard",
    description="Returns all L1 zone data in a single call. Polled every 15s by the frontend. "
    "Server-side cached for 10s. Each zone degrades independently.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_command_center(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Assemble all zone data with asyncio.gather and per-zone circuit breakers."""
    require_admin(user)

    # Check server-side cache
    cache_redis = getattr(request.app.state, "cache_redis", None)
    if cache_redis:
        try:
            import json
            cached = await cache_redis.get(_CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    start = time.monotonic()

    # Collect zones in parallel
    zone_results = await asyncio.gather(
        _collect_zone("system_health", _get_system_health(request, db)),
        _collect_zone("api_traffic", _get_api_traffic(request)),
        _collect_zone("llm_operations", _get_llm_operations(request, db)),
        _collect_zone("pipeline", _get_pipeline(db)),
        return_exceptions=True,
    )

    # Assemble response
    assembly_ms = int((time.monotonic() - start) * 1000)
    degraded_zones = []
    response = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "_meta": {"assembly_ms": assembly_ms, "degraded_zones": []},
    }

    for item in zone_results:
        if isinstance(item, Exception):
            logger.error("Zone collection error: %s", item)
            continue
        name, data = item
        if data is None:
            degraded_zones.append(name)
            response[name] = {"status": "unavailable"}
        else:
            response[name] = data

    response["_meta"]["degraded_zones"] = degraded_zones

    if assembly_ms > 2000:
        logger.warning("Command center assembly took %dms (threshold: 2000ms)", assembly_ms)

    # Cache response
    if cache_redis:
        try:
            import json
            await cache_redis.set(_CACHE_KEY, json.dumps(response, default=str), ex=_CACHE_TTL)
        except Exception:
            pass

    return response


# --- Zone collectors (each returns a dict or raises) ---

async def _get_system_health(request: Request, db: AsyncSession) -> dict:
    """Collect system health from DB, Redis, MCP, Celery, Langfuse."""
    from backend.observability.metrics.db_pool import get_pool_stats
    from backend.observability.metrics.health_checks import (
        get_celery_health,
        get_langfuse_health,
    )
    from backend.database import engine as db_engine

    # DB health
    db_start = time.monotonic()
    from sqlalchemy import text
    await db.execute(text("SELECT 1"))
    db_latency = (time.monotonic() - db_start) * 1000
    pool_stats = await get_pool_stats(db_engine)

    # Redis health
    cache_redis = getattr(request.app.state, "cache_redis", None)
    redis_healthy = False
    redis_latency = 0
    redis_info = {}
    if cache_redis:
        redis_start = time.monotonic()
        try:
            await cache_redis.ping()
            redis_healthy = True
            redis_latency = (time.monotonic() - redis_start) * 1000
            info = await cache_redis.info("memory")
            redis_info = {
                "memory_used_mb": round(info.get("used_memory", 0) / 1024 / 1024, 1),
                "memory_max_mb": round(info.get("maxmemory", 0) / 1024 / 1024, 1) or None,
            }
            db_size = await cache_redis.dbsize()
            redis_info["total_keys"] = db_size
        except Exception:
            redis_latency = (time.monotonic() - redis_start) * 1000

    # MCP health
    mcp_manager = getattr(request.app.state, "mcp_manager", None)
    mcp = {
        "healthy": mcp_manager.healthy if mcp_manager else False,
        "mode": getattr(mcp_manager, "mode", "disabled"),
        "tool_count": getattr(mcp_manager, "tool_count", 0) if mcp_manager else 0,
        "restarts": getattr(mcp_manager, "restart_count", 0) if mcp_manager else 0,
        "uptime_seconds": int(getattr(mcp_manager, "uptime_seconds", 0) or 0) if mcp_manager else 0,
    }

    # Celery + Langfuse
    celery = await get_celery_health(cache_redis) if cache_redis else {}
    langfuse_svc = getattr(request.app.state, "langfuse", None)
    langfuse = await get_langfuse_health(langfuse_svc)

    # Overall status
    all_healthy = (
        redis_healthy
        and mcp.get("healthy", False)
        and pool_stats.get("checked_out", 0) < pool_stats.get("pool_size", 5)
    )

    return {
        "status": "ok" if all_healthy else "degraded",
        "database": {
            "healthy": True,
            "latency_ms": round(db_latency, 1),
            "pool_active": pool_stats.get("checked_out", 0),
            "pool_size": pool_stats.get("pool_size", 0),
            "pool_overflow": pool_stats.get("overflow", 0),
            "migration_head": None,  # Could read from alembic_version table
        },
        "redis": {
            "healthy": redis_healthy,
            "latency_ms": round(redis_latency, 1),
            **redis_info,
        },
        "mcp": mcp,
        "celery": celery,
        "langfuse": langfuse,
    }


async def _get_api_traffic(request: Request) -> dict:
    """Get HTTP traffic metrics from Redis-backed collector."""
    http_metrics = getattr(request.app.state, "http_metrics", None)
    if http_metrics is None:
        return {"status": "unavailable", "error": "HTTP metrics not initialized"}
    return await http_metrics.get_stats()


async def _get_llm_operations(request: Request, db: AsyncSession) -> dict:
    """Get LLM tier health, cost, cascade rate, token budgets."""
    from backend.observability.collector import ObservabilityCollector
    from backend.observability.metrics.health_checks import get_token_budget_status

    collector = ObservabilityCollector()

    # Tier health
    tier_health = await collector.get_tier_health()

    # Cost from DB
    from sqlalchemy import select, func
    from backend.models.logs import LLMCallLog
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=7)

    cost_today = (await db.execute(
        select(func.coalesce(func.sum(LLMCallLog.cost_usd), 0))
        .where(LLMCallLog.created_at >= today_start)
    )).scalar() or 0

    cost_yesterday = (await db.execute(
        select(func.coalesce(func.sum(LLMCallLog.cost_usd), 0))
        .where(LLMCallLog.created_at >= yesterday_start, LLMCallLog.created_at < today_start)
    )).scalar() or 0

    cost_week = (await db.execute(
        select(func.coalesce(func.sum(LLMCallLog.cost_usd), 0))
        .where(LLMCallLog.created_at >= week_start)
    )).scalar() or 0

    # Cascade rate
    cascade_rate = await collector.fallback_rate_last_60s()

    # Token budgets
    token_budget = getattr(request.app.state, "token_budget", None)
    budgets = await get_token_budget_status(token_budget)

    return {
        "tiers": tier_health if isinstance(tier_health, list) else [],
        "cost_today_usd": round(float(cost_today), 2),
        "cost_yesterday_usd": round(float(cost_yesterday), 2),
        "cost_week_usd": round(float(cost_week), 2),
        "cascade_rate_pct": round(cascade_rate * 100, 1) if cascade_rate else 0,
        "token_budgets": budgets,
    }


async def _get_pipeline(db: AsyncSession) -> dict:
    """Get pipeline last run, watermarks, next run time."""
    from backend.observability.metrics.pipeline_stats import (
        get_latest_run,
        get_watermarks,
        get_next_run_time,
    )

    last_run = await get_latest_run(db)
    watermarks = await get_watermarks(db)
    next_run = await get_next_run_time()

    return {
        "last_run": last_run,
        "watermarks": watermarks,
        "next_run_at": next_run,
    }
```

- [ ] **Step 3: Mount router in main.py**

Add to `backend/main.py` router section:
```python
from backend.observability.routers.command_center import router as command_center_router
app.include_router(command_center_router, prefix="/api/v1")
```

- [ ] **Step 4: Write API tests**

Create `tests/api/test_command_center.py` with tests:
1. Unauthenticated → 401
2. Non-admin → 403
3. Happy path → 200 with all 4 zones
4. Degraded mode (mock Redis unavailable) → 200 with `degraded_zones: ["api_traffic"]`
5. Server-side cache hit (two rapid calls)
6. `_meta.assembly_ms` is present and > 0

- [ ] **Step 5: Run tests + lint + commit**

```bash
uv run pytest tests/api/test_command_center.py -v
uv run ruff check --fix backend/ tests/ && uv run ruff format backend/ tests/
git add backend/observability/routers/command_center.py backend/schemas/command_center.py tests/api/ backend/main.py
git commit -m "feat(observability): Command center aggregate endpoint with circuit breakers (S7)"
```

---

### Task 9: S8 — Drill-Down Endpoints (3)

**Files:**
- Modify: `backend/observability/routers/command_center.py` (add 3 drill-down routes)
- Create: `tests/api/test_command_center_drilldowns.py`

- [ ] **Step 1: Add drill-down endpoints to command_center.py**

Add 3 GET endpoints:

```python
@router.get("/api-traffic")
async def get_api_traffic_detail(
    hours: int = 24,
    user: User = Depends(get_current_user),
    request: Request = None,
):
    """Full endpoint table, latency histogram for API traffic drill-down."""
    require_admin(user)
    # Return expanded API traffic data including per-endpoint breakdown
    ...

@router.get("/llm")
async def get_llm_detail(
    hours: int = 24,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
    request: Request = None,
):
    """Per-model cost chart data, cascade log, token consumption."""
    require_admin(user)
    # Query LLMCallLog for detailed breakdown
    ...

@router.get("/pipeline")
async def get_pipeline_detail(
    days: int = 7,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Run history, failed tickers, step duration trends."""
    require_admin(user)
    from backend.observability.metrics.pipeline_stats import get_run_history
    runs = await get_run_history(db, days=days)
    return {"runs": runs, "total": len(runs)}
```

Each endpoint queries deeper data than the aggregate — full tables, historical breakdowns, error logs.

- [ ] **Step 2: Write API tests (2 per endpoint = 6 tests)**

Test auth gate (401/403) and happy path for each drill-down.

- [ ] **Step 3: Lint + commit**

```bash
uv run pytest tests/api/test_command_center_drilldowns.py -v
git add backend/observability/routers/command_center.py tests/api/
git commit -m "feat(observability): 3 drill-down endpoints — API traffic, LLM, Pipeline (S8)"
```

---

## Sprint 4: Frontend

### Task 10: S9 — Frontend L1 (4 Zone Panels + Page)

**Files:**
- Create: `frontend/src/hooks/use-command-center.ts`
- Create: `frontend/src/app/admin/command-center/page.tsx`
- Create: `frontend/src/components/command-center/system-health-panel.tsx`
- Create: `frontend/src/components/command-center/api-traffic-panel.tsx`
- Create: `frontend/src/components/command-center/llm-operations-panel.tsx`
- Create: `frontend/src/components/command-center/pipeline-panel.tsx`
- Create: `frontend/src/components/command-center/status-dot.tsx`
- Create: `frontend/src/components/command-center/gauge-bar.tsx`
- Create: `frontend/src/components/command-center/metric-card.tsx`
- Create: `frontend/src/components/command-center/last-refreshed.tsx`
- Create: `frontend/src/components/command-center/degraded-badge.tsx`
- Create: `frontend/src/types/command-center.ts`

**Visual reference:** Open `command-center-prototype.html` in browser and match the layout.

- [ ] **Step 1: Create TypeScript types**

Create `frontend/src/types/command-center.ts` matching the backend Pydantic schemas. Define `CommandCenterResponse`, `SystemHealthZone`, `ApiTrafficZone`, `LlmOperationsZone`, `PipelineZone`.

- [ ] **Step 2: Create `useCommandCenter` hook**

```typescript
// frontend/src/hooks/use-command-center.ts
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { CommandCenterResponse } from "@/types/command-center";

export function useCommandCenter() {
  return useQuery<CommandCenterResponse>({
    queryKey: ["command-center"],
    queryFn: () => apiFetch("/admin/command-center"),
    refetchInterval: 15_000,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  });
}

export function useCommandCenterDrillDown(zone: string, params?: Record<string, string>) {
  return useQuery({
    queryKey: ["command-center", zone, params],
    queryFn: () => apiFetch(`/admin/command-center/${zone}`, { params }),
    enabled: false, // manual fetch only
    staleTime: 30_000,
  });
}
```

- [ ] **Step 3: Create shared primitive components**

Create in `frontend/src/components/command-center/`:
- `status-dot.tsx` — pulsing green/yellow/red dot (CSS animation)
- `gauge-bar.tsx` — horizontal bar with fill percentage and color thresholds
- `metric-card.tsx` — label + big JetBrains Mono number + subtitle
- `last-refreshed.tsx` — "Last refreshed: Xs ago" with yellow/red thresholds
- `degraded-badge.tsx` — warning badge for unavailable zones

- [ ] **Step 4: Create SystemHealthPanel**

`frontend/src/components/command-center/system-health-panel.tsx` — sidebar panel showing DB, Redis, MCP, Celery, Langfuse health cards with StatusDot and metric details. Match the prototype's Zone 1 layout.

- [ ] **Step 5: Create ApiTrafficPanel**

`frontend/src/components/command-center/api-traffic-panel.tsx` — RPS, latency P95, error rate metric cards + top endpoints table. Use Recharts AreaChart for RPS sparkline (same pattern as existing `sparkline.tsx`).

- [ ] **Step 6: Create LlmOperationsPanel**

`frontend/src/components/command-center/llm-operations-panel.tsx` — tier health cards (green/yellow/red border), cost today vs yesterday with delta arrow, cascade rate, token budget gauges using GaugeBar component.

- [ ] **Step 7: Create PipelinePanel**

`frontend/src/components/command-center/pipeline-panel.tsx` — 9-step timeline with StatusDot per step, last run / next run stats, ticker success/fail counts, watermark status.

- [ ] **Step 8: Create page layout**

`frontend/src/app/admin/command-center/page.tsx`:
- Admin role check (redirect non-admins)
- CSS Grid layout matching prototype: 3-column for MVP
- Wire `useCommandCenter()` hook
- Render 4 zone panels with data
- Show `LastRefreshedIndicator` in top bar
- Show `DegradedBadge` on any zones in `_meta.degraded_zones`

- [ ] **Step 9: Write Jest tests**

Create `frontend/__tests__/components/command-center/` with tests:
1. `CommandCenterPage` renders without crash
2. `SystemHealthPanel` shows correct status dots for healthy/degraded
3. `MetricCard` displays value and label
4. `GaugeBar` renders fill at correct width
5. `StatusDot` has pulse animation class when healthy
6. `LastRefreshedIndicator` shows yellow after 30s
7. `DegradedBadge` renders when zone is unavailable
8. Non-admin redirect (mock `useCurrentUser`)

- [ ] **Step 10: Lint + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npx jest --passWithNoTests
git add frontend/src/
git commit -m "feat(frontend): Command center L1 — 4 zone panels + hooks + page (S9)"
```

---

### Task 11: S10 — Frontend L2 Drill-Downs (3 sheets)

**Files:**
- Create: `frontend/src/components/command-center/drill-down-sheet.tsx`
- Create: `frontend/src/components/command-center/api-traffic-detail.tsx`
- Create: `frontend/src/components/command-center/llm-detail.tsx`
- Create: `frontend/src/components/command-center/pipeline-detail.tsx`

- [ ] **Step 1: Create DrillDownSheet wrapper**

Slide-out panel (use shadcn Sheet component) with zone title, manual Refresh button, close button, and content slot.

- [ ] **Step 2: Create ApiTrafficDetail**

Full endpoint table (sortable by count, latency, errors), latency histogram using Recharts BarChart, error log list.

- [ ] **Step 3: Create LlmDetail**

Per-model cost breakdown chart (Recharts BarChart), cascade event log (scrollable list), daily token consumption line chart.

- [ ] **Step 4: Create PipelineDetail**

Run history table (last 7 days), failed ticker list with error messages, step duration trend chart (Recharts).

- [ ] **Step 5: Wire drill-downs into zone panels**

Each zone panel gets an "expand" click handler that opens the `DrillDownSheet` with the appropriate detail component. The `useCommandCenterDrillDown` hook fetches data on first open, then shows a Refresh button for manual re-fetch.

- [ ] **Step 6: Write Jest tests**

4-5 tests covering: drill-down opens on click, Refresh button triggers refetch, close button works, data renders in table format.

- [ ] **Step 7: Final integration test + commit**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npx jest
git add frontend/src/
git commit -m "feat(frontend): Command center L2 — 3 drill-down sheets (S10)"
```

---

### Task 12: Sprint 4 Wrap-Up — PR + Verification

- [ ] **Step 1: Run full backend test suite**

```bash
uv run pytest tests/unit/ tests/api/ -v --tb=short -q
```

- [ ] **Step 2: Run frontend tests + build**

```bash
cd frontend && npx jest && npm run build
```

- [ ] **Step 3: Manual smoke test**

1. Start backend: `uv run uvicorn backend.main:app --reload --port 8181`
2. Start frontend: `cd frontend && npm run dev`
3. Log in as admin
4. Navigate to `/admin/command-center`
5. Verify all 4 zones render with live data
6. Click each zone — verify drill-down opens
7. Compare layout against `command-center-prototype.html`

- [ ] **Step 4: Open PR**

Branch: `feat/KAN-233-command-center-mvp`
Target: `develop`
Title: `[KAN-233] Platform Operations Command Center MVP (4 zones)`

---

## Self-Review Checklist

| Spec Section | Task(s) | Covered? |
|---|---|---|
| §2.3 Package extraction S1a+S1b | Tasks 1-2 | Yes |
| §2.3 Merge gate | Task 2 Step 9 | Yes |
| §2.3 Verification checklist | Task 2 Steps 5-7 | Yes |
| §3.1 Redis-backed HTTP metrics | Task 3 | Yes |
| §3.1 Sliding window | Task 3 (sorted set pattern) | Yes |
| §3.1 Excluded paths | Task 3 (normalize_path returns None) | Yes |
| §3.1 Insufficient data null | Task 3 (< 20 samples) | Yes |
| §3.3 DB pool stats | Task 4 | Yes |
| §3.5 Pipeline stats | Task 4 | Yes |
| §3.6 LoginAttempt model | Task 5 | Yes |
| §3.6 Purge Celery task | Task 5 Step 6 | Yes |
| §3.6 CCPA/GDPR retention | Task 5 (90-day purge) | Yes |
| §4.1 Migration 021 | Task 5 | Yes |
| §4.2 Migration 022 (separate) | Task 6 | Yes |
| §4.2 Atomic JSONB merge | Task 6 Step 3 | Yes |
| §5.1 asyncio.gather per-zone | Task 8 | Yes |
| §5.1 Per-zone circuit breaker | Task 8 (_collect_zone) | Yes |
| §5.1 10s server-side cache | Task 8 (_CACHE_KEY) | Yes |
| §5.1 _meta.assembly_ms | Task 8 | Yes |
| §5.1 degraded_zones | Task 8 | Yes |
| §5.1 cost_yesterday_usd | Task 8 (_get_llm_operations) | Yes |
| §5.2 Drill-down endpoints (3) | Task 9 | Yes |
| §5.2 Manual refresh only | Task 11 | Yes |
| §5.3 15s poll + refetchOnWindowFocus | Task 10 Step 2 | Yes |
| §5.4 Celery health (inspect + llen + PipelineRun) | Task 7 | Yes |
| §5.5 Langfuse health (probe + local DB) | Task 7 | Yes |
| §6.3 LastRefreshedIndicator | Task 10 Step 3 | Yes |
| §6.3 DegradedZoneBadge | Task 10 Step 3 | Yes |
| §6.6 Copy as JSON | Not explicitly tasked | Gap — add to Task 11 |
| §7.1 Alerting thresholds documented | Spec only, not implemented | Correct (spec §7.1) |
| §12 Prototype reference | Task 10 header | Yes |

**Gap found:** §6.6 "Copy as JSON" button on drill-down sheets. Add to Task 11 Step 1 — include a "Copy JSON" button in the DrillDownSheet wrapper that copies the zone data to clipboard.

---

## Appendix: Expert Review Findings & Fixes Applied

This plan was reviewed by 3 expert personas (Ops Architect, Backend Architect, Engineering TL). 4 Critical + 12 Important findings. Key fixes applied:

### Critical Fixes (must address during implementation)

| # | Finding | Fix | Task |
|---|---------|-----|------|
| C1 | `_KEY_COUNT` / `_KEY_ERRORS` hashes grow unbounded | Use date-bucketed keys: `http_metrics:count:2026-03-31` with 48h TTL. Rotate daily. | Task 3 |
| C2 | `_KEY_TODAY_COUNT` / `_KEY_TODAY_ERRORS` never reset | Use date-bucketed keys with TTL: `http_metrics:today:2026-03-31` (ex=172800) | Task 3 |
| C3 | `llm_call_log.created_at` has no standalone index — 3 cost queries will seqscan | Consolidate into 1 query with `CASE WHEN` buckets. Add index in migration 021 or 022: `CREATE INDEX ix_llm_call_log_created_at ON llm_call_log (created_at)` | Task 8 |
| C4 | `collector.get_tier_health()` and `fallback_rate_last_60s()` require `db` param — plan calls without args | Pass `db` session: `await collector.get_tier_health(db)`, `await collector.fallback_rate_last_60s(db)`. Verify actual method signatures before implementing. | Task 8 |

### Important Fixes

| # | Finding | Fix | Task |
|---|---------|-----|------|
| I1 | Error rate mixes all-time hash with today counter | Compute error rate as `today_errors / today_total` (both from same time bucket) | Task 3 |
| I2 | `get_celery_health` opens own DB session — pool pressure | Pass `db: AsyncSession` from aggregate endpoint, don't create new session | Task 7, 8 |
| I3 | Wildcard `from module import *` in shims risks unintended exports | Define `__all__` in each new module, or use explicit named imports in shims | Task 1, 2 |
| I4 | `git add -A` in Task 2 stages everything | Use explicit file paths | Task 2 |
| I5 | LoginAttempt purge DELETE has no LIMIT — could lock table | Use subquery with LIMIT 1000: `DELETE WHERE id IN (SELECT id ... LIMIT 1000)` | Task 5 |
| I6 | `_record_login_attempt` commits on same session as login endpoint | Use separate `async_session_factory()` session for audit write | Task 5 |
| I7 | `token_budget._get_usage()` does not exist | Add `get_usage(model, window)` public method to TokenBudget, or call Lua script directly | Task 7 |
| I8 | Task 9 drill-down endpoints are `...` stubs | Flesh out with full implementations before Sprint 4 | Task 9 |
| I9 | No sidebar nav link for command center | Add "Command Center" to admin sidebar nav in Task 10 Step 8 | Task 10 |
| I10 | Pydantic schema uses `_meta` (v1 syntax) | Rename to `meta` with `Field(alias="_meta")` and `ConfigDict(populate_by_name=True)` | Task 8 |
| I11 | `normalize_path` tests contradict (health both included and excluded) | Remove the static path test for `/api/v1/health` — it should return `None` (excluded) | Task 3 |
| I12 | `record_step_duration` uses f-string for JSONB — fragile | Use `json.dumps({step_name: round(duration_seconds, 1)})` as parameter | Task 6 |

### Minor Notes

- Circuit breaker naming: `_collect_zone` is timeout-based isolation, not a true circuit breaker. Add clarifying comment.
- Sprint 2 tasks (3-7) are independent and parallelizable — can dispatch as subagents.
- Add `data-testid` to command center components for future Playwright E2E.
- Verify `tests/api/__init__.py` exists before adding test files.
