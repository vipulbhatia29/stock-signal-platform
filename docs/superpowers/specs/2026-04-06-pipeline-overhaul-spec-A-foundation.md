# Spec A: Ingestion Foundation

## Status, Date, Authors

- **Status:** Draft (awaiting PM approval)
- **Date:** 2026-04-06
- **Authors:** Platform / Backend working group
- **Epic:** Pipeline Overhaul (Phase 1 of 4)
- **Depends on:** nothing
- **Blocks:** Spec B (pipeline completeness), Spec C (entry-point unification), Spec D (admin observability)

---

## Problem Statement

The stock signal platform runs a multi-stage nightly ingestion pipeline (price refresh → signals → fundamentals → forecast → news/sentiment → convergence → backtest), but the system currently has **no per-ticker, per-stage freshness visibility** and **no consistent task instrumentation contract**. Concretely:

1. **No ticker-level freshness table.**
   - `stocks.last_fetched_at` exists (single column, price-only) but there is no structure that tells us "when was AAPL's signal snapshot last refreshed?" or "is NVDA's forecast older than the SLA?"
   - The admin UI cannot answer "which tickers in the universe are red across which stages?" without ad-hoc SQL across 7+ tables (`stock_prices`, `signal_snapshots`, `forecast_results`, `news_articles`, `news_sentiment_daily`, `signal_convergence_daily`, `backtest_runs`).
   - Gap detection today is watermark-based and operates at the *pipeline* level (`pipeline_watermarks` keyed on `pipeline_name`, `backend/models/pipeline.py:12-25`) — not per-ticker.

2. **No staleness SLA.**
   - There is no documented or code-level definition of what "fresh" means for each stage. Downstream tasks and admin UIs cannot flag stale data because there is no threshold to compare against.
   - `backend/config.py` today has DB, auth, CORS, LLM keys, and rate-limit settings — nothing about data-freshness SLAs.

3. **Inconsistent PipelineRunner adoption.**
   - `PipelineRunner` exists at `backend/tasks/pipeline.py:24-234` with a clean lifecycle API (`start_run`, `record_ticker_success`, `record_ticker_failure`, `record_step_duration`, `complete_run`, `update_watermark`). It is good infrastructure.
   - Today it is instantiated in **4** task modules (`backend/tasks/forecasting.py:19`, `backend/tasks/market_data.py:27`, `backend/tasks/recommendations.py:12`, `backend/tasks/evaluation.py:16`), each with hand-rolled `try/start_run/record_*/complete_run` boilerplate. The other task modules (`news_sentiment.py`, `convergence.py`, `alerts.py`, `audit.py`, `portfolio.py`, `warm_data.py`, `seed_tasks.py`) do not use it at all — they are invisible to `pipeline_runs` observability.
   - There is no decorator or common wrapper, so adoption is uneven and regressions (forgetting `complete_run` on an error path) are easy to introduce.

4. **No helper for tracing non-agent Celery tasks in Langfuse.**
   - `LangfuseService` (`backend/observability/langfuse.py:16-144`) is designed for **agent** query tracing — every method takes a `trace_id: uuid.UUID` plus `session_id` and `user_id` which have no meaning for nightly jobs.
   - `ObservabilityCollector.record_request` (`backend/observability/collector.py:52-83`) similarly expects LLM-call semantics (provider, model, tier, tokens) — there is no "record a Celery task step" primitive.
   - Task modules like `backend/tasks/news_sentiment.py` (sentiment scoring LLM calls) and `backend/tasks/forecasting.py` (Prophet training) have **zero Langfuse visibility** today — if something degrades at 02:00 UTC we find out the next morning from empty charts, not from traces.
   - ContextVars in `backend/observability/context.py:15-27` (`current_query_id`, `current_session_id`, `current_agent_type`) are all agent-scoped — nothing to propagate to non-agent task observability.

We cannot deliver the rest of the pipeline overhaul (Specs B/C/D) without first fixing this foundation. Every later spec writes into `ticker_ingestion_state`, reads from `StalenessSLAs`, wraps Celery tasks with `@tracked_task`, or traces via `task_tracer` — so those primitives must land first.

---

## Goals

1. Create a **`ticker_ingestion_state`** table, model, and service that tracks per-ticker, per-stage freshness for 8 stages (prices, signals, fundamentals, forecast, news, sentiment, convergence, backtest).
2. Define **staleness SLAs** as versioned, importable constants the whole codebase (services, tasks, admin UI queries) can rely on.
3. Extend `PipelineRunner` with a **`@tracked_task`** decorator that provides a single-line way to wrap a Celery task in the full run lifecycle, eliminating boilerplate and making adoption trivial.
4. Add a **`task_tracer`** async context manager that wraps Langfuse trace creation + `ObservabilityCollector` recording for non-agent code paths (Prophet training, sentiment scoring, news ingestion, convergence, backtest).
5. Ship all of the above with **tests** (unit for service + decorator + tracer, integration against a real Postgres via testcontainers for the state table).
6. **Do NOT** wire the call sites in this spec — keep the change additive and easy to review. Specs B/C/D adopt the primitives.

---

## Non-Goals

