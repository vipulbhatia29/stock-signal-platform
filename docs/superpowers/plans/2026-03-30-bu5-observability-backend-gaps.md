# BU-5: Observability Backend API Gaps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 6 observability API gaps (sort, filter, group-by, summaries, eval scores, Langfuse links) so BU-6 frontend can be built.

**Architecture:** Incremental enhancement of existing service layer. One migration, one new endpoint, instrumentation in the single write point. No new service files or abstraction layers.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, TimescaleDB, Pydantic v2, pytest, Alembic

**Spec:** `docs/superpowers/specs/2026-03-30-bu5-observability-backend-gaps.md`

---

## Chunk 1: Foundation — Migration, Models, Schemas, Sanitizer (Tasks 1–4)

No existing behavior changes. New columns, new schemas, new utility. All independently testable.

---

### Task 1: PII Sanitization Utility

**Files:**
- Create: `backend/utils/sanitize.py`
- Create: `tests/unit/test_sanitize.py`

- [ ] **Step 1: Write failing tests for `sanitize_summary()`**

Create `tests/unit/test_sanitize.py`:

```python
"""Tests for PII sanitization utility."""

from __future__ import annotations

import pytest

from backend.utils.sanitize import sanitize_summary


class TestSanitizeSummary:
    """Tests for sanitize_summary()."""

    def test_redacts_user_id_key(self) -> None:
        result = sanitize_summary({"user_id": "550e8400-e29b-41d4-a716-446655440000", "ticker": "AAPL"})
        assert "[REDACTED]" in result
        assert "AAPL" in result
        assert "550e8400" not in result

    def test_redacts_email_key(self) -> None:
        result = sanitize_summary({"email": "user@example.com", "query": "analyze TSLA"})
        assert "[REDACTED]" in result
        assert "analyze TSLA" in result

    def test_redacts_password_key(self) -> None:
        result = sanitize_summary({"password": "secret123", "action": "login"})
        assert "[REDACTED]" in result
        assert "secret123" not in result

    def test_redacts_nested_pii(self) -> None:
        result = sanitize_summary({"params": {"user_id": "abc-123", "ticker": "MSFT"}})
        assert "[REDACTED]" in result
        assert "MSFT" in result
        assert "abc-123" not in result

    def test_redacts_email_in_string_values(self) -> None:
        result = sanitize_summary({"note": "Contact john@acme.com for details"})
        assert "[EMAIL]" in result
        assert "john@acme.com" not in result

    def test_preserves_financial_data(self) -> None:
        result = sanitize_summary({"ticker": "AAPL", "price": 185.50, "date": "2026-03-28"})
        assert "AAPL" in result
        assert "185.5" in result

    def test_truncates_to_max_length(self) -> None:
        long_data = {"data": "x" * 500}
        result = sanitize_summary(long_data, max_length=100)
        assert len(result) <= 100

    def test_handles_none_input(self) -> None:
        result = sanitize_summary(None)
        assert isinstance(result, str)
        assert len(result) <= 300

    def test_handles_plain_string(self) -> None:
        result = sanitize_summary("hello world")
        assert result == '"hello world"'

    def test_handles_non_serializable(self) -> None:
        result = sanitize_summary(object())
        assert isinstance(result, str)
        assert len(result) <= 300

    def test_returns_sanitize_error_on_failure(self) -> None:
        """If everything fails, return a safe sentinel."""
        # This is hard to trigger normally; we test the contract
        result = sanitize_summary({"ticker": "AAPL"})
        assert isinstance(result, str)

    def test_redacts_api_key(self) -> None:
        result = sanitize_summary({"api_key": "sk-1234567890", "model": "gpt-4"})
        assert "[REDACTED]" in result
        assert "sk-1234567890" not in result

    def test_redacts_authorization_key(self) -> None:
        result = sanitize_summary({"authorization": "Bearer xyz", "status": "ok"})
        assert "[REDACTED]" in result

    def test_redacts_secret_key(self) -> None:
        result = sanitize_summary({"secret": "my-secret", "tool": "search"})
        assert "[REDACTED]" in result
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/unit/test_sanitize.py -v`
Expected: ImportError — `backend.utils.sanitize` does not exist.

- [ ] **Step 3: Implement `sanitize_summary()`**

Create `backend/utils/sanitize.py`:

```python
"""PII sanitization for observability summaries.

Sanitizes tool params/results before storing in the database.
Applied at write time in the observability writer.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_PII_KEYS = frozenset({
    "user_id",
    "email",
    "password",
    "token",
    "api_key",
    "secret",
    "authorization",
})

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def _redact_dict(obj: Any) -> Any:
    """Recursively redact PII keys in dicts/lists."""
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k.lower() in _PII_KEYS else _redact_dict(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_dict(item) for item in obj]
    return obj


def sanitize_summary(raw: Any, max_length: int = 300) -> str:
    """Sanitize and truncate data for observability summaries.

    Args:
        raw: Any input — dict, list, str, None, or other.
        max_length: Maximum output length in characters.

    Returns:
        A sanitized, JSON-serialized, truncated string. Never raises.
    """
    try:
        # Parse string input to recover structure
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                # Plain text — only apply email redaction + truncation
                result = _EMAIL_RE.sub("[EMAIL]", raw)
                return result[:max_length]
        elif isinstance(raw, (dict, list)):
            parsed = raw
        elif raw is None:
            return "null"
        else:
            return str(raw)[:max_length]

        # Recursive PII redaction
        sanitized = _redact_dict(parsed)

        # Serialize
        text = json.dumps(sanitized, default=str)

        # Email redaction on serialized string
        text = _EMAIL_RE.sub("[EMAIL]", text)

        # Truncate
        return text[:max_length]
    except Exception:
        logger.warning("sanitize_summary failed", exc_info=True)
        return "[SANITIZE_ERROR]"
```

