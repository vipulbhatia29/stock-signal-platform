# Phase 4B — AI Chatbot Backend Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a three-layer financial intelligence platform (consume external MCPs → enrich → expose as MCP server) with streaming chat API.

**Architecture:** Tool Registry pattern with pluggable internal tools and external MCP adapters. Provider-agnostic LLM client with fallback chain (Groq → Anthropic → Local). Two-phase agentic loop (tool-calling non-streaming + synthesis streaming). NDJSON streaming chat endpoint. All existing infrastructure reused (TimescaleDB, Redis, Celery).

**Tech Stack:** FastAPI, SQLAlchemy async, Groq/Anthropic/OpenAI SDKs, FastMCP, edgartools, gdeltdoc, mcp SDK, Redis caching, Celery Beat.

**Spec:** `docs/superpowers/specs/2026-03-17-phase-4b-ai-chatbot-design.md`

**JIRA Epic:** KAN-1 | **Stories:** KAN-3 (Tool Orchestration), KAN-4 (Streaming), KAN-5 (Conversation History)

---

## File Structure

### New Files

```
backend/
  agents/
    __init__.py                    # Package init, exports BaseAgent, StockAgent, GeneralAgent
    base.py                        # BaseAgent ABC + ToolFilter dataclass
    stock_agent.py                 # StockAgent (full toolkit)
    general_agent.py               # GeneralAgent (data + news only)
    loop.py                        # agentic_loop() + execute_tool_safely()
    stream.py                      # StreamEvent dataclass + NDJSON serialization
    llm_client.py                  # LLMClient + LLMProvider ABC + RetryPolicy + ProviderHealth
    providers/
      __init__.py                  # Package init
      groq.py                      # GroqProvider(LLMProvider)
      anthropic.py                 # AnthropicProvider(LLMProvider)
      openai.py                    # OpenAIProvider(LLMProvider)
    prompts/
      stock_agent.md               # Few-shot system prompt for StockAgent
      general_agent.md             # Few-shot system prompt for GeneralAgent
  tools/
    registry.py                    # ToolRegistry singleton
    base.py                        # BaseTool ABC, ProxiedTool, CachePolicy, ToolResult, ToolInfo, ToolFilter
    analyze_stock.py               # AnalyzeStockTool(BaseTool)
    portfolio_exposure.py          # PortfolioExposureTool(BaseTool)
    screen_stocks.py               # ScreenStocksTool(BaseTool)
    geopolitical.py                # GeopoliticalEventsTool(BaseTool) — GDELT wrapper
    web_search.py                  # WebSearchTool(BaseTool) — SerpAPI wrapper
    adapters/
      __init__.py                  # Package init
      base.py                      # MCPAdapter ABC
      edgar.py                     # EdgarAdapter(MCPAdapter)
      alpha_vantage.py             # AlphaVantageAdapter(MCPAdapter)
      fred.py                      # FredAdapter(MCPAdapter)
      finnhub.py                   # FinnhubAdapter(MCPAdapter)
  mcp_server/
    __init__.py                    # Package init
    server.py                      # FastMCP server mounted at /mcp
    auth.py                        # JWT auth dependency for MCP connections
  models/
    chat.py                        # ChatSession, ChatMessage SQLAlchemy models
    logs.py                        # LLMCallLog, ToolExecutionLog SQLAlchemy models
  schemas/
    chat.py                        # ChatRequest, ChatSessionResponse, ChatMessageResponse Pydantic schemas
  routers/
    chat.py                        # POST /chat/stream, GET /chat/sessions, etc.
  tasks/
    warm_data.py                   # Celery tasks: sync_analyst_consensus, sync_fred_indicators, etc.
  migrations/versions/
    XXX_008_chat_and_logs.py       # Migration: chat_session, chat_message, llm_call_log, tool_execution_log

tests/
  unit/
    test_tool_registry.py          # ToolRegistry unit tests
    test_tool_base.py              # BaseTool, CachePolicy, ToolResult tests
    test_llm_client.py             # LLMClient + retry + fallback tests
    test_agentic_loop.py           # Agentic loop with mock LLM tests
    test_stream_events.py          # StreamEvent serialization tests
    test_internal_tools.py         # Internal tool execute() tests
    test_mcp_adapters.py           # MCPAdapter mock tests
    test_agents.py                 # Agent prompt loading + tool filter tests
    test_session_management.py     # Session create/resume/expire tests
  api/
    test_chat.py                   # Chat endpoint API tests (auth, stream, sessions)
    test_mcp_server.py             # MCP server endpoint tests
```

### Modified Files

```
backend/config.py                  # Add ALPHA_VANTAGE_API_KEY, FINNHUB_API_KEY
backend/main.py                    # Mount MCP server, register chat router, startup hook for registry
backend/models/__init__.py         # Import new models (chat, logs)
backend/tasks/__init__.py          # Register warm_data tasks
```

---

## Story ↔ Task Mapping

| Story | Plan Tasks | Theme |
|-------|-----------|-------|
| KAN-5: Conversation History | Tasks 1-3 | DB models, schemas, migration |
| KAN-3: Tool Orchestration | Tasks 4-11 | Tool registry, internal tools, MCP adapters, LLM client, agents, loop |
| KAN-4: Streaming Responses | Tasks 12-16 | Stream events, chat router, MCP server, warm pipeline, integration |

---

## Chunk 1: Foundation — Database + Config + Schemas

### Task 1: New Settings Fields + Dependencies

**Files:**
- Modify: `backend/config.py` (add 2 API key fields)
- Modify: `pyproject.toml` (add dependencies)

- [ ] **Step 1: Add API key fields to Settings**

Add after the existing `FRED_API_KEY` field in `backend/config.py`:

```python
ALPHA_VANTAGE_API_KEY: str = ""
FINNHUB_API_KEY: str = ""
```

- [ ] **Step 2: Add new dependencies**

```bash
uv add groq anthropic openai fastmcp mcp edgartools gdeltdoc tiktoken
```

- [ ] **Step 3: Verify import works**

```bash
uv run python -c "import groq; import anthropic; import openai; import fastmcp; import mcp; import edgartools; import tiktoken; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/config.py pyproject.toml uv.lock
git commit -m "feat(4b): add LLM + MCP dependencies and API key settings"
```

---

### Task 2: Chat + Log Database Models

**Files:**
- Create: `backend/models/chat.py`
- Create: `backend/models/logs.py`
- Modify: `backend/models/__init__.py`

- [ ] **Step 1: Write test for model imports**

Create `tests/unit/test_chat_models.py`:

```python
"""Tests for chat and log database models."""

import uuid
from datetime import datetime, timezone

from backend.models.chat import ChatSession, ChatMessage
from backend.models.logs import LLMCallLog, ToolExecutionLog


def test_chat_session_defaults():
    """ChatSession has correct column defaults."""
    session = ChatSession(
        user_id=uuid.uuid4(),
        agent_type="stock",
    )
    assert session.is_active is True
    assert session.agent_type == "stock"


def test_chat_message_fields():
    """ChatMessage stores role, content, and token metadata."""
    msg = ChatMessage(
        session_id=uuid.uuid4(),
        role="user",
        content="Analyze AAPL",
    )
    assert msg.role == "user"
    assert msg.content == "Analyze AAPL"
    assert msg.tool_calls is None


def test_llm_call_log_fields():
    """LLMCallLog stores provider, model, and cost data."""
    log = LLMCallLog(
        provider="groq",
        model="llama-3.3-70b",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=1200,
    )
    assert log.provider == "groq"
    assert log.cost_usd is None


def test_tool_execution_log_fields():
    """ToolExecutionLog stores tool name, params, and status."""
    log = ToolExecutionLog(
        tool_name="compute_signals",
        status="ok",
        latency_ms=250,
        cache_hit=False,
    )
    assert log.status == "ok"
    assert log.cache_hit is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_chat_models.py -v
```

