# Spec D: Portfolio Health Materialization — Design Spec

**Date**: 2026-03-25
**Phase**: 7 (KAN-147)
**Status**: Draft
**Depends on**: Spec B (Agent Intelligence — health score computation)

---

## 1. Problem Statement

The portfolio health score (Spec B) is computed on-demand. To show the user "how has my portfolio health changed over time?" and to measure the impact of recommendations ("did following your advice improve my health score?"), we need daily materialized snapshots.

This follows the same pattern as `PortfolioSnapshot` (daily value capture at market close).

---

## 2. Data Model

### 2.1 `PortfolioHealthSnapshot` Table

New TimescaleDB hypertable — one row per portfolio per day.

```python
# backend/models/portfolio_health.py

class PortfolioHealthSnapshot(Base):
    """Daily portfolio health score snapshot — TimescaleDB hypertable."""

    __tablename__ = "portfolio_health_snapshots"

    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
        primary_key=True,
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        primary_key=True,
    )

    # Composite score
    health_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    grade: Mapped[str] = mapped_column(sa.String(3), nullable=False)  # A+, B, C-, etc.

    # Component scores (0-10 each)
    diversification_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    signal_quality_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    risk_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    income_score: Mapped[float] = mapped_column(sa.Float, nullable=False)
    sector_balance_score: Mapped[float] = mapped_column(sa.Float, nullable=False)

    # Raw metrics (for trend analysis)
    hhi: Mapped[float] = mapped_column(sa.Float, nullable=False)
    weighted_beta: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_sharpe: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_yield: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    weighted_composite: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    avg_correlation: Mapped[float | None] = mapped_column(sa.Float, nullable=True)
    position_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
```

### 2.2 Migration 014

```sql
CREATE TABLE portfolio_health_snapshots (
    portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    snapshot_date TIMESTAMPTZ NOT NULL,
    health_score FLOAT NOT NULL,
    grade VARCHAR(3) NOT NULL,
    diversification_score FLOAT NOT NULL,
    signal_quality_score FLOAT NOT NULL,
    risk_score FLOAT NOT NULL,
    income_score FLOAT NOT NULL,
    sector_balance_score FLOAT NOT NULL,
    hhi FLOAT NOT NULL,
    weighted_beta FLOAT,
    weighted_sharpe FLOAT,
    weighted_yield FLOAT,
    weighted_composite FLOAT,
    avg_correlation FLOAT,
    position_count INTEGER NOT NULL,
    PRIMARY KEY (portfolio_id, snapshot_date)
);

-- TimescaleDB hypertable
SELECT create_hypertable('portfolio_health_snapshots', 'snapshot_date');
```

Upsert pattern (same day re-run updates, doesn't duplicate):
```sql
INSERT INTO portfolio_health_snapshots (...) VALUES (...)
ON CONFLICT (portfolio_id, snapshot_date) DO UPDATE SET
    health_score = EXCLUDED.health_score, ...
```

---

## 3. Pipeline Integration

### 3.1 New Celery Task

```python
# backend/tasks/portfolio.py — add new task

async def _snapshot_health_async() -> dict:
    """Compute and store health snapshots for all portfolios."""
    from backend.tools.portfolio_health import compute_portfolio_health

    async with async_session_factory() as db:
        portfolio_ids = await get_all_portfolio_ids(db)

    computed = 0
    for pid in portfolio_ids:
        async with async_session_factory() as db:
            try:
                health = await compute_portfolio_health(pid, db)
                snapshot = PortfolioHealthSnapshot(
                    portfolio_id=pid,
                    snapshot_date=datetime.now(timezone.utc),
                    health_score=health.health_score,
                    grade=health.grade,
                    # ... all component scores and metrics ...
                )
                # Upsert
                await db.execute(
                    pg_insert(PortfolioHealthSnapshot)
                    .values(...)
                    .on_conflict_do_update(...)
                )
                await db.commit()
                computed += 1
            except Exception:
                logger.warning("Failed to snapshot health for portfolio %s", pid)

    return {"computed": computed, "total": len(portfolio_ids)}


@celery_app.task(name="backend.tasks.portfolio.snapshot_health_task")
def snapshot_health_task() -> dict:
    return asyncio.run(_snapshot_health_async())
```

### 3.2 Beat Schedule

Add after `snapshot-all-portfolios-daily`:

```python
"snapshot-portfolio-health-daily": {
    "task": "backend.tasks.portfolio.snapshot_health_task",
    "schedule": crontab(hour=16, minute=45),  # 15 min after value snapshot
},
```

### 3.3 Nightly Pipeline

Also add as Step 9 in `nightly_pipeline_chain_task` (after portfolio value snapshots):

```python
# Step 9: Portfolio health snapshots
logger.info("Nightly chain step 9/9: health snapshots")
results["health_snapshots"] = snapshot_health_task()
```

---

## 4. API Endpoint

### 4.1 `GET /api/v1/portfolio/health/history`

**Router:** `backend/routers/portfolio.py`
**Auth:** Required
**Query params:** `days` (default 90, max 365)

```python
@router.get("/health/history", response_model=list[PortfolioHealthSnapshotResponse])
async def get_health_history(
    days: int = Query(default=90, le=365),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[PortfolioHealthSnapshotResponse]:
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

---

## 5. Files Changed

| Action | File | Change |
|--------|------|--------|
| **Create** | `backend/models/portfolio_health.py` | PortfolioHealthSnapshot model |
| **Create** | `backend/migrations/versions/XXX_014_health_snapshots.py` | Hypertable creation |
| **Modify** | `backend/tasks/portfolio.py` | Add snapshot_health_task |
| **Modify** | `backend/tasks/__init__.py` | Add beat schedule entry |
| **Modify** | `backend/tasks/market_data.py` | Add Step 9 to nightly chain |
| **Modify** | `backend/routers/portfolio.py` | Add GET /portfolio/health/history |
| **Create** | `backend/schemas/health.py` (extend) | PortfolioHealthSnapshotResponse |
| **Create** | `tests/unit/test_health_snapshot.py` | Snapshot computation tests |
| **Create** | `tests/api/test_health_history.py` | API endpoint tests |

---

## 6. Success Criteria

- [ ] `portfolio_health_snapshots` table created as TimescaleDB hypertable
- [ ] Daily health snapshots captured at 4:45 PM ET
- [ ] Health snapshots also captured during nightly chain (Step 9)
- [ ] `GET /portfolio/health/history?days=90` returns time series
- [ ] Upsert pattern — re-running same day updates without duplicate
- [ ] All component scores and raw metrics persisted
- [ ] Can track health score trend over 90+ days

---

## 7. Out of Scope

- Health score trend chart on frontend → UI phase
- Health score alerts ("your score dropped below 5") → can use existing alert system later
- Per-position health contribution history → just the aggregate for now
- Health score in recommendations ("your score improved after following advice") → future
