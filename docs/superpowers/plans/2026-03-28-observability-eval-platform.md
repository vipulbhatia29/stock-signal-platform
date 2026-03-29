# Observability + Evaluation Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Langfuse integration, user-facing observability page, and periodic agent quality assessment framework with 14 golden queries.

**Architecture:** Langfuse runs as a parallel trace system alongside existing ObservabilityCollector. All SDK calls are fire-and-forget behind a feature flag. Frontend adds a new `/observability` route with KPI ticker + expandable query table. Quality assessment is batch-only (weekly CI + on-demand).

**Tech Stack:** Langfuse v3 (self-hosted Docker), langfuse Python SDK, FastAPI, SQLAlchemy, Alembic, Next.js, TanStack Query, Tailwind.

**Spec:** `docs/superpowers/specs/2026-03-28-observability-eval-platform-design.md`

---

## Implement-Local Scoring Guide

Each task scored: `context_span + convention_density + ambiguity` (each 1-5).
- **≤8:** Delegate to `/implement-local` (DeepSeek via LM Studio), Opus reviews.
- **>8:** Opus implements directly.

---

## Task Overview

| # | Task | Score | Executor | Effort |
|---|------|-------|----------|--------|
| 1 | Docker Compose: Langfuse services | 4 | Local | ~1h |
| 2 | Config: Langfuse settings | 3 | Local | ~30m |
| 3 | Langfuse SDK wrapper service | 6 | Local | ~1.5h |
| 4 | Lifespan: Langfuse init + shutdown | 7 | Local | ~1h |
| 5 | Chat router + ReAct loop: trace + spans (merged 5+6) | 10 | Opus | ~3h |
| 6 | (merged into Task 5) | — | — | — |
| 7 | LLMClient: generation recording | 9 | Opus | ~1.5h |
| 8 | Assessment models + migration | 6 | Local | ~1.5h |
| 9 | Observability query service | 9 | Opus | ~2h |
| 10 | Observability API router | 8 | Local | ~2h |
| 11 | Observability Pydantic schemas | 5 | Local | ~1h |
| 12 | OIDC SSO endpoints | 10 | Opus | ~2h |
| 13 | Golden dataset definition | 7 | Local | ~1.5h |
| 14 | Scoring engine (5 dimensions) | 9 | Opus | ~2h |
| 15 | Assessment runner + CLI entry point | 8 | Local | ~1.5h |
| 16 | CI assessment workflow | 5 | Local | ~1h |
| 17 | Frontend: observability page + KPI | 8 | Local | ~2h |
| 18 | Frontend: QueryTable + expansion | 10 | Opus | ~3h |
| 19 | Unit tests: Langfuse wrapper + spans | 7 | Local | ~1.5h |
| 20 | API tests: observability endpoints | 7 | Local | ~1.5h |
| 21 | Integration tests: assessment runner | 9 | Opus | ~1.5h |
| 22 | Doc updates: TDD, FSD, ADR, memories | 6 | Local | ~1.5h |

---

## Task 1: Docker Compose — Langfuse Services

**Score:** 4 (context_span=1, convention_density=2, ambiguity=1) → **Local**

**Files:**
- Modify: `docker-compose.yml`
- Modify: `backend/.env.example`

- [ ] **Step 1: Add Langfuse services to docker-compose.yml**

After the `redis` service block, before `volumes:`, add:

```yaml
  langfuse-db:
    image: postgres:16-alpine
    container_name: ssp-langfuse-db
    environment:
      POSTGRES_USER: langfuse
      POSTGRES_PASSWORD: langfuse
      POSTGRES_DB: langfuse
    ports:
      - "5434:5432"
    volumes:
      - langfuse_db_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U langfuse"]
      interval: 5s
      timeout: 5s
      retries: 5

  langfuse-server:
    image: langfuse/langfuse:2
    container_name: ssp-langfuse
    depends_on:
      langfuse-db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://langfuse:langfuse@langfuse-db:5432/langfuse
      NEXTAUTH_SECRET: ${LANGFUSE_NEXTAUTH_SECRET:-changeme-langfuse-secret}
      NEXTAUTH_URL: http://localhost:3001
      SALT: ${LANGFUSE_SALT:-changeme-langfuse-salt}
      TELEMETRY_ENABLED: "false"
    ports:
      - "3001:3000"
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:3000/api/public/health"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 2: Add Langfuse volume**

In `volumes:`, add:
```yaml
  langfuse_db_data:
```

- [ ] **Step 3: Add Langfuse env vars to .env.example**

```bash
# --- Langfuse (optional — observability tracing) ---
LANGFUSE_SECRET_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_BASEURL=http://localhost:3001
LANGFUSE_NEXTAUTH_SECRET=changeme-langfuse-secret
LANGFUSE_SALT=changeme-langfuse-salt
```

- [ ] **Step 4: Verify Langfuse starts**

Run: `docker compose up -d langfuse-db langfuse-server`
Run: `docker compose logs langfuse-server --tail 20`
Expected: "Ready on http://localhost:3000"

- [ ] **Step 5: Access Langfuse UI and create API keys**

Open `http://localhost:3001`, create account, create project, copy secret + public keys to `backend/.env`.

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml backend/.env.example
git commit -m "feat(infra): add Langfuse self-hosted services to docker-compose"
```

---

## Task 2: Config — Langfuse Settings

**Score:** 3 (context_span=1, convention_density=1, ambiguity=1) → **Local**

**Files:**
- Modify: `backend/config.py` (Settings class, lines 11-89)

- [ ] **Step 1: Add Langfuse settings to Settings class**

After `LOG_LEVEL` field (line ~72), add:

```python
    # --- Langfuse (optional — tracing + assessment) ---
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_BASEURL: str = "http://localhost:3001"
```

- [ ] **Step 2: Verify settings load**

Run: `uv run python -c "from backend.config import settings; print(settings.LANGFUSE_SECRET_KEY)"`
Expected: `""` (empty, feature disabled)

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(config): add Langfuse settings (feature-flagged on secret key)"
```