Expected: FAIL (ImportError — models don't exist yet)

- [ ] **Step 3: Create `backend/models/chat.py`**

```python
"""Chat session and message models."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.models.base import Base, TimestampMixin


class ChatSession(TimestampMixin, Base):
    """A chat conversation between a user and an agent."""

    __tablename__ = "chat_session"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    agent_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_active_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_chat_session_user", "user_id", "last_active_at"),
    )


class ChatMessage(TimestampMixin, Base):
    """A single message in a chat session."""

    __tablename__ = "chat_message"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_session.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped[ChatSession] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_chat_message_session", "session_id", "created_at"),
    )
```

**Note:** Both `ChatSession` and `ChatMessage` inherit `TimestampMixin` which provides `created_at` and `updated_at`. `ChatSession` also has an explicit `last_active_at` column (per spec §7.1) with `onupdate=func.now()` — update it on each new message. Check the existing `TimestampMixin` definition in `backend/models/base.py` to ensure no field conflicts.

- [ ] **Step 4: Create `backend/models/logs.py`**

```python
"""LLM call and tool execution log models (TimescaleDB hypertables)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, PrimaryKeyConstraint, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB, UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.models.base import Base


class LLMCallLog(Base):
    """One row per LLM API call. TimescaleDB hypertable on created_at."""

    __tablename__ = "llm_call_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_session.id"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_message.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_calls_requested: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Composite PK required for TimescaleDB hypertable partitioning
        PrimaryKeyConstraint("id", "created_at"),
    )


class ToolExecutionLog(Base):
    """One row per tool execution. TimescaleDB hypertable on created_at."""

    __tablename__ = "tool_execution_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), default=uuid.uuid4, nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_session.id"), nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("chat_message.id"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
    )
```

**Important:** The composite PK `(id, created_at)` for hypertables uses SQLAlchemy's `__table_args__` dict approach. Check how existing hypertables (`StockPrice`, `SignalSnapshot`, `PortfolioSnapshot`) define their composite PKs and follow the same pattern exactly. The pattern may use `PrimaryKeyConstraint` explicitly — match it.

- [ ] **Step 5: Update `backend/models/__init__.py`**

Add imports for the new models:

```python
from backend.models.chat import ChatSession, ChatMessage  # noqa: F401
from backend.models.logs import LLMCallLog, ToolExecutionLog  # noqa: F401
```

- [ ] **Step 6: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_chat_models.py -v
```

Expected: 4 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/models/chat.py backend/models/logs.py backend/models/__init__.py tests/unit/test_chat_models.py
git commit -m "feat(4b): add ChatSession, ChatMessage, LLMCallLog, ToolExecutionLog models"
```

---

### Task 3: Alembic Migration 008

**Files:**
- Create: `backend/migrations/versions/XXX_008_chat_and_logs.py`

- [ ] **Step 1: Generate migration**

```bash
uv run alembic revision --autogenerate -m "008_chat_and_logs"
```

- [ ] **Step 2: Review generated migration**

Open the generated file. Verify it creates:
- `chat_session` table with UUID PK, user_id FK, agent_type, title, is_active, timestamps
- `chat_message` table with UUID PK, session_id FK, role, content, tool_calls JSONB, token fields, timestamps
- `llm_call_log` table with composite PK `(id, created_at)`, provider, model, cost, JSONB tool_calls_requested
- `tool_execution_log` table with composite PK `(id, created_at)`, tool_name, params JSONB, status, cache_hit
- `SELECT create_hypertable(...)` for both log tables
- Indexes: `idx_chat_session_user`, `idx_chat_message_session`

**Critical:** Add `create_hypertable` calls manually if autogenerate doesn't include them:

```python
op.execute("SELECT create_hypertable('llm_call_log', 'created_at')")
op.execute("SELECT create_hypertable('tool_execution_log', 'created_at')")
```

Also verify autogenerate did NOT try to drop any existing TimescaleDB indexes (known gotcha — see `architecture/timescaledb-patterns` memory).

- [ ] **Step 3: Run migration**

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Verify tables exist**

```bash
uv run python -c "
import asyncio
from sqlalchemy import text
from backend.database import engine

async def check():
    async with engine.begin() as conn:
        for table in ['chat_session', 'chat_message', 'llm_call_log', 'tool_execution_log']:
            result = await conn.execute(text(f\"SELECT COUNT(*) FROM {table}\"))
            print(f'{table}: OK')

asyncio.run(check())
"
```

- [ ] **Step 5: Run ALL existing tests to verify no regressions**

```bash
uv run pytest tests/unit/ tests/api/ -v
```

Expected: 267 tests pass (143 unit + 124 API)

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/
git commit -m "feat(4b): migration 008 — chat_session, chat_message, llm_call_log, tool_execution_log"
```

---

### Task 4: Chat Pydantic Schemas

**Files:**
- Create: `backend/schemas/chat.py`

- [ ] **Step 1: Write test for schema validation**

Create `tests/unit/test_chat_schemas.py`:

```python
"""Tests for chat Pydantic schemas."""

import uuid

import pytest
from pydantic import ValidationError

from backend.schemas.chat import ChatRequest, ChatSessionResponse, ChatMessageResponse


def test_chat_request_new_session():
    """New session requires agent_type."""
    req = ChatRequest(message="Analyze AAPL", agent_type="stock")
    assert req.session_id is None
    assert req.agent_type == "stock"


def test_chat_request_resume_session():
    """Resume session ignores agent_type."""
    sid = uuid.uuid4()
    req = ChatRequest(message="Follow up", session_id=sid)
    assert req.session_id == sid


def test_chat_request_invalid_agent_type():
    """Invalid agent_type rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(message="Hello", agent_type="invalid")


def test_chat_request_empty_message():
    """Empty message rejected."""
    with pytest.raises(ValidationError):
        ChatRequest(message="", agent_type="stock")


def test_chat_session_response_fields():
    """ChatSessionResponse serializes correctly."""
    resp = ChatSessionResponse(
        id=uuid.uuid4(),
        agent_type="stock",
        title="Analyze AAPL",
        is_active=True,
        created_at="2026-03-17T00:00:00Z",
        last_active_at="2026-03-17T00:00:00Z",
    )
    assert resp.agent_type == "stock"


def test_chat_message_response_fields():
    """ChatMessageResponse serializes correctly."""
    resp = ChatMessageResponse(
        id=uuid.uuid4(),
        role="assistant",
        content="AAPL looks strong...",
        tool_calls=None,
        model_used="llama-3.3-70b",
        tokens_used=150,
        created_at="2026-03-17T00:00:00Z",
    )
    assert resp.role == "assistant"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_chat_schemas.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Create `backend/schemas/chat.py`**

```python
"""Chat request and response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /api/v1/chat/stream."""

    message: str = Field(..., min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None
    agent_type: Literal["stock", "general"] | None = Field(
        default=None,
        description="Required for new sessions. Ignored when resuming.",
    )


class ChatSessionResponse(BaseModel):
    """Response schema for chat session listing."""

    id: uuid.UUID
    agent_type: str
    title: str | None
    is_active: bool
    created_at: datetime
    last_active_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    """Response schema for chat message history."""

    id: uuid.UUID
    role: str
    content: str | None
    tool_calls: dict | None
    model_used: str | None
    tokens_used: int | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_chat_schemas.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/schemas/chat.py tests/unit/test_chat_schemas.py
git commit -m "feat(4b): add chat Pydantic schemas — ChatRequest, ChatSessionResponse, ChatMessageResponse"
```

---

## Chunk 2: Tool Registry + Internal Tools

### Task 5: Tool Base Classes

**Files:**
- Create: `backend/tools/base.py`

**Note:** The existing `backend/tools/` directory has tool modules (`signals.py`, `recommendations.py`, etc.) but no `base.py`. This file introduces the `BaseTool` ABC and related dataclasses that all tools will inherit from.

- [ ] **Step 1: Write test for base classes**

Create `tests/unit/test_tool_base.py`:

```python
"""Tests for tool base classes."""

import asyncio
from datetime import timedelta

import pytest

from backend.tools.base import (
    BaseTool,
    CachePolicy,
    ToolFilter,
    ToolInfo,
    ToolResult,
)


def test_cache_policy_fields():
    policy = CachePolicy(ttl=timedelta(hours=24), key_fields=["ticker"])
    assert policy.ttl == timedelta(hours=24)
    assert policy.key_fields == ["ticker"]


def test_tool_result_ok():
    result = ToolResult(status="ok", data={"price": 150.0})
    assert result.status == "ok"
    assert result.data["price"] == 150.0


def test_tool_result_error():
    result = ToolResult(status="error", error="Tool failed")
    assert result.status == "error"
    assert result.data is None


def test_tool_filter_matches():
    f = ToolFilter(categories=["analysis", "data"])
    info = ToolInfo(name="t", description="d", category="analysis", parameters={})
    assert f.matches(info)


def test_tool_filter_no_match():
    f = ToolFilter(categories=["portfolio"])
    info = ToolInfo(name="t", description="d", category="analysis", parameters={})
    assert not f.matches(info)


def test_tool_info_to_schema():
    """ToolInfo.to_llm_schema() returns OpenAI-compatible function schema."""
    info = ToolInfo(
        name="compute_signals",
        description="Compute signals for a ticker",
        category="data",
        parameters={
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    )
    schema = info.to_llm_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "compute_signals"
    assert "properties" in schema["function"]["parameters"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_tool_base.py -v
```

- [ ] **Step 3: Create `backend/tools/base.py`**

```python
"""Base classes for the Tool Registry system.

All internal tools inherit from BaseTool. External MCP tools are wrapped as ProxiedTool.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachePolicy:
    """Redis caching configuration for a tool."""

    ttl: timedelta
    key_fields: list[str]
    backend: Literal["redis"] = "redis"


@dataclass
class ToolResult:
    """Result of a tool execution."""

    status: Literal["ok", "degraded", "timeout", "error"]
    data: Any = None
    error: str | None = None


@dataclass(frozen=True)
class ToolInfo:
    """Serializable tool metadata for LLM context."""

    name: str
    description: str
    category: str
    parameters: dict[str, Any]

    def to_llm_schema(self) -> dict:
        """Return OpenAI-compatible function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class ToolFilter:
    """Filter for selecting tools by category."""

    categories: list[str]

    def matches(self, info: ToolInfo) -> bool:
        return info.category in self.categories


class BaseTool(ABC):
    """Abstract base for all tools (internal and proxied)."""

    name: str
    description: str
    category: str
    parameters: dict[str, Any]
    cache_policy: CachePolicy | None = None
    timeout_seconds: float = 10.0

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the tool with the given parameters."""
        ...

    def info(self) -> ToolInfo:
        """Return serializable metadata."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            category=self.category,
            parameters=self.parameters,
        )


class ProxiedTool(BaseTool):
    """A tool discovered from an external MCP server."""

    timeout_seconds: float = 30.0

    def __init__(
        self,
        name: str,
        description: str,
        category: str,
        parameters: dict[str, Any],
        adapter: Any,  # MCPAdapter reference
        cache_policy: CachePolicy | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.category = category
        self.parameters = parameters
        self._adapter = adapter
        self.cache_policy = cache_policy

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Delegate execution to the MCP adapter."""
        return await self._adapter.execute(self.name, params)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_tool_base.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/base.py tests/unit/test_tool_base.py
git commit -m "feat(4b): add BaseTool, ProxiedTool, CachePolicy, ToolResult, ToolFilter base classes"
```

---

### Task 6: Tool Registry

**Files:**
- Create: `backend/tools/registry.py`

- [ ] **Step 1: Write test for registry**

Create `tests/unit/test_tool_registry.py`:

```python
"""Tests for ToolRegistry."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from backend.tools.base import BaseTool, CachePolicy, ToolFilter, ToolInfo, ToolResult
from backend.tools.registry import ToolRegistry


class FakeTool(BaseTool):
    """A fake tool for testing."""

    def __init__(self, name: str = "fake_tool", category: str = "test"):
        self.name = name
        self.description = f"Fake tool: {name}"
        self.category = category
        self.parameters = {"type": "object", "properties": {}}
        self.cache_policy = None
        self.timeout_seconds = 5.0

    async def execute(self, params):
        return ToolResult(status="ok", data={"result": "success"})


@pytest.fixture
def registry():
    return ToolRegistry()


def test_register_and_get(registry):
    tool = FakeTool()
    registry.register(tool)
    assert registry.get("fake_tool") is tool


def test_register_duplicate_raises(registry):
    tool = FakeTool()
    registry.register(tool)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_get_unknown_raises(registry):
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_discover_returns_all(registry):
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    infos = registry.discover()
    assert len(infos) == 2
    assert {i.name for i in infos} == {"tool_a", "tool_b"}


def test_by_category(registry):
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    registry.register(FakeTool("tool_c", "analysis"))
    result = registry.by_category("analysis")
    assert len(result) == 2


def test_schemas_with_filter(registry):
    registry.register(FakeTool("tool_a", "analysis"))
    registry.register(FakeTool("tool_b", "data"))
    f = ToolFilter(categories=["analysis"])
    schemas = registry.schemas(f)
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "tool_a"


@pytest.mark.asyncio
async def test_execute(registry):
    tool = FakeTool()
    registry.register(tool)
    result = await registry.execute("fake_tool", {})
    assert result.status == "ok"


def test_health_all_ok(registry):
    registry.register(FakeTool("t1"))
    health = registry.health()
    assert health["t1"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_tool_registry.py -v
```

- [ ] **Step 3: Create `backend/tools/registry.py`**

```python
"""Tool Registry — central hub for all tool discovery and execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

from backend.tools.base import BaseTool, ToolFilter, ToolInfo, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry for all internal and proxied tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Raises ValueError if name is already taken."""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool
        logger.info("tool_registered", extra={"tool": tool.name, "category": tool.category})

    def get(self, name: str) -> BaseTool:
        """Get a tool by name. Raises KeyError if not found."""
        return self._tools[name]

    def discover(self) -> list[ToolInfo]:
        """Return metadata for all registered tools."""
        return [tool.info() for tool in self._tools.values()]

    def by_category(self, *categories: str) -> list[BaseTool]:
        """Return tools matching any of the given categories."""
        return [t for t in self._tools.values() if t.category in categories]

    def schemas(self, tool_filter: ToolFilter) -> list[dict]:
        """Return LLM-compatible function schemas for tools matching the filter."""
        return [
            tool.info().to_llm_schema()
            for tool in self._tools.values()
            if tool_filter.matches(tool.info())
        ]

    async def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with the given params."""
        tool = self.get(name)
        # Cache check would go here (Redis lookup by cache_policy.key_fields)
        # For now, direct execution. Cache layer added in Task 14 (warm pipeline).
        return await asyncio.wait_for(
            tool.execute(params),
            timeout=tool.timeout_seconds,
        )

    def register_mcp(self, adapter: "MCPAdapter") -> None:
        """Register all tools from an MCP adapter."""
        for tool in adapter.get_tools():
            self.register(tool)

    def health(self) -> dict[str, bool]:
        """Return health status for all registered tools."""
        return {name: True for name in self._tools}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/unit/test_tool_registry.py -v
```

Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/registry.py tests/unit/test_tool_registry.py
git commit -m "feat(4b): add ToolRegistry — register, discover, execute, filter, health"
```

---

### Task 7: Internal Tools — Wrap Existing Backend Functions

**Files:**
- Create: `backend/tools/analyze_stock.py`
- Create: `backend/tools/portfolio_exposure.py`
- Create: `backend/tools/screen_stocks.py`
- Create: `backend/tools/web_search.py`
- Create: `backend/tools/geopolitical.py`

Each internal tool wraps an existing backend function (or external API) into the `BaseTool` interface. They follow the same pattern:

1. Inherit from `BaseTool`
2. Set `name`, `description`, `category`, `parameters` (JSON Schema)
3. Implement `async execute(params) -> ToolResult`
4. Wrap existing function calls, catch exceptions, return `ToolResult`

- [ ] **Step 1: Write tests for internal tools**

Create `tests/unit/test_internal_tools.py`:

```python
"""Tests for internal tool wrappers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.base import ToolResult


@pytest.mark.asyncio
async def test_analyze_stock_tool_happy_path():
    """AnalyzeStockTool calls compute_signals and returns result."""
    from backend.tools.analyze_stock import AnalyzeStockTool

    tool = AnalyzeStockTool()
    assert tool.name == "analyze_stock"
    assert tool.category == "analysis"

    # Mock the DB session and signal computation
    with patch("backend.tools.analyze_stock.get_async_session") as mock_session:
        mock_ctx = AsyncMock()
        mock_session.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tools.analyze_stock.compute_signals") as mock_signals:
            mock_signals.return_value = MagicMock(
                composite_score=8.5,
                rsi=MagicMock(value=45.0, signal="neutral"),
                macd=MagicMock(value=1.2, signal="bullish"),
            )
            result = await tool.execute({"ticker": "AAPL"})

    assert result.status == "ok"
    assert "composite_score" in result.data


@pytest.mark.asyncio
async def test_analyze_stock_tool_error():
    """AnalyzeStockTool returns error on exception."""
    from backend.tools.analyze_stock import AnalyzeStockTool

    tool = AnalyzeStockTool()
    with patch("backend.tools.analyze_stock.get_async_session", side_effect=Exception("DB down")):
        result = await tool.execute({"ticker": "AAPL"})

    assert result.status == "error"
    assert "DB down" in result.error


@pytest.mark.asyncio
async def test_web_search_tool():
    """WebSearchTool calls SerpAPI and returns results."""
    from backend.tools.web_search import WebSearchTool

    tool = WebSearchTool()
    assert tool.name == "web_search"
    assert tool.category == "data"

    with patch("backend.tools.web_search.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {
            "organic_results": [{"title": "Test", "link": "https://example.com", "snippet": "Test result"}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(get=AsyncMock(return_value=mock_resp)))
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.execute({"query": "AAPL stock analysis"})

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_geopolitical_tool():
    """GeopoliticalEventsTool calls GDELT and returns events."""
    from backend.tools.geopolitical import GeopoliticalEventsTool

    tool = GeopoliticalEventsTool()
    assert tool.name == "get_geopolitical_events"
    assert tool.category == "macro"

    with patch("backend.tools.geopolitical.GdeltDoc") as mock_gdelt:
        mock_instance = MagicMock()
        mock_instance.article_search.return_value = MagicMock(
            to_dict=MagicMock(return_value={"records": [{"title": "Event"}]})
        )
        mock_gdelt.return_value = mock_instance

        result = await tool.execute({"query": "Iran oil", "days": 7})

    assert result.status == "ok"


@pytest.mark.asyncio
async def test_portfolio_exposure_tool():
    """PortfolioExposureTool returns sector allocation."""
    from backend.tools.portfolio_exposure import PortfolioExposureTool

    tool = PortfolioExposureTool()
    assert tool.name == "get_portfolio_exposure"
    assert tool.category == "portfolio"


@pytest.mark.asyncio
async def test_screen_stocks_tool():
    """ScreenStocksTool wraps bulk signals endpoint logic."""
    from backend.tools.screen_stocks import ScreenStocksTool

    tool = ScreenStocksTool()
    assert tool.name == "screen_stocks"
    assert tool.category == "analysis"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/test_internal_tools.py -v
```

- [ ] **Step 3: Implement all 5 internal tools**

Each tool follows this pattern (showing `analyze_stock.py` as the template):

```python
"""AnalyzeStockTool — complete stock analysis combining technicals + fundamentals."""

from __future__ import annotations

import logging
from typing import Any

from backend.tools.base import BaseTool, CachePolicy, ToolResult

logger = logging.getLogger(__name__)


class AnalyzeStockTool(BaseTool):
    name = "analyze_stock"
    description = (
        "Analyze a stock ticker: compute technical signals (RSI, MACD, SMA, Bollinger), "
        "fundamental metrics (P/E, Piotroski), and generate a composite score with recommendation."
    )
    category = "analysis"
    parameters = {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"},
        },
        "required": ["ticker"],
    }
    cache_policy = None  # Always compute fresh
    timeout_seconds = 15.0

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        ticker = params["ticker"].upper()
        try:
            from backend.database import get_async_session
            from backend.tools.signals import compute_signals
            from backend.tools.fundamentals import fetch_fundamentals
            from backend.tools.recommendations import generate_recommendation

            # Lazy imports to avoid circular deps at module level
            async for session in get_async_session():
                signals = await compute_signals(session, ticker)
                fundamentals = await fetch_fundamentals(ticker)  # sync via run_in_executor internally
                recommendation = generate_recommendation(
                    ticker=ticker,
                    composite_score=signals.composite_score,
                )
                return ToolResult(
                    status="ok",
                    data={
                        "ticker": ticker,
                        "composite_score": signals.composite_score,
                        "rsi": {"value": signals.rsi.value, "signal": signals.rsi.signal},
                        "macd": {"value": signals.macd.value, "signal": signals.macd.signal},
                        "fundamentals": fundamentals,
                        "recommendation": {
                            "action": recommendation.action.value,
                            "confidence": recommendation.confidence.value,
                            "reasoning": recommendation.reasoning,
                        },
                    },
                )
        except Exception as e:
            logger.error("analyze_stock_failed", extra={"ticker": ticker, "error": str(e)})
            return ToolResult(status="error", error=str(e))
```

Implement the other 4 tools following the same pattern:
- **`portfolio_exposure.py`**: Calls `get_portfolio_summary()` from `backend/tools/portfolio.py`. Returns sector allocation, total value, P&L.
- **`screen_stocks.py`**: Calls the bulk signals query logic from `backend/routers/stocks.py`. Accepts filters (min_score, sector, rsi_state). Returns top N matches.
- **`web_search.py`**: Calls SerpAPI via `httpx.AsyncClient`. Uses `settings.SERPAPI_API_KEY`. Returns top 5 organic results (title, link, snippet).
- **`geopolitical.py`**: Uses `gdeltdoc.GdeltDoc().article_search()`. Accepts query string + days. Returns articles with titles, URLs, tone scores.

**Key:** Each tool must handle its own exceptions and return `ToolResult(status="error", error=str(e))` — never let exceptions propagate. This is what enables graceful degradation in the agentic loop.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_internal_tools.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/analyze_stock.py backend/tools/portfolio_exposure.py backend/tools/screen_stocks.py backend/tools/web_search.py backend/tools/geopolitical.py tests/unit/test_internal_tools.py
git commit -m "feat(4b): add 5 internal tools — analyze_stock, portfolio_exposure, screen_stocks, web_search, geopolitical"
```

---

### Task 8: Wrap Existing Tools — compute_signals + recommendations

**Files:**
- Create: `backend/tools/compute_signals_tool.py`
- Create: `backend/tools/recommendations_tool.py`

The existing `backend/tools/signals.py` and `backend/tools/recommendations.py` contain pure functions. We need thin `BaseTool` wrappers that the registry can discover.

- [ ] **Step 1: Write tests**

Add to `tests/unit/test_internal_tools.py`:

```python
@pytest.mark.asyncio
async def test_compute_signals_tool():
    """ComputeSignalsTool wraps existing compute_signals function."""
    from backend.tools.compute_signals_tool import ComputeSignalsTool

    tool = ComputeSignalsTool()
    assert tool.name == "compute_signals"
    assert tool.category == "data"


@pytest.mark.asyncio
async def test_recommendations_tool():
    """RecommendationsTool wraps existing generate_recommendation function."""
    from backend.tools.recommendations_tool import RecommendationsTool

    tool = RecommendationsTool()
    assert tool.name == "get_recommendations"
    assert tool.category == "portfolio"
```

- [ ] **Step 2: Implement both wrapper tools**

Same pattern as Task 7 — `BaseTool` subclass, lazy imports, exception handling, `ToolResult` return.

`compute_signals_tool.py`: Accepts `ticker`, calls `compute_signals(session, ticker)`, returns signal data.
`recommendations_tool.py`: Accepts `ticker`, calls `generate_recommendation()` with optional portfolio context, returns action + confidence + reasoning.

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_internal_tools.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/tools/compute_signals_tool.py backend/tools/recommendations_tool.py tests/unit/test_internal_tools.py
git commit -m "feat(4b): add compute_signals and recommendations BaseTool wrappers"
```

---

## Chunk 3: LLM Client + Agents + Agentic Loop

### Task 9: Stream Event Types

**Files:**
- Create: `backend/agents/stream.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_stream_events.py`:

```python
"""Tests for stream event serialization."""

import json

from backend.agents.stream import StreamEvent


def test_thinking_event():
    e = StreamEvent(type="thinking", content="Analyzing AAPL...")
    line = e.to_ndjson()
    parsed = json.loads(line)
    assert parsed["type"] == "thinking"
    assert parsed["content"] == "Analyzing AAPL..."


def test_tool_start_event():
    e = StreamEvent(type="tool_start", tool="compute_signals", params={"ticker": "AAPL"})
    parsed = json.loads(e.to_ndjson())
    assert parsed["tool"] == "compute_signals"


def test_tool_result_event():
    e = StreamEvent(type="tool_result", tool="compute_signals", status="ok", data={"score": 8.5})
    parsed = json.loads(e.to_ndjson())
    assert parsed["status"] == "ok"


def test_token_event():
    e = StreamEvent(type="token", content="Based on")
    parsed = json.loads(e.to_ndjson())
    assert parsed["content"] == "Based on"


def test_done_event():
    e = StreamEvent(type="done", usage={"tokens": 4521, "model": "llama-3.3-70b"})
    parsed = json.loads(e.to_ndjson())
    assert parsed["usage"]["tokens"] == 4521


def test_provider_fallback_event():
    e = StreamEvent(type="provider_fallback", data={"from": "groq", "to": "anthropic"})
    parsed = json.loads(e.to_ndjson())
    assert parsed["data"]["from"] == "groq"
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement `backend/agents/stream.py`**

```python
"""Stream event types for NDJSON chat streaming."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class StreamEvent:
    """A single event in the NDJSON response stream."""

    type: Literal[
        "thinking", "tool_start", "tool_result", "token",
        "done", "provider_fallback", "context_truncated",
    ]
    content: str | None = None
    tool: str | None = None
    params: dict[str, Any] | None = None
    status: str | None = None
    data: Any = None
    usage: dict[str, Any] | None = None
    error: str | None = None

    def to_ndjson(self) -> str:
        """Serialize to a single JSON line (no trailing newline)."""
        d: dict[str, Any] = {"type": self.type}
        for key in ("content", "tool", "params", "status", "data", "usage", "error"):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        return json.dumps(d)
```

- [ ] **Step 4: Run test, verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend/agents/__init__.py backend/agents/stream.py tests/unit/test_stream_events.py
git commit -m "feat(4b): add StreamEvent dataclass with NDJSON serialization"
```

---

### Task 10: LLM Client + Provider Abstraction

**Files:**
- Create: `backend/agents/llm_client.py`
- Create: `backend/agents/providers/__init__.py`
- Create: `backend/agents/providers/groq.py`
- Create: `backend/agents/providers/anthropic.py`
- Create: `backend/agents/providers/openai.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_llm_client.py`:

```python
"""Tests for LLMClient and provider abstraction."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

import pytest

from backend.agents.llm_client import (
    LLMClient,
    LLMProvider,
    LLMResponse,
    ProviderHealth,
    RetryPolicy,
    MaxRetriesExceeded,
    AllProvidersFailedError,
    RateLimitError,
)


class FakeProvider(LLMProvider):
    """A fake provider for testing."""

    def __init__(self, name="fake", response=None, error=None):
        self._name = name
        self._response = response
        self._error = error
        self.health = ProviderHealth(provider=name)

    @property
    def name(self) -> str:
        return self._name

    async def chat(self, messages, tools, stream=False):
        if self._error:
            raise self._error
        return self._response or LLMResponse(
            content="Test response",
            tool_calls=[],
            model=f"{self._name}-model",
            prompt_tokens=100,
            completion_tokens=50,
        )


@pytest.mark.asyncio
async def test_llm_client_first_provider_succeeds():
    """LLMClient uses first available provider."""
    provider = FakeProvider("groq")
    client = LLMClient(providers=[provider])
    response = await client.chat(messages=[{"role": "user", "content": "Hi"}], tools=[])
    assert response.content == "Test response"
    assert response.model == "groq-model"


@pytest.mark.asyncio
async def test_llm_client_fallback_on_error():
    """LLMClient falls through to next provider on error."""
    bad = FakeProvider("groq", error=Exception("down"))
    good = FakeProvider("anthropic")
    client = LLMClient(providers=[bad, good], retry_policy=RetryPolicy(max_retries=1))
    response = await client.chat(messages=[{"role": "user", "content": "Hi"}], tools=[])
    assert response.model == "anthropic-model"


@pytest.mark.asyncio
async def test_llm_client_all_fail():
    """LLMClient raises AllProvidersFailedError when all providers fail."""
    bad1 = FakeProvider("groq", error=Exception("down"))
    bad2 = FakeProvider("anthropic", error=Exception("down"))
    client = LLMClient(providers=[bad1, bad2], retry_policy=RetryPolicy(max_retries=1))
    with pytest.raises(AllProvidersFailedError):
        await client.chat(messages=[], tools=[])


@pytest.mark.asyncio
async def test_llm_client_skips_exhausted_provider():
    """LLMClient skips providers marked as exhausted."""
    exhausted = FakeProvider("groq")
    exhausted.health.is_exhausted = True
    exhausted.health.exhausted_until = datetime(2099, 1, 1, tzinfo=timezone.utc)
    good = FakeProvider("anthropic")
    client = LLMClient(providers=[exhausted, good])
    response = await client.chat(messages=[], tools=[])
    assert response.model == "anthropic-model"


def test_provider_health_defaults():
    h = ProviderHealth(provider="groq")
    assert h.is_exhausted is False
    assert h.consecutive_failures == 0


def test_retry_policy_defaults():
    p = RetryPolicy()
    assert p.max_retries == 3
    assert p.base_delay == 1.0
    assert p.backoff_factor == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement `backend/agents/llm_client.py`**

This file contains:
- `LLMProvider` ABC with `async chat(messages, tools, stream) -> LLMResponse`
- `LLMResponse` dataclass: `content`, `tool_calls`, `model`, `prompt_tokens`, `completion_tokens`, `has_tool_calls` property, optional `stream` (AsyncIterator for streaming)
- `RetryPolicy` dataclass: `max_retries=3`, `base_delay=1.0`, `max_delay=10.0`, `backoff_factor=2.0`
- `ProviderHealth` dataclass: `provider`, `is_exhausted`, `exhausted_until`, `consecutive_failures`, `last_failure`
- `RateLimitError`, `MaxRetriesExceeded`, `AllProvidersFailedError` exception classes
- `LLMClient` class:
  - `__init__(providers: list[LLMProvider], retry_policy: RetryPolicy = RetryPolicy())`
  - `async chat(messages, tools, stream=False) -> LLMResponse` — iterates providers, skips exhausted, calls `_call_with_retry()`, falls through on failure
  - `async _call_with_retry(provider, messages, tools, stream) -> LLMResponse` — retry loop per spec §4.4

- [ ] **Step 4: Implement provider files**

Each provider file (`groq.py`, `anthropic.py`, `openai.py`) follows this pattern:

```python
"""Groq LLM provider (OpenAI-compatible SDK)."""

from __future__ import annotations

import logging
from typing import Any

from backend.agents.llm_client import LLMProvider, LLMResponse, ProviderHealth

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    """Groq provider using the groq SDK."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        self._api_key = api_key
        self._model = model
        self.health = ProviderHealth(provider="groq")

    @property
    def name(self) -> str:
        return "groq"

    async def chat(self, messages, tools, stream=False) -> LLMResponse:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=self._api_key)
        # Convert tools to OpenAI format (already in that format from registry)
        response = await client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools if tools else None,
            stream=stream,
        )

        if stream:
            # Return LLMResponse with stream iterator
            # Implementation depends on groq SDK streaming API
            ...

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
            model=self._model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
        )
```

- `anthropic.py`: Uses `anthropic.AsyncAnthropic`. Translates Anthropic's tool_use format to the normalized `LLMResponse` format. Key difference: Anthropic uses `content[].type == "tool_use"` blocks instead of `tool_calls` array.
- `openai.py`: Uses `openai.AsyncOpenAI`. Same format as Groq (OpenAI-compatible). Also serves as LM Studio local provider (just change base_url).

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_llm_client.py -v
```

Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/agents/llm_client.py backend/agents/providers/ tests/unit/test_llm_client.py
git commit -m "feat(4b): add LLMClient with provider abstraction, retry policy, fallback chain"
```

---

### Task 11: Agent Types + Prompt Templates

**Files:**
- Create: `backend/agents/base.py`
- Create: `backend/agents/stock_agent.py`
- Create: `backend/agents/general_agent.py`
- Create: `backend/agents/prompts/stock_agent.md`
- Create: `backend/agents/prompts/general_agent.md`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_agents.py`:

```python
"""Tests for agent types and prompt loading."""

from pathlib import Path

from backend.agents.base import BaseAgent
from backend.agents.stock_agent import StockAgent
from backend.agents.general_agent import GeneralAgent
from backend.tools.base import ToolFilter


def test_stock_agent_tool_filter():
    agent = StockAgent()
    assert isinstance(agent.tool_filter, ToolFilter)
    assert "analysis" in agent.tool_filter.categories
    assert "portfolio" in agent.tool_filter.categories
    assert "sec" in agent.tool_filter.categories


def test_general_agent_tool_filter():
    agent = GeneralAgent()
    assert isinstance(agent.tool_filter, ToolFilter)
    assert "data" in agent.tool_filter.categories
    assert "news" in agent.tool_filter.categories
    assert "portfolio" not in agent.tool_filter.categories


def test_stock_agent_system_prompt():
    agent = StockAgent()
    prompt = agent.system_prompt()
    assert len(prompt) > 100
    assert "stock" in prompt.lower() or "financial" in prompt.lower()


def test_general_agent_system_prompt():
    agent = GeneralAgent()
    prompt = agent.system_prompt()
    assert len(prompt) > 100


def test_prompt_files_exist():
    prompts_dir = Path(__file__).resolve().parents[2] / "backend" / "agents" / "prompts"
    assert (prompts_dir / "stock_agent.md").exists()
    assert (prompts_dir / "general_agent.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement `backend/agents/base.py`**

```python
"""Base agent ABC."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.tools.base import ToolFilter

PROMPTS_DIR = Path(__file__).parent / "prompts"


class BaseAgent(ABC):
    """Abstract base for all agent types."""

    @property
    @abstractmethod
    def agent_type(self) -> str:
        """Agent type identifier (e.g., 'stock', 'general')."""
        ...

    @property
    @abstractmethod
    def tool_filter(self) -> ToolFilter:
        """Which tool categories this agent can access."""
        ...

    def system_prompt(self) -> str:
        """Load the agent's system prompt from markdown file."""
        prompt_file = PROMPTS_DIR / f"{self.agent_type}_agent.md"
        return prompt_file.read_text(encoding="utf-8")
```

- [ ] **Step 4: Implement `StockAgent` and `GeneralAgent`**

`stock_agent.py`:
```python
from backend.agents.base import BaseAgent
from backend.tools.base import ToolFilter

class StockAgent(BaseAgent):
    agent_type = "stock"
    tool_filter = ToolFilter(categories=["analysis", "data", "portfolio", "macro", "news", "sec"])
```

`general_agent.py`:
```python
from backend.agents.base import BaseAgent
from backend.tools.base import ToolFilter

class GeneralAgent(BaseAgent):
    agent_type = "general"
    tool_filter = ToolFilter(categories=["data", "news"])
```

- [ ] **Step 5: Write prompt templates**

Create `backend/agents/prompts/stock_agent.md` with:
- Role: "You are a financial analysis assistant..."
- Available tools: `{tools}` placeholder (injected at runtime)
- 3-4 few-shot examples per spec §6.3
- Guardrails: never fabricate numbers, all data from tools

Create `backend/agents/prompts/general_agent.md` with:
- Role: "You are a helpful assistant with access to web search and news data..."
- 2-3 few-shot examples
- Limited scope: no portfolio/SEC access

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/unit/test_agents.py -v
```

Expected: 5 PASS

- [ ] **Step 7: Commit**

```bash
git add backend/agents/ tests/unit/test_agents.py
git commit -m "feat(4b): add StockAgent, GeneralAgent with few-shot prompt templates"
```

---

### Task 12: Agentic Loop

**Files:**
- Create: `backend/agents/loop.py`

This is the core orchestration — the two-phase tool-calling + synthesis loop from spec §5.

- [ ] **Step 1: Write tests**

Create `tests/unit/test_agentic_loop.py`:

```python
"""Tests for the agentic tool-calling loop."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.agents.loop import agentic_loop, execute_tool_safely
from backend.agents.llm_client import LLMResponse
from backend.agents.stream import StreamEvent
from backend.tools.base import ToolResult
from backend.tools.registry import ToolRegistry


@pytest.fixture
def mock_registry():
    reg = ToolRegistry()
    return reg


@pytest.fixture
def mock_llm():
    return AsyncMock()


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.system_prompt.return_value = "You are a test agent."
    agent.tool_filter = MagicMock()
    return agent


@pytest.mark.asyncio
async def test_loop_no_tool_calls(mock_agent, mock_registry, mock_llm):
    """Loop yields token events when LLM responds without tool calls."""
    mock_llm.chat.return_value = LLMResponse(
        content="AAPL looks strong.",
        tool_calls=[],
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
    )
    events = []
    async for event in agentic_loop(
        agent=mock_agent,
        message="Analyze AAPL",
        history=[],
        registry=mock_registry,
        llm=mock_llm,
    ):
        events.append(event)

    types = [e.type for e in events]
    assert "token" in types or "done" in types


@pytest.mark.asyncio
async def test_loop_with_tool_calls(mock_agent, mock_registry, mock_llm):
    """Loop executes tools then gets final synthesis."""
    # First call: LLM requests a tool
    tool_response = LLMResponse(
        content="",
        tool_calls=[{"id": "1", "name": "fake_tool", "arguments": "{}"}],
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
    )
    # Second call: LLM synthesizes
    final_response = LLMResponse(
        content="Based on the analysis...",
        tool_calls=[],
        model="test-model",
        prompt_tokens=200,
        completion_tokens=100,
    )
    mock_llm.chat.side_effect = [tool_response, final_response]

    # Register a fake tool
    from tests.unit.test_tool_registry import FakeTool
    mock_registry.register(FakeTool("fake_tool", "test"))

    events = []
    async for event in agentic_loop(
        agent=mock_agent,
        message="Analyze AAPL",
        history=[],
        registry=mock_registry,
        llm=mock_llm,
    ):
        events.append(event)

    types = [e.type for e in events]
    assert "tool_start" in types
    assert "tool_result" in types


@pytest.mark.asyncio
async def test_loop_max_iterations(mock_agent, mock_registry, mock_llm):
    """Loop stops at max_iterations."""
    # Always return tool calls — should stop at max
    mock_llm.chat.return_value = LLMResponse(
        content="",
        tool_calls=[{"id": "1", "name": "fake_tool", "arguments": "{}"}],
        model="test-model",
        prompt_tokens=100,
        completion_tokens=50,
    )
    from tests.unit.test_tool_registry import FakeTool
    mock_registry.register(FakeTool("fake_tool", "test"))

    events = []
    async for event in agentic_loop(
        agent=mock_agent,
        message="Loop forever",
        history=[],
        registry=mock_registry,
        llm=mock_llm,
        max_iterations=3,
    ):
        events.append(event)

    tool_starts = [e for e in events if e.type == "tool_start"]
    assert len(tool_starts) <= 3


@pytest.mark.asyncio
async def test_execute_tool_safely_success(mock_registry):
    """execute_tool_safely returns ToolResult on success."""
    from tests.unit.test_tool_registry import FakeTool
    mock_registry.register(FakeTool("fake_tool", "test"))

    tool_call = MagicMock()
    tool_call.name = "fake_tool" if hasattr(tool_call, 'name') else None
    result = await execute_tool_safely(mock_registry, "fake_tool", {})
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_execute_tool_safely_timeout(mock_registry):
    """execute_tool_safely returns timeout on slow tool."""
    import asyncio
    from backend.tools.base import BaseTool, ToolResult as TR

    class SlowTool(BaseTool):
        name = "slow_tool"
        description = "Slow"
        category = "test"
        parameters = {}
        timeout_seconds = 0.01  # Very short timeout

        async def execute(self, params):
            await asyncio.sleep(10)
            return TR(status="ok")

    mock_registry.register(SlowTool())
    result = await execute_tool_safely(mock_registry, "slow_tool", {})
    assert result.status == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement `backend/agents/loop.py`**

```python
"""Agentic tool-calling loop — two-phase: tool execution + synthesis streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator

from backend.agents.base import BaseAgent
from backend.agents.llm_client import LLMClient, LLMResponse
from backend.agents.stream import StreamEvent
from backend.tools.base import ToolResult
from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


async def execute_tool_safely(
    registry: ToolRegistry,
    tool_name: str,
    params: dict[str, Any],
) -> ToolResult:
    """Execute a tool with timeout and error isolation."""
    try:
        tool = registry.get(tool_name)
        return await asyncio.wait_for(
            tool.execute(params),
            timeout=tool.timeout_seconds,
        )
    except KeyError:
        return ToolResult(status="error", error=f"Tool '{tool_name}' not found")
    except asyncio.TimeoutError:
        logger.warning("tool_timeout", extra={"tool": tool_name})
        return ToolResult(status="timeout", error="Tool took too long")
    except Exception as e:
        logger.error("tool_failed", extra={"tool": tool_name, "error": str(e)})
        return ToolResult(status="error", error=str(e))


async def agentic_loop(
    agent: BaseAgent,
    message: str,
    history: list[dict[str, Any]],
    registry: ToolRegistry,
    llm: LLMClient,
    max_iterations: int = 15,
) -> AsyncIterator[StreamEvent]:
    """Run the agentic loop: tool calls → synthesis → stream."""
    system_prompt = agent.system_prompt()
    tools = registry.schemas(agent.tool_filter)
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": message},
    ]

    yield StreamEvent(type="thinking", content=f"Analyzing your question...")

    for iteration in range(max_iterations):
        response = await llm.chat(messages=messages, tools=tools, stream=False)

        if not response.has_tool_calls:
            # Synthesis phase — emit tokens
            yield StreamEvent(type="token", content=response.content)
            break

        # Tool-calling phase
        for tool_call in response.tool_calls:
            tc_name = tool_call["name"]
            tc_args = json.loads(tool_call["arguments"]) if isinstance(tool_call["arguments"], str) else tool_call["arguments"]

            yield StreamEvent(type="tool_start", tool=tc_name, params=tc_args)
            result = await execute_tool_safely(registry, tc_name, tc_args)
            yield StreamEvent(
                type="tool_result",
                tool=tc_name,
                status=result.status,
                data=result.data,
                error=result.error,
            )

            # Append tool call + result to messages for next iteration
            messages.append({"role": "assistant", "content": None, "tool_calls": [tool_call]})
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get("id", tc_name),
                "content": json.dumps(result.data if result.data else {"error": result.error}),
            })
    else:
        # Hit max iterations
        yield StreamEvent(type="token", content="I've gathered the available data. Let me summarize what I found.")

    yield StreamEvent(
        type="done",
        usage={
            "model": response.model,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
        },
    )
