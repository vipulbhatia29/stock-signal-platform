# Phase 6A — LLM Factory & Cascade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-model LLM providers with a data-driven, multi-model cascade that proactively avoids rate limits and silently falls between models on failure.

**Architecture:** `llm_model_config` DB table drives cascade order per tier (planner/synthesizer). `GroqProvider` iterates its models internally, falling to `AnthropicProvider` then `OpenAIProvider` via `LLMClient`. `TokenBudget` sliding windows prevent 429s. V1 ReAct graph is deleted.

**Tech Stack:** SQLAlchemy 2.0 async, Alembic, asyncio.Lock, Pydantic v2, FastAPI, pytest

**Spec:** `docs/superpowers/specs/2026-03-25-llm-factory-cascade-design.md`

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| Create | `backend/models/llm_config.py` | SQLAlchemy model for `llm_model_config` table |
| Create | `backend/schemas/llm_config.py` | Pydantic request/response schemas for admin API |
| Create | `backend/agents/model_config.py` | `ModelConfig` dataclass + `ModelConfigLoader` (reads DB, caches) |
| Create | `backend/agents/token_budget.py` | Async sliding-window rate tracker |
| Create | `backend/routers/admin.py` | Admin endpoints (model CRUD, reload) |
| Create | `backend/migrations/versions/xxx_012_llm_model_config.py` | Alembic migration + seed data |
| Create | `tests/unit/agents/test_token_budget.py` | TokenBudget unit tests |
| Create | `tests/unit/providers/test_groq_cascade.py` | GroqProvider cascade unit tests |
| Create | `tests/unit/agents/test_llm_client_tiers.py` | LLMClient tier routing tests |
| Create | `tests/api/test_admin_llm.py` | Admin endpoint tests |
| Modify | `backend/config.py` | Remove `AGENT_V2`, add `GROQ_MODEL_TIERS`, `MAX_TOOL_RESULT_CHARS` |
| Modify | `backend/agents/llm_client.py` | Fix `ProviderHealth.mark_exhausted()` bug, add `AllModelsExhaustedError` |
| Modify | `backend/agents/providers/groq.py` | Multi-model cascade with budget + error handling |
| Modify | `backend/agents/graph.py` | Tool result truncation in `synthesize_node`, update docstring |
| Modify | `backend/agents/stream.py` | Delete `stream_graph_events()`, keep `StreamEvent` + `stream_graph_v2_events` |
| Modify | `backend/main.py` | Remove V1 wiring, add model config loader + tier_config |
| Modify | `backend/routers/chat.py` | Remove V1 branch, V2-only |
| Modify | `backend/models/__init__.py` | Export `LLMModelConfig` |
| Delete | `backend/agents/graph.py` | V1 ReAct graph |
| Delete | `tests/unit/agents/test_agent_graph.py` | V1 tests |
| Delete | `tests/unit/test_agent_graph.py` | V1 duplicate tests |

---

## Task 1: V1 Deprecation — Remove Feature Flag & Dead Code

**Files:**
- Modify: `backend/config.py:54`
- Delete: `backend/agents/graph.py`
- Modify: `backend/agents/stream.py`
- Modify: `backend/main.py:89-160`
- Modify: `backend/routers/chat.py:112-180`
- Modify: `backend/agents/graph.py:1-5` (docstring)
- Delete: `tests/unit/agents/test_agent_graph.py`
- Delete: `tests/unit/test_agent_graph.py`

- [ ] **Step 1: Delete V1 test files**

```bash
git rm tests/unit/agents/test_agent_graph.py tests/unit/test_agent_graph.py
```

- [ ] **Step 2: Remove `AGENT_V2` from Settings**

In `backend/config.py`, delete line 54:
```python
AGENT_V2: bool = False  # Feature flag: Plan→Execute→Synthesize agent
```

- [ ] **Step 3: Delete V1 graph.py**

```bash
git rm backend/agents/graph.py
```

- [ ] **Step 4: Clean stream.py — delete `stream_graph_events`, keep `StreamEvent` and `stream_graph_v2_events`**

In `backend/agents/stream.py`, delete the `stream_graph_events` function (lines 49-95). Keep:
- `StreamEvent` dataclass (line 14)
- `stream_graph_v2_events` function (line 98+)

- [ ] **Step 5: Rename graph_v2.py → graph.py and update docstring**

```bash
git mv backend/agents/graph.py backend/agents/graph.py
```

Update line 3 of the renamed file:
```python
# OLD: Feature-flagged behind AGENT_V2=true. Coexists with the V1 ReAct graph
# NEW: Agent graph: Plan→Execute→Synthesize three-phase LangGraph StateGraph.
```

Update all imports across the codebase:
```bash
# Find and update all references
grep -rn "graph_v2" backend/ tests/ --include="*.py"
```
Change every `from backend.agents.graph import` → `from backend.agents.graph import`.
Key files: `backend/main.py`, `backend/agents/stream.py`, `backend/routers/chat.py`, any test files.

- [ ] **Step 5b: Update .env.example**

Remove `AGENT_V2=` line if present. Add new settings:
```
GROQ_MODEL_TIERS=
MAX_TOOL_RESULT_CHARS=3000
```

- [ ] **Step 6: Rewrite main.py — remove V1 wiring, make V2 unconditional**

In `backend/main.py`:
- Delete lines 89-98 (V1 graph compilation: `build_agent_graph`, `stock_graph`, `general_graph`)
- Remove the `if settings.AGENT_V2 and providers:` conditional (line 114). The V2 block (lines 115-158) becomes unconditional (just `if providers:`).
- Delete the `elif settings.AGENT_V2:` block (lines 159-160).
- Remove imports: `from backend.agents.graph import build_agent_graph`
- Remove imports: `from backend.agents.base import StockAgent, GeneralAgent`