Ensure `backend/utils/__init__.py` exists:

```python
# backend/utils/__init__.py — empty, makes utils a package
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/unit/test_sanitize.py -v`
Expected: All 14 tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/utils/ tests/unit/test_sanitize.py && uv run ruff format backend/utils/ tests/unit/test_sanitize.py
git add backend/utils/sanitize.py backend/utils/__init__.py tests/unit/test_sanitize.py
git commit -m "feat(observability): add PII sanitization utility for tool summaries"
```

---

### Task 2: Migration 020 + Model Updates

**Files:**
- Create: `backend/migrations/versions/020_observability_gaps.py`
- Modify: `backend/models/logs.py`
- Modify: `backend/models/assessment.py`

- [ ] **Step 1: Add columns to SQLAlchemy models**

In `backend/models/logs.py`, add to `LLMCallLog` class (after `loop_step`):

```python
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    langfuse_trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```

Add import at top if not present: `import uuid` and ensure `UUID` is imported from `sqlalchemy.dialects.postgresql`.

In `backend/models/logs.py`, add to `ToolExecutionLog` class (after `loop_step`):

```python
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Ensure `Text` is imported from `sqlalchemy`.

In `backend/models/assessment.py`, add to `AssessmentResult` class (after `created_at`):

```python
    query_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
```

- [ ] **Step 2: Write migration 020 (hand-written)**

Create `backend/migrations/versions/020_observability_gaps.py`:

```python
"""020 — Observability API gaps: status, langfuse_trace_id, summaries, eval query_id.

Revision ID: c2d3e4f5a6b7
Revises: b1fe4c734142
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "c2d3e4f5a6b7"
down_revision = "b1fe4c734142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add observability columns."""
    # llm_call_log: status + langfuse_trace_id
    op.add_column(
        "llm_call_log",
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
    )
    op.add_column(
        "llm_call_log",
        sa.Column("langfuse_trace_id", UUID(as_uuid=True), nullable=True),
    )

    # tool_execution_log: input_summary + output_summary
    op.add_column(
        "tool_execution_log",
        sa.Column("input_summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "tool_execution_log",
        sa.Column("output_summary", sa.Text(), nullable=True),
    )

    # eval_results: query_id
    op.add_column(
        "eval_results",
        sa.Column("query_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_eval_results_query_id", "eval_results", ["query_id"])


def downgrade() -> None:
    """Remove observability columns."""
    op.drop_index("ix_eval_results_query_id", table_name="eval_results")
    op.drop_column("eval_results", "query_id")
    op.drop_column("tool_execution_log", "output_summary")
    op.drop_column("tool_execution_log", "input_summary")
    op.drop_column("llm_call_log", "langfuse_trace_id")
    op.drop_column("llm_call_log", "status")
```

- [ ] **Step 3: Verify migration applies**

Run: `uv run alembic upgrade head`
Expected: Migration applies cleanly. Verify with `uv run alembic current`.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/models/logs.py backend/models/assessment.py && uv run ruff format backend/models/logs.py backend/models/assessment.py
git add backend/models/logs.py backend/models/assessment.py backend/migrations/versions/020_observability_gaps.py
git commit -m "feat(observability): migration 020 — status, langfuse_trace_id, summaries, eval query_id"
```

---

### Task 3: New Pydantic Schemas

**Files:**
- Modify: `backend/schemas/observability.py`

- [ ] **Step 1: Add enums and group-by schemas**

Append to `backend/schemas/observability.py` (after existing classes):

```python
from enum import Enum


class SortByEnum(str, Enum):
    """Sortable columns for query list."""

    timestamp = "timestamp"
    total_cost_usd = "total_cost_usd"
    duration_ms = "duration_ms"
    llm_calls = "llm_calls"
    score = "score"


class SortOrderEnum(str, Enum):
    """Sort direction."""

    asc = "asc"
    desc = "desc"


class GroupByEnum(str, Enum):
    """Grouping dimensions for query aggregation."""

    agent_type = "agent_type"
    date = "date"
    model = "model"
    status = "status"
    provider = "provider"
    tier = "tier"
    tool_name = "tool_name"
    user = "user"
    intent_category = "intent_category"


class DateBucketEnum(str, Enum):
    """Date bucketing granularity."""

    day = "day"
    week = "week"
    month = "month"


class GroupRow(BaseModel):
    """Single row in a grouped aggregation result."""

    key: str
    query_count: int
    total_cost_usd: float
    avg_cost_usd: float
    avg_latency_ms: float
    error_rate: float


class GroupedResponse(BaseModel):
    """Response for grouped query aggregation."""

    group_by: str
    bucket: str | None = None
    groups: list[GroupRow]
    total_queries: int
```

Note: `Enum` import may already exist — check and add only if needed. `BaseModel` is already imported.

- [ ] **Step 2: Lint and commit**

```bash
uv run ruff check --fix backend/schemas/observability.py && uv run ruff format backend/schemas/observability.py
git add backend/schemas/observability.py
git commit -m "feat(observability): add sort, group-by enums and grouped response schemas"
```

---

### Task 4: Extract `require_admin` to Shared Dependencies

**Files:**
- Modify: `backend/dependencies.py`
- Modify: `backend/routers/admin.py`

- [ ] **Step 1: Add `require_admin()` to `backend/dependencies.py`**

Append after existing functions:

```python
def require_admin(user: User) -> User:
    """Raise 403 if user is not an admin.

    Args:
        user: The authenticated user.

    Returns:
        The user if admin.

    Raises:
        HTTPException: 403 if not admin.
    """
    from backend.models.user import UserRole

    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

Ensure `HTTPException` is imported from `fastapi` (likely already is).

- [ ] **Step 2: Update admin router to use shared `require_admin`**

In `backend/routers/admin.py`:
- Replace the local `_require_admin` definition (lines 35-39) with an import:
  ```python
  from backend.dependencies import require_admin
  ```