```

**DB Logging (spec §9):** The agentic loop must also persist to `LLMCallLog` and `ToolExecutionLog` tables. Add a `db: AsyncSession` parameter to `agentic_loop()`. After each `llm.chat()` call, insert an `LLMCallLog` row (provider, model, tokens, latency). After each `execute_tool_safely()` call, insert a `ToolExecutionLog` row (tool_name, params, status, latency, cache_hit). Use `db.add()` + `await db.flush()` (commit happens at the router level). This ensures all LLM calls and tool executions are tracked for observability.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_agentic_loop.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/agents/loop.py tests/unit/test_agentic_loop.py
git commit -m "feat(4b): add agentic loop — two-phase tool-calling + synthesis with max iterations"
```

---

## Chunk 4: MCP Adapters + MCP Server + Warm Pipeline

### Task 13: MCP Adapter Base + 4 Adapters

**Files:**
- Create: `backend/tools/adapters/__init__.py`
- Create: `backend/tools/adapters/base.py`
- Create: `backend/tools/adapters/edgar.py`
- Create: `backend/tools/adapters/alpha_vantage.py`
- Create: `backend/tools/adapters/fred.py`
- Create: `backend/tools/adapters/finnhub.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_mcp_adapters.py`:

```python
"""Tests for MCP adapter base and implementations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.adapters.base import MCPAdapter
from backend.tools.base import ProxiedTool, ToolResult


def test_mcp_adapter_is_abstract():
    """MCPAdapter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        MCPAdapter()


@pytest.mark.asyncio
async def test_edgar_adapter_discover():
    """EdgarAdapter discovers expected tools."""
    from backend.tools.adapters.edgar import EdgarAdapter

    adapter = EdgarAdapter()
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_10k_section" in names
    assert "get_13f_holdings" in names


@pytest.mark.asyncio
async def test_alpha_vantage_adapter_discover():
    """AlphaVantageAdapter discovers expected tools."""
    from backend.tools.adapters.alpha_vantage import AlphaVantageAdapter

    adapter = AlphaVantageAdapter(api_key="test")
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_news_sentiment" in names


@pytest.mark.asyncio
async def test_fred_adapter_discover():
    """FredAdapter discovers expected tools."""
    from backend.tools.adapters.fred import FredAdapter

    adapter = FredAdapter(api_key="test")
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_economic_series" in names


@pytest.mark.asyncio
async def test_finnhub_adapter_discover():
    """FinnhubAdapter discovers expected tools."""
    from backend.tools.adapters.finnhub import FinnhubAdapter

    adapter = FinnhubAdapter(api_key="test")
    tools = adapter.get_tools()
    names = [t.name for t in tools]
    assert "get_analyst_ratings" in names
```