- [ ] **Step 7: Rewrite chat.py — remove V1 branch**

In `backend/routers/chat.py`:
- Delete line 112: `use_v2 = settings.AGENT_V2 and hasattr(request.app.state, "agent_v2_graph")`
- Delete the `if use_v2:` / V1 `else:` branch. Keep only the V2 path (`_event_generator_v2`).
- Delete the V1 `event_generator()` inner function (lines ~120-180).
- Remove import: `from backend.agents.stream import stream_graph_events`
- Remove references to `app.state.stock_graph` and `app.state.general_graph`.

- [ ] **Step 8: Run tests to verify nothing breaks**

```bash
uv run pytest tests/unit/ -v --no-header -q 2>&1 | tail -5
```
Expected: All pass (minus the 2 deleted V1 test files = ~725 pass).

- [ ] **Step 9: Lint**

```bash
uv run ruff check --fix backend/ && uv run ruff format backend/
```

- [ ] **Step 10: Commit**

```bash
git add -A && git commit -m "refactor: remove V1 ReAct graph + AGENT_V2 flag — V2 is now the only path"
```

---

## Task 2: Fix ProviderHealth.mark_exhausted() Bug

**Files:**
- Modify: `backend/agents/llm_client.py:57-62`
- Test: `tests/unit/agents/test_llm_client.py` (existing)

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/agents/test_llm_client.py`:

```python
def test_mark_exhausted_sets_future_time():
    """mark_exhausted with retry_after should set exhausted_until to now + retry_after."""
    health = ProviderHealth(provider="groq")
    health.mark_exhausted(retry_after=60.0)
    assert health.is_exhausted is True
    assert health.exhausted_until is not None
    # Should be in the future, not the past
    assert health.exhausted_until > datetime.now(timezone.utc)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/agents/test_llm_client.py::test_mark_exhausted_sets_future_time -v
```
Expected: FAIL — `exhausted_until` is in the past (current bug).

- [ ] **Step 3: Fix the bug**

In `backend/agents/llm_client.py`, `ProviderHealth.mark_exhausted()`:

```python
# OLD (line 61):
self.exhausted_until = datetime.now(timezone.utc).replace(second=0, microsecond=0)

# NEW:
self.exhausted_until = datetime.now(timezone.utc) + timedelta(seconds=retry_after)
```

Add `from datetime import timedelta` to imports if not present.

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/agents/test_llm_client.py::test_mark_exhausted_sets_future_time -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/llm_client.py tests/unit/agents/test_llm_client.py
git commit -m "fix: ProviderHealth.mark_exhausted() — set exhausted_until to future, not now"
```

---

## Task 3: Token Budget Module

**Files:**
- Create: `backend/agents/token_budget.py`
- Create: `tests/unit/agents/test_token_budget.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/agents/test_token_budget.py`:

```python
"""Tests for the async sliding-window token budget tracker."""

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.agents.token_budget import TokenBudget, ModelLimits


@pytest.fixture
def budget():
    limits = {
        "model-a": ModelLimits(tpm=1000, rpm=10, tpd=10000, rpd=100),
        "model-b": ModelLimits(tpm=500, rpm=5, tpd=5000, rpd=50),
    }
    return TokenBudget(limits=limits)


class TestEstimateTokens:
    def test_basic_estimate(self):
        est = TokenBudget.estimate_tokens([{"content": "a" * 400}])
        # 400 chars // 4 = 100 tokens * 1.2 margin = 120
        assert est == 120

    def test_empty_messages(self):
        est = TokenBudget.estimate_tokens([])
        assert est == 0


class TestCanAfford:
    @pytest.mark.asyncio
    async def test_under_threshold_returns_true(self, budget):
        assert await budget.can_afford("model-a", 100) is True

    @pytest.mark.asyncio
    async def test_at_80pct_threshold_returns_false(self, budget):
        # Record enough to hit 80% of TPM (1000 * 0.8 = 800)
        await budget.record("model-a", 750)
        # 750 + 100 = 850 > 800 threshold
        assert await budget.can_afford("model-a", 100) is False

    @pytest.mark.asyncio
    async def test_unknown_model_allowed(self, budget):
        assert await budget.can_afford("unknown-model", 9999) is True

    @pytest.mark.asyncio
    async def test_rpm_limit_enforced(self, budget):
        # Record 8 requests (80% of rpm=10 → threshold at 8)
        for _ in range(8):
            await budget.record("model-a", 1)
        assert await budget.can_afford("model-a", 1) is False


class TestRecord:
    @pytest.mark.asyncio
    async def test_record_updates_window(self, budget):
        await budget.record("model-a", 500)
        # Now 500/1000 TPM used — 500 + 400 = 900 > 800 threshold
        assert await budget.can_afford("model-a", 400) is False
        # But 500 + 200 = 700 < 800 threshold
        assert await budget.can_afford("model-a", 200) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/agents/test_token_budget.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.agents.token_budget'`

- [ ] **Step 3: Implement TokenBudget**

Create `backend/agents/token_budget.py`:

```python
"""Async sliding-window token and request budget tracker.

Tracks tokens-per-minute (TPM), requests-per-minute (RPM),
tokens-per-day (TPD), and requests-per-day (RPD) per model.
Uses asyncio.Lock for async safety.

Usage:
    budget = TokenBudget(limits={"model": ModelLimits(...)})
    if await budget.can_afford("model", estimated_tokens):
        response = await provider.chat(...)
        await budget.record("model", actual_tokens)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MINUTE = 60
_DAY = 86_400
_THRESHOLD = 0.80


@dataclass(frozen=True)
class ModelLimits:
    """Rate limits for a single model."""

    tpm: int
    rpm: int
    tpd: int
    rpd: int


@dataclass
class _ModelState:
    """Per-model sliding-window state."""

    minute_tokens: deque = field(default_factory=deque)
    minute_tokens_total: int = 0
    minute_requests: deque = field(default_factory=deque)
    minute_requests_total: int = 0
    day_tokens: deque = field(default_factory=deque)
    day_tokens_total: int = 0
    day_requests: deque = field(default_factory=deque)
    day_requests_total: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TokenBudget:
    """Async sliding-window rate tracker for multiple models."""

    def __init__(self, limits: dict[str, ModelLimits] | None = None) -> None:
        self._limits: dict[str, ModelLimits] = dict(limits or {})
        self._state: dict[str, _ModelState] = {
            model: _ModelState() for model in self._limits
        }

    def load_limits(self, models: list[Any]) -> None:
        """Populate limits from ModelConfig list."""
        for m in models:
            if m.tpm_limit is not None:
                self._limits[m.model_name] = ModelLimits(
                    tpm=m.tpm_limit,
                    rpm=m.rpm_limit or 30,
                    tpd=m.tpd_limit or 100_000,
                    rpd=m.rpd_limit or 1_000,
                )

    @staticmethod
    def estimate_tokens(messages: list[dict[str, Any] | Any]) -> int:
        """Estimate token count. Heuristic: len(text) // 4 * 1.2."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if isinstance(content, str):
                total_chars += len(content)
        raw = total_chars // 4
        return int(raw * 1.20)

    async def can_afford(self, model: str, estimated_tokens: int) -> bool:
        """Check whether model has budget. Uses 80% threshold."""
        lim = self._limits.get(model)
        if lim is None:
            return True

        state = self._get_state(model)
        async with state.lock:
            now = time.monotonic()
            tpm_used = self._prune_window(state.minute_tokens, _MINUTE, now)
            state.minute_tokens_total = tpm_used
            rpm_used = self._prune_window(state.minute_requests, _MINUTE, now)
            state.minute_requests_total = rpm_used
            tpd_used = self._prune_window(state.day_tokens, _DAY, now)
            state.day_tokens_total = tpd_used
            rpd_used = self._prune_window(state.day_requests, _DAY, now)
            state.day_requests_total = rpd_used

            # Threshold checks inside the lock to prevent stale reads
            if tpm_used + estimated_tokens > lim.tpm * _THRESHOLD:
                return False
            if rpm_used + 1 > lim.rpm * _THRESHOLD:
                return False
            if tpd_used + estimated_tokens > lim.tpd * _THRESHOLD:
                return False
            if rpd_used + 1 > lim.rpd * _THRESHOLD:
                return False
            return True

    async def record(self, model: str, tokens_used: int) -> None:
        """Record a completed request."""
        state = self._get_state(model)
        now = time.monotonic()
        async with state.lock:
            state.minute_tokens.append((now, tokens_used))
            state.minute_tokens_total += tokens_used
            state.minute_requests.append((now, 1))
            state.minute_requests_total += 1
            state.day_tokens.append((now, tokens_used))
            state.day_tokens_total += tokens_used
            state.day_requests.append((now, 1))
            state.day_requests_total += 1

    def _get_state(self, model: str) -> _ModelState:
        if model not in self._state:
            self._state[model] = _ModelState()
        return self._state[model]

    @staticmethod
    def _prune_window(log: deque, window_seconds: int, now: float) -> int:
        """Prune expired entries and return running total."""
        cutoff = now - window_seconds
        total = sum(count for _, count in log)
        while log and log[0][0] < cutoff:
            _, count = log.popleft()
            total -= count
        return total
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/unit/agents/test_token_budget.py -v
```
Expected: All pass

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/agents/token_budget.py tests/unit/agents/test_token_budget.py
uv run ruff format backend/agents/token_budget.py tests/unit/agents/test_token_budget.py
git add backend/agents/token_budget.py tests/unit/agents/test_token_budget.py
git commit -m "feat: add async TokenBudget — sliding-window rate tracker per model"
```

---

## Task 4: LLM Model Config — DB Model, Schema, Migration

**Files:**
- Create: `backend/models/llm_config.py`
- Create: `backend/schemas/llm_config.py`
- Create: `backend/agents/model_config.py`
- Create: `backend/migrations/versions/xxx_012_llm_model_config.py`
- Modify: `backend/models/__init__.py`

- [ ] **Step 1: Create SQLAlchemy model**

Create `backend/models/llm_config.py`:

```python
"""LLM model cascade configuration."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class LLMModelConfig(Base):
    """Configurable LLM model cascade — one row per model per tier."""

    __tablename__ = "llm_model_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpm_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rpd_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_per_1k_input: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    cost_per_1k_output: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

- [ ] **Step 2: Create Pydantic schemas**

Create `backend/schemas/llm_config.py`:

```python
"""Request/response schemas for LLM model config admin API."""

from pydantic import BaseModel


class LLMModelConfigResponse(BaseModel):
    id: int
    provider: str
    model_name: str
    tier: str
    priority: int
    is_enabled: bool
    tpm_limit: int | None
    rpm_limit: int | None
    tpd_limit: int | None
    rpd_limit: int | None
    cost_per_1k_input: float
    cost_per_1k_output: float
    notes: str | None

    model_config = {"from_attributes": True}


class LLMModelConfigUpdate(BaseModel):
    priority: int | None = None
    is_enabled: bool | None = None
    tpm_limit: int | None = None
    rpm_limit: int | None = None
    tpd_limit: int | None = None
    rpd_limit: int | None = None
    cost_per_1k_input: float | None = None
    cost_per_1k_output: float | None = None
    notes: str | None = None
```

- [ ] **Step 3: Create ModelConfig dataclass + loader**

Create `backend/agents/model_config.py`:

```python
"""Data-driven model cascade configuration loader."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelConfig:
    """Single model configuration from llm_model_config table."""

    id: int
    provider: str
    model_name: str
    tier: str
    priority: int
    is_enabled: bool
    tpm_limit: int | None
    rpm_limit: int | None
    tpd_limit: int | None
    rpd_limit: int | None
    cost_per_1k_input: float
    cost_per_1k_output: float