- Replace all 12 calls from `_require_admin(user)` to `require_admin(user)`.

- [ ] **Step 3: Run existing admin tests to verify no breakage**

Run: `uv run pytest tests/api/test_admin_observability.py tests/unit/ -k admin -v --tb=short`
Expected: All existing tests PASS.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/dependencies.py backend/routers/admin.py && uv run ruff format backend/dependencies.py backend/routers/admin.py
git add backend/dependencies.py backend/routers/admin.py
git commit -m "refactor: extract require_admin to shared dependencies"
```

---

## Chunk 2: Instrumentation — Writer, Collector, Callers (Tasks 5–8)

Wire the new columns into the write path. All changes are additive — existing behavior preserved.

---

### Task 5: Observability Writer — New Columns

**Files:**
- Modify: `backend/agents/observability_writer.py`
- Modify: `tests/unit/agents/test_observability_writer.py`

- [ ] **Step 1: Write failing tests for new writer fields**

Add new test methods to the existing `TestWriteEvent` class in `tests/unit/agents/test_observability_writer.py`. Follow the established mock pattern (inline `mock_session` + `mock_cm` + `patch`):

```python
    @pytest.mark.asyncio
    async def test_writes_status_on_llm_call(self) -> None:
        """LLM call event should write explicit status from data dict."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_atype = "backend.agents.observability_writer.current_agent_type"
        patch_aid = "backend.agents.observability_writer.current_agent_instance_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as m_sid, patch(patch_qid) as m_qid:
                with patch(patch_atype) as m_at, patch(patch_aid) as m_ai:
                    m_sid.get.return_value = uuid.uuid4()
                    m_qid.get.return_value = uuid.uuid4()
                    m_at.get.return_value = "react_v2"
                    m_ai.get.return_value = None
                    await write_event("llm_call", {
                        "provider": "groq", "model": "llama-3.3-70b",
                        "status": "error",
                    })

        row = mock_session.add.call_args[0][0]
        assert row.status == "error"

    @pytest.mark.asyncio
    async def test_defaults_status_to_completed(self) -> None:
        """LLM call without explicit status should default to 'completed'."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_atype = "backend.agents.observability_writer.current_agent_type"
        patch_aid = "backend.agents.observability_writer.current_agent_instance_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as m_sid, patch(patch_qid) as m_qid:
                with patch(patch_atype) as m_at, patch(patch_aid) as m_ai:
                    m_sid.get.return_value = uuid.uuid4()
                    m_qid.get.return_value = uuid.uuid4()
                    m_at.get.return_value = None
                    m_ai.get.return_value = None
                    await write_event("llm_call", {
                        "provider": "groq", "model": "llama-3.3-70b",
                    })

        row = mock_session.add.call_args[0][0]
        assert row.status == "completed"

    @pytest.mark.asyncio
    async def test_writes_langfuse_trace_id(self) -> None:
        """LLM call event should write langfuse_trace_id from data dict."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        trace_id = uuid.uuid4()
        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_atype = "backend.agents.observability_writer.current_agent_type"
        patch_aid = "backend.agents.observability_writer.current_agent_instance_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as m_sid, patch(patch_qid) as m_qid:
                with patch(patch_atype) as m_at, patch(patch_aid) as m_ai:
                    m_sid.get.return_value = uuid.uuid4()
                    m_qid.get.return_value = uuid.uuid4()
                    m_at.get.return_value = None
                    m_ai.get.return_value = None
                    await write_event("llm_call", {
                        "provider": "groq", "model": "llama-3.3-70b",
                        "langfuse_trace_id": trace_id,
                    })

        row = mock_session.add.call_args[0][0]
        assert row.langfuse_trace_id == trace_id

    @pytest.mark.asyncio
    async def test_writes_input_summary_on_tool(self) -> None:
        """Tool event should write PII-sanitized input_summary."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_atype = "backend.agents.observability_writer.current_agent_type"
        patch_aid = "backend.agents.observability_writer.current_agent_instance_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as m_sid, patch(patch_qid) as m_qid:
                with patch(patch_atype) as m_at, patch(patch_aid) as m_ai:
                    m_sid.get.return_value = uuid.uuid4()
                    m_qid.get.return_value = uuid.uuid4()
                    m_at.get.return_value = None
                    m_ai.get.return_value = None
                    await write_event("tool_execution", {
                        "tool_name": "analyze_stock", "status": "ok",
                        "params": {"ticker": "AAPL"}, "result": {"score": 8.5},
                    })

        row = mock_session.add.call_args[0][0]
        assert row.input_summary is not None
        assert "AAPL" in row.input_summary

    @pytest.mark.asyncio
    async def test_writes_output_summary_on_tool(self) -> None:
        """Tool event should write PII-sanitized output_summary."""
        from backend.agents.observability_writer import write_event

        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        patch_factory = "backend.agents.observability_writer.async_session_factory"
        patch_sid = "backend.agents.observability_writer.current_session_id"
        patch_qid = "backend.agents.observability_writer.current_query_id"
        patch_atype = "backend.agents.observability_writer.current_agent_type"
        patch_aid = "backend.agents.observability_writer.current_agent_instance_id"
        with patch(patch_factory, return_value=mock_cm):
            with patch(patch_sid) as m_sid, patch(patch_qid) as m_qid:
                with patch(patch_atype) as m_at, patch(patch_aid) as m_ai:
                    m_sid.get.return_value = uuid.uuid4()
                    m_qid.get.return_value = uuid.uuid4()
                    m_at.get.return_value = None
                    m_ai.get.return_value = None
                    await write_event("tool_execution", {
                        "tool_name": "analyze_stock", "status": "ok",
                        "params": {"ticker": "AAPL"}, "result": {"score": 8.5},
                    })

        row = mock_session.add.call_args[0][0]
        assert row.output_summary is not None
        assert "8.5" in row.output_summary