---

## Task 3: Langfuse SDK Wrapper Service

**Score:** 6 (context_span=2, convention_density=2, ambiguity=2) → **Local**

**Files:**
- Create: `backend/services/langfuse_service.py`
- Modify: `pyproject.toml` (add langfuse dep)
- Test: `tests/unit/services/test_langfuse_service.py`

- [ ] **Step 1: Add langfuse dependency**

Run: `uv add langfuse`

- [ ] **Step 2: Write failing test**

Create `tests/unit/services/test_langfuse_service.py`:

```python
"""Tests for Langfuse service wrapper."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from backend.services.langfuse_service import LangfuseService


class TestLangfuseService:
    def test_disabled_when_no_secret(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        assert svc.enabled is False

    def test_enabled_when_secret_set(self):
        with patch("backend.services.langfuse_service.Langfuse") as mock_cls:
            mock_cls.return_value = MagicMock()
            svc = LangfuseService(
                secret_key="sk-test", public_key="pk-test", base_url="http://localhost:3001"
            )
            assert svc.enabled is True
            mock_cls.assert_called_once()

    def test_create_trace_returns_none_when_disabled(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        result = svc.create_trace(
            trace_id=uuid.uuid4(), session_id=uuid.uuid4(), user_id=uuid.uuid4()
        )
        assert result is None

    def test_create_trace_returns_trace_when_enabled(self):
        with patch("backend.services.langfuse_service.Langfuse") as mock_cls:
            mock_client = MagicMock()
            mock_trace = MagicMock()
            mock_client.trace.return_value = mock_trace
            mock_cls.return_value = mock_client

            svc = LangfuseService(
                secret_key="sk-test", public_key="pk-test", base_url="http://localhost:3001"
            )
            result = svc.create_trace(
                trace_id=uuid.uuid4(),
                session_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                metadata={"agent_type": "react_v2"},
            )
            assert result is mock_trace
            mock_client.trace.assert_called_once()

    def test_flush_noop_when_disabled(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        svc.flush()  # should not raise

    def test_record_generation_noop_when_no_trace(self):
        svc = LangfuseService(secret_key="", public_key="", base_url="")
        svc.record_generation(
            trace=None,
            name="llm.groq.llama",
            model="llama-3.3-70b",
            input_messages=[],
            output="test",
            prompt_tokens=10,
            completion_tokens=5,
            cost_usd=0.001,
        )
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/services/test_langfuse_service.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 4: Implement LangfuseService**

Create `backend/services/langfuse_service.py`:

```python
"""Langfuse tracing wrapper — fire-and-forget, feature-flagged.

All methods are safe to call when Langfuse is disabled (no-op).
Errors in Langfuse calls are logged but never propagated.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


class LangfuseService:
    """Thin wrapper around the Langfuse SDK.

    Feature-flagged: if secret_key is empty, all methods are no-ops.
    All SDK calls are wrapped in try-except to ensure fire-and-forget.
    """

    def __init__(self, secret_key: str, public_key: str, base_url: str) -> None:
        self._client = None
        self.enabled = False
        if secret_key:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    secret_key=secret_key,
                    public_key=public_key,
                    host=base_url,
                )
                self.enabled = True
                logger.info("Langfuse client initialized at %s", base_url)
            except Exception:
                logger.warning("Langfuse initialization failed — tracing disabled", exc_info=True)

    def create_trace(
        self,
        trace_id: uuid.UUID,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a Langfuse trace for a user query. Returns trace object or None."""
        if not self._client:
            return None
        try:
            return self._client.trace(
                id=str(trace_id),
                session_id=str(session_id),
                user_id=str(user_id),
                metadata=metadata or {},
            )
        except Exception:
            logger.warning("Langfuse trace creation failed", exc_info=True)
            return None

    def record_generation(
        self,
        trace: Any | None,
        name: str,
        model: str,
        input_messages: list[dict],
        output: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        """Record an LLM generation span on an existing trace."""
        if not trace:
            return None
        try:
            return trace.generation(
                name=name,
                model=model,
                input=input_messages,
                output=output,
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
                metadata=metadata or {},
                **({"cost": cost_usd} if cost_usd is not None else {}),
            )
        except Exception:
            logger.warning("Langfuse generation recording failed", exc_info=True)
            return None

    def create_span(
        self,
        trace: Any | None,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        """Create a span (tool execution, ReAct iteration) on an existing trace."""
        if not trace:
            return None
        try:
            return trace.span(name=name, metadata=metadata or {})
        except Exception:
            logger.warning("Langfuse span creation failed", exc_info=True)
            return None

    def end_span(self, span: Any | None) -> None:
        """End a span (sets end_time)."""
        if not span:
            return
        try:
            span.end()
        except Exception:
            logger.warning("Langfuse span end failed", exc_info=True)

    def flush(self) -> None:
        """Flush pending events to Langfuse server."""
        if not self._client:
            return
        try:
            self._client.flush()
        except Exception:
            logger.warning("Langfuse flush failed", exc_info=True)

    def shutdown(self) -> None:
        """Flush and close the Langfuse client."""
        if not self._client:
            return
        try:
            self._client.flush()
            self._client.shutdown()
        except Exception:
            logger.warning("Langfuse shutdown failed", exc_info=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_langfuse_service.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add backend/services/langfuse_service.py tests/unit/services/test_langfuse_service.py pyproject.toml uv.lock
git commit -m "feat(langfuse): add LangfuseService wrapper with fire-and-forget pattern"
```

---

## Task 4: Lifespan — Langfuse Init + Shutdown

**Score:** 7 (context_span=3, convention_density=2, ambiguity=2) → **Local**

**Files:**
- Modify: `backend/main.py` (lifespan function, lines 37-257)

- [ ] **Step 1: Add Langfuse init in lifespan startup**

After the CacheService block (after `logger.info("CacheService initialized")`, around line 114), add:

```python
    # Langfuse tracing — parallel to ObservabilityCollector (fire-and-forget)
    from backend.services.langfuse_service import LangfuseService

    langfuse_service = LangfuseService(
        secret_key=settings.LANGFUSE_SECRET_KEY,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        base_url=settings.LANGFUSE_BASEURL,
    )
    app.state.langfuse = langfuse_service
```

- [ ] **Step 2: Add Langfuse shutdown**

In the shutdown section (after `await close_redis()`), add:

```python
    if hasattr(app.state, "langfuse"):
        app.state.langfuse.shutdown()
```

- [ ] **Step 3: Verify app starts**

Run: `uv run uvicorn backend.main:app --port 8181 &`
Run: `sleep 3 && curl -s http://localhost:8181/api/v1/health | python -m json.tool`
Expected: healthy response
Run: `kill %1`

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(langfuse): initialize LangfuseService in app lifespan"
```

---

## Task 5: Chat Router + ReAct Loop — Trace + Span Instrumentation

**Score:** 10 (context_span=4, convention_density=3, ambiguity=3) → **Opus**

**Note:** Tasks 5+6 from the original plan are merged because the chat router passes `langfuse_trace` to react_loop — they must ship together.

**Files:**
- Modify: `backend/routers/chat.py` (_event_generator function, lines 186-390)
- Modify: `backend/agents/react_loop.py` (react_loop function, lines 306-497)

### Part A: react_loop parameter + span instrumentation

- [ ] **Step 1: Add langfuse_trace parameter to react_loop signature**

Add after `max_iterations` parameter:
```python
    langfuse_trace: Any | None = None,
```

Update the `from typing` import to include `Any`.

- [ ] **Step 2: Add iteration span creation inside the loop**

Inside `for i in range(max_iterations):`, after wall clock check (around line 357), add:

```python
        # Langfuse: start iteration span
        iter_span = None
        if langfuse_trace:
            try:
                # Name the final iteration "synthesis" when LLM finishes without tool calls
                # (determined after LLM response — rename below if needed)
                iter_span = langfuse_trace.span(
                    name=f"react.iteration.{i + 1}",
                    metadata={"iteration": i + 1},
                )
            except Exception:
                logger.debug("langfuse_iteration_span_failed", extra={"iteration": i})
```

- [ ] **Step 3: Rename span to "synthesis" when LLM finishes**

After `if not response.has_tool_calls:` (the finish check, around line 397), before yielding, add:

```python
            # Langfuse: rename iteration span to "synthesis" — this is the final answer
            if iter_span:
                try:
                    iter_span.update(name="synthesis")
                    iter_span.end()
                except Exception:
                    logger.debug("langfuse_synthesis_span_failed")
```

- [ ] **Step 4: Wrap tool execution with Langfuse spans**

After `results = await _execute_tools(...)`, add:

```python
            # Langfuse: record tool execution spans
            _EXTERNAL_TOOLS = {"web_search", "get_geopolitical_events"}
            if iter_span:
                for tc, result in zip(tool_calls, results):
                    try:
                        tool_type = "external" if tc["name"] in _EXTERNAL_TOOLS else "db"
                        tool_span = iter_span.span(
                            name=f"tool.{tc['name']}",
                            metadata={
                                "type": tool_type,
                                "source": tc["name"],
                                "cache_hit": getattr(result, "cache_hit", False),
                                "status": result.status,
                            },
                        )
                        tool_span.end()
                    except Exception:
                        logger.debug("langfuse_tool_span_failed", extra={"tool": tc["name"]})
```

- [ ] **Step 5: End iteration span at end of loop body**

Before circuit breaker check (step 15), add:

```python
        # Langfuse: end iteration span
        if iter_span:
            try:
                iter_span.end()
            except Exception:
                logger.debug("langfuse_iter_end_failed", extra={"iteration": i})
```

### Part B: Chat router trace creation

- [ ] **Step 6: Create Langfuse trace in _event_generator**

In `backend/routers/chat.py`, after `build_user_context` call (around line 214), add:

```python
        # Create Langfuse trace for this query (fire-and-forget)
        langfuse_svc = getattr(request.app.state, "langfuse", None)
        langfuse_trace = None
        if langfuse_svc:
            langfuse_trace = langfuse_svc.create_trace(
                trace_id=query_id,
                session_id=chat_session.id,
                user_id=user.id,
                metadata={"agent_type": chat_session.agent_type},
            )
```

- [ ] **Step 7: Pass langfuse_trace to react_loop call**

Add `langfuse_trace=langfuse_trace` to the `react_loop()` call (around line 306).

- [ ] **Step 8: Verify existing tests still pass**

Run: `uv run pytest tests/unit/ -v -k "react" --no-header`
Expected: all existing react loop tests pass

- [ ] **Step 9: Commit**

```bash
git add backend/agents/react_loop.py backend/routers/chat.py
git commit -m "feat(langfuse): create trace per query + instrument ReAct loop with spans"
```

---

## Task 6: (merged into Task 5 above)

---

## Task 7: LLMClient — Generation Recording

**Score:** 9 (context_span=3, convention_density=3, ambiguity=3) → **Opus**

**Note:** LLM generation recording lives here (not in react_loop Task 5) because LLMClient knows the model, tokens, and cost. react_loop only records iteration + tool spans.

**Files:**
- Modify: `backend/agents/llm_client.py` (LLMClient.__init__ and chat method)
- Modify: `backend/main.py` (wire langfuse_service into LLMClient)

- [ ] **Step 1: Accept langfuse_service in LLMClient.__init__**

Add `langfuse_service: Any | None = None` parameter. Store as `self._langfuse = langfuse_service`.

- [ ] **Step 2: Record Langfuse generation in LLMClient.chat()**

After a successful provider call returns `response` (around line 240, after `return response`), add before the return:

```python
                # Langfuse: record generation (fire-and-forget)
                if self._langfuse and self._langfuse.enabled:
                    try:
                        from backend.agents.context_vars import current_query_id
                        qid = current_query_id.get(None)
                        if qid and self._langfuse._client:
                            trace = self._langfuse._client.trace(id=str(qid))
                            trace.generation(
                                name=f"llm.{provider.name}.{response.model}",
                                model=response.model,
                                input=messages[-1:],
                                output=response.content or "",
                                usage={
                                    "prompt_tokens": response.prompt_tokens,
                                    "completion_tokens": response.completion_tokens,
                                },
                                metadata={
                                    "type": "llm",
                                    "tier": tier or "",
                                    "provider": provider.name,
                                },
                            )
                    except Exception:
                        logger.debug("langfuse_generation_failed")
```

- [ ] **Step 3: Wire langfuse_service in main.py**

Where `llm_client = LLMClient(providers=providers, collector=collector)` is created (around line 173), add `langfuse_service=langfuse_service`.

- [ ] **Step 4: Verify existing tests pass**

Run: `uv run pytest tests/unit/ -v -k "llm_client" --no-header`

- [ ] **Step 5: Commit**

```bash
git add backend/agents/llm_client.py backend/main.py
git commit -m "feat(langfuse): record LLM generations in LLMClient with model/cost/tier metadata"
```

---

## Task 8: Assessment Models + Migration

**Score:** 6 (context_span=2, convention_density=2, ambiguity=2) → **Local**

**Files:**
- Create: `backend/models/assessment.py`
- Create: `backend/migrations/versions/017_assessment_tables_and_log_indexes.py`

- [ ] **Step 1: Create assessment models**

Create `backend/models/assessment.py` with `AssessmentRun` and `AssessmentResult` SQLAlchemy models (same schema as spec §6.1-6.2 `eval_runs`/`eval_results` tables, renamed to avoid the `eval` keyword in filenames).

Table names in DB remain `eval_runs` and `eval_results` (spec-compliant).

```python
"""Agent quality assessment models — periodic quality scoring."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class AssessmentRun(Base):
    """One row per assessment execution (weekly CI or on-demand)."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    total_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    passed_queries: Mapped[int] = mapped_column(Integer, nullable=False)
    pass_rate: Mapped[float] = mapped_column(Float, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<AssessmentRun {self.trigger} pass_rate={self.pass_rate:.0%}>"


class AssessmentResult(Base):
    """One row per golden query in an assessment run."""

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, name="eval_run_id"
    )
    query_index: Mapped[int] = mapped_column(Integer, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    agent_type: Mapped[str] = mapped_column(String(50), nullable=False, default="react_v2")
    # Scores
    tool_selection_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grounding_score: Mapped[float] = mapped_column(Float, nullable=False)
    termination_pass: Mapped[bool] = mapped_column(Boolean, nullable=False)
    external_resilience_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reasoning_coherence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Metadata
    tools_called: Mapped[dict] = mapped_column(JSONB, nullable=False)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    total_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    langfuse_trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AssessmentResult q{self.query_index} {self.intent_category}>"
```

- [ ] **Step 2: Write Alembic migration manually**

Create migration with: `eval_runs` table, `eval_results` table with indexes, plus missing indexes on `llm_call_log` and `tool_execution_log` (see spec §12.3).

**Important:** Do NOT use `alembic revision --autogenerate` — it falsely rewrites entire schema for TimescaleDB. Write manually.

- [ ] **Step 3: Run migration**

Run: `uv run alembic upgrade head`

- [ ] **Step 4: Import models in __init__.py**

Add to `backend/models/__init__.py` (required for Alembic discovery + test teardown):

```python
from backend.models.assessment import AssessmentRun, AssessmentResult  # noqa: F401
```

- [ ] **Step 5: Commit**

```bash
git add backend/models/assessment.py backend/models/__init__.py backend/migrations/versions/017_*.py
git commit -m "feat(assessment): add eval_runs + eval_results tables and log indexes (migration 017)"
```

---

## Task 9: Observability Query Service

**Score:** 9 (context_span=4, convention_density=3, ambiguity=2) → **Opus**

**Files:**
- Create: `backend/services/observability_queries.py`
- Test: `tests/unit/services/test_observability_queries.py`

Shared query logic for both user-facing observability endpoints and existing admin endpoints. DRY refactor per spec §12.3.

- [ ] **Step 1: Write failing tests**

Tests for:
- `get_kpis(session, user_id=None)` — returns KPI dict with 5 values
- `get_query_list(session, user_id=None, page=1, size=25)` — paginated list grouped by query_id
- `get_query_detail(session, query_id)` — L2 step data from log tables
- `get_latest_assessment(session)` — most recent eval_runs row

- [ ] **Step 2: Implement service**

Key design decisions:
- `get_kpis()`: count distinct query_id for today, avg cost_usd per query, avg latency from tool_execution_log, latest pass_rate from eval_runs, fallback_rate from `collector.fallback_rate_last_60s(db)` (requires DB session)
- `get_query_list()`: group by query_id on llm_call_log, join tool_execution_log for tool names, left join chat_messages for query text
- `get_query_detail()`: all log rows for a query_id ordered by created_at, tagged with type (llm/db/external)
- User filtering: join llm_call_log.session_id → chat_session.user_id when user_id provided

- [ ] **Step 2b: Refactor admin router to use shared service**

Refactor `backend/routers/admin.py` `get_query_cost()` (lines 266-346) to delegate to `observability_queries.get_query_detail()`. This avoids duplicate query logic. The admin endpoint becomes a thin wrapper that adds admin-only fields (escalation rate, cascade log). Also wire `get_llm_metrics()` to delegate KPI aggregation to the shared service.

**Note:** Admin `/observability/query/{query_id}/cost` path is confusingly similar to new `/observability/queries/{query_id}`. Add a deprecation comment on the admin endpoint pointing to the new one.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/services/test_observability_queries.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/services/observability_queries.py tests/unit/services/test_observability_queries.py
git commit -m "feat(observability): add shared query service for KPIs, queries, and assessment results"
```

---

## Task 10: Observability API Router

**Score:** 8 (context_span=3, convention_density=3, ambiguity=2) → **Local**

**Files:**
- Create: `backend/routers/observability.py`
- Modify: `backend/main.py` (add router mount after line 297)

- [ ] **Step 1: Create observability router**

6 endpoints per spec §7.1:
- `GET /observability/kpis` — user sees own data, admin sees all
- `GET /observability/queries` — paginated, filterable (date_from, date_to, agent_type, status)
- `GET /observability/queries/{query_id}` — L2 detail
- `GET /observability/queries/{query_id}/langfuse-url` — deep link URL
- `GET /observability/assessment/latest` — latest run summary
- `GET /observability/assessment/history` — admin only

- [ ] **Step 2: Mount router in main.py**

After line 297 (`app.include_router(market.router, ...)`), add:

```python
from backend.routers import observability
app.include_router(observability.router, prefix="/api/v1", tags=["observability"])
```

- [ ] **Step 3: Verify endpoints appear in OpenAPI**

Run: `uv run uvicorn backend.main:app --port 8181 &`
Run: `curl -s http://localhost:8181/openapi.json | python -m json.tool | grep observability`
Run: `kill %1`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/observability.py backend/main.py
git commit -m "feat(observability): add 6 API endpoints for KPIs, queries, and assessments"
```

---

## Task 11: Observability Pydantic Schemas

**Score:** 5 (context_span=2, convention_density=2, ambiguity=1) → **Local**

**Files:**
- Create: `backend/schemas/observability.py`

- [ ] **Step 1: Define all schemas**

```python
"""Pydantic schemas for observability API responses."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class KPIResponse(BaseModel):
    queries_today: int
    avg_latency_ms: float
    avg_cost_per_query: float
    pass_rate: float | None
    fallback_rate_pct: float


class QueryRow(BaseModel):
    query_id: uuid.UUID
    timestamp: datetime
    query_text: str
    agent_type: str
    tools_used: list[str]
    llm_calls: int
    llm_models: list[str]
    db_calls: int
    external_calls: int
    external_sources: list[str]  # e.g. ["yfinance", "Google News"]
    total_cost_usd: float
    duration_ms: int
    score: float | None
    status: str


class QueryListResponse(BaseModel):
    items: list[QueryRow]
    total: int
    page: int
    size: int


class StepDetail(BaseModel):
    step_number: int
    action: str
    type_tag: str
    model_name: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    cache_hit: bool = False


class QueryDetailResponse(BaseModel):
    query_id: uuid.UUID
    query_text: str
    steps: list[StepDetail]
    langfuse_trace_url: str | None = None


class LangfuseURLResponse(BaseModel):
    url: str | None


class AssessmentRunSummary(BaseModel):
    id: uuid.UUID
    trigger: str
    total_queries: int
    passed_queries: int
    pass_rate: float
    total_cost_usd: float
    started_at: datetime
    completed_at: datetime


class AssessmentHistoryResponse(BaseModel):
    items: list[AssessmentRunSummary]
```

- [ ] **Step 2: Commit**

```bash
git add backend/schemas/observability.py
git commit -m "feat(observability): add Pydantic schemas for observability API"
```

---

## Task 12: OIDC SSO Endpoints

**Score:** 10 (context_span=4, convention_density=3, ambiguity=3) → **Opus**

**Files:**
- Create: `backend/services/oidc_provider.py`
- Modify: `backend/routers/auth.py`
- Test: `tests/api/test_oidc.py`

- [ ] **Step 1: Research Langfuse v3 custom auth config**

Verify Langfuse supports `AUTH_CUSTOM_CLIENT_ID`, `AUTH_CUSTOM_ISSUER` etc. Check their docs/source.

- [ ] **Step 2: Implement OIDC discovery endpoint**

`GET /api/v1/auth/.well-known/openid-configuration` — returns JSON discovery document.

- [ ] **Step 3: Implement authorize endpoint**

`GET /api/v1/auth/authorize` — validates existing JWT cookie, issues short-lived auth code.

- [ ] **Step 4: Implement token exchange**

`POST /api/v1/auth/token` — exchanges auth code for access token.

- [ ] **Step 5: Implement userinfo endpoint**

`GET /api/v1/auth/userinfo` — returns `{sub, email, name, auth_provider}`.

The `auth_provider` field returns `"local"` now, `"google"` after Phase C (KAN-152). Langfuse SSO works identically for both — it trusts our JWT regardless of origin.

- [ ] **Step 6: Fallback — URL token if OIDC doesn't work with Langfuse**

If Langfuse v3 doesn't support custom OIDC, implement signed URL approach instead. The `/langfuse-url` endpoint already exists (Task 10) — just add a short-lived signed token to the URL.

- [ ] **Step 7: Write tests**

Run: `uv run pytest tests/api/test_oidc.py -v`

- [ ] **Step 8: Commit**

```bash
git add backend/services/oidc_provider.py backend/routers/auth.py tests/api/test_oidc.py
git commit -m "feat(auth): add OIDC endpoints for Langfuse SSO"
```

---

## Task 12b: Tool Group Fixes (prerequisite for assessment)

**Score:** 4 (context_span=1, convention_density=2, ambiguity=1) → **Local**

**Files:**
- Modify: `backend/agents/tool_groups.py`

- [ ] **Step 1: Add missing tools to groups**

In `TOOL_GROUPS` dict:
- Add `"dividend_sustainability"` to `"stock"` list (query 9 needs it for dividend follow-ups)
- Add `"market_briefing"` to `"portfolio"` list (query 13 needs cross-domain portfolio+market synthesis)

- [ ] **Step 2: Commit**

```bash
git add backend/agents/tool_groups.py
git commit -m "fix(agent): add dividend_sustainability to stock group, market_briefing to portfolio group"
```

---

## Task 13: Golden Dataset Definition

**Score:** 7 (context_span=2, convention_density=2, ambiguity=3) → **Local**

**Files:**
- Create: `backend/tasks/golden_dataset.py`

- [ ] **Step 1: Define all 14 queries + failure variants**

Frozen dataclass with: `query_text`, `intent_category`, `expected_tools` (frozenset), `expected_route` (str), `grounding_checks` (tuple of substrings), `max_iterations`, `is_reasoning` (bool), `is_failure_variant` (bool), `mock_failures` (dict).

All 14 queries from spec §5.2 (REVISED after Session 68 routing audit) plus 3 failure variants.

**Key corrections from audit:**
- `compute_signals` removed from expected tools — `analyze_stock` calls it internally
- Query 7 reworded to "What should I buy for my portfolio?" to trigger portfolio route
- Each query has `expected_route` field matching actual intent classifier behavior
- Task 12b must be completed first (tool group gaps fixed)

- [ ] **Step 2: Commit**

```bash
git add backend/tasks/golden_dataset.py
git commit -m "feat(assessment): define 14 golden queries with expected tools and grounding checks"
```

---

## Task 14: Scoring Engine (5 Dimensions)

**Score:** 9 (context_span=3, convention_density=3, ambiguity=3) → **Opus**

**Files:**
- Create: `backend/tasks/scoring_engine.py`
- Test: `tests/unit/tasks/test_scoring_engine.py`

- [ ] **Step 1: Write failing tests for each scoring dimension**

Tests for `score_tool_selection()`, `score_grounding()`, `score_termination()`, `score_external_resilience()`, `score_reasoning_coherence()`.

- [ ] **Step 2: Implement 4 deterministic scorers**

- `score_tool_selection(expected: frozenset, actual: set) -> bool` — expected ⊆ actual
- `score_grounding(response: str, checks: tuple[str, ...]) -> float` — substring presence ratio (0.0-1.0)
- `score_termination(iterations: int, max_expected: int, tools: list[str]) -> bool` — within bounds, no duplicate consecutive calls
- `score_external_resilience(response: str, mock_failures: dict) -> bool` — no hallucinated data for failed APIs

- [ ] **Step 3: Implement LLM-as-judge scorer**

- `score_reasoning_coherence(response: str, tool_outputs: list[str], llm_chat: Callable) -> float` — Sonnet scores 1-5, only for reasoning queries (#11-14)

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/tasks/test_scoring_engine.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/tasks/scoring_engine.py tests/unit/tasks/test_scoring_engine.py
git commit -m "feat(assessment): implement 5-dimension scoring engine"
```

---

## Task 15: Assessment Runner + CLI Entry Point

**Score:** 8 (context_span=3, convention_density=3, ambiguity=2) → **Local**

**Files:**
- Create: `backend/tasks/assessment_runner.py`

- [ ] **Step 1: Implement runner**

Functions:
- `run_assessment(trigger: str = "local") -> AssessmentRun` — loads golden dataset, runs each query through ReAct loop with real LLM, scores each, writes to DB, pushes to Langfuse dataset
- `_seed_test_user(session)` — creates test user with portfolio for assessment queries
- CLI: `if __name__ == "__main__": asyncio.run(run_assessment())`

- [ ] **Step 2: Verify CLI works**

Run: `uv run python -m backend.tasks.assessment_runner`
Expected: runs (requires GROQ_API_KEY), outputs JSON summary

- [ ] **Step 3: Commit**

```bash
git add backend/tasks/assessment_runner.py
git commit -m "feat(assessment): implement runner with CLI entry point"
```

---

## Task 16: CI Assessment Workflow

**Score:** 5 (context_span=2, convention_density=2, ambiguity=1) → **Local**

**Files:**
- Create: `.github/workflows/assessment.yml`

- [ ] **Step 1: Create workflow**

Weekly Monday 6am UTC + manual trigger. Uses CI secrets for DB, Redis, Groq, Langfuse. Runs migration then assessment runner. **Checks threshold:** runner exits with code 1 if any deterministic score fails (tool selection, grounding, termination, resilience). Reasoning coherence < 3/5 is a soft warning (logged but doesn't fail CI). Uploads JSON results as artifact.

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/assessment.yml
git commit -m "ci: add weekly agent quality assessment workflow"
```

---

## Task 17: Frontend — Observability Page + KPI Ticker

**Score:** 8 (context_span=3, convention_density=3, ambiguity=2) → **Local**

**Files:**
- Create: `frontend/src/app/(authenticated)/observability/page.tsx`
- Create: `frontend/src/components/ObservabilityKPIs.tsx`
- Create: `frontend/src/hooks/useObservabilityKPIs.ts`
- Modify: `frontend/src/components/sidebar-nav.tsx`

- [ ] **Step 1: Create useObservabilityKPIs hook**

TanStack Query calling `GET /api/v1/observability/kpis`.

- [ ] **Step 2: Create ObservabilityKPIs component**

5 StatTile cards. Reuse `StatTile` pattern from dashboard.

- [ ] **Step 3: Create page.tsx**

KPI ticker + placeholder div for QueryTable.

- [ ] **Step 4: Add sidebar nav link**

Add "Observability" entry with Activity icon.

- [ ] **Step 5: Verify page renders**

Run: `cd frontend && npm run dev`
Navigate to `/observability`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add observability page with KPI ticker"
```

---

## Task 18: Frontend — QueryTable + Expansion

**Score:** 10 (context_span=4, convention_density=3, ambiguity=3) → **Opus**

**Files:**
- Create: `frontend/src/components/QueryTable.tsx`
- Create: `frontend/src/components/QueryDetailPanel.tsx`
- Create: `frontend/src/components/StepRow.tsx`
- Create: `frontend/src/hooks/useQueryList.ts`
- Create: `frontend/src/hooks/useQueryDetail.ts`
- Modify: `frontend/src/app/(authenticated)/observability/page.tsx`

- [ ] **Step 1: Create hooks** — useQueryList (paginated, filtered), useQueryDetail (single query L2)
- [ ] **Step 2: Create StepRow** — type badge (LLM/DB/External), tool name, latency, cost, cache indicator
- [ ] **Step 3: Create QueryDetailPanel** — list of StepRows + "View in Langfuse" button
- [ ] **Step 4: Create QueryTable** — sortable columns, click to expand, pagination, date/agent/status filters
- [ ] **Step 5: Wire into page** — replace placeholder
- [ ] **Step 6: Verify** — `cd frontend && npm run dev`, navigate to `/observability`
- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat(frontend): add QueryTable with expandable detail and Langfuse deep-link"
```

---

## Task 19: Unit Tests — Langfuse Wrapper + Spans

**Score:** 7 (context_span=3, convention_density=2, ambiguity=2) → **Local**

**Files:**
- Create: `tests/unit/agents/test_react_loop_langfuse.py`

- [ ] **Step 1: Write tests**

- `test_react_loop_creates_iteration_spans` — mock LLM finishes on first call, verify span created
- `test_react_loop_creates_tool_spans` — mock LLM returns tool_call, verify tool span
- `test_react_loop_no_crash_when_langfuse_fails` — mock trace.span to raise, loop still completes
- `test_react_loop_noop_when_no_trace` — `langfuse_trace=None`, no errors

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/agents/test_react_loop_langfuse.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agents/test_react_loop_langfuse.py
git commit -m "test: unit tests for Langfuse span instrumentation in ReAct loop"
```

---

## Task 20: API Tests — Observability Endpoints

**Score:** 7 (context_span=3, convention_density=2, ambiguity=2) → **Local**

**Files:**
- Create: `tests/api/test_observability.py`

- [ ] **Step 1: Write tests**

- `test_kpis_requires_auth` — 401
- `test_kpis_returns_data` — seed llm_call_log, verify 5 KPI fields
- `test_query_list_pagination` — page=1, size=5
- `test_query_detail_returns_steps` — seed log rows, verify L2 data
- `test_query_detail_404` — unknown query_id
- `test_langfuse_url_null_when_disabled` — LANGFUSE_BASEURL empty
- `test_assessment_latest_null_when_no_runs` — 200 with null
- `test_assessment_history_admin_only` — 403 for non-admin

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/api/test_observability.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_observability.py
git commit -m "test: API tests for observability endpoints"
```

---

## Task 21: Integration Tests — Assessment Runner

**Score:** 9 (context_span=4, convention_density=3, ambiguity=2) → **Opus**

**Files:**
- Create: `tests/integration/test_assessment_runner.py`

- [ ] **Step 1: Write integration test**

Mock LLM with pre-canned responses. Real DB via testcontainers. Mock Langfuse SDK. Verify:
- `eval_runs` row created with correct pass_rate
- `eval_results` rows for all 14 queries
- Deterministic scores correct
- Langfuse push attempted

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/integration/test_assessment_runner.py -v`

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_assessment_runner.py
git commit -m "test: integration tests for assessment runner with mocked LLM"
```

---

## Task 22: Doc Updates — TDD, FSD, ADR, Memories

**Score:** 6 (context_span=2, convention_density=2, ambiguity=2) → **Local**

**Files:**
- Modify: `docs/TDD.md`
- Modify: `docs/FSD.md`
- Modify: `project-plan.md`
- Modify: `PROGRESS.md`
- Update Serena memories: `project/state`, `architecture/system-overview`
- Modify: `MEMORY.md`

- [ ] **Step 1: Update TDD.md**

Add:
- §3.14 Observability API: 6 endpoints with schemas
- §5.5 Langfuse Integration: Docker, SDK, span hierarchy, feature flag, SSO
- §5.6 Assessment Framework: golden dataset, scoring rubric, CI job
- ADR: "Langfuse as parallel trace system — fire-and-forget, not replacing ObservabilityCollector"

- [ ] **Step 2: Update FSD.md**

Add:
- FR-9: Observability page (KPI ticker, query table L1/L2/L3, filters, Langfuse deep-link)
- FR-10: Assessment framework (14 golden queries, 5 scoring dimensions, weekly CI)

- [ ] **Step 3: Mark Phase B complete in project-plan.md**

Add checkmarks + session number to B1-B12 tasks.

- [ ] **Step 4: Add PROGRESS.md session entry**

Session entry: Langfuse integration, observability page, assessment framework, test counts, Alembic head.

- [ ] **Step 5: Update Serena memories**

- `project/state`: phase, test counts, Alembic head (017), resume point
- `architecture/system-overview`: add Langfuse (port 3001), observability router, assessment models, Alembic head → 017
- `future_work/AgentArchitectureBrainstorming`: update "Observability Gaps" section — Langfuse now provides visual trace debugging, prompt versioning, and assessment framework on top of DB-backed metrics. Mark observability as "COMPLETE" not "partially wired".

- [ ] **Step 6: Update MEMORY.md project state**

- [ ] **Step 7: Commit**

```bash
git add docs/TDD.md docs/FSD.md project-plan.md PROGRESS.md
git commit -m "docs: update TDD, FSD, ADR, project-plan for Phase B observability"
```

---

## Execution Dependencies

```
Task 1 (Docker) ─── no deps
Task 2 (Config) ─── no deps
Task 3 (SDK wrapper) ─── depends on Task 2
Task 4 (Lifespan) ─── depends on Task 3
Task 5 (Chat trace + ReAct spans) ─── depends on Task 4
Task 7 (LLMClient generations) ─── depends on Task 4
Task 8 (Migration) ─── no deps
Task 9 (Query service) ─── depends on Task 8
Task 10 (API router) ─── depends on Task 9, 11
Task 11 (Schemas) ─── no deps
Task 12 (OIDC SSO) ─── depends on Task 1
Task 13 (Golden dataset) ─── no deps
Task 14 (Scoring engine) ─── depends on Task 13
Task 15 (Runner) ─── depends on Task 8, 14
Task 16 (CI workflow) ─── depends on Task 15
Task 17 (Frontend KPI) ─── depends on Task 10
Task 18 (Frontend table) ─── depends on Task 17
Task 19 (Langfuse tests) ─── depends on Task 5
Task 20 (API tests) ─── depends on Task 10
Task 21 (Runner tests) ─── depends on Task 15
Task 22 (Docs) ─── depends on all above
```

**Parallelizable groups:**
- Group A (Tasks 1, 2, 8, 11, 13): No dependencies — can run in parallel
- Group B (Tasks 3, 9, 14): Depend on Group A
- Group C (Tasks 4, 10, 12, 15): Depend on Group B
- Group D (Tasks 5, 7, 16, 17): Depend on Group C
- Group E (Task 18): Depends on Group D
- Group F (Tasks 19, 20, 21): Test tasks, depend on implementations
- Group G (Task 22): Final docs, depends on all
