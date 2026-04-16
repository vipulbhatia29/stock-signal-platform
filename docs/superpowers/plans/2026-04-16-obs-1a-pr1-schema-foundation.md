# Obs 1a PR1 — Schema Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans.

**Goal:** Establish the `observability.*` Postgres schema, versioned Pydantic event contracts, the `EventType` enum, and the `uuid-utils` dependency. No application code is touched — pure foundation that PR2-PR5 build on.

**Architecture:** New Alembic migration creates the `observability` schema + `schema_versions` registry table. `backend/observability/schema/v1.py` defines `ObsEventBase` (the envelope every event inherits) plus `EventType` / `AttributionLayer` / `Severity` enums. `uuid-utils` is added for UUIDv7 (used starting PR3).

**Tech Stack:** Alembic, SQLAlchemy 2.0, Pydantic v2, Postgres, `uv`, `uuid-utils` (new).

**Spec reference:** `docs/superpowers/specs/2026-04-16-obs-1a-foundations-design.md` §2.2b, §3.3, §4.1-4.4.

**Prerequisites:** None.

**Dependency for:** PR2 (uses `ObsEventBase`, `EventType`), PR3 (uuid-utils UUIDv7), PR4-PR5 (event envelope).

**Fact-sheet anchors:** Alembic head = `b3c4d5e6f7a8` (migration 029, per §1). `pyproject.toml` deps include `structlog` and `httpx` already but NOT `uuid-utils` (per §11).

---

## File Structure

**Create:**
- `backend/migrations/versions/030_observability_schema.py`
- `backend/observability/schema/__init__.py` (re-exports)
- `backend/observability/schema/v1.py` (`ObsEventBase`, `EventType`, `AttributionLayer`, `Severity`)
- `backend/observability/models/__init__.py` (re-export)
- `backend/observability/models/schema_versions.py` (`SchemaVersion` SQLAlchemy model)
- `tests/unit/observability/__init__.py` (empty)
- `tests/unit/observability/test_schema_v1.py`
- `tests/unit/observability/test_migration_030.py`

**Modify:**
- `pyproject.toml` — add `uuid-utils>=0.12.0` to `[project.dependencies]`
- `uv.lock` — regenerated via `uv sync`

---

## Task 1: Add `uuid-utils` dep

**Files:** `pyproject.toml`, `uv.lock`

- [ ] **Step 1:** Edit `pyproject.toml`, add `"uuid-utils>=0.12.0",` alphabetically between `structlog` and `tiktoken`. Run `uv sync`.
- [ ] **Step 2:** `uv run python -c "import uuid_utils; print(uuid_utils.uuid7())"` → UUIDv7 printed.
- [ ] **Step 3:** Commit: `chore(obs-1a): add uuid-utils dep for UUIDv7 trace_id generation`.

---

## Task 2: Migration 030 — observability schema + schema_versions table

**Files:**
- Create: `backend/migrations/versions/030_observability_schema.py`
- Create: `tests/unit/observability/test_migration_030.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/observability/test_migration_030.py
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_observability_schema_and_seed(db_session):
    schema = (await db_session.execute(
        text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'observability'")
    )).scalar()
    assert schema == "observability"

    cols = {r[0] for r in (await db_session.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='observability' AND table_name='schema_versions'"
    ))).all()}
    assert {"version", "applied_at", "notes"}.issubset(cols)

    seeded = (await db_session.execute(text(
        "SELECT version FROM observability.schema_versions ORDER BY applied_at DESC LIMIT 1"
    ))).scalar()
    assert seeded == "v1"
```

- [ ] **Step 2:** `uv run pytest tests/unit/observability/test_migration_030.py -v` → FAIL (schema absent).

- [ ] **Step 3: Write migration**

```python
# backend/migrations/versions/030_observability_schema.py
"""Observability schema foundation (Obs 1a PR1).

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-16
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS observability"))
    op.create_table(
        "schema_versions",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
        schema="observability",
    )
    op.execute(sa.text(
        "INSERT INTO observability.schema_versions (version, notes) "
        "VALUES ('v1', 'Obs 1a PR1 — initial event contract (ObsEventBase)')"
    ))


def downgrade() -> None:
    op.drop_table("schema_versions", schema="observability")
    op.execute(sa.text("DROP SCHEMA IF EXISTS observability"))
```

- [ ] **Step 4:** `uv run alembic upgrade head && uv run pytest tests/unit/observability/test_migration_030.py -v` → PASS. `uv run alembic current` → `c4d5e6f7a8b9 (head)`.

- [ ] **Step 5: Verify downgrade**

```bash
uv run alembic downgrade b3c4d5e6f7a8
uv run pytest tests/unit/observability/test_migration_030.py -v  # should FAIL (schema gone)
uv run alembic upgrade head                                       # restore
```

- [ ] **Step 6:** Commit: `feat(obs-1a): add migration 030 — observability schema + schema_versions table`.

---

## Task 3: `SchemaVersion` SQLAlchemy model