- **No call-site adoption.** The 4 tasks already using `PipelineRunner()` keep their existing code. Adoption of `@tracked_task` is deferred to Spec D.
- **No admin endpoints.** `get_universe_health()` service exists but no router mounts it. Spec D adds `/api/v1/admin/ingestion/health`.
- **No UI.** Readiness rendering (red/yellow/green dashboard) is in Spec G.
- **No changes to `stocks.last_fetched_at`.** That column stays put; the new table lives alongside.
- **No backfill of forecast/signals/etc. timestamps.** Migration seeds only `prices_updated_at` from `stocks.last_fetched_at`; other columns start NULL and are filled organically as tasks run.
- **No changes to `pipeline_runs` or `pipeline_watermarks` schemas.** Those stay exactly as they are.
- **No Langfuse schema changes.** `task_tracer` uses the existing trace API.

---

## Design

### A1. Ticker ingestion state table

#### Schema — exact DDL

```sql
CREATE TABLE ticker_ingestion_state (
    ticker                 VARCHAR(10)  PRIMARY KEY REFERENCES stocks(ticker) ON DELETE CASCADE,
    prices_updated_at      TIMESTAMPTZ  NULL,
    signals_updated_at     TIMESTAMPTZ  NULL,
    fundamentals_updated_at TIMESTAMPTZ NULL,
    forecast_updated_at    TIMESTAMPTZ  NULL,
    forecast_retrained_at  TIMESTAMPTZ  NULL,   -- last full Prophet retrain (not cheap refit)
    news_updated_at        TIMESTAMPTZ  NULL,
    sentiment_updated_at   TIMESTAMPTZ  NULL,
    convergence_updated_at TIMESTAMPTZ  NULL,
    backtest_updated_at    TIMESTAMPTZ  NULL,
    recommendation_updated_at TIMESTAMPTZ NULL,
    last_error             JSONB        NULL,   -- {"stage": str, "message": str, "at": iso8601}
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX ix_ticker_ingestion_state_prices_updated_at
    ON ticker_ingestion_state (prices_updated_at);
CREATE INDEX ix_ticker_ingestion_state_signals_updated_at
    ON ticker_ingestion_state (signals_updated_at);
CREATE INDEX ix_ticker_ingestion_state_forecast_updated_at
    ON ticker_ingestion_state (forecast_updated_at);
```

Notes:
- **One row per ticker**, ~1-3 KB, ~5-10k rows max — small, fits in a buffer.
- `ticker` PK + `ON DELETE CASCADE` matches existing `Stock.ticker` FK pattern (see `backend/models/price.py`, `backend/models/signal.py`).
- **No TimescaleDB hypertable** — this is mutable current-state, not time series. The history is in `pipeline_runs` and the domain tables themselves.
- `forecast_retrained_at` distinguishes a full retrain (expensive, 14-day SLA) from a refit on new data (cheap, daily). Both update `forecast_updated_at`; only retrain updates `forecast_retrained_at`.
- Indexes on the hot query columns only — admin dashboards filter on "where prices/signals/forecast are stale". Other columns can scan.

#### Migration file

- **Path:** `backend/migrations/versions/025_ticker_ingestion_state.py`
- **Revision ID:** new, e.g. `e1f2a3b4c5d6`
- **down_revision:** `"b2351fa2d293"` (024 forecast intelligence tables — current head per MEMORY.md)
- **Upgrade:**
  1. `op.create_table("ticker_ingestion_state", ...)` — 11 columns, PK on `ticker`, FK to `stocks.ticker` with CASCADE.
  2. Create three indexes.
  3. Backfill: `INSERT INTO ticker_ingestion_state (ticker, prices_updated_at, created_at, updated_at) SELECT ticker, last_fetched_at, now(), now() FROM stocks;`
  4. No TimescaleDB calls (not a hypertable).
- **Downgrade:**
  1. `op.drop_index(...)` × 3
  2. `op.drop_table("ticker_ingestion_state")`

This is strictly additive. An empty table is a valid state, and the FK cascade means we inherit `stocks` lifecycle.

#### Model file

- **Path:** `backend/models/ticker_ingestion_state.py`

```python
"""Per-ticker, per-stage ingestion freshness tracking."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class TickerIngestionState(Base):
    """One row per ticker — freshness timestamps for each pipeline stage.

    Mutable current-state table (NOT time-series). History lives in
    pipeline_runs and the domain tables themselves.
    """

    __tablename__ = "ticker_ingestion_state"

    ticker: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        primary_key=True,
    )

    prices_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    signals_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fundamentals_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    forecast_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    forecast_retrained_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    news_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sentiment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    convergence_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    backtest_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recommendation_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    def __repr__(self) -> str:
        return f"<TickerIngestionState {self.ticker}>"
```

This model must be imported in `backend/models/__init__.py` (see `backend/models/__init__.py:1-74`) so Alembic autogenerate and test teardown discover it.

#### Service file

- **Path:** `backend/services/ticker_state.py`