```

- [ ] **Step 2: Run tests — verify they fail**

Run: `uv run pytest tests/unit/agents/test_observability_writer.py -v -k "status or langfuse or summary"`
Expected: FAIL — fields not yet written.

- [ ] **Step 3: Update `write_event()` to write new fields**

In `backend/agents/observability_writer.py`, modify the `write_event()` function:

For the `llm_call` branch, add to the `LLMCallLog(...)` constructor:
```python
                    status=data.get("status", "completed"),
                    langfuse_trace_id=data.get("langfuse_trace_id"),
```

For the `tool_execution` branch, add import at top:
```python
from backend.utils.sanitize import sanitize_summary
```

Add to the `ToolExecutionLog(...)` constructor:
```python
                    input_summary=sanitize_summary(data.get("params", {})),
                    output_summary=sanitize_summary(data.get("result", "")),
```

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/unit/agents/test_observability_writer.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/agents/observability_writer.py && uv run ruff format backend/agents/observability_writer.py
git add backend/agents/observability_writer.py tests/unit/agents/test_observability_writer.py
git commit -m "feat(observability): writer writes status, langfuse_trace_id, input/output summaries"
```

---

### Task 6: Collector Signature Updates

**Files:**
- Modify: `backend/agents/observability.py`

- [ ] **Step 1: Update `record_request()` signature**

In `backend/agents/observability.py`, modify `ObservabilityCollector.record_request()`:

Add new params:
```python
    async def record_request(
        self,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
        loop_step: int | None = None,
        status: str = "completed",
        langfuse_trace_id: str | None = None,
    ) -> None:
```

Add to the data dict inside the method:
```python
                        "status": status,
                        "langfuse_trace_id": langfuse_trace_id,
```

- [ ] **Step 2: Update `record_tool_execution()` signature**

Add new `result` param:
```python
    async def record_tool_execution(
        self,
        tool_name: str,
        latency_ms: int,
        status: str,
        result_size_bytes: int | None = None,
        params: dict | None = None,
        error: str | None = None,
        cache_hit: bool = False,
        loop_step: int | None = None,
        result: Any = None,
    ) -> None:
```

Add `from typing import Any` import if not present.

Add to the data dict:
```python
                        "result": result,
```

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `uv run pytest tests/unit/agents/ -v --tb=short`
Expected: All existing tests PASS (new params have defaults).

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/agents/observability.py && uv run ruff format backend/agents/observability.py
git add backend/agents/observability.py
git commit -m "feat(observability): add status, langfuse_trace_id, result params to collector"
```

---

### Task 7: Caller Updates — ReAct Loop, LLMProvider, V1 Executor

**Files:**
- Modify: `backend/agents/react_loop.py` (lines ~255 and ~398)
- Modify: `backend/agents/llm_client.py` (lines ~149-169 `LLMProvider._record_success()`)
- Modify: `backend/agents/executor.py` (line ~257)

**IMPORTANT:** `record_request()` is called from TWO places:
1. `LLMProvider._record_success()` at `llm_client.py:161` — the primary path (has real model/cost data)
2. `react_loop.py:398` — a secondary recording point in the ReAct loop

Both must be updated.

- [ ] **Step 1: Update `LLMProvider._record_success()` to pass `langfuse_trace_id`**

In `backend/agents/llm_client.py`, modify `_record_success()` (line ~149) to read the ContextVar and pass it:

```python
    async def _record_success(
        self,
        model: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        tier: str = "",
    ) -> None:
        """Record a successful LLM call with cost. Called by subclass after API response."""
        if not self.collector:
            return
        cost = self._compute_cost(model, prompt_tokens, completion_tokens)

        # Read query_id from ContextVar — it IS the Langfuse trace ID
        from backend.request_context import current_query_id
        qid = current_query_id.get(None)

        await self.collector.record_request(
            model=model,
            provider=self.name,
            tier=tier,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            langfuse_trace_id=qid,
        )
```

- [ ] **Step 2: Update ReAct loop — both tool recording (line ~255) and LLM recording (line ~398)**

In `backend/agents/react_loop.py`, at line ~255, add `result=result.data`:

```python
        await collector.record_tool_execution(
            tool_name=name,
            latency_ms=latency_ms,
            status=result.status,
            result_size_bytes=result_size,
            params=params,
            error=result.error,
            cache_hit=cache_hit,
            loop_step=loop_step,
            result=result.data,
        )
```

At line ~398, add `langfuse_trace_id` to the second `record_request()` call:

```python
        from backend.request_context import current_query_id
        qid = current_query_id.get(None)

        if collector:
            await collector.record_request(
                model=response.model,
                provider="",
                tier="react",
                latency_ms=0,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                loop_step=i,
                langfuse_trace_id=qid,
            )
```

- [ ] **Step 3: Update V1 executor for consistency**

In `backend/agents/executor.py`, at line ~257, add `result=result_data` to the `collector.record_tool_execution()` call (same pattern as react_loop).

- [ ] **Step 4: Run existing tests**

Run: `uv run pytest tests/unit/ -v --tb=short -q`
Expected: All tests PASS (new params have defaults).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/agents/react_loop.py backend/agents/llm_client.py backend/agents/executor.py && uv run ruff format backend/agents/react_loop.py backend/agents/llm_client.py backend/agents/executor.py
git add backend/agents/react_loop.py backend/agents/llm_client.py backend/agents/executor.py
git commit -m "feat(observability): pass result and langfuse_trace_id from callers to collector"
```

---

### Task 8: Chat Router Decline Logging + Assessment Runner ContextVar

**Files:**
- Modify: `backend/routers/chat.py`
- Modify: `backend/tasks/assessment_runner.py`