**Files:**
- Create: `backend/observability/models/__init__.py`, `backend/observability/models/schema_versions.py`

- [ ] **Step 1: Create files**

```python
# backend/observability/models/__init__.py
from backend.observability.models.schema_versions import SchemaVersion
__all__ = ["SchemaVersion"]
```

```python
# backend/observability/models/schema_versions.py
"""SchemaVersion model — pointer to the active Pydantic event contract version.

describe_observability_schema() MCP tool reads the most recent row to report
which Pydantic schema version (v1, v2, ...) agents should expect.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from backend.models.base import Base


class SchemaVersion(Base):
    __tablename__ = "schema_versions"
    __table_args__ = {"schema": "observability"}

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2:** Smoke-test: `uv run python -c "from backend.observability.models import SchemaVersion; print(SchemaVersion.__tablename__, SchemaVersion.__table_args__)"` → `schema_versions {'schema': 'observability'}`.

- [ ] **Step 3:** Commit: `feat(obs-1a): add SchemaVersion SQLAlchemy model`.

---

## Task 4: `ObsEventBase` + enums (`EventType` / `AttributionLayer` / `Severity`)

**Files:**
- Create: `backend/observability/schema/__init__.py`, `backend/observability/schema/v1.py`
- Create: `tests/unit/observability/test_schema_v1.py`

- [ ] **Step 1: Failing tests**

Covers (per spec §4.1-4.4): enum membership, required-field construction, JSON round-trip, rejects naive datetime, rejects invalid env.

```python
# tests/unit/observability/test_schema_v1.py
from datetime import datetime, timezone
from uuid import UUID
import pytest
from pydantic import ValidationError
from backend.observability.schema.v1 import (
    AttributionLayer, EventType, ObsEventBase, Severity,
)


def test_event_type_covers_1a_scope():
    assert {
        "LLM_CALL", "TOOL_EXECUTION", "LOGIN_ATTEMPT", "DQ_FINDING",
        "PIPELINE_LIFECYCLE", "EXTERNAL_API_CALL", "RATE_LIMITER_EVENT",
    }.issubset({e.name for e in EventType})


def test_attribution_layer_enum():
    assert {l.value for l in AttributionLayer} == {
        "http", "auth", "db", "cache", "external_api", "llm",
        "agent", "celery", "frontend", "anomaly_engine",
    }


def test_severity_enum():
    assert {s.value for s in Severity} == {"info", "warning", "error", "critical"}


def _valid_payload(**overrides):
    base = dict(
        event_type=EventType.LLM_CALL,
        trace_id=UUID("01234567-89ab-7def-8123-456789abcdef"),
        span_id=UUID("01234567-89ab-7def-8123-456789abcde0"),
        parent_span_id=None,
        ts=datetime(2026, 4, 16, 12, tzinfo=timezone.utc),
        env="dev",
        git_sha=None, user_id=None, session_id=None, query_id=None,
    )
    base.update(overrides)
    return base


def test_round_trip():
    event = ObsEventBase(**_valid_payload())
    assert ObsEventBase.model_validate_json(event.model_dump_json()) == event


def test_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        ObsEventBase(**_valid_payload(ts=datetime(2026, 4, 16, 12)))  # naive


def test_rejects_invalid_env():
    with pytest.raises(ValidationError):
        ObsEventBase(**_valid_payload(env="production"))  # must be dev/staging/prod