class ModelConfigLoader:
    """Reads llm_model_config from DB, caches in memory."""

    def __init__(self) -> None:
        self._cache: dict[str, list[ModelConfig]] = {}

    async def load(self, session: AsyncSession) -> dict[str, list[ModelConfig]]:
        """Load enabled models grouped by tier, ordered by priority."""
        from backend.models.llm_config import LLMModelConfig

        result = await session.execute(
            select(LLMModelConfig)
            .where(LLMModelConfig.is_enabled.is_(True))
            .order_by(LLMModelConfig.tier, LLMModelConfig.priority)
        )
        rows = result.scalars().all()

        grouped: dict[str, list[ModelConfig]] = {}
        for row in rows:
            mc = ModelConfig(
                id=row.id,
                provider=row.provider,
                model_name=row.model_name,
                tier=row.tier,
                priority=row.priority,
                is_enabled=row.is_enabled,
                tpm_limit=row.tpm_limit,
                rpm_limit=row.rpm_limit,
                tpd_limit=row.tpd_limit,
                rpd_limit=row.rpd_limit,
                cost_per_1k_input=float(row.cost_per_1k_input or 0),
                cost_per_1k_output=float(row.cost_per_1k_output or 0),
            )
            grouped.setdefault(mc.tier, []).append(mc)

        self._cache = grouped
        logger.info("Loaded %d model configs across %d tiers", len(rows), len(grouped))
        return grouped

    async def reload(self, session: AsyncSession) -> dict[str, list[ModelConfig]]:
        """Force re-read from DB. Called by admin reload endpoint."""
        logger.info("Reloading model config from DB")
        return await self.load(session)

    @property
    def cached(self) -> dict[str, list[ModelConfig]]:
        return self._cache
```

- [ ] **Step 4: Export model in `__init__.py`**

In `backend/models/__init__.py`, add:
```python
from backend.models.llm_config import LLMModelConfig
```
And add `"LLMModelConfig"` to `__all__`.

- [ ] **Step 5: Write Alembic migration MANUALLY**

**CRITICAL: Do NOT use `alembic revision --autogenerate`** — it rewrites the entire schema. Write manually.

First verify: `uv run alembic heads` → should be `d68e82e90c96`.
Then check Docker: `docker ps | grep 5433` → only `ssp-postgres`.

```bash
uv run alembic revision -m "012_llm_model_config"
```

Edit the generated file:

```python
"""012_llm_model_config

Create llm_model_config table for data-driven LLM cascade.
"""

from alembic import op
import sqlalchemy as sa

revision = "<generated>"
down_revision = "d68e82e90c96"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_model_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("tpm_limit", sa.Integer(), nullable=True),
        sa.Column("rpm_limit", sa.Integer(), nullable=True),
        sa.Column("tpd_limit", sa.Integer(), nullable=True),
        sa.Column("rpd_limit", sa.Integer(), nullable=True),
        sa.Column("cost_per_1k_input", sa.Numeric(10, 6), server_default="0"),
        sa.Column("cost_per_1k_output", sa.Numeric(10, 6), server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_name", "tier", name="uq_provider_model_tier"),
    )

    # Seed: Planner tier
    op.execute("""
        INSERT INTO llm_model_config (provider, model_name, tier, priority, tpm_limit, rpm_limit, tpd_limit, rpd_limit, notes)
        VALUES
        ('groq', 'llama-3.3-70b-versatile', 'planner', 1, 12000, 30, 100000, 1000, 'Best tool-calling, strong JSON'),
        ('groq', 'moonshotai/kimi-k2-instruct', 'planner', 2, 10000, 60, 300000, 1000, 'Good reasoning for complex plans'),
        ('groq', 'meta-llama/llama-4-scout-17b-16e-instruct', 'planner', 3, 30000, 30, 500000, 1000, 'Fast, generous TPM fallback'),
        ('anthropic', 'claude-sonnet-4-6', 'planner', 4, NULL, NULL, NULL, NULL, 'Paid fallback'),
        ('openai', 'gpt-4o', 'planner', 5, NULL, NULL, NULL, NULL, 'Last-resort fallback')
    """)

    # Seed: Synthesizer tier
    op.execute("""
        INSERT INTO llm_model_config (provider, model_name, tier, priority, tpm_limit, rpm_limit, tpd_limit, rpd_limit, notes)
        VALUES
        ('groq', 'openai/gpt-oss-120b', 'synthesizer', 1, 8000, 30, 200000, 1000, 'Highest quality free model'),
        ('groq', 'moonshotai/kimi-k2-instruct', 'synthesizer', 2, 10000, 60, 300000, 1000, 'Strong reasoning fallback'),
        ('anthropic', 'claude-sonnet-4-6', 'synthesizer', 3, NULL, NULL, NULL, NULL, 'Quality guarantee'),
        ('openai', 'gpt-4o', 'synthesizer', 4, NULL, NULL, NULL, NULL, 'Last-resort fallback')
    """)


def downgrade() -> None:
    op.drop_table("llm_model_config")