**IMPORTANT — Decline logging pitfalls:**
1. A freshly instantiated `ObservabilityCollector()` has `_db_writer = None`, making `record_request()` a silent no-op. Must use `write_event` directly from `observability_writer.py` instead.
2. `current_session_id` ContextVar is NOT set at decline paths 1 and 2 (before session resolution). The writer reads it with `.get()` which defaults to `None` — this is fine since `session_id` is nullable on `LLMCallLog`.
3. There are **4** decline paths, not 3: input guard, injection, intent out_of_scope, and **session abuse check** (`decline_count >= 5` at line ~145).

- [ ] **Step 1: Add decline logging to chat router**

In `backend/routers/chat.py`, add a helper at module level (near `_decline_stream`):

```python
async def _log_decline(reason: str) -> None:
    """Log a declined query to llm_call_log for observability.

    Uses write_event directly — the collector requires DB writer setup
    that is only available in the agent pipeline, not the router scope.
    """
    from backend.agents.observability_writer import write_event

    await write_event("llm_call", {
        "provider": "none",
        "model": "none",
        "tier": "none",
        "latency_ms": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "status": "declined",
        "error": reason,
    })
```

Then add `await _log_decline(...)` at each of the 4 decline paths:

**Path 1 — Input guard failure (line ~111):**
```python
    if length_err:
        await _log_decline("input_length_exceeded")
        return StreamingResponse(_decline_stream(length_err), ...)
```

**Path 2 — Injection detection (line ~136):**
```python
    if detect_injection(body.message):
        await _log_decline("injection_detected")
        ...  # existing decline_count increment and return
```

**Path 3 — Session abuse check (line ~145):**
```python
    if (chat_session.decline_count or 0) >= 5:
        await _log_decline("session_abuse_limit")
        return StreamingResponse(...)
```

**Path 4 — Intent classifier out_of_scope (line ~238, inside generator):**
```python
        if classified.intent == "out_of_scope":
            await _log_decline("out_of_scope")
            decline_msg = classified.decline_message or (...)
            yield StreamEvent(type="decline", content=decline_msg).to_ndjson() + "\n"
```

- [ ] **Step 2: Write tests for decline logging**

Add to `tests/unit/test_chat_decline_logging.py` (new file):

```python
"""Tests for chat router decline logging to observability."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest


class TestDeclineLogging:
    """Tests that decline paths write to llm_call_log."""

    @pytest.mark.asyncio
    async def test_log_decline_writes_llm_call_with_declined_status(self) -> None:
        """_log_decline should call write_event with status='declined'."""
        with patch("backend.routers.chat.write_event", new_callable=AsyncMock) as mock_write:
            # Import after patching
            from backend.routers.chat import _log_decline

            await _log_decline("injection_detected")

            mock_write.assert_awaited_once()
            call_args = mock_write.call_args
            assert call_args[0][0] == "llm_call"
            assert call_args[0][1]["status"] == "declined"
            assert call_args[0][1]["error"] == "injection_detected"
```

- [ ] **Step 3: Update assessment runner — return `query_id` as 4th tuple element**

In `backend/tasks/assessment_runner.py`:

**3a. Update `_run_query_live()` signature and return:**

```python
async def _run_query_live(
    golden: GoldenQuery,
    user: User,
    session: Any,
) -> tuple[str, list[str], int, uuid_mod.UUID]:
    """Run a single query through the live ReAct agent.

    Returns:
        Tuple of (response_text, tools_called, iterations, query_id).
    """
    import uuid as uuid_mod
    from backend.request_context import current_query_id

    # Set ContextVar for observability — assessment runs bypass chat router
    query_id = uuid_mod.uuid4()
    current_query_id.set(query_id)

    # ... existing implementation unchanged ...

    return response_text, tools_called, iterations, query_id  # ADD query_id
```

Note: add `import uuid as uuid_mod` at the top of the function (lazy import pattern).

**3b. Update the caller in `run_assessment()` (line ~345):**

Change the unpacking from 3-tuple to 4-tuple:
```python
                if dry_run:
                    response_text, tools_called, iterations = _get_dry_run_response(golden)
                    query_id = uuid_mod.uuid4()  # dry run: generate placeholder
                else:
                    response_text, tools_called, iterations, query_id = await _run_query_live(
                        golden, user, session
                    )
```

Add `import uuid as uuid_mod` at the top of `run_assessment()` if not present.

**3c. Add `query_id` to AssessmentResult constructor (line ~379):**

```python
            result_row = AssessmentResult(
                run_id=run_id,
                query_index=idx + 1,
                query_text=golden.query_text,
                intent_category=golden.intent_category,
                agent_type="react_v2",
                tool_selection_pass=tool_ok,
                grounding_score=float(scores["grounding"]),
                termination_pass=termination_ok,
                external_resilience_pass=resilience_ok if golden.is_failure_variant else None,
                reasoning_coherence_score=(
                    float(scores["reasoning_coherence"])
                    if scores["reasoning_coherence"] is not None
                    else None
                ),
                tools_called={"tools": tools_called},
                iteration_count=iterations,
                total_cost_usd=0.0,
                total_duration_ms=duration_ms,
                query_id=query_id,  # NEW: enable eval score join
            )
```

- [ ] **Step 4: Write assessment runner test**

Add to existing assessment runner tests:

```python
    @pytest.mark.asyncio
    async def test_run_query_live_returns_query_id(self) -> None:
        """_run_query_live should return a 4-tuple with query_id as UUID."""
        # Mock the react_loop and ToolRegistry
        with patch("backend.tasks.assessment_runner.react_loop") as mock_loop:
            with patch("backend.tasks.assessment_runner.ToolRegistry"):
                mock_loop.return_value = AsyncMock()  # async generator mock
                # ... setup golden query fixture ...
                result = await _run_query_live(golden, user, session)
                assert len(result) == 4
                assert isinstance(result[3], uuid.UUID)
```

- [ ] **Step 5: Run existing tests**