- [ ] **Step 2: Implement `backend/tools/adapters/base.py`**

```python
"""MCPAdapter ABC — base class for external MCP server connections."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.tools.base import ProxiedTool, ToolResult


class MCPAdapter(ABC):
    """Abstract adapter for consuming an external MCP server's tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter identifier (e.g., 'edgar_tools')."""
        ...

    @abstractmethod
    def get_tools(self) -> list[ProxiedTool]:
        """Return ProxiedTool instances for all tools this adapter exposes."""
        ...

    @abstractmethod
    async def execute(self, tool_name: str, params: dict) -> ToolResult:
        """Execute a specific tool via the external MCP server or library."""
        ...

    async def health_check(self) -> bool:
        """Check if the external MCP server is reachable. Default: True."""
        return True
```

- [ ] **Step 3: Implement 4 adapter files**

Each adapter:
1. Inherits `MCPAdapter`
2. Defines `get_tools()` returning `ProxiedTool` instances with proper name, description, category, parameters JSON Schema
3. Implements `async execute()` using the appropriate library/API
4. Handles errors gracefully returning `ToolResult(status="error", ...)`

**EdgarAdapter:** Uses `edgartools` Python library directly (not MCP protocol). Tools: `get_10k_section`, `get_13f_holdings`, `get_insider_trades`, `get_8k_events`.