```python
"""Per-ticker, per-stage ingestion freshness service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.config import settings
from backend.database import async_session_factory
from backend.models.ticker_ingestion_state import TickerIngestionState

logger = logging.getLogger(__name__)

Stage = Literal[
    "prices",
    "signals",
    "fundamentals",
    "forecast",
    "forecast_retrain",
    "news",
    "sentiment",
    "convergence",
    "backtest",
    "recommendation",
]

StageStatus = Literal["green", "yellow", "red", "unknown"]

# Stage -> column name. "forecast_retrain" writes to forecast_retrained_at.
_STAGE_COLUMNS: dict[Stage, str] = {
    "prices": "prices_updated_at",
    "signals": "signals_updated_at",
    "fundamentals": "fundamentals_updated_at",
    "forecast": "forecast_updated_at",
    "forecast_retrain": "forecast_retrained_at",
    "news": "news_updated_at",
    "sentiment": "sentiment_updated_at",
    "convergence": "convergence_updated_at",
    "backtest": "backtest_updated_at",
    "recommendation": "recommendation_updated_at",
}


@dataclass(frozen=True, slots=True)
class ReadinessState:
    """Per-ticker freshness snapshot with per-stage status buckets."""

    ticker: str
    stages: dict[Stage, StageStatus]
    timestamps: dict[Stage, datetime | None]
    overall: StageStatus  # min(green, yellow, red) — worst-stage wins


@dataclass(frozen=True, slots=True)
class ReadinessRow:
    """Flat row for the universe health dashboard."""

    ticker: str
    prices: StageStatus
    signals: StageStatus
    fundamentals: StageStatus
    forecast: StageStatus
    news: StageStatus
    sentiment: StageStatus
    convergence: StageStatus
    backtest: StageStatus
    overall: StageStatus


async def mark_stage_updated(ticker: str, stage: Stage) -> None:
    """Idempotent upsert of the stage timestamp for a ticker.

    Called by every task completion path in Specs B/C/D. Safe to call
    concurrently — uses ON CONFLICT DO UPDATE.

    Args:
        ticker: Stock ticker symbol.
        stage: Which pipeline stage just completed.
    """
    now = datetime.now(timezone.utc)
    col = _STAGE_COLUMNS[stage]
    values = {
        "ticker": ticker,
        col: now,
        "created_at": now,
        "updated_at": now,
    }
    stmt = insert(TickerIngestionState).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker"],
        set_={col: now, "updated_at": now},
    )
    try:
        async with async_session_factory() as session:
            await session.execute(stmt)
            await session.commit()
    except Exception:
        logger.warning(
            "Failed to mark stage %s for ticker %s", stage, ticker, exc_info=True
        )
        # fire-and-forget — we never want observability writes to kill a task


async def get_ticker_readiness(ticker: str) -> ReadinessState:
    """Return freshness status for a single ticker across all stages.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        ReadinessState with per-stage status and the worst-stage overall.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(TickerIngestionState).where(
                TickerIngestionState.ticker == ticker
            )
        )
        row = result.scalar_one_or_none()

    return _compute_readiness(ticker, row)


async def get_universe_health() -> list[ReadinessRow]:
    """Return freshness status for every ticker in the universe.

    Returns:
        One ReadinessRow per ticker in the ticker_ingestion_state table,
        sorted by overall status (red first) then ticker.
    """
    async with async_session_factory() as session:
        result = await session.execute(select(TickerIngestionState))
        rows = list(result.scalars())

    readiness = [_compute_readiness(r.ticker, r) for r in rows]
    return [_to_row(r) for r in sorted(
        readiness,
        key=lambda r: (
            {"red": 0, "yellow": 1, "unknown": 2, "green": 3}[r.overall],
            r.ticker,
        ),
    )]


def _compute_readiness(
    ticker: str, row: TickerIngestionState | None
) -> ReadinessState:
    """Compute per-stage status from a row (or absence thereof)."""
    sla = settings.staleness_slas
    now = datetime.now(timezone.utc)

    def status_for(ts: datetime | None, green: timedelta, yellow: timedelta) -> StageStatus:
        if ts is None:
            return "unknown"
        age = now - ts
        if age <= green:
            return "green"
        if age <= yellow:
            return "yellow"
        return "red"

    timestamps: dict[Stage, datetime | None] = {
        "prices": row.prices_updated_at if row else None,
        "signals": row.signals_updated_at if row else None,
        "fundamentals": row.fundamentals_updated_at if row else None,
        "forecast": row.forecast_updated_at if row else None,
        "forecast_retrain": row.forecast_retrained_at if row else None,
        "news": row.news_updated_at if row else None,
        "sentiment": row.sentiment_updated_at if row else None,
        "convergence": row.convergence_updated_at if row else None,
        "backtest": row.backtest_updated_at if row else None,
    }

    # Yellow = 2 x green SLA. Red = > 2 x green SLA.
    stages: dict[Stage, StageStatus] = {
        "prices": status_for(timestamps["prices"], sla.prices, sla.prices * 2),
        "signals": status_for(timestamps["signals"], sla.signals, sla.signals * 2),
        "fundamentals": status_for(
            timestamps["fundamentals"], sla.fundamentals, sla.fundamentals * 2
        ),
        "forecast": status_for(timestamps["forecast"], sla.forecast, sla.forecast * 2),
        "forecast_retrain": status_for(
            timestamps["forecast_retrain"],
            sla.forecast_retrain,
            sla.forecast_retrain * 2,
        ),
        "news": status_for(timestamps["news"], sla.news, sla.news * 2),
        "sentiment": status_for(timestamps["sentiment"], sla.sentiment, sla.sentiment * 2),
        "convergence": status_for(
            timestamps["convergence"], sla.convergence, sla.convergence * 2
        ),
        "backtest": status_for(timestamps["backtest"], sla.backtest, sla.backtest * 2),
    }

    overall = _worst(stages.values())
    return ReadinessState(
        ticker=ticker, stages=stages, timestamps=timestamps, overall=overall
    )


def _worst(values) -> StageStatus:  # noqa: ANN001
    """Return the worst stage status (red > yellow > unknown > green)."""
    priority = {"red": 0, "yellow": 1, "unknown": 2, "green": 3}
    return min(values, key=lambda s: priority[s], default="unknown")


def _to_row(r: ReadinessState) -> ReadinessRow:
    """Flatten a ReadinessState into a dashboard row (drops forecast_retrain)."""
    s = r.stages
    return ReadinessRow(
        ticker=r.ticker,
        prices=s["prices"],
        signals=s["signals"],
        fundamentals=s["fundamentals"],
        forecast=s["forecast"],
        news=s["news"],
        sentiment=s["sentiment"],
        convergence=s["convergence"],
        backtest=s["backtest"],
        overall=r.overall,
    )
```