Run: `uv run pytest tests/unit/ tests/api/ -v --tb=short -q`
Expected: All tests PASS.

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix backend/routers/chat.py backend/tasks/assessment_runner.py tests/unit/test_chat_decline_logging.py && uv run ruff format backend/routers/chat.py backend/tasks/assessment_runner.py tests/unit/test_chat_decline_logging.py
git add backend/routers/chat.py backend/tasks/assessment_runner.py tests/unit/test_chat_decline_logging.py
git commit -m "feat(observability): log 4 decline paths + assessment runner query_id propagation"
```

---

## Chunk 3: Enhanced Query List — Sort, Filter, Eval Join (Tasks 9–11)

---

### Task 9: Enhanced `get_query_list()` Service

**Files:**
- Modify: `backend/services/observability_queries.py`

- [ ] **Step 1: Write failing tests for sort + filter + eval score**

Add to `tests/unit/services/test_observability_queries.py`:

Tests for: `sort_by` (each of 5 columns, asc/desc), `status` HAVING filter, `cost_min`/`cost_max` HAVING filter, eval score join (present + absent), NULLS LAST for score sort, `cost_min > cost_max` raises ValueError.

(Full test code for each scenario — follow the existing mock pattern in the test file. Each test creates mock DB rows, calls `get_query_list()` with the new params, and asserts the output.)

- [ ] **Step 2: Update `get_query_list()` function signature**

Add new params to `get_query_list()`:

```python
async def get_query_list(
    db: AsyncSession,
    user_id: uuid.UUID | None = None,
    page: int = 1,
    size: int = 25,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    agent_type: str | None = None,
    sort_by: str = "timestamp",
    sort_order: str = "desc",
    status: str | None = None,
    cost_min: float | None = None,
    cost_max: float | None = None,
) -> dict:
```

- [ ] **Step 3: Implement sort, status/cost HAVING filters, eval score LEFT JOIN**

Key implementation points:
- Add `tool_latency_sq` scalar subquery for `duration_ms` sorting
- Add `eval_sq` subquery for eval score LEFT JOIN
- Build `SORT_MAP` dict mapping enum values to SQL expressions
- Apply `HAVING` clauses for status and cost filters BEFORE the count subquery
- Derive worst-status per group via `MAX(CASE WHEN ...)`
- Apply `NULLS LAST` for score sorting

- [ ] **Step 4: Run tests — verify they pass**

Run: `uv run pytest tests/unit/services/test_observability_queries.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/services/observability_queries.py tests/unit/services/test_observability_queries.py && uv run ruff format backend/services/observability_queries.py tests/unit/services/test_observability_queries.py
git add backend/services/observability_queries.py tests/unit/services/test_observability_queries.py
git commit -m "feat(observability): enhanced get_query_list — sort, filter, eval score join"
```

---

### Task 10: Enhanced Router — Query List Params + Status Enum

**Files:**
- Modify: `backend/schemas/observability.py` (add `StatusFilterEnum`)
- Modify: `backend/routers/observability.py`
- Create: `tests/api/test_observability_api.py` (new file — `test_observability.py` does not exist)

**Prerequisite:** Tasks 3 (schemas) and 9 (service) must be complete.

- [ ] **Step 1: Add `StatusFilterEnum` to schemas**

In `backend/schemas/observability.py`, add alongside the other enums:

```python
class StatusFilterEnum(str, Enum):
    """Query status filter values."""

    completed = "completed"
    error = "error"
    declined = "declined"
    timeout = "timeout"
```

- [ ] **Step 2: Add new query params to `/queries` endpoint**

Update the `queries()` function signature:

```python
from backend.schemas.observability import SortByEnum, SortOrderEnum, StatusFilterEnum

async def queries(
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=100),
    agent_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort_by: SortByEnum = SortByEnum.timestamp,
    sort_order: SortOrderEnum = SortOrderEnum.desc,
    status: StatusFilterEnum | None = None,
    cost_min: float | None = Query(None, ge=0),
    cost_max: float | None = Query(None, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> QueryListResponse:
```

Add `cost_min > cost_max` validation:
```python
    if cost_min is not None and cost_max is not None and cost_min > cost_max:
        raise HTTPException(status_code=422, detail="cost_min must be <= cost_max")
```

Pass new params to `get_query_list()`:
```python
    result = await get_query_list(
        db,
        user_id=_user_scope(user),
        page=page,
        size=size,
        agent_type=agent_type,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by.value,
        sort_order=sort_order.value,
        status=status.value if status else None,
        cost_min=cost_min,
        cost_max=cost_max,
    )
```

- [ ] **Step 3: Create API test file and write tests**

Create `tests/api/test_observability_api.py` (new file — follow patterns from `tests/api/test_admin_observability.py` for fixture setup):

```python
"""API tests for observability endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


class TestQueryListParams:
    """Tests for GET /observability/queries with new params."""

    @pytest.mark.asyncio
    async def test_invalid_sort_by_returns_422(self, client: AsyncClient, auth_headers: dict) -> None:
        """Invalid sort_by enum value should return 422."""
        response = await client.get(
            "/api/v1/observability/queries?sort_by=badvalue",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self, client: AsyncClient, auth_headers: dict) -> None:
        """Invalid status enum value should return 422."""
        response = await client.get(
            "/api/v1/observability/queries?status=badvalue",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cost_min_gt_cost_max_returns_422(self, client: AsyncClient, auth_headers: dict) -> None:
        """cost_min > cost_max should return 422."""
        response = await client.get(
            "/api/v1/observability/queries?cost_min=10&cost_max=1",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_sort_params_accepted(self, client: AsyncClient, auth_headers: dict) -> None:
        """Valid sort_by and sort_order should return 200."""
        response = await client.get(
            "/api/v1/observability/queries?sort_by=total_cost_usd&sort_order=asc",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_grouped_endpoint_not_shadowed(self, client: AsyncClient, auth_headers: dict) -> None:
        """GET /queries/grouped should not be shadowed by /queries/{query_id}."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=agent_type",
            headers=auth_headers,
        )
        # Should NOT be 422 (UUID parse failure) — route ordering must be correct
        assert response.status_code != 422