**AlphaVantageAdapter:** Uses `httpx` REST calls to Alpha Vantage API. Tools: `get_news_sentiment`, `get_quotes`.

**FredAdapter:** Uses `httpx` REST calls to FRED API. Tool: `get_economic_series` (accepts `series_ids` list).

**FinnhubAdapter:** Uses `httpx` REST calls to Finnhub API. Tools: `get_analyst_ratings`, `get_social_sentiment`, `get_etf_holdings`, `get_esg_scores`, `get_supply_chain`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_mcp_adapters.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/adapters/ tests/unit/test_mcp_adapters.py
git commit -m "feat(4b): add MCPAdapter base + Edgar, AlphaVantage, FRED, Finnhub adapters"
```

---

### Task 14: MCP Server (Layer 3 — Expose)

**Files:**
- Create: `backend/mcp_server/__init__.py`
- Create: `backend/mcp_server/server.py`
- Create: `backend/mcp_server/auth.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_mcp_server.py`:

```python
"""Tests for MCP server setup."""

from backend.mcp_server.server import create_mcp_app


def test_mcp_app_creates():
    """MCP app can be created with a registry."""
    from backend.tools.registry import ToolRegistry
    registry = ToolRegistry()
    mcp = create_mcp_app(registry)
    assert mcp is not None