**Concurrency**: `mark_stage_updated` is called from many Celery workers in parallel. Postgres `INSERT ... ON CONFLICT DO UPDATE` is atomic and our hot-path contention is one row per ticker, so lock wait is negligible.

**Error policy**: The service wraps its write in try/except and logs at warning. An observability write failure must never kill the underlying ingestion task. This matches the existing fire-and-forget pattern in `ObservabilityCollector._safe_db_write` (`backend/observability/collector.py:303-308`).

---

### A2. Staleness SLA constants

- **File:** `backend/config.py` (edit in place, append new settings class)

```python
from datetime import timedelta

class StalenessSLAs:
    """Green-threshold freshness SLAs per pipeline stage.

    Yellow = 2x green. Red = >2x green. See services/ticker_state.py
    for the bucketing logic.

    These are module-level constants (immutable) rather than a Pydantic
    settings class because they are a *product decision*, not an env knob.
    If a deployment wants tighter SLAs, bump the constants in a PR — don't
    flip them per-environment.
    """

    prices: timedelta = timedelta(hours=4)
    signals: timedelta = timedelta(hours=4)
    fundamentals: timedelta = timedelta(hours=24)
    forecast: timedelta = timedelta(hours=24)
    forecast_retrain: timedelta = timedelta(days=14)
    news: timedelta = timedelta(hours=6)
    sentiment: timedelta = timedelta(hours=6)
    convergence: timedelta = timedelta(hours=24)
    backtest: timedelta = timedelta(days=7)
```

And expose it via the existing `settings` singleton:

```python
class Settings(BaseSettings):
    # ... existing fields ...

    @property
    def staleness_slas(self) -> StalenessSLAs:
        return StalenessSLAs()
```

The choice of a plain class (not `BaseSettings`) is intentional: **SLAs are not env-configurable**. A product decision that forecast freshness is 24h should live in code, reviewed in a PR, not silently overridden by a deploy env var. Tests that need to override use monkeypatch.

---

### A3. PipelineRunner unified contract

#### Existing state

- `PipelineRunner` class: `backend/tasks/pipeline.py:24-234`.
  - `start_run(pipeline_name, trigger, tickers_total) -> UUID` (lines 27-63)
  - `record_ticker_success(run_id, ticker)` (lines 65-77)
  - `record_ticker_failure(run_id, ticker, error)` (lines 79-95)
  - `record_step_duration(run_id, step_name, duration_seconds)` (lines 97-130, atomic JSONB merge)
  - `complete_run(run_id) -> status` (lines 132-165)
  - `update_watermark(pipeline_name, completed_date)` (lines 167-199)
  - `detect_stale_runs()` (lines 201-234)
- Free functions: `detect_gap` (lines 242-287), `set_watermark_status` (lines 290-303), `with_retry` (lines 311-351).

#### Current callers

Grep `PipelineRunner()` in `backend/tasks/`:

| File | Line | Usage |
|---|---|---|
| `backend/tasks/forecasting.py` | 19 | module-level `_runner = PipelineRunner()` |
| `backend/tasks/market_data.py` | 27 | module-level `_runner = PipelineRunner()` |
| `backend/tasks/recommendations.py` | 12 | module-level `_runner = PipelineRunner()` |
| `backend/tasks/evaluation.py` | 16 | module-level `_runner = PipelineRunner()` |

Each caller hand-rolls the `start_run` / `record_*` / `complete_run` lifecycle inside the task body. The **other** task modules (`news_sentiment.py`, `convergence.py`, `alerts.py`, `audit.py`, `portfolio.py`, `warm_data.py`, `seed_tasks.py`) don't use PipelineRunner at all — invisible to `pipeline_runs`.

#### New `@tracked_task` decorator

- **File:** `backend/tasks/pipeline.py` (append to existing module)

