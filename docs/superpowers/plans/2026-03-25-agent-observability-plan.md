# Phase 6B — Agent Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the agent pipeline to write every LLM call and tool execution to the database, expose real-time cascade health metrics in memory, and provide admin API endpoints for monitoring.

**Architecture:** Fire-and-forget async DB writes in the provider/executor hot path (logging failures never block user requests). In-memory `ObservabilityCollector` singleton tracks real-time RPM, cascade events, and per-model health via sliding windows. ContextVars carry `session_id` and `query_id` from the chat router down to the write layer without changing any function signatures.

**Tech Stack:** Python asyncio, SQLAlchemy async, ContextVars, FastAPI, existing `LLMCallLog` / `ToolExecutionLog` models (TimescaleDB hypertables, migrations 008+010)

**Spec:** `docs/superpowers/specs/2026-03-25-agent-observability-design.md`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/agents/observability.py` | ObservabilityCollector singleton — in-memory metrics + async DB writes |
| Modify | `backend/request_context.py` | Add `current_session_id`, `current_query_id` ContextVars |
| Modify | `backend/routers/chat.py` | Set ContextVars before streaming |
| Modify | `backend/agents/providers/groq.py` | Record LLM calls + cascade events via collector |
| Modify | `backend/agents/llm_client.py` | Record provider-level fallback events |
| Modify | `backend/agents/executor.py` | Record tool execution events via collector |
| Modify | `backend/routers/admin.py` | Add 4 observability endpoints |
| Modify | `backend/main.py` | Instantiate collector, wire into providers/executor, shutdown flush |
| Create | `tests/unit/agents/test_observability.py` | Unit tests for collector |
| Create | `tests/api/test_admin_observability.py` | API tests for admin endpoints |

---

### Task 1: ContextVars for Request Tracing

**Files:**
- Modify: `backend/request_context.py`
- Modify: `backend/routers/chat.py:101-104`
- Create: `tests/unit/test_request_context.py`

- [ ] **Step 1: Write failing test for new ContextVars**

```python
# tests/unit/test_request_context.py
"""Tests for request-scoped context variables."""
import uuid

import pytest

from backend.request_context import current_query_id, current_session_id, current_user_id


class TestContextVars:
    """Tests for ContextVar defaults and set/get."""

    def test_current_user_id_default_is_none(self) -> None:
        """current_user_id should default to None."""
        assert current_user_id.get() is None

    def test_current_session_id_default_is_none(self) -> None:
        """current_session_id should default to None."""
        assert current_session_id.get() is None

    def test_current_query_id_default_is_none(self) -> None:
        """current_query_id should default to None."""
        assert current_query_id.get() is None

    def test_set_and_get_session_id(self) -> None:
        """Setting current_session_id should be retrievable."""
        sid = uuid.uuid4()
        token = current_session_id.set(sid)
        assert current_session_id.get() == sid
        current_session_id.reset(token)

    def test_set_and_get_query_id(self) -> None:
        """Setting current_query_id should be retrievable."""
        qid = uuid.uuid4()
        token = current_query_id.set(qid)
        assert current_query_id.get() == qid
        current_query_id.reset(token)
```

- [ ] **Step 2: Run test — expect ImportError (ContextVars don't exist yet)**

Run: `uv run pytest tests/unit/test_request_context.py -v`
Expected: FAIL — `ImportError: cannot import name 'current_session_id'`

- [ ] **Step 3: Add ContextVars to request_context.py**

```python
# backend/request_context.py — full replacement
"""Request-scoped context variables for tool execution and observability.

Tools called by LangGraph's ToolNode don't receive the FastAPI request
or user object. This module provides contextvars that the chat router
sets before streaming, and tools/providers read during execution.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

# Set by chat_stream before invoking the LangGraph graph.
# Read by tools that need user context (portfolio_exposure, etc.).
current_user_id: ContextVar[uuid.UUID | None] = ContextVar("current_user_id", default=None)

# Set by chat_stream for observability tracing.
# Read by ObservabilityCollector when writing LLMCallLog/ToolExecutionLog.
current_session_id: ContextVar[uuid.UUID | None] = ContextVar("current_session_id", default=None)
current_query_id: ContextVar[uuid.UUID | None] = ContextVar("current_query_id", default=None)
```

- [ ] **Step 4: Set ContextVars in chat.py**

In `backend/routers/chat.py`, after `_ctx_token = current_user_id.set(user.id)` (line 101), add:

```python
from backend.request_context import current_session_id, current_query_id

# ... inside chat_stream(), after current_user_id.set():
_session_token = current_session_id.set(chat_session.id)  # noqa: F841
_query_token = current_query_id.set(query_id)  # noqa: F841
```

Add imports at the top of the file alongside the existing `current_user_id` import:
```python
from backend.request_context import current_query_id, current_session_id, current_user_id
```

- [ ] **Step 5: Run tests — expect all pass**

Run: `uv run pytest tests/unit/test_request_context.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add backend/request_context.py backend/routers/chat.py tests/unit/test_request_context.py
git commit -m "feat(observability): add session_id + query_id ContextVars for request tracing"
```

---

### Task 2: ObservabilityCollector — In-Memory Metrics

**Files:**
- Create: `backend/agents/observability.py`
- Create: `tests/unit/agents/test_observability.py`

- [ ] **Step 1: Write failing tests for ObservabilityCollector**

```python
# tests/unit/agents/test_observability.py
"""Tests for ObservabilityCollector in-memory metrics."""

import pytest

from backend.agents.observability import ObservabilityCollector


class TestRecordRequest:
    """Tests for recording successful LLM requests."""

    @pytest.mark.asyncio
    async def test_record_increments_model_count(self) -> None:
        """Recording a request should increment the per-model count."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=150,
            prompt_tokens=100,
            completion_tokens=50,
        )
        stats = collector.get_stats()
        assert stats["requests_by_model"]["llama-3.3-70b"] == 1

    @pytest.mark.asyncio
    async def test_record_updates_rpm(self) -> None:
        """Recording a request should update RPM tracking."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=150,
            prompt_tokens=100,
            completion_tokens=50,
        )
        stats = collector.get_stats()
        assert stats["rpm_by_model"]["llama-3.3-70b"] == 1

    @pytest.mark.asyncio
    async def test_record_tracks_latency(self) -> None:
        """Recording a request should track latency."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b",
            provider="groq",
            tier="planner",
            latency_ms=200,
            prompt_tokens=100,
            completion_tokens=50,
        )
        health = collector.get_tier_health()
        model_entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert model_entry["latency"]["avg_ms"] == 200