```

- [ ] **Step 2: Implement `backend/mcp_server/server.py`**

```python
"""FastMCP server — exposes Tool Registry as MCP Streamable HTTP at /mcp."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from backend.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_mcp_app(registry: ToolRegistry) -> FastMCP:
    """Create a FastMCP server that mirrors the Tool Registry."""
    mcp = FastMCP("StockSignal Intelligence Platform")

    for tool_info in registry.discover():
        # Register each tool with FastMCP
        tool = registry.get(tool_info.name)

        # FastMCP uses decorator pattern — we register dynamically
        @mcp.tool(name=tool_info.name, description=tool_info.description)
        async def _handler(params: dict = {}, _tool=tool):
            result = await _tool.execute(params)
            return result.data if result.status == "ok" else {"error": result.error}

    return mcp
```

**Note:** The exact FastMCP API may differ — check the library docs with `context7` MCP if needed. The key pattern is: iterate `registry.discover()`, register each tool dynamically with FastMCP.

- [ ] **Step 3: Implement `backend/mcp_server/auth.py`**

JWT authentication dependency for MCP connections. Reuses the existing `get_current_user` dependency from `backend/routers/auth.py`.

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_mcp_server.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/mcp_server/ tests/unit/test_mcp_server.py
git commit -m "feat(4b): add FastMCP server — exposes Tool Registry at /mcp"
```

---

### Task 15: Warm Data Pipeline (Celery Tasks)

**Files:**
- Create: `backend/tasks/warm_data.py`
- Modify: `backend/tasks/__init__.py`

- [ ] **Step 1: Write tests**

Create `tests/unit/test_warm_data.py`:

```python
"""Tests for warm data Celery tasks."""

from unittest.mock import patch, MagicMock, AsyncMock

import pytest


def test_sync_analyst_consensus_task_exists():
    """Task is registered with Celery."""
    from backend.tasks.warm_data import sync_analyst_consensus_task
    assert sync_analyst_consensus_task.name


def test_sync_fred_indicators_task_exists():
    from backend.tasks.warm_data import sync_fred_indicators_task
    assert sync_fred_indicators_task.name


def test_sync_institutional_holders_task_exists():
    from backend.tasks.warm_data import sync_institutional_holders_task
    assert sync_institutional_holders_task.name
```

- [ ] **Step 2: Implement `backend/tasks/warm_data.py`**

Three Celery tasks following the existing `asyncio.run()` bridge pattern from `backend/tasks/market_data.py`:

- `sync_analyst_consensus_task`: Fetches Finnhub analyst ratings for all watched tickers, caches in Redis (24h TTL)
- `sync_fred_indicators_task`: Fetches key FRED series (Fed rate, CPI, 10Y, unemployment, oil), caches in Redis (24h TTL)
- `sync_institutional_holders_task`: Fetches 13F holders for portfolio stocks via EdgarTools, caches in Redis (7d TTL)

Add to Celery Beat schedule (in the existing schedule configuration):
```python
"sync-analyst-consensus": {"task": "...", "schedule": crontab(hour=6, minute=0)},  # Daily 6am ET
"sync-fred-indicators": {"task": "...", "schedule": crontab(hour=7, minute=0)},    # Daily 7am ET
"sync-institutional-holders": {"task": "...", "schedule": crontab(hour=2, minute=0, day_of_week=0)},  # Weekly Sunday 2am ET
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/unit/test_warm_data.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/tasks/warm_data.py backend/tasks/__init__.py tests/unit/test_warm_data.py
git commit -m "feat(4b): add warm data pipeline — analyst, FRED, institutional holder Celery tasks"
```

---

## Chunk 5: Chat Router + Session Management + Integration

### Task 16: Session Management Functions

**Files:**
- Create: `backend/tools/chat_session.py`

Pure functions for session CRUD — no router dependency, independently testable.

- [ ] **Step 1: Write tests**

Create `tests/unit/test_session_management.py`:

```python
"""Tests for chat session management functions."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import uuid