```

- [ ] **Step 6: Run migration**

```bash
docker ps | grep 5433  # verify only ssp-postgres
uv run alembic upgrade head
```

- [ ] **Step 7: Verify**

```bash
uv run python -c "
import asyncio
from backend.database import async_session_factory
from sqlalchemy import text
async def check():
    async with async_session_factory() as s:
        r = await s.execute(text('SELECT count(*) FROM llm_model_config'))
        print(f'Seed rows: {r.scalar()}')
        r = await s.execute(text('SELECT provider, model_name, tier, priority FROM llm_model_config ORDER BY tier, priority'))
        for row in r.fetchall():
            print(f'  {row}')
asyncio.run(check())
"
```
Expected: 9 seed rows (5 planner + 4 synthesizer).

- [ ] **Step 8: Commit**

```bash
git add backend/models/llm_config.py backend/schemas/llm_config.py backend/agents/model_config.py backend/models/__init__.py backend/migrations/versions/
git commit -m "feat: add llm_model_config table — data-driven cascade configuration"
```

---

## Task 5: GroqProvider Multi-Model Cascade

**Files:**
- Modify: `backend/agents/providers/groq.py`
- Modify: `backend/agents/llm_client.py` (add `AllModelsExhaustedError`)
- Create: `tests/unit/providers/__init__.py`
- Create: `tests/unit/providers/test_groq_cascade.py`

- [ ] **Step 1: Add `AllModelsExhaustedError` to llm_client.py**

In `backend/agents/llm_client.py`, after `MaxRetriesExceeded`:

```python
class AllModelsExhaustedError(Exception):
    """All models within a provider's cascade have been exhausted."""
    pass
```

- [ ] **Step 2: Write failing tests for cascade**

Create `tests/unit/providers/__init__.py` (empty).

Create `tests/unit/providers/test_groq_cascade.py`:

```python
"""Tests for GroqProvider multi-model cascade."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agents.llm_client import AllModelsExhaustedError, LLMResponse
from backend.agents.providers.groq import GroqProvider
from backend.agents.token_budget import ModelLimits, TokenBudget


@pytest.fixture
def budget():
    return TokenBudget(limits={
        "model-1": ModelLimits(tpm=10000, rpm=30, tpd=100000, rpd=1000),
        "model-2": ModelLimits(tpm=5000, rpm=30, tpd=50000, rpd=1000),
    })


@pytest.fixture
def provider(budget):
    return GroqProvider(
        api_key="test-key",
        models=["model-1", "model-2"],
        token_budget=budget,
    )


class TestGroqCascade:
    @pytest.mark.asyncio
    async def test_first_model_succeeds(self, provider):
        with patch.object(provider, "_call_model", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = LLMResponse(content="ok", tool_calls=[], model="model-1", prompt_tokens=10, completion_tokens=5)
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "model-1"

    @pytest.mark.asyncio
    async def test_cascade_on_api_error(self, provider):
        """First model fails with APIError, second succeeds."""
        call_count = 0
        async def mock_call(model, messages, tools, stream):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Failed to call a function")
            return LLMResponse(content="ok", tool_calls=[], model=model, prompt_tokens=10, completion_tokens=5)

        with patch.object(provider, "_call_model", side_effect=mock_call):
            result = await provider.chat([{"role": "user", "content": "hi"}], [])
            assert result.model == "model-2"

    @pytest.mark.asyncio
    async def test_all_models_exhausted(self, provider):
        """All models fail → AllModelsExhaustedError."""
        with patch.object(provider, "_call_model", new_callable=AsyncMock, side_effect=Exception("fail")):
            with pytest.raises(AllModelsExhaustedError):
                await provider.chat([{"role": "user", "content": "hi"}], [])
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/unit/providers/test_groq_cascade.py -v
```
Expected: FAIL — GroqProvider doesn't accept `models` or `token_budget` yet.

- [ ] **Step 4: Rewrite GroqProvider for multi-model cascade**

Replace `backend/agents/providers/groq.py` entirely. The new implementation:
- Accepts `models: list[str]` and `token_budget: TokenBudget`
- Iterates models in order, checking budget before each
- Catches Groq-specific errors (`APIError`, `APIStatusError`, `APIConnectionError`) and cascades
- Raises `AllModelsExhaustedError` when all models fail

```python
"""Groq LLM provider — multi-model cascade with budget-aware routing."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.agents.llm_client import (
    AllModelsExhaustedError,
    LLMProvider,
    LLMResponse,
    ProviderHealth,
)
from backend.agents.token_budget import TokenBudget

logger = logging.getLogger(__name__)

# Groq error imports — optional, fail gracefully if not installed
try:
    from groq import APIConnectionError as GroqConnectionError
    from groq import APIError as GroqAPIError
    from groq import APIStatusError as GroqStatusError

    _GROQ_ERRORS = (GroqAPIError, GroqStatusError, GroqConnectionError)
except ImportError:
    _GROQ_ERRORS = ()