```python
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


def tracked_task(
    pipeline_name: str,
    *,
    trigger: str = "scheduled",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorate an async task function with the PipelineRunner lifecycle.

    The decorated function is called with `run_id: UUID` as an extra
    keyword arg — it can use it to call `record_ticker_success`, etc.
    If the inner function raises, the run is marked failed and the
    exception propagates.

    Usage (adopted in Spec D, not this spec):

        @shared_task(name="tasks.news_sentiment")
        def nightly_news_sentiment_task() -> dict:
            return asyncio.run(_run())

        @tracked_task("news_sentiment")
        async def _run(*, run_id: uuid.UUID) -> dict:
            tickers = await _load_universe()
            for t in tickers:
                try:
                    await _score_one(t)
                    await _runner.record_ticker_success(run_id, t)
                except Exception as e:
                    await _runner.record_ticker_failure(run_id, t, repr(e))
            return {"tickers": len(tickers)}

    Args:
        pipeline_name: Name recorded in pipeline_runs.pipeline_name.
        trigger: "scheduled" | "backfill" | "manual".

    Returns:
        A decorator that wraps an async function.
    """
    def decorator(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        runner = PipelineRunner()

        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tickers_total = kwargs.pop("tickers_total", 0)  # type: ignore[assignment]
            run_id = await runner.start_run(
                pipeline_name=pipeline_name,
                trigger=trigger,
                tickers_total=tickers_total,
            )
            try:
                result = await fn(*args, run_id=run_id, **kwargs)  # type: ignore[arg-type]
            except Exception:
                logger.exception(
                    "Tracked task %s crashed — marking run %s failed",
                    pipeline_name,
                    run_id,
                )
                async with async_session_factory() as session:
                    stmt = (
                        update(PipelineRun)
                        .where(PipelineRun.id == run_id)
                        .values(
                            status="failed",
                            completed_at=datetime.now(timezone.utc),
                            error_summary={"_exception": "see logs"},
                        )
                    )
                    await session.execute(stmt)
                    await session.commit()
                raise
            else:
                await runner.complete_run(run_id)
                return result

        return wrapper

    return decorator
```

Design notes:
- **Kwarg injection of `run_id`.** The decorated function must accept a keyword-only `run_id: uuid.UUID` parameter. This is explicit and testable (no hidden globals).
- **`tickers_total` passthrough.** Callers pass it in `kwargs`; the decorator consumes it before forwarding to `fn`. Default 0 (tasks that process the whole universe can pass it after counting).
- **Error path.** Do not swallow — always re-raise so Celery retry policy still triggers. But before re-raise, update the `PipelineRun` row to status=failed.
- **Error summary.** We write `{"_exception": "see logs"}` — deliberately *not* `repr(exc)` or `str(exc)`. Hard Rule #10: no `str(e)` in observability writes. Operators look at Sentry/logs for the real traceback.
- **No Langfuse.** Task-level Langfuse tracing is the `task_tracer`'s job (A4) — decorator stays narrow.

#### Migration path for existing 4 callers

**NOT in this spec.** The 4 existing callers keep their current hand-rolled code. Spec D refactors them to use `@tracked_task` one at a time, behind green tests. This spec ships the decorator + tests; nothing calls it yet in production code.

---

### A4. Task tracer helper

- **File:** `backend/services/observability/task_tracer.py` (new package: also needs `backend/services/observability/__init__.py`)