import pytest

from backend.tools.chat_session import (
    create_session,
    load_session_messages,
    expire_inactive_sessions,
    build_context_window,
)


@pytest.mark.asyncio
async def test_build_context_window_under_budget():
    """Messages under token budget are returned as-is."""
    messages = [
        {"role": "user", "content": "Analyze AAPL"},
        {"role": "assistant", "content": "AAPL looks strong."},
    ]
    result = build_context_window(messages, max_tokens=16000)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_build_context_window_truncates():
    """Messages exceeding budget are summarized."""
    # Create enough messages to exceed 16K tokens
    messages = [
        {"role": "user", "content": "x" * 5000}
        for _ in range(10)
    ]
    result = build_context_window(messages, max_tokens=1000)
    assert len(result) < len(messages)
```

- [ ] **Step 2: Implement `backend/tools/chat_session.py`**

Functions:
- `async create_session(db, user_id, agent_type) -> ChatSession`
- `async load_session_messages(db, session_id, limit=20) -> list[dict]`
- `async list_user_sessions(db, user_id) -> list[ChatSession]` — returns active sessions ordered by last_active_at DESC
- `async deactivate_session(db, session_id, user_id) -> None` — soft-delete (set is_active=False), validates ownership
- `async expire_inactive_sessions(db, max_age_hours=24) -> int` — marks sessions inactive
- `build_context_window(messages, max_tokens=16000) -> list[dict]` — pure function, uses tiktoken for counting, truncates oldest messages when over budget
- `auto_title(first_message: str) -> str` — first 100 chars trimmed to word boundary

- [ ] **Step 3: Run tests**

- [ ] **Step 4: Commit**

```bash
git add backend/tools/chat_session.py tests/unit/test_session_management.py
git commit -m "feat(4b): add session management — create, load, expire, context windowing"
```

---

### Task 17: Chat Router

**Files:**
- Create: `backend/routers/chat.py`

- [ ] **Step 1: Write tests**

Create `tests/api/test_chat.py`:

```python
"""API tests for chat endpoints."""