class GroqProvider(LLMProvider):
    """Groq provider with internal multi-model cascade."""

    def __init__(
        self,
        api_key: str,
        models: list[str] | None = None,
        token_budget: TokenBudget | None = None,
    ) -> None:
        self._api_key = api_key
        self._models = models or ["llama-3.3-70b-versatile"]
        self._token_budget = token_budget
        self.health = ProviderHealth(provider="groq")
        self._chat_models: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "groq"

    def get_chat_model(self) -> Any:
        """Return LangChain ChatGroq for the first model (LangGraph compat)."""
        model = self._models[0]
        if model not in self._chat_models:
            from langchain_groq import ChatGroq
            self._chat_models[model] = ChatGroq(api_key=self._api_key, model=model)
        return self._chat_models[model]

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool = False,
    ) -> LLMResponse:
        """Try each model in cascade order. Raise AllModelsExhaustedError if all fail."""
        est_tokens = TokenBudget.estimate_tokens(messages) if self._token_budget else 0
        errors: list[tuple[str, Exception]] = []

        for model in self._models:
            # Check budget
            if self._token_budget and not await self._token_budget.can_afford(model, est_tokens):
                logger.info("Groq cascade skip %s: budget exhausted", model)
                errors.append((model, Exception("budget_exhausted")))
                continue

            try:
                response = await self._call_model(model, messages, tools, stream)
                # Record actual usage
                if self._token_budget:
                    actual = (response.prompt_tokens or 0) + (response.completion_tokens or 0)
                    await self._token_budget.record(model, actual)
                return response
            except Exception as exc:
                # Classify the error for observability
                reason = "unknown_error"
                if _GROQ_ERRORS and isinstance(exc, _GROQ_ERRORS):
                    err_str = str(exc)
                    if "Failed to call a function" in err_str:
                        reason = "tool_call_failure"
                    elif hasattr(exc, "status_code") and getattr(exc, "status_code", 0) >= 500:
                        reason = "server_error"
                    elif isinstance(exc, _GROQ_ERRORS[-1]):  # APIConnectionError
                        reason = "connection_error"
                    else:
                        reason = "api_error"
                elif isinstance(exc, asyncio.TimeoutError):
                    reason = "timeout"
                logger.warning("Groq %s failed (%s): %s — cascading", model, reason, exc)
                errors.append((model, exc))
                continue

        raise AllModelsExhaustedError(
            f"All {len(self._models)} Groq models exhausted: "
            + ", ".join(f"{m}: {e}" for m, e in errors)
        )

    def _get_client(self) -> Any:
        """Return cached AsyncGroq client (one per provider, not per call)."""
        if not hasattr(self, "_client"):
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self._api_key)
        return self._client

    async def _call_model(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        stream: bool,
    ) -> LLMResponse:
        """Call a single Groq model."""
        client = self._get_client()
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools if tools else None,
                stream=False,
            ),
            timeout=30.0,
        )
        choice = response.choices[0]
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls,
            model=model,
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
        )
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/providers/test_groq_cascade.py -v
```
Expected: All pass.

- [ ] **Step 6: Run full unit suite for regressions**

```bash
uv run pytest tests/unit/ -q --no-header 2>&1 | tail -5
```

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check --fix backend/agents/providers/groq.py && uv run ruff format backend/agents/providers/groq.py
git add backend/agents/providers/groq.py backend/agents/llm_client.py tests/unit/providers/
git commit -m "feat: GroqProvider multi-model cascade with budget-aware routing"
```

---

## Task 6: Admin Router — Model Config CRUD + Reload

**Files:**
- Create: `backend/routers/admin.py`
- Modify: `backend/main.py` (mount admin router)
- Create: `tests/api/test_admin_llm.py`

- [ ] **Step 1: Create admin router**

Create `backend/routers/admin.py`:

```python
"""Admin endpoints for LLM model configuration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.llm_config import LLMModelConfig
from backend.models.user import User, UserRole
from backend.schemas.llm_config import LLMModelConfigResponse, LLMModelConfigUpdate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin role (uses UserRole enum, not string comparison)."""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/llm-models", response_model=list[LLMModelConfigResponse])
async def list_models(
    _user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> list[LLMModelConfigResponse]:
    """List all LLM model configurations."""
    result = await db.execute(
        select(LLMModelConfig).order_by(LLMModelConfig.tier, LLMModelConfig.priority)
    )
    return [LLMModelConfigResponse.model_validate(r) for r in result.scalars().all()]


@router.patch("/llm-models/{model_id}", response_model=LLMModelConfigResponse)
async def update_model(
    model_id: int,
    body: LLMModelConfigUpdate,
    _user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> LLMModelConfigResponse:
    """Update a model configuration."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update")

    result = await db.execute(
        select(LLMModelConfig).where(LLMModelConfig.id == model_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    for key, value in updates.items():
        setattr(model, key, value)
    await db.commit()
    await db.refresh(model)
    return LLMModelConfigResponse.model_validate(model)


@router.post("/llm-models/reload", status_code=200)
async def reload_models(
    request: Request,
    _user: User = Depends(_require_admin),
    db: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    """Force reload cascade config from DB and rebuild providers."""
    loader = request.app.state.model_config_loader
    new_configs = await loader.reload(db)

    # Rebuild token budget limits
    token_budget = request.app.state.token_budget
    all_models = [m for tier_models in new_configs.values() for m in tier_models]
    token_budget.load_limits(all_models)

    # Note: Provider instances are NOT rebuilt here — that requires
    # restart. This reloads configs and budget limits only.
    # Full provider rebuild on reload is a future enhancement.
    logger.info("Model config reloaded: %d models across %d tiers",
                sum(len(v) for v in new_configs.values()), len(new_configs))
    return {"status": "reloaded", "tiers": len(new_configs)}
```

- [ ] **Step 2: Mount admin router in main.py**

Add to `backend/main.py` router mounting section:
```python
from backend.routers.admin import router as admin_router
app.include_router(admin_router, prefix="/api/v1")
```

- [ ] **Step 3: Write admin API tests**

Create `tests/api/test_admin_llm.py` with tests for list, update, and auth enforcement. (Follow existing `tests/api/` patterns with testcontainers.)

- [ ] **Step 4: Run tests, lint, commit**