```python
"""Task-level tracing helper for non-agent Celery code paths.

Wraps Langfuse trace creation + ObservabilityCollector recording so
nightly jobs (sentiment scoring, Prophet training, news ingestion,
convergence, backtest) get the same visibility agents get today.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from backend.observability.langfuse import LangfuseService
from backend.observability.collector import ObservabilityCollector

logger = logging.getLogger(__name__)


@asynccontextmanager
async def trace_task(
    name: str,
    *,
    langfuse: LangfuseService,
    collector: ObservabilityCollector,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator["TaskTraceHandle"]:
    """Trace a non-agent task block in Langfuse + the DB collector.

    Usage:
        async with trace_task(
            "nightly_sentiment_scoring",
            langfuse=langfuse_service,
            collector=observability_collector,
            metadata={"ticker_count": 500},
        ) as handle:
            await do_work()
            handle.add_metadata(articles_scored=1234)
            handle.record_llm(
                model="gpt-4o-mini",
                provider="openai",
                tier="cheap",
                latency_ms=450,
                prompt_tokens=300,
                completion_tokens=40,
                cost_usd=0.0012,
            )

    On exit, the trace is ended; on exception, status is set to "error"
    and the exception re-raises.

    Args:
        name: Human-readable task name (e.g., "nightly_sentiment_scoring").
        langfuse: The app-level LangfuseService (may be disabled — no-op safe).
        collector: The app-level ObservabilityCollector.
        metadata: Optional initial metadata dict (ticker count, config, etc).
    """
    trace_id = uuid.uuid4()
    # Non-agent: session_id/user_id don't exist. Reuse trace_id as a
    # stable identifier so Langfuse doesn't null-pointer.
    trace = langfuse.create_trace(
        trace_id=trace_id,
        session_id=trace_id,
        user_id=trace_id,
        metadata={"task": name, **(metadata or {})},
    )
    handle = TaskTraceHandle(
        name=name,
        trace_id=trace_id,
        trace=trace,
        langfuse=langfuse,
        collector=collector,
    )
    started_at = time.perf_counter()
    try:
        yield handle
    except Exception as exc:
        handle._status = "error"
        handle._error = type(exc).__name__
        logger.warning("trace_task %s failed: %s", name, type(exc).__name__)
        raise
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        handle._duration_ms = duration_ms
        await handle._finalize()


class TaskTraceHandle:
    """Handle yielded by trace_task — exposes metadata and LLM recording."""

    def __init__(
        self,
        *,
        name: str,
        trace_id: uuid.UUID,
        trace: Any | None,
        langfuse: LangfuseService,
        collector: ObservabilityCollector,
    ) -> None:
        self.name = name
        self.trace_id = trace_id
        self._trace = trace
        self._langfuse = langfuse
        self._collector = collector
        self._metadata: dict[str, Any] = {}
        self._status: str = "completed"
        self._error: str | None = None
        self._duration_ms: int = 0

    def add_metadata(self, **kwargs: Any) -> None:
        """Attach metadata to the trace (flushed on exit)."""
        self._metadata.update(kwargs)

    async def record_llm(
        self,
        *,
        model: str,
        provider: str,
        tier: str,
        latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float | None = None,
    ) -> None:
        """Record an LLM call made inside this task (e.g. sentiment scorer)."""
        await self._collector.record_request(
            model=model,
            provider=provider,
            tier=tier,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            status="completed",
            langfuse_trace_id=self.trace_id,
        )

    async def _finalize(self) -> None:
        """End the trace with final metadata (fire-and-forget)."""
        if self._trace is None:
            return
        try:
            self._trace.update(
                metadata={
                    "task": self.name,
                    "status": self._status,
                    "error": self._error,
                    "duration_ms": self._duration_ms,
                    **self._metadata,
                }
            )
        except Exception:
            logger.warning("trace_task finalize failed for %s", self.name, exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singletons — set from FastAPI lifespan (main.py) so callers can
# `from backend.services.observability.task_tracer import langfuse_service`
# and tests can patch `backend.services.observability.task_tracer.langfuse_service`.
# ─────────────────────────────────────────────────────────────────────────────

langfuse_service: LangfuseService | None = None
observability_collector: ObservabilityCollector | None = None


def set_langfuse_service(svc: LangfuseService | None) -> None:
    """Called from main.py lifespan to publish the app-level LangfuseService."""
    global langfuse_service
    langfuse_service = svc


def set_observability_collector(coll: ObservabilityCollector | None) -> None:
    """Called from main.py lifespan to publish the app-level collector."""
    global observability_collector
    observability_collector = coll
```

Design notes:
- **Reuses existing `LangfuseService`.** No new Langfuse SDK calls — `create_trace` (langfuse.py:40-59) is exactly what we want. We pass `trace_id` as session_id and user_id because `LangfuseService.create_trace` requires them; the alternative is to add a new method and we prefer to keep `LangfuseService` surface stable.
- **`record_llm` records to the DB collector** via existing `record_request` (`collector.py:52-83`), passing `langfuse_trace_id=self.trace_id` so agent observability queries join cleanly.
- **Fire-and-forget on finalize.** A trace finalization failure must not propagate.
- **No ContextVar writes.** `context.py` vars are agent-scoped (`current_query_id`, `current_session_id`, `current_agent_type`). Task tracer does not mutate them — it passes `trace_id` explicitly.
- **Import cost.** `LangfuseService` is disabled when `LANGFUSE_SECRET_KEY` is empty, so dev/test environments pay zero cost.

---

## Files Created

1. `backend/models/ticker_ingestion_state.py` — SQLAlchemy model
2. `backend/services/ticker_state.py` — service with `mark_stage_updated`, `get_ticker_readiness`, `get_universe_health`, `ReadinessState`, `ReadinessRow`
3. `backend/services/observability/__init__.py` — new sub-package marker
4. `backend/services/observability/task_tracer.py` — `trace_task` context manager + `TaskTraceHandle`
5. `backend/migrations/versions/025_ticker_ingestion_state.py` — Alembic migration
6. `tests/unit/services/test_ticker_state.py` — service unit tests
7. `tests/unit/tasks/test_pipeline_runner_decorator.py` — decorator tests
8. `tests/unit/services/test_task_tracer.py` — context manager tests
9. `tests/api/test_ingestion_health_state.py` — integration against real Postgres (testcontainers)

## Files Modified

1. `backend/config.py` — add `StalenessSLAs` class and `Settings.staleness_slas` property
2. `backend/models/__init__.py` — import `TickerIngestionState`, add to `__all__`
3. `backend/tasks/pipeline.py` — append `tracked_task` decorator (plus imports: `functools.wraps`, `ParamSpec`, `TypeVar`, `Awaitable`, `Callable`)

## Upstream / Downstream Impact