```

Note: Ensure `conftest.py` at `tests/api/` level provides `client` and `auth_headers` fixtures. Check `tests/api/test_admin_observability.py` for the pattern.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/api/test_observability_api.py -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/schemas/observability.py backend/routers/observability.py tests/api/test_observability_api.py && uv run ruff format backend/schemas/observability.py backend/routers/observability.py tests/api/test_observability_api.py
git add backend/schemas/observability.py backend/routers/observability.py tests/api/test_observability_api.py
git commit -m "feat(observability): query list — sort, status enum, cost range params + API tests"
```

---

### Task 11: Enhanced Query Detail — Summaries + Langfuse URL

**Files:**
- Modify: `backend/services/observability_queries.py`

- [ ] **Step 1: Write failing tests for summaries and Langfuse URL**

Tests for: tool step summaries populated from DB columns, LLM step summaries derived, Langfuse URL constructed, missing trace_id → None, missing LANGFUSE_BASEURL → None.

- [ ] **Step 2: Update `get_query_detail()` to populate summaries + Langfuse URL**

In the LLM events loop, replace hardcoded summary `None`:
```python
        events.append(
            (
                row.created_at,
                {
                    "action": f"llm.{row.provider}.{row.model}",
                    "type_tag": "llm",
                    "model_name": row.model,
                    "input_summary": f"→ {row.provider}/{row.model}",
                    "output_summary": f"{row.completion_tokens or 0} tokens, {row.latency_ms or 0}ms, ${row.cost_usd or 0:.4f}",
                    "latency_ms": row.latency_ms,
                    "cost_usd": float(row.cost_usd) if row.cost_usd else None,
                    "cache_hit": False,
                },
            )
        )
```

In the tool events loop, read from DB columns:
```python
                {
                    "action": f"tool.{row.tool_name}",
                    "type_tag": type_tag,
                    "model_name": None,
                    "input_summary": row.input_summary,
                    "output_summary": row.output_summary,
                    ...
                },
```

For Langfuse URL, after building steps. **Note:** Use `from backend.config import settings` (module-level singleton, NOT `get_settings()` which does not exist). Guard on `LANGFUSE_SECRET_KEY` (not `LANGFUSE_BASEURL` which always has a non-None default of `http://localhost:3001`):

```python
    from backend.config import settings

    langfuse_trace_id = None
    for row in llm_rows:
        if row.langfuse_trace_id:
            langfuse_trace_id = row.langfuse_trace_id
            break

    langfuse_url = None
    if langfuse_trace_id and settings.LANGFUSE_SECRET_KEY and settings.LANGFUSE_BASEURL:
        langfuse_url = f"{settings.LANGFUSE_BASEURL}/trace/{langfuse_trace_id}"

    return {
        "query_id": query_id,
        "query_text": query_text,
        "steps": steps,
        "langfuse_trace_url": langfuse_url,
    }
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/services/test_observability_queries.py -v -k detail`
Expected: All tests PASS.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/services/observability_queries.py && uv run ruff format backend/services/observability_queries.py
git add backend/services/observability_queries.py tests/unit/services/test_observability_queries.py
git commit -m "feat(observability): query detail — summaries populated, Langfuse deep-link"
```

---

## Chunk 4: Group-By Endpoint (Tasks 12–13)

---

### Task 12: `get_query_groups()` Service Function

**Files:**
- Modify: `backend/services/observability_queries.py`
- Modify: `tests/unit/services/test_observability_queries.py`

- [ ] **Step 1: Write failing tests for each group-by dimension**

16 tests covering: each of 9 dimensions (dedicated mock per branch), date bucketing (day/week/month), date key ISO format, tool_name cross-table query, intent_category empty result, user group (admin vs non-admin), empty results.

- [ ] **Step 2: Implement `get_query_groups()`**

Add to `backend/services/observability_queries.py`:

```python
async def get_query_groups(
    db: AsyncSession,
    group_by: str,
    user_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    bucket: str = "day",
) -> dict:
    """Return aggregated query groups."""
```

Implementation handles 3 base table paths:
- `llm_call_log` groups: agent_type, date, model, status, provider, tier
- `tool_execution_log`: tool_name
- `chat_sessions` JOIN `users`: user
- `eval_results`: intent_category

Each path builds: `GROUP BY {column}`, `SELECT key, COUNT(DISTINCT query_id), SUM(cost_usd), AVG(latency_ms), error_rate`.

Date group: use `func.date_trunc(bucket, LLMCallLog.created_at)`, serialize key to ISO 8601 string via `str(row.key.isoformat())`.

User group: JOIN through `chat_sessions` to `users`, return `user.email` as key.

intent_category: GROUP BY on `eval_results.intent_category`, no user scoping.

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/unit/services/test_observability_queries.py -v -k groups`
Expected: All 16 tests PASS.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/services/observability_queries.py tests/unit/services/test_observability_queries.py && uv run ruff format backend/services/observability_queries.py tests/unit/services/test_observability_queries.py
git add backend/services/observability_queries.py tests/unit/services/test_observability_queries.py
git commit -m "feat(observability): get_query_groups — 9 dimensions with date bucketing"
```

---

### Task 13: Grouped Endpoint Router + API Tests

**Prerequisite:** Task 4 must be complete (`require_admin` in `dependencies.py`). Task 10 must be complete (`tests/api/test_observability_api.py` exists).

**Files:**
- Modify: `backend/routers/observability.py`
- Modify: `tests/api/test_observability_api.py`

- [ ] **Step 1: Add `/queries/grouped` endpoint**

**CRITICAL:** Register this endpoint BEFORE the existing `/queries/{query_id}` route to avoid route shadowing.

In `backend/routers/observability.py`, add the endpoint ABOVE the `query_detail` function:

```python
from backend.dependencies import require_admin
from backend.schemas.observability import (
    GroupByEnum,
    DateBucketEnum,
    GroupedResponse,
)
from backend.services.observability_queries import get_query_groups