```bash
uv run pytest tests/api/test_admin_llm.py -v
uv run ruff check --fix backend/routers/admin.py && uv run ruff format backend/routers/admin.py
git add backend/routers/admin.py tests/api/test_admin_llm.py backend/main.py
git commit -m "feat: admin API for LLM model config CRUD + reload"
```

---

## Task 7: Wire Tier Config in main.py

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/config.py` (add `GROQ_MODEL_TIERS`, `MAX_TOOL_RESULT_CHARS`)

- [ ] **Step 1: Add new settings**

In `backend/config.py`, add after `MCP_TOOLS`:
```python
GROQ_MODEL_TIERS: str = ""  # Fallback CSV if llm_model_config table is empty
MAX_TOOL_RESULT_CHARS: int = 3000  # Per tool result, for synthesizer
```

- [ ] **Step 2: Rewrite main.py LLM wiring**

Replace the current provider setup (lines 81-87) and V2 graph setup (lines 113-158) with:

```python
# 3. Load model cascade config from DB
from backend.agents.model_config import ModelConfigLoader
from backend.agents.token_budget import TokenBudget

config_loader = ModelConfigLoader()
async with async_session_factory() as session:
    model_configs = await config_loader.load(session)

if not model_configs:
    logger.warning("llm_model_config table empty — falling back to env vars")
    # Fallback to env var or defaults
    # ... (create single-model providers like before)

# Build token budget from loaded configs
token_budget = TokenBudget()
all_models = [m for tier_models in model_configs.values() for m in tier_models]
token_budget.load_limits(all_models)

# Build providers per tier
from itertools import groupby

PROVIDER_MAP = {
    "groq": (GroqProvider, "GROQ_API_KEY"),
    "anthropic": (AnthropicProvider, "ANTHROPIC_API_KEY"),
    "openai": (OpenAIProvider, "OPENAI_API_KEY"),
}

def build_providers_for_tier(models):
    providers = []
    # Sort by provider before groupby — groupby only groups consecutive keys
    sorted_models = sorted(models, key=lambda m: m.provider)
    for provider_name, group in groupby(sorted_models, key=lambda m: m.provider):
        group_list = list(group)
        cls, env_key = PROVIDER_MAP[provider_name]
        api_key = getattr(settings, env_key, "")
        if not api_key:
            logger.warning("Skipping %s — %s not set", provider_name, env_key)
            continue
        if provider_name == "groq":
            providers.append(cls(
                api_key=api_key,
                models=[m.model_name for m in group_list],
                token_budget=token_budget,
            ))
        else:
            providers.append(cls(api_key=api_key, model=group_list[0].model_name))
    return providers

planner_providers = build_providers_for_tier(model_configs.get("planner", []))
synth_providers = build_providers_for_tier(model_configs.get("synthesizer", []))

llm_client = LLMClient(
    providers=planner_providers,
    tier_config={
        "planner": planner_providers,
        "synthesizer": synth_providers,
    },
)

app.state.model_config_loader = config_loader
app.state.token_budget = token_budget
```

- [ ] **Step 3: Add `llm_model_config` to critical tables validation**

```python
_CRITICAL_TABLES = ["users", "stocks", "stock_prices", "signal_snapshots", "llm_model_config"]
```

- [ ] **Step 4: Test the full startup**

```bash
uv run uvicorn backend.main:app --port 8181 &
sleep 5
curl -s http://localhost:8181/api/v1/health | python -m json.tool
kill %1
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/unit/ -q --no-header 2>&1 | tail -5
```

- [ ] **Step 6: Lint and commit**

```bash
uv run ruff check --fix backend/ && uv run ruff format backend/
git add backend/config.py backend/main.py
git commit -m "feat: wire tier_config — planner and synthesizer get separate model cascades"
```

---

## Task 8: Tool Result Truncation

**Files:**
- Modify: `backend/agents/graph.py`
- Create: `tests/unit/agents/test_truncation.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/agents/test_truncation.py`:

```python
"""Tests for tool result truncation before synthesis."""

import json
import pytest
from backend.agents.graph import truncate_tool_results


class TestTruncateToolResults:
    def test_small_result_unchanged(self):
        results = [{"tool": "t1", "status": "ok", "data": "short"}]
        truncated = truncate_tool_results(results, max_chars=3000)
        assert truncated == results

    def test_large_text_truncated(self):
        results = [{"tool": "t1", "status": "ok", "data": "x" * 5000}]
        truncated = truncate_tool_results(results, max_chars=100)
        assert len(json.dumps(truncated[0]["data"])) <= 150  # some overhead

    def test_error_result_never_truncated(self):
        data = "x" * 5000
        results = [{"tool": "t1", "status": "error", "data": data}]
        truncated = truncate_tool_results(results, max_chars=100)
        assert truncated[0]["data"] == data

    def test_json_array_truncated(self):
        data = {"items": list(range(100)), "total": 100}
        results = [{"tool": "t1", "status": "ok", "data": data}]
        truncated = truncate_tool_results(results, max_chars=200)
        assert len(truncated[0]["data"]["items"]) <= 10
```

- [ ] **Step 2: Implement truncation function**

Add to `backend/agents/graph.py`:

```python
def truncate_tool_results(
    results: list[dict[str, Any]],
    max_chars: int = 3000,
) -> list[dict[str, Any]]:
    """Truncate tool results for the synthesizer to reduce token usage."""
    import json

    truncated = []
    for r in results:
        if r.get("status") == "error":
            truncated.append(r)
            continue

        data = r.get("data")
        data_str = json.dumps(data) if not isinstance(data, str) else data

        if len(data_str) <= max_chars:
            truncated.append(r)
            continue

        # Truncate
        if isinstance(data, dict):
            # Truncate long arrays within the dict
            new_data = {}
            for k, v in data.items():
                if isinstance(v, list) and len(v) > 5:
                    new_data[k] = v[:5]
                    new_data[f"_{k}_note"] = f"... ({len(v) - 5} more)"
                else:
                    new_data[k] = v
            truncated.append({**r, "data": new_data})
        elif isinstance(data, str):
            truncated.append({
                **r,
                "data": data[:max_chars] + f"... [truncated, {len(data)} chars total]",
            })
        else:
            truncated.append({**r, "data": str(data)[:max_chars]})

    return truncated
