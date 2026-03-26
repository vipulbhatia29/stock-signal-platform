# Spec D: Portfolio Health Materialization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materialize daily portfolio health snapshots in a TimescaleDB hypertable for trend tracking, add a nightly pipeline task, and expose a history API endpoint.

**Architecture:** `PortfolioHealthSnapshot` model mirrors the pattern of `PortfolioSnapshot` (daily value capture). New Celery Beat task runs at 4:45 PM ET (after value snapshot at 4:30 PM). Also added as Step 9 in nightly pipeline chain. History endpoint returns time series for the health trend chart.

**Tech Stack:** SQLAlchemy, TimescaleDB hypertable, Celery Beat, FastAPI

**Spec:** `docs/superpowers/specs/2026-03-25-health-materialization-design.md`
**Depends on:** Spec B (Agent Intelligence) — uses `compute_portfolio_health()` function from `backend/tools/portfolio_health.py`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/models/portfolio_health.py` | PortfolioHealthSnapshot ORM model |
| Create | `backend/migrations/versions/XXX_014_health_snapshots.py` | Hypertable creation |
| Modify | `backend/schemas/health.py` | Add PortfolioHealthSnapshotResponse |
| Modify | `backend/tasks/portfolio.py` | Add snapshot_health_task |
| Modify | `backend/tasks/__init__.py` | Add Beat schedule entry |
| Modify | `backend/tasks/market_data.py` | Add Step 9 to nightly chain |
| Modify | `backend/routers/portfolio.py` | Add GET /portfolio/health/history |
| Create | `tests/unit/test_health_snapshot.py` | Snapshot computation tests |
| Create | `tests/api/test_health_history.py` | API endpoint tests |

---

### Task 1: PortfolioHealthSnapshot Model + Migration

**Files:**
- Create: `backend/models/portfolio_health.py`
- Create: migration file

- [ ] **Step 1: Create the model**

```python
# backend/models/portfolio_health.py
"""Daily portfolio health score snapshot — TimescaleDB hypertable."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class PortfolioHealthSnapshot(Base):
    """Daily portfolio health score snapshot — one row per portfolio per day."""

    __tablename__ = "portfolio_health_snapshots"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
    )
    health_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    grade: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    diversification_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    signal_quality_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    risk_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    income_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    sector_balance_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    hhi: Mapped[float] = mapped_column(sa.Float, nullable=False)
    weighted_beta: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_sharpe: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_yield: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_composite: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    avg_correlation: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    position_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<PortfolioHealthSnapshot {self.portfolio_id} {self.snapshot_date} score={self.health_score}>"
```

- [ ] **Step 2: Create manual migration (NOT autogenerate)**

Autogenerate tends to rewrite the entire schema for TimescaleDB. Write manually:

```python
# backend/migrations/versions/XXX_014_health_snapshots.py
"""014 — portfolio_health_snapshots hypertable."""

from alembic import op
import sqlalchemy as sa

revision = "..."  # auto-generated
down_revision = "..."  # previous head
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "portfolio_health_snapshots",
        sa.Column("portfolio_id", sa.UUID(), sa.ForeignKey("portfolios.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("health_score", sa.Float(), nullable=False),
        sa.Column("grade", sa.String(3), nullable=False),
        sa.Column("diversification_score", sa.Float(), nullable=False),
        sa.Column("signal_quality_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("income_score", sa.Float(), nullable=False),
        sa.Column("sector_balance_score", sa.Float(), nullable=False),
        sa.Column("hhi", sa.Float(), nullable=False),
        sa.Column("weighted_beta", sa.Float(), nullable=True),
        sa.Column("weighted_sharpe", sa.Float(), nullable=True),
        sa.Column("weighted_yield", sa.Float(), nullable=True),
        sa.Column("weighted_composite", sa.Float(), nullable=True),
        sa.Column("avg_correlation", sa.Float(), nullable=True),
        sa.Column("position_count", sa.Integer(), nullable=False),
    )
    op.execute("SELECT create_hypertable('portfolio_health_snapshots', 'snapshot_date')")


def downgrade():
    op.drop_table("portfolio_health_snapshots")
```

- [ ] **Step 3: Apply migration**

```bash
uv run alembic upgrade head
```

- [ ] **Step 4: Commit**

```bash
git add backend/models/portfolio_health.py backend/migrations/versions/*014*
git commit -m "feat(materialization): PortfolioHealthSnapshot model + migration 014"
```

---

### Task 2: Celery Task + Beat Schedule

**Files:**
- Modify: `backend/tasks/portfolio.py`
- Modify: `backend/tasks/__init__.py`
- Modify: `backend/tasks/market_data.py`

- [ ] **Step 1: Add snapshot_health_task to portfolio.py**

```python
# Add to backend/tasks/portfolio.py

async def _snapshot_health_async() -> dict:
    """Compute and store health snapshots for all portfolios."""
    from datetime import datetime, timezone

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from backend.models.portfolio_health import PortfolioHealthSnapshot
    from backend.tools.portfolio_health import compute_portfolio_health

    async with async_session_factory() as db:
        portfolio_ids = await get_all_portfolio_ids(db)

    computed = 0
    skipped = 0
    for pid in portfolio_ids:
        try:
            async with async_session_factory() as db:
                health = await compute_portfolio_health(pid, db)
                now = datetime.now(timezone.utc)

                stmt = pg_insert(PortfolioHealthSnapshot).values(
                    portfolio_id=pid,
                    snapshot_date=now,
                    health_score=health.health_score,
                    grade=health.grade,
                    diversification_score=next(c.score for c in health.components if c.name == "diversification"),
                    signal_quality_score=next(c.score for c in health.components if c.name == "signal_quality"),
                    risk_score=next(c.score for c in health.components if c.name == "risk"),
                    income_score=next(c.score for c in health.components if c.name == "income"),
                    sector_balance_score=next(c.score for c in health.components if c.name == "sector_balance"),
                    hhi=health.metrics.get("hhi", 0),
                    weighted_beta=health.metrics.get("weighted_beta"),
                    weighted_sharpe=health.metrics.get("weighted_sharpe"),
                    weighted_yield=health.metrics.get("weighted_yield"),
                    weighted_composite=health.metrics.get("weighted_composite"),
                    avg_correlation=health.metrics.get("avg_correlation"),
                    position_count=len(health.position_details),
                ).on_conflict_do_update(
                    constraint="portfolio_health_snapshots_pkey",
                    set_={
                        "health_score": health.health_score,
                        "grade": health.grade,
                        # ... all other fields ...
                    },
                )
                await db.execute(stmt)
                await db.commit()
                computed += 1
        except Exception:
            logger.warning("Failed to snapshot health for portfolio %s", pid, exc_info=True)
            skipped += 1

    logger.info("Health snapshots: %d computed, %d skipped", computed, skipped)
    return {"computed": computed, "skipped": skipped}


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    max_retries=2,
    retry_backoff=True,
    name="backend.tasks.portfolio.snapshot_health_task",
)
def snapshot_health_task(self) -> dict:
    """Capture daily health score snapshots for all portfolios."""
    logger.info("Starting health snapshots (attempt %d)", self.request.retries + 1)
    return asyncio.run(_snapshot_health_async())
```

- [ ] **Step 2: Add Beat schedule entry**

In `backend/tasks/__init__.py`, add after `snapshot-all-portfolios-daily`:

```python
    "snapshot-portfolio-health-daily": {
        "task": "backend.tasks.portfolio.snapshot_health_task",
        "schedule": crontab(hour=16, minute=45),  # 15 min after value snapshot
    },
```

- [ ] **Step 3: Add Step 9 to nightly chain**

In `backend/tasks/market_data.py`, in `nightly_pipeline_chain_task()`, after Step 8:

```python
    # Step 9: Portfolio health snapshots
    logger.info("Nightly chain step 9/9: health snapshots")
    from backend.tasks.portfolio import snapshot_health_task
    results["health_snapshots"] = snapshot_health_task()
```

Update the docstring step count from 8 to 9.

- [ ] **Step 4: Commit**

```bash
git add backend/tasks/portfolio.py backend/tasks/__init__.py backend/tasks/market_data.py
git commit -m "feat(materialization): health snapshot Celery task + Beat schedule + nightly Step 9"
```

---

### Task 3: History API Endpoint

**Files:**
- Modify: `backend/schemas/health.py`
- Modify: `backend/routers/portfolio.py`
- Create: `tests/api/test_health_history.py`

- [ ] **Step 1: Add response schema**

In `backend/schemas/health.py`, add:

```python
class PortfolioHealthSnapshotResponse(BaseModel):
    """A single daily health snapshot for trend display."""
    snapshot_date: str
    health_score: float
    grade: str
    diversification_score: float
    signal_quality_score: float
    risk_score: float
    income_score: float
    sector_balance_score: float
    hhi: float
    weighted_beta: float | None
    weighted_sharpe: float | None
    weighted_yield: float | None
    position_count: int

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Add endpoint**

In `backend/routers/portfolio.py`:

```python
from fastapi import Query

@router.get("/health/history", response_model=list[PortfolioHealthSnapshotResponse])
async def get_health_history(
    days: int = Query(default=90, le=365, ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PortfolioHealthSnapshotResponse]:
    """Get portfolio health score history for trend chart."""
    from datetime import datetime, timedelta, timezone
    from backend.models.portfolio_health import PortfolioHealthSnapshot
    from backend.schemas.health import PortfolioHealthSnapshotResponse

    portfolio = await get_or_create_portfolio(user.id, db)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(PortfolioHealthSnapshot)
        .where(
            PortfolioHealthSnapshot.portfolio_id == portfolio.id,
            PortfolioHealthSnapshot.snapshot_date >= cutoff,
        )
        .order_by(PortfolioHealthSnapshot.snapshot_date.asc())
    )
    return [PortfolioHealthSnapshotResponse.model_validate(r) for r in result.scalars().all()]
```

**IMPORTANT:** This endpoint path `/health/history` must be registered BEFORE the `/{ticker}` pattern in the portfolio router to avoid route shadowing (same gotcha as PR #92).

- [ ] **Step 3: Write API tests**

```python
# tests/api/test_health_history.py
"""API tests for portfolio health history endpoint."""

import pytest
from httpx import AsyncClient


class TestHealthHistory:
    """Tests for GET /api/v1/portfolio/health/history."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated should return 401."""
        response = await client.get("/api/v1/portfolio/health/history")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_empty_list_initially(self, authenticated_client: AsyncClient) -> None:
        """New user with no snapshots should get empty list."""
        response = await authenticated_client.get("/api/v1/portfolio/health/history")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_days_param_validation(self, authenticated_client: AsyncClient) -> None:
        """Days > 365 should return 422."""
        response = await authenticated_client.get("/api/v1/portfolio/health/history?days=500")
        assert response.status_code == 422
```

- [ ] **Step 4: Run tests + commit**

```bash
uv run pytest tests/api/test_health_history.py -v
git add backend/schemas/health.py backend/routers/portfolio.py tests/api/test_health_history.py
git commit -m "feat(materialization): GET /portfolio/health/history endpoint + tests"
```

---

### Task 4: Final Verification

- [ ] **Step 1: Full test suite**

```bash
uv run pytest tests/unit/ tests/api/ -q --tb=short
uv run ruff check backend/ tests/
```

- [ ] **Step 2: Verify migration**

```bash
uv run alembic current  # should show migration 014
```

- [ ] **Step 3: Commit any remaining fixes**

---

## Execution Summary

| Task | Description | New Tests | Files |
|------|-------------|-----------|-------|
| 1 | Model + migration 014 | 0 | 2 |
| 2 | Celery task + Beat schedule + nightly Step 9 | 0 | 3 |
| 3 | History endpoint + schema + tests | 3 | 3 |
| 4 | Final verification | 0 | 0 |
| **Total** | | **~3** | **8** |