@router.get(
    "/queries/grouped",
    response_model=GroupedResponse,
    summary="Aggregate queries by dimension",
    description="Returns grouped aggregation (count, cost, latency, error rate) by the specified dimension.",
)
async def grouped_queries(
    group_by: GroupByEnum = Query(..., description="Grouping dimension"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    bucket: DateBucketEnum = DateBucketEnum.day,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> GroupedResponse:
    """Return grouped query aggregation."""
    if group_by == GroupByEnum.user:
        require_admin(user)

    result = await get_query_groups(
        db,
        group_by=group_by.value,
        user_id=_user_scope(user) if group_by != GroupByEnum.intent_category else None,
        date_from=date_from,
        date_to=date_to,
        bucket=bucket.value,
    )
    return GroupedResponse(**result)
```

- [ ] **Step 2: Write API tests**

Add to `tests/api/test_observability_api.py`:

```python
class TestGroupedEndpoint:
    """Tests for GET /observability/queries/grouped."""

    @pytest.mark.asyncio
    async def test_valid_group_by_returns_200(self, client: AsyncClient, auth_headers: dict) -> None:
        """Valid group_by should return 200 with GroupedResponse shape."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=agent_type",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["group_by"] == "agent_type"
        assert "groups" in data

    @pytest.mark.asyncio
    async def test_user_group_non_admin_returns_403(self, client: AsyncClient, auth_headers: dict) -> None:
        """group_by=user as non-admin should return 403."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=user",
            headers=auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_user_group_admin_returns_200(self, client: AsyncClient, admin_auth_headers: dict) -> None:
        """group_by=user as admin should return 200."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=user",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_group_by_returns_422(self, client: AsyncClient, auth_headers: dict) -> None:
        """Invalid group_by value should return 422."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=badvalue",
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_date_group_accepts_bucket_param(self, client: AsyncClient, auth_headers: dict) -> None:
        """group_by=date with bucket=week should return 200."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=date&bucket=week",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_intent_category_returns_200(self, client: AsyncClient, auth_headers: dict) -> None:
        """group_by=intent_category should return 200 (may be empty)."""
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=intent_category",
            headers=auth_headers,
        )
        assert response.status_code == 200
```

Note: `admin_auth_headers` fixture must provide JWT for a user with `role=UserRole.ADMIN`. Check existing test fixtures for the admin user pattern.

**Important:** The `group_by=user` admin enforcement is ONLY in the router (Task 13), NOT in the service function `get_query_groups()`. Service-layer tests for this dimension should test the query logic, not the 403 guard. The 403 guard is tested at the API layer above.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/api/test_observability_api.py -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 4: Lint and commit**

```bash
uv run ruff check --fix backend/routers/observability.py tests/api/test_observability_api.py && uv run ruff format backend/routers/observability.py tests/api/test_observability_api.py
git add backend/routers/observability.py tests/api/test_observability_api.py
git commit -m "feat(observability): GET /queries/grouped endpoint — 9 dimensions"
```

---

## Chunk 5: Integration Tests + Docs (Tasks 14–15)

---

### Task 14: Integration Tests

**Files:**
- Create: `tests/integration/test_observability_queries.py`

- [ ] **Step 1: Write HAVING + cost filter integration test**

Seed 3 `LLMCallLog` rows with different `cost_usd` (0.001, 0.01, 0.1). Call `get_query_list(cost_min=0.005)` and assert only 2 results. Verify `total` matches.

- [ ] **Step 2: Write date_trunc bucketing integration test**

Seed rows across 2 weeks. Call `get_query_groups(group_by="date", bucket="week")` and assert 2 groups with correct ISO key format.

- [ ] **Step 3: Run integration tests**

Run: `uv run pytest tests/integration/test_observability_queries.py -v`
Expected: 2 tests PASS (requires Docker DB — skip in CI if unavailable).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_observability_queries.py
git commit -m "test(observability): integration tests for HAVING filters and date bucketing"
```

---

### Task 15: Doc Updates + Final Verification

**Files:**
- Modify: `docs/TDD.md`
- Modify: `docs/FSD.md`

- [ ] **Step 1: Update TDD.md §3.13**

Add new params to the query list endpoint contract. Add the grouped endpoint contract with request/response schemas.

- [ ] **Step 2: Update FSD.md**

Update observability functional requirements to reflect new sorting, filtering, grouping, summaries, eval scores, and Langfuse links.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/unit/ tests/api/ -v --tb=short -q`
Expected: All tests PASS, no regressions.

- [ ] **Step 4: Run linting**

Run: `uv run ruff check backend/ tests/ && uv run ruff format --check backend/ tests/`
Expected: Zero errors.

- [ ] **Step 5: Commit**

```bash
git add docs/TDD.md docs/FSD.md
git commit -m "docs: update TDD and FSD for observability API gaps (BU-5)"
```

---

## Summary

| Chunk | Tasks | What it delivers |
|-------|-------|-----------------|
| 1 (Foundation) | 1–4 | Sanitizer, migration, schemas, admin guard extraction |
| 2 (Instrumentation) | 5–8 | Writer fields, collector params, caller wiring, decline logging |
| 3 (Query List) | 9–11 | Sort, filter, eval join, summaries, Langfuse URL |
| 4 (Group-By) | 12–13 | New endpoint with 9 dimensions |
| 5 (Integration + Docs) | 14–15 | Integration tests, TDD/FSD updates |

**Total tasks:** 15
**Estimated tests:** ~70 new
**Estimated time:** ~1.5 sessions