```

- [ ] **Step 2:** Run → FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

```python
# backend/observability/schema/__init__.py
from backend.observability.schema.v1 import (
    AttributionLayer, EventType, ObsEventBase, Severity,
)
__all__ = ["ObsEventBase", "EventType", "Severity", "AttributionLayer"]
```

```python
# backend/observability/schema/v1.py
"""Event contract v1 — baseline fields present on every event.

Per spec §4.1-4.4:
- Every event carries trace_id + span_id + parent_span_id (causality tree)
- ts MUST be tz-aware UTC (never datetime.utcnow)
- env enum-constrained (dev|staging|prod)
- EventType forward-declared with every type used in 1a PR1-PR5

Additive evolution only — bumping to v2 = new `observability.schema_versions` row.
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, field_validator


class EventType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_EXECUTION = "tool_execution"
    LOGIN_ATTEMPT = "login_attempt"
    DQ_FINDING = "dq_finding"
    PIPELINE_LIFECYCLE = "pipeline_lifecycle"
    EXTERNAL_API_CALL = "external_api_call"
    RATE_LIMITER_EVENT = "rate_limiter_event"


class AttributionLayer(str, Enum):
    HTTP = "http"
    AUTH = "auth"
    DB = "db"
    CACHE = "cache"
    EXTERNAL_API = "external_api"
    LLM = "llm"
    AGENT = "agent"
    CELERY = "celery"
    FRONTEND = "frontend"
    ANOMALY_ENGINE = "anomaly_engine"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ObsEventBase(BaseModel):
    """Envelope on every event. Subclasses add payload-specific fields."""

    model_config = ConfigDict(extra="allow", frozen=False, str_strip_whitespace=True)

    event_type: EventType
    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None
    ts: datetime
    env: Literal["dev", "staging", "prod"]
    git_sha: str | None
    user_id: UUID | None
    session_id: UUID | None
    query_id: UUID | None

    @field_validator("ts")
    @classmethod
    def _ts_tz_aware_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must be tz-aware UTC (spec §4.3)")
        return v.astimezone(timezone.utc)
```

- [ ] **Step 4:** `uv run pytest tests/unit/observability/test_schema_v1.py -v` → 6 passed.

- [ ] **Step 5:** Commit: `feat(obs-1a): add ObsEventBase + EventType enum (schema v1)`.

---

## Task 5: `describe_observability_schema()` skeleton

Spec §2.9 — skeleton only in 1a; full MCP registration lands in 1c. Purpose: a plain async function that queries `observability.schema_versions` for the active version and returns a minimal schema manifest. 1c wraps it as an MCP tool.

**Files:**
- Create: `backend/observability/mcp/__init__.py` (empty)
- Create: `backend/observability/mcp/describe_schema.py`
- Create: `tests/unit/observability/test_describe_schema.py`

- [ ] **Step 1: Failing test**

```python
# tests/unit/observability/test_describe_schema.py
import pytest
from backend.observability.mcp.describe_schema import describe_observability_schema


@pytest.mark.asyncio
async def test_describe_returns_current_schema_version(db_session):
    result = await describe_observability_schema()
    assert result["schema_version"] == "v1"
    assert "event_types" in result
    assert "llm_call" in result["event_types"]
```

- [ ] **Step 2: Implement skeleton**

```python
# backend/observability/mcp/describe_schema.py
"""Skeleton for 1c's MCP tool — returns active schema version + event type list.

1c adds: table list with row counts + retention, enum registry, tool manifest.
Keeping the skeleton here so agents calling it at session start don't break mid-1a.
"""
from __future__ import annotations
from sqlalchemy import text
from backend.database import async_session_factory
from backend.observability.schema.v1 import EventType


async def describe_observability_schema() -> dict:
    async with async_session_factory() as db:
        row = (await db.execute(text(
            "SELECT version FROM observability.schema_versions ORDER BY applied_at DESC LIMIT 1"
        ))).scalar()
    return {
        "schema_version": row or "unknown",
        "event_types": [e.value for e in EventType],
    }
```

- [ ] **Step 3:** `uv run pytest tests/unit/observability/test_describe_schema.py -v` → 1 passed.
- [ ] **Step 4:** Commit: `feat(obs-1a): skeleton describe_observability_schema() — 1c extends to MCP tool`.

---

## Task 6: Full-suite sanity + lint

- [ ] `uv run pytest tests/unit/ -q --tb=short` → 2115 + 8 = 2123 passed.
- [ ] `uv run pytest tests/api/ -q --tb=short` → 448 passed, 0 regressions.
- [ ] `uv run ruff check --fix backend/observability/ tests/unit/observability/`
- [ ] `uv run ruff format backend/observability/ tests/unit/observability/`
- [ ] `uv run ruff check backend/observability/ tests/unit/observability/` → 0 errors.
- [ ] `uv run alembic current` → `c4d5e6f7a8b9 (head)`.
- [ ] If ruff edited files, commit: `style(obs-1a): ruff auto-fixes`.

---

## Acceptance Criteria

- [x] `observability` Postgres schema exists; `observability.schema_versions` with `version='v1'` seeded row
- [x] Migration up/down tested green; chain unbroken (029 → 030)
- [x] `backend.observability.schema.v1` exports `ObsEventBase`, `EventType`, `AttributionLayer`, `Severity`
- [x] `ObsEventBase` rejects naive datetimes; `env` restricted to enum values
- [x] `uuid-utils>=0.12.0` in pyproject; UUIDv7 import works
- [x] Full unit + API suite green; zero regressions; net +7 unit tests
- [x] Ruff clean

---

## Risks

| Risk | Mitigation |
|---|---|
| Other migrations merged to `develop` during review → rebase | Conflict detected by `alembic history`; rebase + re-run upgrade |
| `uuid-utils` version too loose | Pin `>=0.12.0` (where UUIDv7 landed); tighten upper bound if breakage observed |
| `extra="allow"` hides typos in subclass event payloads | Subclass PRs add their own validators; test coverage is the guardrail |

---

## Commit Sequence

1. `chore(obs-1a): add uuid-utils dep for UUIDv7 trace_id generation`
2. `feat(obs-1a): add migration 030 — observability schema + schema_versions table`
3. `feat(obs-1a): add SchemaVersion SQLAlchemy model`
4. `feat(obs-1a): add ObsEventBase + EventType enum (schema v1)`
5. (optional) `style(obs-1a): ruff auto-fixes`

PR body references: spec §2.2b, §3.3, §4.1-4.4; JIRA KAN-458, KAN-464; fact sheet §1 (Alembic head 029).