```

- [ ] **Step 3: Wire into synthesize_node**

In `graph_v2.py`, `synthesize_node`:

```python
async def synthesize_node(state: AgentStateV2) -> dict:
    """Synthesize phase: produce final analysis from tool results."""
    from backend.config import settings

    # Truncate tool results before synthesis
    raw_results = state.get("tool_results", [])
    truncated = truncate_tool_results(raw_results, max_chars=settings.MAX_TOOL_RESULT_CHARS)

    synthesis = await synthesize_fn(
        tool_results=truncated,
        user_context=state.get("user_context", {}),
    )
    # ... rest unchanged
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/agents/test_truncation.py -v
uv run pytest tests/unit/ -q --no-header 2>&1 | tail -5
```

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check --fix backend/agents/graph.py tests/unit/agents/test_truncation.py
uv run ruff format backend/agents/graph.py tests/unit/agents/test_truncation.py
git add backend/agents/graph.py tests/unit/agents/test_truncation.py
git commit -m "feat: truncate tool results before synthesis — configurable per-result cap"
```

---

## Task 9: LLM Client Tier Routing Tests

**Files:**
- Create: `tests/unit/agents/test_llm_client_tiers.py`

- [ ] **Step 1: Write tier routing tests**

```python
"""Tests for LLMClient tier_config routing."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agents.llm_client import LLMClient, LLMResponse, LLMProvider, ProviderHealth


class MockProvider(LLMProvider):
    def __init__(self, provider_name: str):
        self._name = provider_name
        self.health = ProviderHealth(provider=provider_name)

    @property
    def name(self) -> str:
        return self._name

    def get_chat_model(self):
        return MagicMock()

    async def chat(self, messages, tools, stream=False):
        return LLMResponse(content="ok", tool_calls=[], model=self._name, prompt_tokens=10, completion_tokens=5)


class TestTierRouting:
    @pytest.mark.asyncio
    async def test_planner_tier_uses_planner_providers(self):
        planner = MockProvider("planner-groq")
        synth = MockProvider("synth-groq")
        client = LLMClient(
            providers=[planner],
            tier_config={"planner": [planner], "synthesizer": [synth]},
        )
        result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], tier="planner")
        assert result.model == "planner-groq"

    @pytest.mark.asyncio
    async def test_synthesizer_tier_uses_synth_providers(self):
        planner = MockProvider("planner-groq")
        synth = MockProvider("synth-groq")
        client = LLMClient(
            providers=[planner],
            tier_config={"planner": [planner], "synthesizer": [synth]},
        )
        result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], tier="synthesizer")
        assert result.model == "synth-groq"

    @pytest.mark.asyncio
    async def test_no_tier_uses_default(self):
        default = MockProvider("default")
        client = LLMClient(providers=[default])
        result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[])
        assert result.model == "default"

    @pytest.mark.asyncio
    async def test_unknown_tier_uses_default(self):
        default = MockProvider("default")
        client = LLMClient(
            providers=[default],
            tier_config={"planner": [MockProvider("p")]},
        )
        result = await client.chat(messages=[{"role": "user", "content": "hi"}], tools=[], tier="unknown")
        assert result.model == "default"
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/unit/agents/test_llm_client_tiers.py -v
```
Expected: All pass (these test existing `LLMClient.chat()` tier logic which already works).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/agents/test_llm_client_tiers.py
git commit -m "test: add LLMClient tier routing tests — verify planner vs synthesizer dispatch"
```

---

## Task 10: Final Integration — Full Test Suite + Lint

- [ ] **Step 1: Run full unit test suite**

```bash
uv run pytest tests/unit/ -v --no-header -q 2>&1 | tail -10
```
Expected: ~750+ pass, 0 fail.

- [ ] **Step 2: Run API tests**

```bash
uv run pytest tests/api/ -v --no-header -q 2>&1 | tail -10
```

- [ ] **Step 3: Full lint**

```bash
uv run ruff check backend/ tests/ && uv run ruff format --check backend/ tests/
```

- [ ] **Step 4: Start backend and verify manually**

```bash
uv run uvicorn backend.main:app --reload --port 8181
# In another terminal:
curl -s http://localhost:8181/api/v1/health | python -m json.tool
```

- [ ] **Step 5: Final commit if any fixups needed**

```bash
git add -A && git commit -m "chore: Phase 6A final fixups and lint"
```

---

## Summary

| Task | Description | New Tests |
|---|---|---|
| 1 | V1 deprecation — delete graph.py, flag, V1 wiring | 0 (delete ~188 lines) |
| 2 | Fix ProviderHealth.mark_exhausted() bug | 1 |
| 3 | TokenBudget module | ~7 |
| 4 | LLM model config — DB model, schema, migration, loader | 0 (schema/model, tested via API) |
| 5 | GroqProvider multi-model cascade | ~3 |
| 6 | Admin router — CRUD + reload | ~4 |
| 7 | Wire tier_config in main.py | 0 (integration verified manually) |
| 8 | Tool result truncation | ~4 |
| 9 | LLM Client tier routing tests | ~4 |
| 10 | Final integration pass | 0 |
| **Total** | | **~23 new tests** |