import pytest
from httpx import AsyncClient

# Assumes conftest.py provides `client` and `auth_headers` fixtures


@pytest.mark.asyncio
async def test_chat_stream_requires_auth(client: AsyncClient):
    """POST /chat/stream returns 401 without auth."""
    resp = await client.post("/api/v1/chat/stream", json={"message": "Hi"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_new_session_requires_agent_type(client: AsyncClient, auth_headers):
    """POST /chat/stream without session_id requires agent_type."""
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"message": "Hi"},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # agent_type required for new session


@pytest.mark.asyncio
async def test_chat_sessions_list(client: AsyncClient, auth_headers):
    """GET /chat/sessions returns user's sessions."""
    resp = await client.get("/api/v1/chat/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_chat_session_delete(client: AsyncClient, auth_headers):
    """DELETE /chat/sessions/{id} soft-deletes."""
    # First create a session via the stream endpoint (or directly)
    # Then delete it
    import uuid
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/v1/chat/sessions/{fake_id}", headers=auth_headers)
    assert resp.status_code in (200, 404)  # 404 if session doesn't exist
```

- [ ] **Step 2: Implement `backend/routers/chat.py`**

```python
"""Chat router — streaming chat endpoint + session management."""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.routers.auth import get_current_user
from backend.schemas.chat import ChatRequest, ChatSessionResponse, ChatMessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Stream a chat response via NDJSON."""
    from backend.agents.loop import agentic_loop
    from backend.agents.stock_agent import StockAgent
    from backend.agents.general_agent import GeneralAgent
    from backend.tools.chat_session import create_session, load_session_messages

    # Resolve or create session
    if body.session_id:
        # Resume existing session
        session_messages = await load_session_messages(db, body.session_id)
        agent_type = ...  # Load from ChatSession record
    else:
        if not body.agent_type:
            raise HTTPException(status_code=422, detail="agent_type required for new session")
        session = await create_session(db, user.id, body.agent_type)
        session_messages = []
        agent_type = body.agent_type

    # Select agent
    agent = StockAgent() if agent_type == "stock" else GeneralAgent()

    # Access registry and LLM client from app.state (set during lifespan startup)
    # Note: `request` must be added as a parameter to the endpoint
    registry = request.app.state.registry
    llm = request.app.state.llm_client

    async def event_generator():
        async for event in agentic_loop(
            agent=agent,
            message=body.message,
            history=session_messages,
            registry=registry,
            llm=llm,
        ):
            yield event.to_ndjson() + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
    )


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List user's chat sessions."""
    from backend.tools.chat_session import list_user_sessions
    return await list_user_sessions(db, user.id)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get messages for a session."""
    from backend.tools.chat_session import load_session_messages
    return await load_session_messages(db, session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Soft-delete a chat session."""
    from backend.tools.chat_session import deactivate_session
    await deactivate_session(db, session_id, user.id)
    return {"status": "ok"}
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/api/test_chat.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/chat.py tests/api/test_chat.py
git commit -m "feat(4b): add chat router — POST /stream, GET /sessions, DELETE /sessions/{id}"
```

---

### Task 18: Wire Everything in `main.py`

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add startup initialization**

Add to `backend/main.py`:

1. Import and include the chat router: `app.include_router(chat_router, prefix="/api/v1")`
2. Add a startup event that:
   - Creates the `ToolRegistry` singleton
   - Registers all 7 internal tools
   - Creates all 4 MCP adapters and registers their ProxiedTools
   - Creates the `LLMClient` with configured providers
   - Mounts the FastMCP server at `/mcp`
3. Expose `get_registry()` and `get_llm_client()` module-level getters

Use the FastAPI **lifespan** pattern (not deprecated `@app.on_event("startup")`), and store state on `app.state` (not module globals — CLAUDE.md rule #7 forbids mutable module state):

```python
from contextlib import asynccontextmanager

from backend.tools.registry import ToolRegistry
from backend.tools.analyze_stock import AnalyzeStockTool
from backend.tools.portfolio_exposure import PortfolioExposureTool
from backend.tools.screen_stocks import ScreenStocksTool
from backend.tools.compute_signals_tool import ComputeSignalsTool
from backend.tools.recommendations_tool import RecommendationsTool
from backend.tools.web_search import WebSearchTool
from backend.tools.geopolitical import GeopoliticalEventsTool
from backend.tools.adapters.edgar import EdgarAdapter
from backend.tools.adapters.alpha_vantage import AlphaVantageAdapter
from backend.tools.adapters.fred import FredAdapter
from backend.tools.adapters.finnhub import FinnhubAdapter
from backend.agents.llm_client import LLMClient, RetryPolicy
from backend.agents.providers.groq import GroqProvider
from backend.agents.providers.anthropic import AnthropicProvider
from backend.config import settings


@asynccontextmanager
async def lifespan(app):
    # --- Startup ---
    registry = ToolRegistry()
    # Internal tools
    for tool_cls in [AnalyzeStockTool, PortfolioExposureTool, ScreenStocksTool,
                     ComputeSignalsTool, RecommendationsTool, WebSearchTool, GeopoliticalEventsTool]:
        registry.register(tool_cls())

    # MCP adapter tools — use register_mcp convenience method
    for adapter in [
        EdgarAdapter(),
        AlphaVantageAdapter(api_key=settings.ALPHA_VANTAGE_API_KEY),
        FredAdapter(api_key=settings.FRED_API_KEY),
        FinnhubAdapter(api_key=settings.FINNHUB_API_KEY),
    ]:
        registry.register_mcp(adapter)

    # LLM client
    providers = []
    if settings.GROQ_API_KEY:
        providers.append(GroqProvider(api_key=settings.GROQ_API_KEY))
    if settings.ANTHROPIC_API_KEY:
        providers.append(AnthropicProvider(api_key=settings.ANTHROPIC_API_KEY))
    llm_client = LLMClient(providers=providers)

    # Store on app.state (not module globals — rule #7)
    app.state.registry = registry
    app.state.llm_client = llm_client

    yield

    # --- Shutdown ---
    # Cleanup if needed


app = FastAPI(lifespan=lifespan)
```

In endpoints, access via `request.app.state.registry` and `request.app.state.llm_client`:

```python
from fastapi import Request

@router.post("/stream")
async def chat_stream(body: ChatRequest, request: Request, ...):
    registry = request.app.state.registry
    llm = request.app.state.llm_client
    ...
```

- [ ] **Step 2: Run ALL tests**

```bash
uv run pytest tests/unit/ tests/api/ -v
```

Expected: All 267 existing + ~40 new tests pass

- [ ] **Step 3: Lint**

```bash
uv run ruff check --fix && uv run ruff format
```

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(4b): wire Tool Registry, LLM client, MCP server, chat router in main.py startup"
```

---

### Task 19: End-to-End Smoke Test

**Files:** None new — verification only.

- [ ] **Step 1: Start backend**

```bash
uv run uvicorn backend.main:app --reload --port 8181
```

- [ ] **Step 2: Verify health + tool registry**

```bash
curl http://localhost:8181/health
# Expected: {"status": "ok"}
```

- [ ] **Step 3: Test chat stream via curl**

```bash
# Login first to get cookie
curl -c cookies.txt -X POST http://localhost:8181/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@test.com", "password": "testpassword"}'

# Stream a chat request
curl -b cookies.txt -N http://localhost:8181/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze AAPL", "agent_type": "stock"}'
```

Expected: NDJSON stream with `thinking`, `tool_start`, `tool_result`, `token`, `done` events.

- [ ] **Step 4: Test MCP endpoint**

```bash
# MCP server should respond at /mcp
curl http://localhost:8181/mcp
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -v --tb=short
```

Expected: All tests pass (267 existing + ~40 new ≈ 307 total)

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat(4b): end-to-end verification — chat stream + MCP server working"
```

---

## Post-Implementation Checklist

After all 19 tasks are complete:

- [ ] Run `ruff check --fix && ruff format` — zero errors
- [ ] Run `uv run pytest tests/unit/ tests/api/ -v` — all green
- [ ] Update `PROGRESS.md` with session entry
- [ ] Update `project-plan.md` — mark Phase 4B deliverables with ✅
- [ ] Update Serena memory `project/state` with new test count + resume point
- [ ] Open PR: `feat/KAN-3-tool-orchestration` → `develop` (or per-Story PRs)