- **Reads from:** `stocks.ticker` (FK), `stocks.last_fetched_at` (backfill only, one-shot in migration).
- **Writes to:** `ticker_ingestion_state` (new table), `pipeline_runs` (via decorator's `start_run`/`complete_run`). No modifications to existing rows in existing tables.
- **Consumed by:**
  - **Spec B** — adds `mark_stage_updated` call sites in the `convergence` and `backtest` tasks, and tightens the `forecast_retrain` vs `forecast` semantics.
  - **Spec C** — entry-point unification uses `get_ticker_readiness` to decide whether a single-ticker request should trigger a just-in-time refresh.
  - **Spec D** — admin observability router reads `get_universe_health()`; adopts `@tracked_task` on all 7 currently-untracked task modules; wires `trace_task` around sentiment scoring and Prophet training.
  - **Spec G** — frontend dashboard renders the `ReadinessRow[]` as a heatmap.
- **Produces no API endpoints itself** (admin endpoints come in Spec D).
- **Produces no UI changes itself** (UI comes in Spec D and G).

## Test Impact

### Existing test files affected

Grep of `tests/` for imports of `backend.tasks.pipeline`, `backend.observability.langfuse`, `backend.observability.collector`:

| File | Change |
|---|---|
| `tests/unit/pipeline/test_pipeline_infra.py` | Add tests for `tracked_task` decorator (happy path, exception, run row update). Existing PipelineRunner tests unchanged. |
| `tests/unit/pipeline/test_nightly_chain.py` | No change — exercises the existing 4 callers, which keep their code. |
| `tests/unit/services/test_langfuse_service.py` | No change — `trace_task` uses the existing `create_trace` method; existing contract tests still cover it. |
| `tests/unit/agents/test_agent_observability.py` | No change — agent path unaffected. |
| `tests/unit/agents/test_langfuse_instrumentation.py` | No change. |

### New test files to create

- `tests/unit/services/test_ticker_state.py`
- `tests/unit/tasks/test_pipeline_runner_decorator.py`
- `tests/unit/services/test_task_tracer.py`
- `tests/api/test_ingestion_health_state.py`

### Specific test cases needed

**`test_ticker_state.py`** (service unit):

1. `test_mark_stage_updated_inserts_new_row` — empty table, call `mark_stage_updated("AAPL", "prices")`, assert row created with `prices_updated_at` populated and other columns NULL.
2. `test_mark_stage_updated_upserts_existing_row` — pre-seed, call again, assert `updated_at` bumped and `prices_updated_at` refreshed, other timestamps untouched.
3. `test_mark_stage_updated_distinct_stages` — call for all 9 stages on one ticker, assert all 9 columns populated.
4. `test_mark_stage_updated_forecast_vs_forecast_retrain` — calling `forecast` updates `forecast_updated_at` only; calling `forecast_retrain` updates `forecast_retrained_at` only.
5. `test_mark_stage_updated_swallows_db_error` — monkeypatch `async_session_factory` to raise; assert function returns normally (fire-and-forget).
6. `test_get_ticker_readiness_missing_row_returns_unknown` — ticker not in table → all stages `unknown`, overall `unknown`.
7. `test_get_ticker_readiness_green_when_fresh` — freezegun `now`, seed ts within green SLA, assert `green` for each stage.
8. `test_get_ticker_readiness_yellow_between_1x_and_2x_sla` — seed ts aged 1.5× SLA, assert `yellow`.
9. `test_get_ticker_readiness_red_beyond_2x_sla` — seed ts aged 3× SLA, assert `red`.
10. `test_get_ticker_readiness_overall_is_worst_stage` — prices green, forecast red, signals yellow → overall `red`.
11. `test_get_universe_health_orders_red_first` — seed 3 tickers (red, green, yellow), assert order: red, yellow, green.
12. `test_get_universe_health_empty_table_returns_empty_list`.
13. `test_staleness_slas_exact_values` — import `StalenessSLAs`, assert each field matches the spec (`prices == timedelta(hours=4)`, etc.) — acts as a change-detector.

**`test_pipeline_runner_decorator.py`**:

14. `test_tracked_task_happy_path_calls_start_and_complete` — decorate a fn returning `{"ok": True}`, call it, assert `pipeline_runs` row created then marked `success`.
15. `test_tracked_task_injects_run_id_kwarg` — inner fn asserts `run_id` is a UUID.
16. `test_tracked_task_forwards_tickers_total` — pass `tickers_total=500`, assert row has `tickers_total=500` and inner fn does NOT receive `tickers_total` kwarg (consumed).
17. `test_tracked_task_marks_failed_on_exception` — inner fn raises; assert row status=`failed`, `completed_at` set, `error_summary` = `{"_exception": "see logs"}`, exception re-raised.
18. `test_tracked_task_no_str_e_leakage` — regression for Hard Rule #10: raise `ValueError("secret db password")`, assert no fragment of the message appears in `error_summary`.
19. `test_tracked_task_default_trigger_is_scheduled`.
20. `test_tracked_task_custom_trigger_passthrough` — `@tracked_task("x", trigger="manual")` → row has `trigger="manual"`.

**`test_task_tracer.py`**:

21. `test_trace_task_creates_langfuse_trace_with_task_metadata` — mock `LangfuseService`, assert `create_trace` called once with `metadata` containing `{"task": "my_task"}` plus extras.
22. `test_trace_task_handles_disabled_langfuse` — `LangfuseService(secret_key="")` (disabled), assert no exception and `handle._trace is None`.
23. `test_trace_task_records_llm_via_collector` — mock collector, call `handle.record_llm(...)`, assert `collector.record_request` called with matching kwargs and `langfuse_trace_id == handle.trace_id`.
24. `test_trace_task_exception_sets_error_status` — inside `async with`, raise; assert `handle._status == "error"`, `_error == "ValueError"`, exception re-raised.
25. `test_trace_task_measures_duration_ms` — freezegun tick the clock 250ms, assert `_duration_ms >= 200`.
26. `test_trace_task_finalize_swallows_langfuse_errors` — mock trace.update to raise, assert context manager exits cleanly.
27. `test_trace_task_add_metadata_merges_into_final_update` — call `handle.add_metadata(articles=10)`, assert `trace.update` called with `articles=10` present.

**`test_ingestion_health_state.py`** (API tier, real DB via testcontainers):

28. `test_mark_stage_updated_persists_across_sessions` — call in one session, read in another, assert row visible.
29. `test_get_universe_health_with_real_timestamps` — seed 5 tickers at different ages, call service, assert status bucketing matches SLAs.
30. `test_migration_025_upgrade_downgrade_clean` — run migration up, verify table + indexes + FK, run down, verify clean.
31. `test_migration_025_backfill_populates_prices_updated_at_from_stocks` — pre-seed `stocks` with `last_fetched_at`, run migration, assert `ticker_ingestion_state.prices_updated_at` matches.
32. `test_stocks_cascade_delete_removes_ingestion_state_row` — delete a stock, assert its `ticker_ingestion_state` row is gone (FK CASCADE).

---

## Migration Strategy

1. **Deploy migration 025** — pure additive DDL. Creates `ticker_ingestion_state` with backfill from `stocks.last_fetched_at` (prices column only). Zero downtime — no locks on hot tables beyond the FK reference.
2. **Deploy service + decorator + tracer** — they land as new files with zero call sites. Production behavior unchanged.
3. **Spec D adoption** — each task module is migrated to `@tracked_task` + `mark_stage_updated` in a separate PR, one at a time, behind feature tests. Tasks that don't adopt yet remain invisible to the new table for now — they'll still show up as `unknown` in the dashboard until adopted.
4. **Admin endpoint (Spec D)** + **UI (Spec G)** consume `get_universe_health()`.

**Backfill rationale:** We seed `prices_updated_at` because `stocks.last_fetched_at` is a reliable proxy for the most recent price fetch per ticker. We do **not** attempt to backfill signals/fundamentals/forecast/etc. from `max(snapshot_date)` of their respective tables — that would require 7 heavy joins in a migration, and the data becomes correct organically within one nightly run.

---

## Risk + Rollback

| Risk | Likelihood | Mitigation |
|---|---|---|
| Migration fails on large `stocks` table during backfill INSERT-SELECT | Low (stocks is ~5-10k rows) | Single transaction; rollback is trivial |
| FK ON DELETE CASCADE breaks a seldom-used admin flow that deletes stocks | Low | Admin stock-deletion paths should cascade anyway; documented |
| `mark_stage_updated` lock contention on hot tickers | Very low | One-row upsert per call, Postgres handles at sub-ms |
| `tracked_task` decorator subtly breaks Celery retry semantics | Low | Re-raises all exceptions; Celery retry policy untouched |
| `task_tracer` leaks Langfuse traces on disabled config | None | Disabled path returns `None` and early-exits |

**Rollback plan:** `alembic downgrade -1` drops the table. Service + decorator + tracer have no call sites (by design of this spec), so reverting the code is a pure file delete with no data consequences.

**No data loss** — migration is additive; downgrade is `DROP TABLE`.

---

## Open Questions

1. **Should `forecast_retrain` be a separate "stage" in the service enum, or a flag on `forecast`?** Current design: separate stage with its own SLA (14d vs forecast's 24h), flattened out of `ReadinessRow` for dashboard simplicity. Alternative: merge into one stage with two columns surfaced via metadata. Recommend: keep separate — clearer semantics.
2. **Do we index `fundamentals_updated_at`, `news_updated_at`, `sentiment_updated_at`?** Not in the initial migration. Dashboards filter on "worst stage" which hits all columns equally — no index helps. If a future admin query filters specifically on one, add the index then.
3. **Is `str(StageStatus)` safe for the admin API, or do we need an enum?** Current design: `Literal` for type safety in Python, serialized to string. Spec D router will validate. Alternative: a SQLAlchemy `Enum` type on the column — but the column is `TIMESTAMPTZ`, the status is *computed*. No ambiguity. Keep as is.
4. **Should `tracked_task` also write to `ticker_ingestion_state`?** No — the decorator doesn't know which stage a given task corresponds to (one task might touch 2 stages). The *task body* calls `mark_stage_updated("signals")` explicitly per stage. Keeps the decorator stage-agnostic.
5. **Should the `task_tracer` emit an in-memory event queue like `collector._cascade_log`?** Not in this spec. If admin debugging needs it, add in Spec D.

---

## Dependencies

- **Blocks:**
  - **Spec B** (Pipeline Completeness) — convergence/backtest tasks must call `mark_stage_updated` at completion.
  - **Spec C** (Entry Point Unification) — just-in-time single-ticker refresh reads `get_ticker_readiness`.
  - **Spec D** (Admin + Observability) — admin router reads `get_universe_health()`; Spec D adopts `@tracked_task` and `trace_task` across all nightly task modules; wires them around the sentiment scorer and Prophet training in particular.
- **Depends on:** nothing. This spec is the root of the overhaul.