class TestRecordCascade:
    """Tests for recording cascade events."""

    @pytest.mark.asyncio
    async def test_cascade_increments_count(self) -> None:
        """Recording a cascade should increment the cascade count."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-3.3-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        stats = collector.get_stats()
        assert stats["cascade_count"] == 1

    @pytest.mark.asyncio
    async def test_cascade_tracks_per_model(self) -> None:
        """Cascade events should be tracked per model."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-3.3-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        stats = collector.get_stats()
        assert stats["cascades_by_model"]["llama-3.3-70b"] == 1

    @pytest.mark.asyncio
    async def test_cascade_recorded_in_log(self) -> None:
        """Cascade events should appear in the cascade log."""
        collector = ObservabilityCollector()
        await collector.record_cascade(
            from_model="llama-3.3-70b",
            reason="rate_limit",
            provider="groq",
            tier="planner",
        )
        stats = collector.get_stats()
        assert len(stats["cascade_log"]) == 1
        assert stats["cascade_log"][0]["model"] == "llama-3.3-70b"
        assert stats["cascade_log"][0]["reason"] == "rate_limit"


class TestTierHealth:
    """Tests for tier health classification."""

    @pytest.mark.asyncio
    async def test_healthy_status_no_failures(self) -> None:
        """A model with no recent failures should be 'healthy'."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="llama-3.3-70b", provider="groq", tier="planner",
            latency_ms=100, prompt_tokens=50, completion_tokens=25,
        )
        health = collector.get_tier_health()
        model_entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert model_entry["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_degraded_status_few_failures(self) -> None:
        """A model with 1-3 recent failures should be 'degraded'."""
        collector = ObservabilityCollector()
        for _ in range(2):
            await collector.record_cascade(
                from_model="llama-3.3-70b", reason="rate_limit",
                provider="groq", tier="planner",
            )
        health = collector.get_tier_health()
        model_entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert model_entry["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_down_status_many_failures(self) -> None:
        """A model with 4+ recent failures should be 'down'."""
        collector = ObservabilityCollector()
        for _ in range(5):
            await collector.record_cascade(
                from_model="llama-3.3-70b", reason="rate_limit",
                provider="groq", tier="planner",
            )
        health = collector.get_tier_health()
        model_entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert model_entry["status"] == "down"

    @pytest.mark.asyncio
    async def test_disabled_status(self) -> None:
        """A manually disabled model should show 'disabled'."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-3.3-70b", enabled=False)
        health = collector.get_tier_health()
        model_entry = next(t for t in health["tiers"] if t["model"] == "llama-3.3-70b")
        assert model_entry["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_health_summary_counts(self) -> None:
        """Health summary should count models by status."""
        collector = ObservabilityCollector()
        await collector.record_request(
            model="model-a", provider="groq", tier="planner",
            latency_ms=100, prompt_tokens=50, completion_tokens=25,
        )
        collector.toggle_model("model-b", enabled=False)
        health = collector.get_tier_health()
        assert health["summary"]["total"] == 2
        assert health["summary"]["healthy"] == 1
        assert health["summary"]["disabled"] == 1


class TestToggleModel:
    """Tests for model enable/disable."""

    @pytest.mark.asyncio
    async def test_toggle_disable(self) -> None:
        """Disabling a model should add it to disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-3.3-70b", enabled=False)
        assert "llama-3.3-70b" in collector._disabled_models

    @pytest.mark.asyncio
    async def test_toggle_enable(self) -> None:
        """Re-enabling a model should remove it from disabled set."""
        collector = ObservabilityCollector()
        collector.toggle_model("llama-3.3-70b", enabled=False)
        collector.toggle_model("llama-3.3-70b", enabled=True)
        assert "llama-3.3-70b" not in collector._disabled_models
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/unit/agents/test_observability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.agents.observability'`

- [ ] **Step 3: Implement ObservabilityCollector**

```python
# backend/agents/observability.py
"""ObservabilityCollector — in-memory real-time metrics for agent pipeline.

Tracks LLM request counts, cascade events, per-model latency, and
health classification. Optionally writes events to LLMCallLog and
ToolExecutionLog tables asynchronously (fire-and-forget).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

# Sliding window durations
_RPM_WINDOW_S = 60
_HEALTH_WINDOW_S = 300  # 5 minutes
_LATENCY_MAXLEN = 100
_CASCADE_LOG_MAXLEN = 1000


class ObservabilityCollector:
    """Async-safe in-memory metrics collector for LLM and tool events."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

        # Cumulative counters
        self._requests_by_model: dict[str, int] = {}
        self._cascade_count: int = 0
        self._cascades_by_model: dict[str, int] = {}

        # Sliding windows (deques of timestamps)
        self._rpm_windows: dict[str, deque[float]] = {}
        self._failures_windows: dict[str, deque[float]] = {}
        self._successes_windows: dict[str, deque[float]] = {}

        # Latency tracking (recent values for percentile calc)
        self._latency_by_model: dict[str, deque[int]] = {}

        # Cascade event log
        self._cascade_log: deque[dict[str, Any]] = deque(maxlen=_CASCADE_LOG_MAXLEN)

        # Admin-disabled models
        self._disabled_models: set[str] = set()

        # DB write function (injected at startup, None = no DB writes)
        self._db_writer: Any = None

    def set_db_writer(self, writer: Any) -> None:
        """Inject the async DB write function (set during app lifespan)."""
        self._db_writer = writer

    async def record_request(
        self,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record a successful LLM request."""
        now = time.monotonic()
        async with self._lock:
            self._requests_by_model[model] = self._requests_by_model.get(model, 0) + 1

            if model not in self._rpm_windows:
                self._rpm_windows[model] = deque()
            self._rpm_windows[model].append(now)

            if model not in self._successes_windows:
                self._successes_windows[model] = deque()
            self._successes_windows[model].append(now)

            if model not in self._latency_by_model:
                self._latency_by_model[model] = deque(maxlen=_LATENCY_MAXLEN)
            self._latency_by_model[model].append(latency_ms)

        # Fire-and-forget DB write
        if self._db_writer:
            asyncio.create_task(
                self._safe_db_write("llm_call", {
                    "provider": provider,
                    "model": model,
                    "tier": tier,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "error": None,
                })
            )

    async def record_cascade(
        self,
        from_model: str,
        reason: str,
        provider: str,
        tier: str,
    ) -> None:
        """Record a cascade event (model skipped)."""
        now = time.monotonic()
        async with self._lock:
            self._cascade_count += 1
            self._cascades_by_model[from_model] = self._cascades_by_model.get(from_model, 0) + 1

            if from_model not in self._failures_windows:
                self._failures_windows[from_model] = deque()
            self._failures_windows[from_model].append(now)

            self._cascade_log.append({
                "model": from_model,
                "reason": reason,
                "provider": provider,
                "tier": tier,
                "timestamp": now,
            })

        # Fire-and-forget DB write
        if self._db_writer:
            asyncio.create_task(
                self._safe_db_write("llm_call", {
                    "provider": provider,
                    "model": from_model,
                    "tier": tier,
                    "latency_ms": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "error": reason,
                })
            )

    async def record_tool_execution(
        self,
        tool_name: str,
        latency_ms: int,
        status: str,
        result_size_bytes: int | None = None,
        params: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Record a tool execution event (fire-and-forget DB write only)."""
        if self._db_writer:
            asyncio.create_task(
                self._safe_db_write("tool_execution", {
                    "tool_name": tool_name,
                    "latency_ms": latency_ms,
                    "status": status,
                    "result_size_bytes": result_size_bytes,
                    "params": params,
                    "error": error,
                })
            )

    def toggle_model(self, model: str, *, enabled: bool) -> None:
        """Enable or disable a model at runtime (admin action)."""
        if enabled:
            self._disabled_models.discard(model)
        else:
            self._disabled_models.add(model)

    def get_stats(self) -> dict[str, Any]:
        """Return current in-memory metrics snapshot."""
        now = time.monotonic()
        rpm: dict[str, int] = {}
        for model, window in self._rpm_windows.items():
            self._prune_window(window, now, _RPM_WINDOW_S)
            rpm[model] = len(window)

        return {
            "requests_by_model": dict(self._requests_by_model),
            "cascade_count": self._cascade_count,
            "cascades_by_model": dict(self._cascades_by_model),
            "rpm_by_model": rpm,
            "cascade_log": list(self._cascade_log)[-50:],
        }

    def get_tier_health(self) -> dict[str, Any]:
        """Return per-model health classification with latency stats."""
        now = time.monotonic()
        tiers: list[dict[str, Any]] = []

        all_models = set(self._requests_by_model.keys()) | set(self._cascades_by_model.keys()) | self._disabled_models

        for model in sorted(all_models):
            # Prune windows
            failures = self._failures_windows.get(model, deque())
            self._prune_window(failures, now, _HEALTH_WINDOW_S)
            successes = self._successes_windows.get(model, deque())
            self._prune_window(successes, now, _HEALTH_WINDOW_S)

            # Classify health
            if model in self._disabled_models:
                status = "disabled"
            elif len(failures) >= 4:
                status = "down"
            elif len(failures) >= 1:
                status = "degraded"
            else:
                status = "healthy"

            # Latency stats
            latencies = list(self._latency_by_model.get(model, []))
            if latencies:
                avg_ms = sum(latencies) // len(latencies)
                sorted_lat = sorted(latencies)
                p95_idx = int(len(sorted_lat) * 0.95)
                p95_ms = sorted_lat[min(p95_idx, len(sorted_lat) - 1)]
            else:
                avg_ms = 0
                p95_ms = 0

            tiers.append({
                "model": model,
                "status": status,
                "failures_5m": len(failures),
                "successes_5m": len(successes),
                "cascade_count": self._cascades_by_model.get(model, 0),
                "latency": {"avg_ms": avg_ms, "p95_ms": p95_ms},
            })

        summary = {
            "total": len(tiers),
            "healthy": sum(1 for t in tiers if t["status"] == "healthy"),
            "degraded": sum(1 for t in tiers if t["status"] == "degraded"),
            "down": sum(1 for t in tiers if t["status"] == "down"),
            "disabled": sum(1 for t in tiers if t["status"] == "disabled"),
        }

        return {"tiers": tiers, "summary": summary}

    async def _safe_db_write(self, event_type: str, data: dict) -> None:
        """Write to DB, swallowing all errors (never block the user)."""
        try:
            await self._db_writer(event_type, data)
        except Exception:
            logger.warning("Failed to write %s event to DB", event_type, exc_info=True)

    @staticmethod
    def _prune_window(window: deque, now: float, max_age_s: float) -> None:
        """Remove entries older than max_age_s from a timestamp deque."""
        cutoff = now - max_age_s
        while window and window[0] < cutoff:
            window.popleft()
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `uv run pytest tests/unit/agents/test_observability.py -v`
Expected: 14 passed

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/agents/observability.py tests/unit/agents/test_observability.py
uv run ruff format backend/agents/observability.py tests/unit/agents/test_observability.py
git add backend/agents/observability.py tests/unit/agents/test_observability.py
git commit -m "feat(observability): ObservabilityCollector — in-memory metrics + health classification"
```

---

### Task 3: DB Write Layer

**Files:**
- Create: `backend/agents/observability_writer.py`
- Create: `tests/unit/agents/test_observability_writer.py`

- [ ] **Step 1: Write failing tests for the DB writer**

```python
# tests/unit/agents/test_observability_writer.py
"""Tests for observability DB write functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWriteLLMCall:
    """Tests for write_llm_call."""

    @pytest.mark.asyncio
    async def test_writes_llm_call_log(self) -> None:
        """Should insert an LLMCallLog row."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.agents.observability_writer.async_session_factory", return_value=mock_cm):
            with patch("backend.agents.observability_writer.current_session_id") as mock_sid:
                with patch("backend.agents.observability_writer.current_query_id") as mock_qid:
                    mock_sid.get.return_value = uuid.uuid4()
                    mock_qid.get.return_value = uuid.uuid4()

                    await write_event("llm_call", {
                        "provider": "groq",
                        "model": "llama-3.3-70b",
                        "tier": "planner",
                        "latency_ms": 150,
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "error": None,
                    })

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_writes_tool_execution_log(self) -> None:
        """Should insert a ToolExecutionLog row."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.agents.observability_writer.async_session_factory", return_value=mock_cm):
            with patch("backend.agents.observability_writer.current_session_id") as mock_sid:
                with patch("backend.agents.observability_writer.current_query_id") as mock_qid:
                    mock_sid.get.return_value = uuid.uuid4()
                    mock_qid.get.return_value = uuid.uuid4()

                    await write_event("tool_execution", {
                        "tool_name": "analyze_stock",
                        "latency_ms": 300,
                        "status": "ok",
                        "result_size_bytes": 1024,
                        "params": {"ticker": "AAPL"},
                        "error": None,
                    })

        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_error_does_not_raise(self) -> None:
        """DB write failures should be swallowed (logged, not raised)."""
        from backend.agents.observability_writer import write_event

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.agents.observability_writer.async_session_factory", return_value=mock_cm):
            # Should not raise
            await write_event("llm_call", {
                "provider": "groq",
                "model": "llama-3.3-70b",
                "tier": "planner",
                "latency_ms": 150,
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "error": None,
            })
```

- [ ] **Step 2: Run tests — expect ImportError**

Run: `uv run pytest tests/unit/agents/test_observability_writer.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement write_event**

```python
# backend/agents/observability_writer.py
"""Async fire-and-forget DB writer for observability events.

Writes LLMCallLog and ToolExecutionLog rows. Reads session_id and
query_id from ContextVars. Never raises — all errors are logged and
swallowed to avoid blocking user requests.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.request_context import current_query_id, current_session_id

logger = logging.getLogger(__name__)


async def write_event(event_type: str, data: dict) -> None:
    """Write an observability event to the database.

    Args:
        event_type: "llm_call" or "tool_execution"
        data: Event data dict (keys match model columns).
    """
    try:
        session_id = current_session_id.get()
        query_id = current_query_id.get()

        async with async_session_factory() as db:
            if event_type == "llm_call":
                row = LLMCallLog(
                    session_id=session_id,
                    query_id=query_id,
                    provider=data["provider"],
                    model=data["model"],
                    tier=data.get("tier"),
                    latency_ms=data.get("latency_ms"),
                    prompt_tokens=data.get("prompt_tokens"),
                    completion_tokens=data.get("completion_tokens"),
                    error=data.get("error"),
                )
            elif event_type == "tool_execution":
                row = ToolExecutionLog(
                    session_id=session_id,
                    query_id=query_id,
                    tool_name=data["tool_name"],
                    latency_ms=data.get("latency_ms"),
                    status=data["status"],
                    result_size_bytes=data.get("result_size_bytes"),
                    params=data.get("params"),
                    error=data.get("error"),
                )
            else:
                logger.warning("Unknown event type: %s", event_type)
                return

            db.add(row)
            await db.commit()
    except Exception:
        logger.warning("Failed to write %s event to DB", event_type, exc_info=True)
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `uv run pytest tests/unit/agents/test_observability_writer.py -v`
Expected: 3 passed

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/agents/observability_writer.py tests/unit/agents/test_observability_writer.py
uv run ruff format backend/agents/observability_writer.py tests/unit/agents/test_observability_writer.py
git add backend/agents/observability_writer.py tests/unit/agents/test_observability_writer.py
git commit -m "feat(observability): fire-and-forget DB writer for LLMCallLog + ToolExecutionLog"
```

---

### Task 4: Instrument GroqProvider + LLMClient

**Files:**
- Modify: `backend/agents/providers/groq.py`
- Modify: `backend/agents/llm_client.py`
- Create: `tests/unit/agents/test_groq_observability.py`

- [ ] **Step 1: Write failing tests for instrumented GroqProvider**

```python
# tests/unit/agents/test_groq_observability.py
"""Tests for observability instrumentation in GroqProvider and LLMClient."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.llm_client import LLMResponse
from backend.agents.observability import ObservabilityCollector


class TestGroqProviderObservability:
    """Tests for GroqProvider recording to ObservabilityCollector."""

    @pytest.mark.asyncio
    async def test_successful_call_records_request(self) -> None:
        """A successful Groq call should record a request event."""
        collector = ObservabilityCollector()
        from backend.agents.providers.groq import GroqProvider

        provider = GroqProvider(
            api_key="test-key",
            models=["model-a"],
            collector=collector,
        )

        mock_response = LLMResponse(
            content="hello", tool_calls=[], model="model-a",
            prompt_tokens=10, completion_tokens=5,
        )
        with patch.object(provider, "_call_model", new_callable=AsyncMock, return_value=mock_response):
            await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

        stats = collector.get_stats()
        assert stats["requests_by_model"]["model-a"] == 1

    @pytest.mark.asyncio
    async def test_cascade_records_event(self) -> None:
        """When a model fails and cascades, a cascade event should be recorded."""
        collector = ObservabilityCollector()
        from backend.agents.providers.groq import GroqProvider

        provider = GroqProvider(
            api_key="test-key",
            models=["model-a", "model-b"],
            collector=collector,
        )

        mock_response = LLMResponse(
            content="hello", tool_calls=[], model="model-b",
            prompt_tokens=10, completion_tokens=5,
        )

        call_count = 0
        async def _side_effect(model_name, messages, tools, stream):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("rate limit exceeded")
            return mock_response

        with patch.object(provider, "_call_model", side_effect=_side_effect):
            await provider.chat(messages=[{"role": "user", "content": "hi"}], tools=[])

        stats = collector.get_stats()
        assert stats["cascade_count"] == 1
        assert stats["cascades_by_model"]["model-a"] == 1
        assert stats["requests_by_model"]["model-b"] == 1
```

- [ ] **Step 2: Run tests — expect TypeError (collector param doesn't exist yet)**

Run: `uv run pytest tests/unit/agents/test_groq_observability.py -v`
Expected: FAIL — `TypeError: GroqProvider.__init__() got an unexpected keyword argument 'collector'`

- [ ] **Step 3: Add collector param to GroqProvider**

In `backend/agents/providers/groq.py`, modify `__init__` to accept an optional `collector` parameter:

```python
import time  # add to imports

from backend.agents.observability import ObservabilityCollector  # add import


class GroqProvider(LLMProvider):
    """Groq provider with internal multi-model cascade."""

    def __init__(
        self,
        api_key: str,
        models: list[str] | None = None,
        token_budget: TokenBudget | None = None,
        collector: ObservabilityCollector | None = None,
    ) -> None:
        self._api_key = api_key
        self._models = models or ["llama-3.3-70b-versatile"]
        self._token_budget = token_budget
        self._collector = collector
        self.health = ProviderHealth(provider="groq")
        self._chat_models: dict[str, Any] = {}
```

In the `chat()` method, add timing + collector calls:

```python
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool = False,
    ) -> LLMResponse:
        estimated_tokens = TokenBudget.estimate_tokens(messages)
        errors: list[tuple[str, str]] = []

        for model_name in self._models:
            # Budget check
            if self._token_budget:
                if not await self._token_budget.can_afford(model_name, estimated_tokens):
                    logger.info("Skipping %s — over budget", model_name)
                    errors.append((model_name, "over_budget"))
                    if self._collector:
                        await self._collector.record_cascade(
                            from_model=model_name, reason="over_budget",
                            provider="groq", tier="",
                        )
                    continue

            try:
                start = time.monotonic()
                result = await self._call_model(model_name, messages, tools, stream)
                elapsed_ms = int((time.monotonic() - start) * 1000)

                # Record usage on success
                if self._token_budget:
                    actual = result.prompt_tokens + result.completion_tokens
                    await self._token_budget.record(model_name, actual)

                # Record to collector
                if self._collector:
                    await self._collector.record_request(
                        model=model_name, provider="groq", tier="",
                        latency_ms=elapsed_ms,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                    )
                return result
            except Exception as exc:
                error_type = _classify_error(exc)
                logger.warning(
                    "Groq model %s failed (%s): %s — cascading",
                    model_name, error_type, str(exc)[:200],
                )
                errors.append((model_name, error_type))

                # Record cascade event
                if self._collector:
                    await self._collector.record_cascade(
                        from_model=model_name, reason=error_type,
                        provider="groq", tier="",
                    )

                # Auth errors affect all models — don't cascade
                if error_type == "auth":
                    break

        raise AllModelsExhaustedError(
            f"All {len(self._models)} Groq models exhausted: "
            + ", ".join(f"{m}({e})" for m, e in errors)
        )
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `uv run pytest tests/unit/agents/test_groq_observability.py -v`
Expected: 2 passed

- [ ] **Step 5: Run existing Groq tests to verify no regression**

Run: `uv run pytest tests/unit/providers/test_groq_cascade.py -v`
Expected: 14 passed (existing tests pass without collector — it's optional)

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix backend/agents/providers/groq.py tests/unit/agents/test_groq_observability.py
uv run ruff format backend/agents/providers/groq.py tests/unit/agents/test_groq_observability.py
git add backend/agents/providers/groq.py backend/agents/llm_client.py tests/unit/agents/test_groq_observability.py
git commit -m "feat(observability): instrument GroqProvider with collector recording"
```

---

### Task 5: Instrument Executor for Tool Logging

**Files:**
- Modify: `backend/agents/executor.py`
- Create: `tests/unit/agents/test_executor_observability.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/agents/test_executor_observability.py
"""Tests for tool execution observability in executor."""

from unittest.mock import AsyncMock

import pytest

from backend.agents.observability import ObservabilityCollector
from backend.tools.base import ToolResult


class TestExecutorObservability:
    """Tests for executor recording tool execution events."""

    @pytest.mark.asyncio
    async def test_successful_tool_records_event(self) -> None:
        """A successful tool execution should record to collector."""
        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(return_value=ToolResult(
            status="ok", data={"ticker": "AAPL", "price": 150.0}
        ))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["tool_name"] == "analyze_stock"
        assert call_kwargs["status"] == "ok"
        assert call_kwargs["latency_ms"] >= 0

    @pytest.mark.asyncio
    async def test_failed_tool_records_error(self) -> None:
        """A failed tool execution should record error to collector."""
        from backend.agents.executor import execute_plan

        collector = ObservabilityCollector()
        collector.record_tool_execution = AsyncMock()

        tool_executor = AsyncMock(side_effect=Exception("tool crashed"))

        steps = [{"tool": "analyze_stock", "params": {"ticker": "AAPL"}}]
        await execute_plan(steps, tool_executor, collector=collector)

        collector.record_tool_execution.assert_called_once()
        call_kwargs = collector.record_tool_execution.call_args[1]
        assert call_kwargs["tool_name"] == "analyze_stock"
        assert call_kwargs["status"] == "error"
        assert "tool crashed" in call_kwargs["error"]
```

- [ ] **Step 2: Run tests — expect TypeError (collector param doesn't exist)**

Run: `uv run pytest tests/unit/agents/test_executor_observability.py -v`
Expected: FAIL — `TypeError: execute_plan() got an unexpected keyword argument 'collector'`

- [ ] **Step 3: Add collector param to execute_plan**

In `backend/agents/executor.py`, modify the `execute_plan` signature to accept an optional `collector`:

```python
from backend.agents.observability import ObservabilityCollector  # add import
import json  # add for result_size_bytes


async def execute_plan(
    steps: list[dict[str, Any]],
    tool_executor: Any,
    on_step: Any | None = None,
    collector: ObservabilityCollector | None = None,
) -> dict[str, Any]:
```

Inside the step loop, wrap the tool execution with timing and collector recording. After the retry loop (after `tool_calls += 1` at line 164), add:

```python
        tool_calls += 1

        # Record to observability collector
        if collector:
            tool_elapsed_ms = int((time.monotonic() - tool_start) * 1000)
            result_data = result.data if result else None
            try:
                result_bytes = len(json.dumps(result_data, default=str)) if result_data else 0
            except (TypeError, ValueError):
                result_bytes = 0
            await collector.record_tool_execution(
                tool_name=tool_name,
                latency_ms=tool_elapsed_ms,
                status=result.status if result else "error",
                result_size_bytes=result_bytes,
                params=params,
                error=result.error if result and result.status == "error" else None,
            )
```

And add `tool_start = time.monotonic()` before the retry loop:

```python
        # Execute with retry
        tool_start = time.monotonic()
        result: ToolResult | None = None
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `uv run pytest tests/unit/agents/test_executor_observability.py -v`
Expected: 2 passed

- [ ] **Step 5: Run existing executor tests to verify no regression**

Run: `uv run pytest tests/unit/agents/ -v --tb=short`
Expected: All existing tests pass (collector is optional, defaults to None)

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix backend/agents/executor.py tests/unit/agents/test_executor_observability.py
uv run ruff format backend/agents/executor.py tests/unit/agents/test_executor_observability.py
git add backend/agents/executor.py tests/unit/agents/test_executor_observability.py
git commit -m "feat(observability): instrument executor with tool execution logging"
```

---

### Task 6: Admin Observability Endpoints

**Files:**
- Modify: `backend/routers/admin.py`
- Create: `tests/api/test_admin_observability.py`

- [ ] **Step 1: Write failing API tests**

```python
# tests/api/test_admin_observability.py
"""API tests for admin observability endpoints."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.dependencies import create_access_token, hash_password
from backend.models.user import User, UserRole


async def _create_user(db_url: str, *, role: UserRole = UserRole.USER) -> User:
    """Create a user in the test database and return it."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    user = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("TestPass1"),
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    async with factory() as session:
        session.add(user)
        await session.commit()
    await engine.dispose()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


class TestLLMMetrics:
    """Tests for GET /api/v1/admin/llm-metrics."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/llm-metrics")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Regular user should get 403."""
        user = await _create_user(db_url, role=UserRole.USER)
        response = await client.get("/api/v1/admin/llm-metrics", headers=_auth_headers(user))
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gets_metrics(self, client: AsyncClient, db_url: str) -> None:
        """Admin should get metrics dict."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get("/api/v1/admin/llm-metrics", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert "requests_by_model" in data
        assert "cascade_count" in data
        assert "rpm_by_model" in data


class TestTierHealth:
    """Tests for GET /api/v1/admin/tier-health."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/tier-health")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_gets_health(self, client: AsyncClient, db_url: str) -> None:
        """Admin should get tier health dict."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get("/api/v1/admin/tier-health", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert "tiers" in data
        assert "summary" in data


class TestTierToggle:
    """Tests for POST /api/v1/admin/tier-toggle."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.post("/api/v1/admin/tier-toggle", json={"model": "x", "enabled": False})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_toggles_model(self, client: AsyncClient, db_url: str) -> None:
        """Admin should be able to toggle a model."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.post(
            "/api/v1/admin/tier-toggle",
            json={"model": "llama-3.3-70b", "enabled": False},
            headers=_auth_headers(admin),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestLLMUsage:
    """Tests for GET /api/v1/admin/llm-usage."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/llm-usage")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_gets_usage(self, client: AsyncClient, db_url: str) -> None:
        """Admin should get usage data."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get("/api/v1/admin/llm-usage", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "total_cost_usd" in data
        assert "escalation_rate" in data
```

- [ ] **Step 2: Run tests — expect 404s (endpoints don't exist)**

Run: `uv run pytest tests/api/test_admin_observability.py -v`
Expected: FAIL — multiple 404/405 errors

- [ ] **Step 3: Add admin observability endpoints**

Add to `backend/routers/admin.py`:

```python
from backend.schemas.llm_config import TierToggleRequest  # add import


@router.get(
    "/llm-metrics",
    summary="Get LLM cascade metrics",
    description="Returns real-time in-memory LLM request and cascade statistics.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_llm_metrics(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Get real-time LLM metrics from the ObservabilityCollector."""
    _require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        return {"requests_by_model": {}, "cascade_count": 0, "cascades_by_model": {}, "rpm_by_model": {}, "cascade_log": []}
    return collector.get_stats()


@router.get(
    "/tier-health",
    summary="Get tier health status",
    description="Returns per-model health classification with latency stats.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_tier_health(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Get per-model health classification."""
    _require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        return {"tiers": [], "summary": {"total": 0, "healthy": 0, "degraded": 0, "down": 0, "disabled": 0}}
    return collector.get_tier_health()


@router.post(
    "/tier-toggle",
    summary="Enable/disable a model",
    description="Toggle a model on or off at runtime without a redeploy.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def tier_toggle(
    body: TierToggleRequest,
    request: Request,
    user: User = Depends(get_current_user),
) -> dict:
    """Toggle a model on/off at runtime."""
    _require_admin(user)
    collector = getattr(request.app.state, "collector", None)
    if collector is None:
        raise HTTPException(status_code=503, detail="Observability not initialized")
    collector.toggle_model(body.model, enabled=body.enabled)
    logger.info("Toggled model %s → enabled=%s", body.model, body.enabled)
    return {"status": "ok", "model": body.model, "enabled": body.enabled}


@router.get(
    "/llm-usage",
    summary="Get LLM usage stats (30-day)",
    description="Aggregated LLM usage from the database: cost, latency, escalation rate.",
    responses={401: {"description": "Not authenticated"}, 403: {"description": "Not admin"}},
)
async def get_llm_usage(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Get 30-day LLM usage from llm_call_log table."""
    _require_admin(user)
    from sqlalchemy import func, text

    from backend.models.logs import LLMCallLog

    # 30-day window
    cutoff = text("now() - interval '30 days'")

    # Total requests + cost + avg latency
    stmt = select(
        func.count().label("total_requests"),
        func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("total_cost_usd"),
        func.coalesce(func.avg(LLMCallLog.latency_ms), 0).label("avg_latency_ms"),
    ).where(
        LLMCallLog.created_at >= cutoff,
        LLMCallLog.error.is_(None),
    )
    result = await db.execute(stmt)
    row = result.one()

    # Per-model breakdown
    model_stmt = select(
        LLMCallLog.model,
        LLMCallLog.provider,
        func.count().label("request_count"),
        func.coalesce(func.sum(LLMCallLog.cost_usd), 0).label("cost_usd"),
    ).where(
        LLMCallLog.created_at >= cutoff,
        LLMCallLog.error.is_(None),
    ).group_by(LLMCallLog.model, LLMCallLog.provider)
    model_result = await db.execute(model_stmt)
    models = [
        {"model": r.model, "provider": r.provider, "request_count": r.request_count, "cost_usd": float(r.cost_usd)}
        for r in model_result.all()
    ]

    # Escalation rate (Anthropic calls / total calls)
    total = row.total_requests or 0
    if total > 0:
        anthropic_stmt = select(func.count()).where(
            LLMCallLog.created_at >= cutoff,
            LLMCallLog.error.is_(None),
            LLMCallLog.provider == "anthropic",
        )
        anthropic_result = await db.execute(anthropic_stmt)
        anthropic_count = anthropic_result.scalar() or 0
        escalation_rate = round(anthropic_count / total, 4)
    else:
        escalation_rate = 0.0

    return {
        "total_requests": total,
        "total_cost_usd": float(row.total_cost_usd),
        "avg_latency_ms": round(float(row.avg_latency_ms)),
        "models": models,
        "escalation_rate": escalation_rate,
    }
```

Also add `Request` import and `TierToggleRequest` schema. In `backend/schemas/llm_config.py`, add:

```python
class TierToggleRequest(BaseModel):
    """Request body for POST /admin/tier-toggle."""
    model: str
    enabled: bool
```

In `admin.py` imports, add:

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from backend.schemas.llm_config import LLMModelConfigResponse, LLMModelConfigUpdate, TierToggleRequest
```

- [ ] **Step 4: Run tests — expect all pass**

Run: `uv run pytest tests/api/test_admin_observability.py -v`
Expected: 10 passed

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/routers/admin.py backend/schemas/llm_config.py tests/api/test_admin_observability.py
uv run ruff format backend/routers/admin.py backend/schemas/llm_config.py tests/api/test_admin_observability.py
git add backend/routers/admin.py backend/schemas/llm_config.py tests/api/test_admin_observability.py
git commit -m "feat(observability): 4 admin endpoints — llm-metrics, tier-health, tier-toggle, llm-usage"
```

---

### Task 7: Wire Everything in main.py

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Instantiate collector and wire into providers/executor**

In `backend/main.py` lifespan, after `token_budget = TokenBudget()` (line 87), add:

```python
    from backend.agents.observability import ObservabilityCollector
    from backend.agents.observability_writer import write_event

    collector = ObservabilityCollector()
    collector.set_db_writer(write_event)
    app.state.collector = collector
```

When creating the GroqProvider (line 101-106), pass the collector:

```python
        providers.append(
            GroqProvider(
                api_key=settings.GROQ_API_KEY,
                models=groq_models or None,
                token_budget=token_budget,
                collector=collector,
            )
        )
```

When building `_tool_executor` and `execute_plan` binding (line 141-147, 165-172), pass collector to execute_plan:

```python
        app.state.agent_graph = build_agent_graph(
            plan_fn=_plan_fn,
            execute_fn=lambda steps, tool_executor, on_step=None: execute_plan(
                steps, tool_executor, on_step=on_step, collector=collector
            ),
            synthesize_fn=_synthesize_fn,
            format_simple_fn=format_simple_result,
            tool_executor=_tool_executor,
            tools_description=tools_desc,
        )
```

- [ ] **Step 2: Run full unit test suite**

Run: `uv run pytest tests/unit/ -q --tb=short`
Expected: All pass (766+new tests)

- [ ] **Step 3: Run full API test suite**

Run: `uv run pytest tests/api/ -q --tb=short`
Expected: All pass

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/main.py
uv run ruff format backend/main.py
git add backend/main.py
git commit -m "feat(observability): wire collector into app lifespan, providers, executor"
```

---

### Task 8: Documentation + Final Verification

**Files:**
- Modify: `docs/TDD.md`
- Modify: `docs/FSD.md`
- Modify: `project-plan.md`

- [ ] **Step 1: Update TDD.md**

Add section 3.14 for the 4 new admin observability endpoints (llm-metrics, tier-health, tier-toggle, llm-usage). Update §10.3 Monitoring & Observability to reference ObservabilityCollector.

- [ ] **Step 2: Update FSD.md**

Update NFR-6: Observability to reflect the new capabilities (in-memory metrics, DB logging, admin endpoints, escalation rate tracking).

- [ ] **Step 3: Update project-plan.md**

Mark Phase 6B tasks as complete with checkmarks.

- [ ] **Step 4: Run full test suite one final time**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
```
Expected: All pass

- [ ] **Step 5: Lint everything**

```bash
uv run ruff check backend/ tests/
uv run ruff format backend/ tests/
```

- [ ] **Step 6: Commit**

```bash
git add docs/TDD.md docs/FSD.md project-plan.md
git commit -m "docs: update TDD, FSD, project-plan for Phase 6B observability"
```

---

## Execution Summary

| Task | Description | New Tests | Files |
|------|-------------|-----------|-------|
| 1 | ContextVars for tracing | 5 | 3 |
| 2 | ObservabilityCollector | 14 | 2 |
| 3 | DB write layer | 3 | 2 |
| 4 | Instrument GroqProvider | 2 | 3 |
| 5 | Instrument executor | 2 | 2 |
| 6 | Admin endpoints | 10 | 3 |
| 7 | Wire in main.py | 0 | 1 |
| 8 | Documentation | 0 | 3 |
| **Total** | | **~36** | **19** |
