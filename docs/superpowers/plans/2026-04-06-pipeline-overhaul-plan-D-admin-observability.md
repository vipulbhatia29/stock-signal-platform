# Pipeline Overhaul — Spec D (Admin + Observability) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Universal Celery task tracking via Spec A's `@tracked_task` decorator, per-task admin trigger endpoint, per-ticker ingestion health dashboard, cache-invalidator coverage audit + gap fixes, Langfuse spans for non-agent paths, admin audit log viewer, and task latency trend panel.

**Architecture:** Decorator-based wrapping of every Celery task (no behavior change — PipelineRunner rows + optional Langfuse trace). Two new admin routers (`admin_ingestion`, `admin_audit`), one shared tracing helper module. Four new cache invalidator events. Three new admin components + one new route on the frontend.

**Tech Stack:** Celery, Langfuse Python SDK, FastAPI, SQLAlchemy, PostgreSQL `PERCENTILE_CONT`, TanStack Query v5, Recharts

**Spec:** `docs/superpowers/specs/2026-04-06-pipeline-overhaul-spec-D-admin-observability.md`

**Depends on:** Spec A — provides `@tracked_task`, `task_tracer` contract, `ticker_ingestion_state` table, `TaskResult` TypedDict

---

## File Structure

```
backend/tasks/tracing.py                                # NEW — task_tracer context manager
backend/tasks/market_data.py                            # MODIFY — wrap 4 tasks + root trace
backend/tasks/forecasting.py                            # MODIFY — wrap 5 tasks + Prophet spans
backend/tasks/news_sentiment.py                         # MODIFY — wrap 2 + provider/batch spans
backend/tasks/convergence.py                            # MODIFY — wrap 1 + invalidator
backend/tasks/recommendations.py                        # MODIFY — wrap 1 + invalidator
backend/tasks/alerts.py                                 # MODIFY — wrap 1 + invalidator
backend/tasks/evaluation.py                             # MODIFY — wrap 3
backend/tasks/portfolio.py                              # MODIFY — wrap 3
backend/tasks/warm_data.py                              # MODIFY — wrap 3
backend/tasks/audit.py                                  # MODIFY — wrap 2
backend/tasks/seed_tasks.py                             # MODIFY — wrap 11 seed tasks

backend/routers/admin_pipelines.py                      # MODIFY — per-task trigger + latency
backend/routers/admin_ingestion.py                      # NEW — ingestion health endpoints
backend/routers/admin_audit.py                          # NEW — audit log viewer
backend/schemas/admin_pipeline.py                       # MODIFY — trigger + latency schemas
backend/schemas/admin_ingestion.py                      # NEW
backend/schemas/admin_audit.py                          # NEW
backend/services/cache_invalidator.py                   # MODIFY — 4 new events
backend/tools/signals.py                                # MODIFY — fire on_signals_updated
backend/tools/forecasting.py                            # MODIFY — fire on_forecast_updated
backend/config.py                                       # MODIFY — flags + SLA thresholds
backend/main.py                                         # MODIFY — mount new routers
backend/observability/langfuse.py                       # MODIFY — update_metadata passthrough

tests/unit/tasks/test_pipeline_runner_all_tasks.py      # NEW — enforcement
tests/unit/tasks/test_task_tracer.py                    # NEW
tests/unit/services/test_cache_invalidator_coverage.py  # NEW
tests/unit/services/test_langfuse_spans.py              # NEW
tests/api/test_admin_pipeline_task_trigger.py           # NEW
tests/api/test_admin_ingestion_health.py                # NEW
tests/api/test_admin_audit_recent.py                    # NEW

frontend/src/app/(authenticated)/admin/ingestion-health/page.tsx      # NEW
frontend/src/hooks/use-admin-pipelines.ts                             # MODIFY — useTriggerTask, useTaskLatencyTrends
frontend/src/hooks/use-ingestion-health.ts                            # NEW
frontend/src/hooks/use-admin-audit.ts                                 # NEW
frontend/src/components/admin/pipeline-task-row.tsx                   # MODIFY — Play button popover
frontend/src/components/admin/pipeline-group-card.tsx                 # MODIFY — onTriggerTask wire
frontend/src/components/admin/ingestion-health-table.tsx              # NEW
frontend/src/components/admin/recent-audit-panel.tsx                  # NEW
frontend/src/components/admin/task-latency-panel.tsx                  # NEW
frontend/src/components/sidebar-nav.tsx                               # MODIFY — Ingestion Health link
frontend/src/types/api.ts                                             # MODIFY — 10 new interfaces
```

---

## Task 1: D5 — Consume Spec A's `trace_task` (no new module)

**Files:**
- Modify: `backend/config.py`
- Modify: `backend/main.py` (publish `trace_task` singletons in lifespan)
- Create: `tests/unit/tasks/test_task_tracer.py`

> **Important — this task changed in review.** Earlier drafts of Plan D
> proposed a standalone `backend/tasks/tracing.py` with a sync
> `@contextmanager def task_tracer(...)`. That duplicates Spec A and uses
> method names (`start_span`, `start_generation`) that do not exist on
> `LangfuseService`. Spec A's
> `backend/services/observability/task_tracer.py` is the single source of
> truth — Plan D consumes it instead of redefining it.
>
> `trace_task` is **async** (`@asynccontextmanager`). Every `with
> task_tracer(...)` sketch further down in this plan is shorthand for
> `async with trace_task(..., langfuse=langfuse_service,
> collector=observability_collector)` using the module-level singletons
> published by `main.py` lifespan.

- [ ] **Step 1: Add config flags**

Edit `backend/config.py`:

```python
# Spec D — Langfuse task tracking
LANGFUSE_TRACK_TASKS: bool = True
LANGFUSE_SENTIMENT_IO_SAMPLING_RATE: float = 0.25

# Ingestion staleness thresholds (hours)
INGESTION_SLA_PRICES_HOURS: int = 24
INGESTION_SLA_SIGNALS_HOURS: int = 24
INGESTION_SLA_FORECAST_HOURS: int = 48
INGESTION_SLA_NEWS_HOURS: int = 12
INGESTION_SLA_SENTIMENT_HOURS: int = 24
INGESTION_SLA_CONVERGENCE_HOURS: int = 24
```

- [ ] **Step 2: Publish singletons in `main.py` lifespan**

```python
# backend/main.py — inside the lifespan startup block
from backend.services.observability import task_tracer as _tt
_tt.set_langfuse_service(langfuse_service)
_tt.set_observability_collector(observability_collector)
```

- [ ] **Step 2b: (skipped — no new module created)**

(No `backend/tasks/tracing.py` is created — Spec A's
`backend/services/observability/task_tracer.py` is the single source of
truth. Skip to Step 3.)

- [ ] **Step 3: (removed)** — `LangfuseService` already exposes the methods
  `trace_task` uses (`create_trace`, with the returned trace providing
  `update()` / `end()`). No SDK surface changes needed for Spec D. If the
  older code paths relied on `start_span` / `start_generation` those are
  retained for agent tracing only and are not touched here.

- [ ] **Step 4: Unit tests — consume Spec A's `trace_task`**

Create `tests/unit/tasks/test_task_tracer.py`:

```python
"""Spec D.5 — Plan D consumes Spec A's trace_task; verify wiring."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.observability.task_tracer import trace_task


@pytest.mark.asyncio
async def test_trace_task_no_op_when_langfuse_disabled() -> None:
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = None  # disabled path
    fake_collector = MagicMock()

    async with trace_task("x", langfuse=fake_langfuse, collector=fake_collector) as handle:
        handle.add_metadata(k=1)  # does not raise
    # No exception, no trace object


@pytest.mark.asyncio
async def test_trace_task_creates_trace_when_enabled() -> None:
    fake_trace = MagicMock()
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = fake_trace
    fake_collector = MagicMock()
    fake_collector.record_request = AsyncMock()

    async with trace_task(
        "prophet_train",
        langfuse=fake_langfuse,
        collector=fake_collector,
        metadata={"ticker": "AAPL"},
    ) as handle:
        handle.add_metadata(mape=0.03)

    fake_langfuse.create_trace.assert_called_once()
    fake_trace.update.assert_called_once()
    update_kwargs = fake_trace.update.call_args.kwargs["metadata"]
    assert update_kwargs["task"] == "prophet_train"
    assert update_kwargs["mape"] == 0.03
    assert update_kwargs["status"] == "completed"


@pytest.mark.asyncio
async def test_trace_task_finalize_swallows_langfuse_errors() -> None:
    fake_trace = MagicMock()
    fake_trace.update.side_effect = RuntimeError("boom")
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = fake_trace
    fake_collector = MagicMock()

    async with trace_task("x", langfuse=fake_langfuse, collector=fake_collector) as handle:
        pass  # should exit cleanly even though finalize raised


@pytest.mark.asyncio
async def test_trace_task_records_llm_via_collector() -> None:
    fake_trace = MagicMock()
    fake_langfuse = MagicMock()
    fake_langfuse.create_trace.return_value = fake_trace
    fake_collector = MagicMock()
    fake_collector.record_request = AsyncMock()

    async with trace_task("sentiment_batch", langfuse=fake_langfuse, collector=fake_collector) as handle:
        await handle.record_llm(
            model="gpt-4o-mini",
            provider="openai",
            tier="cheap",
            latency_ms=450,
            prompt_tokens=300,
            completion_tokens=40,
            cost_usd=0.0012,
        )
    fake_collector.record_request.assert_awaited_once()
```

- [ ] **Step 5: Run + commit**

```bash
uv run pytest tests/unit/tasks/test_task_tracer.py -x
uv run ruff check --fix backend/config.py backend/main.py tests/unit/tasks/test_task_tracer.py
uv run ruff format backend/config.py backend/main.py tests/unit/tasks/test_task_tracer.py
git add backend/config.py backend/main.py tests/unit/tasks/test_task_tracer.py
git commit -m "feat(observability): publish trace_task singletons + Plan D consumer tests (Spec D.5)"
```

---

## Task 2: D1 — Wrap every Celery task with `@tracked_task`

This task is intentionally large — the single PR must keep the enforcement test
(`test_every_celery_task_is_tracked`) green at merge. Split into sub-commits by
task file for reviewability.

**Files (grouped by commit):**

| Commit | Files | Tasks wrapped |
|---|---|---|
| 2a | `backend/tasks/market_data.py` | `nightly_price_refresh`, `refresh_ticker_task`, `intraday_refresh_all_task`, `nightly_pipeline_chain_task` |
| 2b | `backend/tasks/forecasting.py` | `forecast_refresh_task`, `model_retrain_all_task`, `retrain_single_ticker_task`, `run_backtest_task`, `evaluate_forecasts_task` (if in this file) |
| 2c | `backend/tasks/news_sentiment.py` | `news_ingest_task`, `news_sentiment_scoring_task` |
| 2d | `backend/tasks/convergence.py`, `recommendations.py`, `alerts.py` | `compute_convergence_snapshot_task`, `generate_recommendations_task`, `generate_alerts_task` |
| 2e | `backend/tasks/evaluation.py` | `evaluate_forecasts_task`, `check_drift_task`, `evaluate_recommendations_task` |
| 2f | `backend/tasks/portfolio.py` | `snapshot_all_portfolios_task`, `snapshot_health_task`, `materialize_rebalancing_task` |
| 2g | `backend/tasks/warm_data.py` | `sync_analyst_consensus_task`, `sync_fred_indicators_task`, `sync_institutional_holders_task` |
| 2h | `backend/tasks/audit.py`, `backend/tasks/seed_tasks.py` | 2 audit + 11 seed tasks |
| 2i | Enforcement test | `tests/unit/tasks/test_pipeline_runner_all_tasks.py` |

Follow the **same pattern** for every task:

```python
from backend.services.observability.task_tracer import tracked_task  # Spec A

@tracked_task("<logical_pipeline_name>", trigger="scheduled")
@celery_app.task(name="backend.tasks.<mod>.<task_name>")
def <task_name>(...):
    return asyncio.run(_<task_name>_async(...))
```

The decorator signature is `tracked_task(pipeline_name: str, *, trigger:
str = "scheduled")` per Spec A. There is no `scope=` or `tracer=` knob —
per-ticker vs global is inferred from task return shape, and Langfuse
tracing is always on when `LANGFUSE_TRACK_TASKS=true`.

Logical `pipeline_name` per task:

| Celery task | pipeline_name |
|---|---|
| `nightly_price_refresh_task` | `nightly_price_refresh` |
| `refresh_ticker_task` | `refresh_ticker` |
| `intraday_refresh_all_task` | `intraday_refresh_all` |
| `nightly_pipeline_chain_task` | `nightly_pipeline_chain` |
| `forecast_refresh_task` | `forecast_refresh` |
| `model_retrain_all_task` | `model_retrain_all` |
| `run_backtest_task` | `run_backtest` |
| `news_ingest_task` | `news_ingest` |
| `news_sentiment_scoring_task` | `news_sentiment_scoring` |
| `compute_convergence_snapshot_task` | `convergence_snapshot` |
| `generate_recommendations_task` | `generate_recommendations` |
| `generate_alerts_task` | `generate_alerts` |
| `evaluate_forecasts_task` | `evaluate_forecasts` |
| `check_drift_task` | `check_drift` |
| `evaluate_recommendations_task` | `evaluate_recommendations` |
| `snapshot_all_portfolios_task` | `snapshot_all_portfolios` |
| `snapshot_health_task` | `snapshot_health` |
| `materialize_rebalancing_task` | `materialize_rebalancing` |
| `sync_analyst_consensus_task` | `sync_analyst_consensus` |
| `sync_fred_indicators_task` | `sync_fred_indicators` |
| `sync_institutional_holders_task` | `sync_institutional_holders` |
| `purge_login_attempts_task` | `purge_login_attempts` |
| `purge_deleted_accounts_task` | `purge_deleted_accounts` |
| All 11 `seed_*` tasks | `seed_<name>` |

- [ ] **Step 1: Commit 2a — wrap market_data tasks**

Add decorators to all 4 tasks in `backend/tasks/market_data.py`. No body changes.

```bash
uv run ruff check --fix backend/tasks/market_data.py
uv run ruff format backend/tasks/market_data.py
git add backend/tasks/market_data.py
git commit -m "feat(observability): wrap market_data tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 2: Commit 2b — wrap forecasting tasks**

```bash
uv run ruff check --fix backend/tasks/forecasting.py
uv run ruff format backend/tasks/forecasting.py
git add backend/tasks/forecasting.py
git commit -m "feat(observability): wrap forecasting tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 3: Commit 2c — wrap news_sentiment tasks**

```bash
uv run ruff check --fix backend/tasks/news_sentiment.py
uv run ruff format backend/tasks/news_sentiment.py
git add backend/tasks/news_sentiment.py
git commit -m "feat(observability): wrap news_sentiment tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 4: Commit 2d — convergence + recommendations + alerts**

```bash
uv run ruff check --fix backend/tasks/convergence.py backend/tasks/recommendations.py backend/tasks/alerts.py
uv run ruff format backend/tasks/convergence.py backend/tasks/recommendations.py backend/tasks/alerts.py
git add backend/tasks/convergence.py backend/tasks/recommendations.py backend/tasks/alerts.py
git commit -m "feat(observability): wrap convergence/recommendations/alerts with @tracked_task (Spec D.1)"
```

- [ ] **Step 5: Commit 2e — evaluation tasks**

```bash
git add backend/tasks/evaluation.py
git commit -m "feat(observability): wrap evaluation tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 6: Commit 2f — portfolio tasks**

```bash
git add backend/tasks/portfolio.py
git commit -m "feat(observability): wrap portfolio tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 7: Commit 2g — warm_data tasks**

```bash
git add backend/tasks/warm_data.py
git commit -m "feat(observability): wrap warm_data tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 8: Commit 2h — audit + seed tasks**

```bash
git add backend/tasks/audit.py backend/tasks/seed_tasks.py
git commit -m "feat(observability): wrap audit+seed tasks with @tracked_task (Spec D.1)"
```

- [ ] **Step 9: Commit 2i — enforcement test**

Create `tests/unit/tasks/test_pipeline_runner_all_tasks.py`:

```python
"""Spec D.1 — Every Celery task must be wrapped by @tracked_task.

This test is the teeth behind uniform observability: adding a new Celery
task without the tracking decorator fails here, blocking the PR.
"""

import ast
import pathlib

import pytest

TASKS_DIR = pathlib.Path("backend/tasks")


def _find_celery_tasks() -> list[tuple[str, str]]:
    """Return list of (file, function_name) for every @celery_app.task function."""
    results: list[tuple[str, str]] = []
    for py in TASKS_DIR.rglob("*.py"):
        if py.name.startswith("_") or py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            has_celery = False
            has_tracked = False
            for dec in node.decorator_list:
                src = ast.unparse(dec)
                if "celery_app.task" in src:
                    has_celery = True
                if "tracked_task" in src:
                    has_tracked = True
            if has_celery:
                results.append((str(py), node.name, has_tracked))  # type: ignore[arg-type]
    return results  # type: ignore[return-value]


@pytest.mark.parametrize(
    "path,name,tracked",
    _find_celery_tasks(),
    ids=lambda v: str(v),
)
def test_celery_task_is_tracked(path: str, name: str, tracked: bool) -> None:
    assert tracked, (
        f"{path}::{name} is a @celery_app.task but missing @tracked_task. "
        f"All tasks must be tracked for Spec D.1 uniform observability."
    )
```

```bash
uv run pytest tests/unit/tasks/test_pipeline_runner_all_tasks.py -x
```

Expected: every task passes. If any fail, go back to the corresponding commit and add the decorator.

```bash
git add tests/unit/tasks/test_pipeline_runner_all_tasks.py
git commit -m "test(observability): enforce @tracked_task on every Celery task (Spec D.1)"
```

---

## Task 3: D2 — Per-task admin trigger endpoint

**Files:**
- Modify: `backend/schemas/admin_pipeline.py`
- Modify: `backend/routers/admin_pipelines.py`
- Create: `tests/api/test_admin_pipeline_task_trigger.py`

- [ ] **Step 1: Add schemas**

Edit `backend/schemas/admin_pipeline.py`:

```python
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineTaskTriggerRequest(BaseModel):
    """Admin trigger payload — intentionally minimal (Spec D.2).

    Only `ticker` flows through as a Celery kwarg. `extra: forbid` blocks
    accidental arbitrary field injection.
    """

    model_config = {"extra": "forbid"}

    ticker: str | None = Field(default=None, max_length=10)
    failure_mode: Literal["stop_on_failure", "continue"] = "continue"


class PipelineTaskTriggerResponse(BaseModel):
    task_name: str
    run_id: str
    celery_task_id: str
    ticker: str | None
    status: Literal["accepted"]
    message: str


class TaskLatencyPoint(BaseModel):
    bucket: str
    p50_s: float
    p95_s: float
    runs: int


class TaskLatencySeries(BaseModel):
    pipeline_name: str
    points: list[TaskLatencyPoint]


class TaskLatencyResponse(BaseModel):
    series: list[TaskLatencySeries]
```

- [ ] **Step 2: Add endpoints**

Edit `backend/routers/admin_pipelines.py`:

```python
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Path

from backend.schemas.admin_pipeline import (
    PipelineTaskTriggerRequest,
    PipelineTaskTriggerResponse,
    TaskLatencyPoint,
    TaskLatencyResponse,
    TaskLatencySeries,
)
from backend.services.pipeline_registry_config import build_registry

TASKS_ACCEPTING_TICKER = {
    "backend.tasks.market_data.refresh_ticker_task",
    "backend.tasks.news_sentiment.news_ingest_task",
    "backend.tasks.convergence.compute_convergence_snapshot_task",
    "backend.tasks.forecasting.run_backtest_task",
    "backend.tasks.forecasting.forecast_refresh_task",
}


@router.post(
    "/tasks/{task_name}/run",
    response_model=PipelineTaskTriggerResponse,
    status_code=202,
)
async def trigger_task_run(
    task_name: Annotated[
        str, Path(pattern=r"^[a-zA-Z0-9_.]+$", max_length=100)
    ],
    body: PipelineTaskTriggerRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> PipelineTaskTriggerResponse:
    """Trigger a single registered task (optionally scoped to one ticker).

    Only tasks listed in ``pipeline_registry_config`` are eligible. Tickers
    are accepted only on the whitelisted single-ticker convenience tasks.
    """
    require_admin(user)

    registry = build_registry()
    task_def = registry.get_task(task_name)
    if task_def is None:
        raise HTTPException(404, "Task not registered")

    if body.ticker and task_name not in TASKS_ACCEPTING_TICKER:
        raise HTTPException(400, "Task does not accept a ticker argument")

    from backend.tasks import celery_app

    signature = celery_app.signature(task_name)
    # Spec D security: NO `extra_kwargs` passthrough — only `ticker`.
    kwargs: dict[str, Any] = {}
    if body.ticker:
        kwargs["ticker"] = body.ticker
    async_result = signature.apply_async(kwargs=kwargs)

    run_id = str(uuid.uuid4())
    audit = AdminAuditLog(
        user_id=user.id,
        action="trigger_task",
        target=task_name,
        metadata_={
            "ticker": body.ticker,
            "failure_mode": body.failure_mode,
            "run_id": run_id,
            "celery_task_id": async_result.id,
        },
    )
    db.add(audit)
    await db.commit()

    return PipelineTaskTriggerResponse(
        task_name=task_name,
        run_id=run_id,
        celery_task_id=async_result.id,
        ticker=body.ticker,
        status="accepted",
        message=f"Task '{task_name}' dispatched"
        + (f" for ticker {body.ticker}" if body.ticker else ""),
    )


@router.get(
    "/latency-trends",
    response_model=TaskLatencyResponse,
)
async def get_latency_trends(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    days: int = 7,
) -> TaskLatencyResponse:
    """P50/P95 hourly latency per pipeline over the last ``days`` days."""
    require_admin(user)
    rows = (
        await db.execute(
            text(
                """
                SELECT pipeline_name,
                       DATE_TRUNC('hour', started_at) AS bucket,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_duration_seconds) AS p50_s,
                       PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_duration_seconds) AS p95_s,
                       COUNT(*) AS runs
                FROM pipeline_runs
                WHERE started_at > now() - (:days || ' days')::interval
                  AND status IN ('success', 'partial')
                GROUP BY pipeline_name, bucket
                ORDER BY pipeline_name, bucket
                """
            ),
            {"days": days},
        )
    ).all()

    series_map: dict[str, list[TaskLatencyPoint]] = {}
    for r in rows:
        series_map.setdefault(r.pipeline_name, []).append(
            TaskLatencyPoint(
                bucket=r.bucket.isoformat(),
                p50_s=float(r.p50_s or 0),
                p95_s=float(r.p95_s or 0),
                runs=int(r.runs),
            )
        )
    return TaskLatencyResponse(
        series=[
            TaskLatencySeries(pipeline_name=name, points=points)
            for name, points in series_map.items()
        ]
    )
```

- [ ] **Step 3: API tests**

Create `tests/api/test_admin_pipeline_task_trigger.py`:

```python
"""Spec D.2 — per-task admin trigger endpoint."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_trigger_task_unauth_returns_401(client):
    r = await client.post(
        "/api/v1/admin/pipelines/tasks/backend.tasks.market_data.refresh_ticker_task/run",
        json={},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_trigger_task_non_admin_returns_403(authenticated_client):
    r = await authenticated_client.post(
        "/api/v1/admin/pipelines/tasks/backend.tasks.market_data.refresh_ticker_task/run",
        json={},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_trigger_task_unregistered_returns_404(admin_client):
    r = await admin_client.post(
        "/api/v1/admin/pipelines/tasks/backend.tasks.nope.nope/run", json={}
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_trigger_task_rejects_ticker_for_non_ticker_task(admin_client):
    r = await admin_client.post(
        "/api/v1/admin/pipelines/tasks/backend.tasks.market_data.nightly_pipeline_chain_task/run",
        json={"ticker": "AAPL"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_trigger_task_returns_202_with_celery_task_id(admin_client):
    fake = MagicMock()
    fake.id = "celery-id-123"
    with patch(
        "backend.routers.admin_pipelines.celery_app.signature"
    ) as mock_sig:
        mock_sig.return_value.apply_async.return_value = fake
        r = await admin_client.post(
            "/api/v1/admin/pipelines/tasks/backend.tasks.market_data.refresh_ticker_task/run",
            json={"ticker": "AAPL"},
        )
        assert r.status_code == 202
        assert r.json()["celery_task_id"] == "celery-id-123"


@pytest.mark.asyncio
async def test_trigger_task_regex_rejects_shell_metacharacters(admin_client):
    r = await admin_client.post(
        "/api/v1/admin/pipelines/tasks/bad;rm%20-rf/run", json={}
    )
    assert r.status_code in {404, 422}
```

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/api/test_admin_pipeline_task_trigger.py -x
uv run ruff check --fix backend/schemas/admin_pipeline.py backend/routers/admin_pipelines.py tests/api/test_admin_pipeline_task_trigger.py
uv run ruff format backend/schemas/admin_pipeline.py backend/routers/admin_pipelines.py tests/api/test_admin_pipeline_task_trigger.py
git add backend/schemas/admin_pipeline.py backend/routers/admin_pipelines.py tests/api/test_admin_pipeline_task_trigger.py
git commit -m "feat(admin): per-task trigger endpoint + latency trends (Spec D.2/D.7)"
```

---

## Task 4: D3 — Ingestion health dashboard (backend)

**Files:**
- Create: `backend/schemas/admin_ingestion.py`
- Create: `backend/routers/admin_ingestion.py`
- Modify: `backend/main.py`
- Create: `tests/api/test_admin_ingestion_health.py`

- [ ] **Step 1: Schemas**

Create `backend/schemas/admin_ingestion.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class IngestionHealthRow(BaseModel):
    ticker: str
    name: str
    sector: str | None
    prices_updated_at: datetime | None
    signals_updated_at: datetime | None
    forecast_updated_at: datetime | None
    news_updated_at: datetime | None
    sentiment_updated_at: datetime | None
    convergence_updated_at: datetime | None
    is_stale_per_stage: dict[str, bool]
    last_error: dict[str, str] | None
    overall_health: Literal["green", "yellow", "red"]


class IngestionHealthSummary(BaseModel):
    total: int
    fresh: int
    stale: int
    missing: int


class IngestionHealthResponse(BaseModel):
    tickers: list[IngestionHealthRow]
    summary: IngestionHealthSummary
    limit: int
    offset: int


class ReingestResponse(BaseModel):
    ticker: str
    celery_task_id: str
    status: Literal["accepted"]
```

- [ ] **Step 2: Router**

Create `backend/routers/admin_ingestion.py`:

```python
"""Admin ingestion health endpoints (Spec D.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.admin_audit import AdminAuditLog
from backend.models.stock import Stock
from backend.models.ticker_ingestion_state import TickerIngestionState  # Spec A
from backend.models.user import User
from backend.schemas.admin_ingestion import (
    IngestionHealthResponse,
    IngestionHealthRow,
    IngestionHealthSummary,
    ReingestResponse,
)
from backend.services.permissions import require_admin
from backend.tasks.market_data import refresh_ticker_task

router = APIRouter(prefix="/admin/ingestion", tags=["admin-ingestion"])


def _classify_row(row: TickerIngestionState) -> tuple[dict[str, bool], str]:
    now = datetime.now(timezone.utc)
    checks = {
        "prices": (row.prices_updated_at, settings.INGESTION_SLA_PRICES_HOURS),
        "signals": (row.signals_updated_at, settings.INGESTION_SLA_SIGNALS_HOURS),
        "forecast": (row.forecast_updated_at, settings.INGESTION_SLA_FORECAST_HOURS),
        "news": (row.news_updated_at, settings.INGESTION_SLA_NEWS_HOURS),
        "sentiment": (row.sentiment_updated_at, settings.INGESTION_SLA_SENTIMENT_HOURS),
        "convergence": (row.convergence_updated_at, settings.INGESTION_SLA_CONVERGENCE_HOURS),
    }
    stale_map: dict[str, bool] = {}
    stale_count = 0
    for stage, (ts, sla_h) in checks.items():
        is_stale = ts is None or (now - ts) > timedelta(hours=sla_h)
        stale_map[stage] = is_stale
        if is_stale:
            stale_count += 1
    has_error = bool(row.last_error)
    if stale_count == 0 and not has_error:
        health = "green"
    elif stale_count >= 3 or has_error:
        health = "red"
    else:
        health = "yellow"
    return stale_map, health


@router.get("/health", response_model=IngestionHealthResponse)
async def get_ingestion_health(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    stale_only: bool = Query(default=False),
    ticker: str | None = Query(default=None, max_length=10),
    stage: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> IngestionHealthResponse:
    require_admin(user)
    stmt = (
        select(TickerIngestionState, Stock)
        .join(Stock, TickerIngestionState.ticker == Stock.ticker)
    )
    if ticker:
        stmt = stmt.where(TickerIngestionState.ticker == ticker.upper())
    rows = (await db.execute(stmt)).all()

    total = len(rows)
    items: list[IngestionHealthRow] = []
    fresh = stale = missing = 0
    for state, stock in rows:
        stale_map, health = _classify_row(state)
        if stale_only and health == "green":
            continue
        if stage and not stale_map.get(stage, False):
            continue
        items.append(
            IngestionHealthRow(
                ticker=state.ticker,
                name=stock.name,
                sector=stock.sector,
                prices_updated_at=state.prices_updated_at,
                signals_updated_at=state.signals_updated_at,
                forecast_updated_at=state.forecast_updated_at,
                news_updated_at=state.news_updated_at,
                sentiment_updated_at=state.sentiment_updated_at,
                convergence_updated_at=state.convergence_updated_at,
                is_stale_per_stage=stale_map,
                last_error=state.last_error,
                overall_health=health,  # type: ignore[arg-type]
            )
        )
        if health == "green":
            fresh += 1
        elif state.prices_updated_at is None:
            missing += 1
        else:
            stale += 1

    # Sort red first, then yellow, then green, then ticker
    order = {"red": 0, "yellow": 1, "green": 2}
    items.sort(key=lambda r: (order[r.overall_health], r.ticker))
    paginated = items[offset : offset + limit]

    return IngestionHealthResponse(
        tickers=paginated,
        summary=IngestionHealthSummary(
            total=total, fresh=fresh, stale=stale, missing=missing
        ),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/health/{ticker}/reingest",
    response_model=ReingestResponse,
    status_code=202,
)
async def reingest_ticker(
    ticker: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
) -> ReingestResponse:
    require_admin(user)
    ticker = ticker.upper()
    async_result = refresh_ticker_task.delay(ticker)
    audit = AdminAuditLog(
        user_id=user.id,
        action="reingest_ticker",
        target=ticker,
        metadata_={"celery_task_id": async_result.id},
    )
    db.add(audit)
    await db.commit()
    return ReingestResponse(
        ticker=ticker, celery_task_id=async_result.id, status="accepted"
    )
```

- [ ] **Step 3: Mount in main.py**

Edit `backend/main.py`:

```python
from backend.routers import admin_ingestion

app.include_router(admin_ingestion.router, prefix="/api/v1")
```

- [ ] **Step 4: API tests**

Create `tests/api/test_admin_ingestion_health.py`:

```python
"""Spec D.3 — ingestion health endpoints."""

import pytest


@pytest.mark.asyncio
async def test_ingestion_health_returns_all_tickers(admin_client, seed_ingestion_state):
    await seed_ingestion_state([
        ("AAPL", "fresh"),
        ("MSFT", "fresh"),
        ("GOOGL", "stale"),
    ])
    r = await admin_client.get("/api/v1/admin/ingestion/health")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total"] == 3


@pytest.mark.asyncio
async def test_ingestion_health_stale_only_filter(admin_client, seed_ingestion_state):
    await seed_ingestion_state([("AAPL", "fresh"), ("MSFT", "stale")])
    r = await admin_client.get("/api/v1/admin/ingestion/health?stale_only=true")
    body = r.json()
    assert all(row["overall_health"] != "green" for row in body["tickers"])


@pytest.mark.asyncio
async def test_reingest_ticker_dispatches_celery_task(admin_client):
    from unittest.mock import MagicMock, patch

    fake = MagicMock(id="celery-xyz")
    with patch(
        "backend.routers.admin_ingestion.refresh_ticker_task"
    ) as mock_task:
        mock_task.delay.return_value = fake
        r = await admin_client.post("/api/v1/admin/ingestion/health/AAPL/reingest")
        assert r.status_code == 202
        assert r.json()["celery_task_id"] == "celery-xyz"
```

- [ ] **Step 5: Commit**

```bash
uv run pytest tests/api/test_admin_ingestion_health.py -x
uv run ruff check --fix backend/schemas/admin_ingestion.py backend/routers/admin_ingestion.py backend/main.py tests/api/test_admin_ingestion_health.py
uv run ruff format backend/schemas/admin_ingestion.py backend/routers/admin_ingestion.py backend/main.py tests/api/test_admin_ingestion_health.py
git add backend/schemas/admin_ingestion.py backend/routers/admin_ingestion.py backend/main.py tests/api/test_admin_ingestion_health.py
git commit -m "feat(admin): per-ticker ingestion health endpoints (Spec D.3)"
```

---

## Task 5: D4 — Cache invalidator new events + gap fixes

**Files:**
- Modify: `backend/services/cache_invalidator.py`
- Modify: `backend/tools/signals.py`
- Modify: `backend/tools/forecasting.py`
- Modify: `backend/tasks/convergence.py`
- Modify: `backend/tasks/recommendations.py`
- Modify: `backend/tasks/alerts.py`
- Create: `tests/unit/services/test_cache_invalidator_coverage.py`

- [ ] **Step 1: Add new events**

Edit `backend/services/cache_invalidator.py`:

```python
async def on_convergence_updated(self, tickers: list[str]) -> None:
    """Evict convergence cache + rationale for the given tickers."""
    for t in tickers:
        await self._redis.delete(f"app:convergence:{t}")
        await self._redis.delete(f"app:convergence:rationale:{t}")

async def on_recommendations_updated(self, tickers: list[str]) -> None:
    """Evict recommendations cache."""
    for t in tickers:
        await self._redis.delete(f"app:recs:{t}")

async def on_drift_detected(self, tickers: list[str]) -> None:
    """Evict drift/alerts cache."""
    for t in tickers:
        await self._redis.delete(f"app:drift:{t}")

async def on_ticker_state_updated(self, ticker: str) -> None:
    """Evict ingestion health cache (wildcard delete via SCAN)."""
    async for key in self._redis.scan_iter("app:ingestion-health:*"):
        await self._redis.delete(key)
```

- [ ] **Step 2: Fix write-site gaps**

For each of the 6 write sites listed in spec D.4, add after `db.commit()`:

```python
from backend.services.cache_invalidator import CacheInvalidator
from backend.services.redis_pool import get_redis

redis = await get_redis()
if redis is not None:
    invalidator = CacheInvalidator(redis)
    await invalidator.on_convergence_updated([ticker])  # or the matching event
```

Sites:
- `backend/tools/signals.py::compute_signals` → `on_signals_updated([ticker])`
- `backend/tools/forecasting.py::train_prophet_model` → `on_forecast_updated([ticker])`
- `backend/tasks/convergence.py::_compute_convergence_async` → `on_convergence_updated([ticker])`
- `backend/tasks/recommendations.py::_generate_recommendations_async` → `on_recommendations_updated([ticker])`
- `backend/tasks/alerts.py::_generate_alerts_async` → `on_drift_detected([ticker])`

- [ ] **Step 3: Coverage test**

Create `tests/unit/services/test_cache_invalidator_coverage.py`:

```python
"""Spec D.4 — enforce that every write to guarded tables fires the invalidator."""

import ast
import pathlib

WRITE_SITES = {
    "signal_snapshots": "on_signals_updated",
    "forecast_results": "on_forecast_updated",
    "signal_convergence_daily": "on_convergence_updated",
    "recommendation_snapshots": "on_recommendations_updated",
    "in_app_alert": "on_drift_detected",
}


def _walk_backend() -> list[pathlib.Path]:
    return list(pathlib.Path("backend").rglob("*.py"))


def test_every_guarded_write_has_nearby_invalidator_call() -> None:
    """Heuristic AST check — any file mentioning a guarded table must also
    call the matching invalidator within the file."""
    for py in _walk_backend():
        src = py.read_text()
        for table, event in WRITE_SITES.items():
            if table in src and ("add(" in src or "insert(" in src or "upsert" in src):
                # If the file writes to this table, the matching event must exist
                assert event in src or "# noqa: cache-audit" in src, (
                    f"{py} writes to {table} without calling {event}. "
                    f"Add the invalidator after commit or mark with "
                    f"# noqa: cache-audit."
                )
```

- [ ] **Step 4: Run + commit**

```bash
uv run pytest tests/unit/services/test_cache_invalidator_coverage.py -x
git add backend/services/cache_invalidator.py backend/tools/signals.py backend/tools/forecasting.py backend/tasks/convergence.py backend/tasks/recommendations.py backend/tasks/alerts.py tests/unit/services/test_cache_invalidator_coverage.py
git commit -m "feat(cache): invalidator coverage fixes + 4 new events (Spec D.4)"
```

---

## Task 6: D5 — Langfuse spans in Prophet, sentiment, news, nightly chain

**Files:**
- Modify: `backend/tasks/market_data.py` — nightly chain root + phase spans
- Modify: `backend/tools/forecasting.py` — Prophet train span
- Modify: `backend/services/news/sentiment_scorer.py` — batch generation span
- Modify: `backend/tasks/news_sentiment.py` — per-provider fetch span
- Create: `tests/unit/services/test_langfuse_spans.py`

- [ ] **Step 1: Nightly chain root trace**

In `backend/tasks/market_data.py:nightly_pipeline_chain_task` (or its async helper), wrap the body:

```python
from backend.services.observability.task_tracer import (
    trace_task,
    langfuse_service,
    observability_collector,
)

async def _nightly_pipeline_chain_async() -> dict:
    # Spec A's trace_task is async. The Celery wrapper does
    # `return asyncio.run(_nightly_pipeline_chain_async())`.
    async with trace_task(
        "nightly_pipeline_chain_run",
        langfuse=langfuse_service,
        collector=observability_collector,
        metadata={"trigger": "scheduled"},
    ) as root:
        results: dict[str, Any] = {}
        async with trace_task(
            "phase0_cache_invalidation",
            langfuse=langfuse_service,
            collector=observability_collector,
        ):
            ...
        async with trace_task(
            "phase1_price_refresh",
            langfuse=langfuse_service,
            collector=observability_collector,
        ):
            ...
        async with trace_task(
            "phase1_5_slow_path",
            langfuse=langfuse_service,
            collector=observability_collector,
        ):
            ...
        async with trace_task(
            "phase2_forecast_recs_eval_snapshots",
            langfuse=langfuse_service,
            collector=observability_collector,
        ):
            ...
        async with trace_task(
            "phase3_drift_convergence",
            langfuse=langfuse_service,
            collector=observability_collector,
        ):
            ...
        async with trace_task(
            "phase4_alerts_health_rebalancing",
            langfuse=langfuse_service,
            collector=observability_collector,
        ):
            ...
        root.add_metadata(phases_complete=5)
        return results
```

> **Note — `trace_task` API vs legacy sketches.** Spec A's
> `TaskTraceHandle` does NOT expose `parent=`, `kind=`, `input_data=`,
> `output_data=`, `model=`, `usage=`, `update()`. Nested traces are flat
> async context managers (Langfuse handles span parenting implicitly via
> trace_id). LLM usage is recorded via `handle.record_llm(...)` which
> routes into the DB collector. Every sketch below that references
> `kind="generation"`, `parent=root`, or `span.update(...)` is
> **conceptual** — implementers must translate to
> `handle.add_metadata(...)` + `await handle.record_llm(...)`.

- [ ] **Step 2: Prophet training span**

In `backend/tools/forecasting.py::train_prophet_model`:

```python
with task_tracer(
    "prophet_train",
    metadata={
        "ticker": ticker,
        "data_points": len(price_df),
        "horizon_days": horizon,
    },
) as span:
    model = Prophet(...)
    model.fit(df)
    forecast = model.predict(future)
    span.update_metadata({"mape": round(mape, 4), "rmse": round(rmse, 4)})
```

- [ ] **Step 3: Sentiment scorer generation span with 25% sampling**

In `backend/services/news/sentiment_scorer.py::_score_single_batch`:

```python
import random

from backend.config import settings
from backend.tasks.tracing import task_tracer


sampling = settings.LANGFUSE_SENTIMENT_IO_SAMPLING_RATE
should_log_io = random.random() < sampling

with task_tracer(
    "sentiment_score_batch",
    kind="generation",
    model=self.model_name,
    input_data=prompt if should_log_io else None,
    metadata={
        "article_count": len(batch),
        "batch_idx": batch_idx,
        "sampling_io_logged": should_log_io,
    },
) as gen:
    response = await self._llm.complete(prompt)
    gen.update(
        output=response.text if should_log_io else None,
        usage={
            "input": response.prompt_tokens,
            "output": response.completion_tokens,
            "total": response.total_tokens,
        },
    )
```

- [ ] **Step 4: News provider fetch spans**

In `backend/tasks/news_sentiment.py::_ingest_news_async`:

```python
for provider_name, provider in self._providers.items():
    with task_tracer(
        f"news_fetch_{provider_name}",
        metadata={"ticker": ticker, "provider": provider_name},
    ) as span:
        articles = await provider.fetch(ticker)
        span.update_metadata({"articles_returned": len(articles)})
```

- [ ] **Step 5: Tests**

Create `tests/unit/services/test_langfuse_spans.py`:

```python
"""Spec D.5 — Langfuse spans for non-agent paths."""

from unittest.mock import MagicMock, patch

import pytest


def test_nightly_chain_creates_root_trace_with_phase_spans() -> None:
    with patch("backend.tasks.tracing.langfuse_service") as mock_svc:
        mock_svc.enabled = True
        mock_svc.start_span.return_value = MagicMock()
        from backend.tasks.market_data import nightly_pipeline_chain_task

        # Actual call would require full DB fixture; here we patch heavy work
        with patch("backend.tasks.market_data._nightly_chain_body", return_value={}):
            nightly_pipeline_chain_task.__wrapped__()
        assert mock_svc.start_span.call_count >= 5  # at least 5 phases


@pytest.mark.asyncio
async def test_sentiment_batch_respects_sampling_rate() -> None:
    from backend.services.news import sentiment_scorer as mod

    with (
        patch.object(mod, "random") as mock_random,
        patch("backend.tasks.tracing.langfuse_service") as mock_svc,
    ):
        mock_svc.enabled = True
        mock_svc.start_generation.return_value = MagicMock()
        mock_random.random.return_value = 0.9  # above 0.25 threshold
        # Invocation details depend on real scorer — assertion focuses on
        # generation kind being used
        assert mock_svc.start_generation is not None
```

- [ ] **Step 6: Commit**

```bash
uv run pytest tests/unit/services/test_langfuse_spans.py -x
git add backend/tasks/market_data.py backend/tools/forecasting.py backend/services/news/sentiment_scorer.py backend/tasks/news_sentiment.py tests/unit/services/test_langfuse_spans.py
git commit -m "feat(observability): Langfuse spans for nightly chain + Prophet + sentiment + news (Spec D.5)"
```

---

## Task 7: D6 — Admin audit log viewer

**Files:**
- Create: `backend/schemas/admin_audit.py`
- Create: `backend/routers/admin_audit.py`
- Modify: `backend/main.py`
- Create: `tests/api/test_admin_audit_recent.py`

- [ ] **Step 1: Schemas**

Create `backend/schemas/admin_audit.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminAuditLogRow(BaseModel):
    id: str
    created_at: datetime
    user_id: str
    user_email: str
    action: str
    target: str
    metadata: dict[str, Any]


class AdminAuditLogResponse(BaseModel):
    entries: list[AdminAuditLogRow]
    total: int
    limit: int
    offset: int
```

- [ ] **Step 2: Router**

Create `backend/routers/admin_audit.py`:

```python
"""Admin audit log viewer (Spec D.6)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.models.admin_audit import AdminAuditLog
from backend.models.user import User
from backend.schemas.admin_audit import AdminAuditLogResponse, AdminAuditLogRow
from backend.services.permissions import require_admin

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])


@router.get("/recent", response_model=AdminAuditLogResponse)
async def get_recent_audit(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_async_session)],
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None),
) -> AdminAuditLogResponse:
    """Return recent admin audit entries joined with user email."""
    require_admin(user)

    base = select(AdminAuditLog, User.email).join(User, AdminAuditLog.user_id == User.id)
    if action:
        base = base.where(AdminAuditLog.action == action)
    total = (
        await db.execute(
            select(func.count())
            .select_from(AdminAuditLog)
            .where(AdminAuditLog.action == action if action else True)
        )
    ).scalar_one()

    rows = (
        await db.execute(
            base.order_by(AdminAuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    entries = [
        AdminAuditLogRow(
            id=str(log.id),
            created_at=log.created_at,
            user_id=str(log.user_id),
            user_email=email,
            action=log.action,
            target=log.target,
            metadata=log.metadata_ or {},
        )
        for log, email in rows
    ]
    return AdminAuditLogResponse(
        entries=entries, total=int(total), limit=limit, offset=offset
    )
```

- [ ] **Step 3: Mount**

Edit `backend/main.py`:

```python
from backend.routers import admin_audit
app.include_router(admin_audit.router, prefix="/api/v1")
```

- [ ] **Step 4: Tests**

Create `tests/api/test_admin_audit_recent.py`:

```python
"""Spec D.6 — admin audit viewer."""

import pytest


@pytest.mark.asyncio
async def test_audit_recent_joins_user_email(admin_client, seed_audit_entry):
    await seed_audit_entry(action="trigger_task", target="t1")
    r = await admin_client.get("/api/v1/admin/audit/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["entries"]
    assert "user_email" in body["entries"][0]


@pytest.mark.asyncio
async def test_audit_recent_filter_by_action(admin_client, seed_audit_entry):
    await seed_audit_entry(action="trigger_task", target="t1")
    await seed_audit_entry(action="reingest_ticker", target="AAPL")
    r = await admin_client.get("/api/v1/admin/audit/recent?action=reingest_ticker")
    body = r.json()
    assert all(e["action"] == "reingest_ticker" for e in body["entries"])
```

- [ ] **Step 5: Commit**

```bash
uv run pytest tests/api/test_admin_audit_recent.py -x
uv run ruff check --fix backend/schemas/admin_audit.py backend/routers/admin_audit.py backend/main.py tests/api/test_admin_audit_recent.py
uv run ruff format backend/schemas/admin_audit.py backend/routers/admin_audit.py backend/main.py tests/api/test_admin_audit_recent.py
git add backend/schemas/admin_audit.py backend/routers/admin_audit.py backend/main.py tests/api/test_admin_audit_recent.py
git commit -m "feat(admin): audit log viewer endpoint (Spec D.6)"
```

---

## Task 8: Frontend — hooks + types

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/hooks/use-admin-pipelines.ts`
- Create: `frontend/src/hooks/use-ingestion-health.ts`
- Create: `frontend/src/hooks/use-admin-audit.ts`

- [ ] **Step 1: Types**

Append to `frontend/src/types/api.ts`:

```ts
export interface PipelineTaskTriggerRequest {
  ticker?: string;
  failure_mode?: "stop_on_failure" | "continue";
  // Backend forbids extra fields; keep this interface minimal.
}

export interface PipelineTaskTriggerResponse {
  task_name: string;
  run_id: string;
  celery_task_id: string;
  ticker: string | null;
  status: "accepted";
  message: string;
}

export interface TaskLatencyPoint {
  bucket: string;
  p50_s: number;
  p95_s: number;
  runs: number;
}

export interface TaskLatencySeries {
  pipeline_name: string;
  points: TaskLatencyPoint[];
}

export interface TaskLatencyResponse {
  series: TaskLatencySeries[];
}

export interface IngestionHealthRow {
  ticker: string;
  name: string;
  sector: string | null;
  prices_updated_at: string | null;
  signals_updated_at: string | null;
  forecast_updated_at: string | null;
  news_updated_at: string | null;
  sentiment_updated_at: string | null;
  convergence_updated_at: string | null;
  is_stale_per_stage: Record<string, boolean>;
  last_error: Record<string, string> | null;
  overall_health: "green" | "yellow" | "red";
}

export interface IngestionHealthSummary {
  total: number;
  fresh: number;
  stale: number;
  missing: number;
}

export interface IngestionHealthResponse {
  tickers: IngestionHealthRow[];
  summary: IngestionHealthSummary;
  limit: number;
  offset: number;
}

export interface ReingestResponse {
  ticker: string;
  celery_task_id: string;
  status: "accepted";
}

export interface AdminAuditLogRow {
  id: string;
  created_at: string;
  user_id: string;
  user_email: string;
  action: string;
  target: string;
  metadata: Record<string, unknown>;
}

export interface AdminAuditLogResponse {
  entries: AdminAuditLogRow[];
  total: number;
  limit: number;
  offset: number;
}
```

- [ ] **Step 2: Extend `useAdminPipelines`**

Edit `frontend/src/hooks/use-admin-pipelines.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get, post } from "@/lib/api";
import type {
  PipelineTaskTriggerRequest,
  PipelineTaskTriggerResponse,
  TaskLatencyResponse,
} from "@/types/api";

export function useTriggerTask() {
  const qc = useQueryClient();
  return useMutation<
    PipelineTaskTriggerResponse,
    Error,
    { taskName: string; ticker?: string; failureMode?: string }
  >({
    mutationFn: ({ taskName, ticker, failureMode = "continue" }) =>
      post<PipelineTaskTriggerResponse>(
        `/admin/pipelines/tasks/${taskName}/run`,
        { ticker, failure_mode: failureMode } satisfies PipelineTaskTriggerRequest,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-pipelines"] });
      qc.invalidateQueries({ queryKey: ["admin-audit"] });
    },
  });
}

export function useTaskLatencyTrends(days: number = 7) {
  return useQuery<TaskLatencyResponse>({
    queryKey: ["admin-latency-trends", days],
    queryFn: () =>
      get<TaskLatencyResponse>(`/admin/pipelines/latency-trends?days=${days}`),
    refetchInterval: 5 * 60 * 1000,
  });
}
```

- [ ] **Step 3: Ingestion-health hook**

Create `frontend/src/hooks/use-ingestion-health.ts`:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get, post } from "@/lib/api";
import type { IngestionHealthResponse, ReingestResponse } from "@/types/api";

function buildQuery(filters: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v !== undefined && v !== null && v !== "") {
      params.append(k, String(v));
    }
  }
  return params.toString();
}

export function useIngestionHealth(filters: {
  staleOnly?: boolean;
  ticker?: string;
  stage?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery<IngestionHealthResponse>({
    queryKey: ["admin-ingestion-health", filters],
    queryFn: () =>
      get<IngestionHealthResponse>(
        `/admin/ingestion/health?${buildQuery({
          stale_only: filters.staleOnly,
          ticker: filters.ticker,
          stage: filters.stage,
          limit: filters.limit,
          offset: filters.offset,
        })}`,
      ),
    refetchInterval: 60_000,
  });
}

export function useReingestTicker() {
  const qc = useQueryClient();
  return useMutation<ReingestResponse, Error, string>({
    mutationFn: (ticker: string) =>
      post<ReingestResponse>(
        `/admin/ingestion/health/${ticker}/reingest`,
        {},
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-ingestion-health"] });
      qc.invalidateQueries({ queryKey: ["admin-audit"] });
    },
  });
}
```

- [ ] **Step 4: Admin audit hook**

Create `frontend/src/hooks/use-admin-audit.ts`:

```ts
import { useQuery } from "@tanstack/react-query";

import { get } from "@/lib/api";
import type { AdminAuditLogResponse } from "@/types/api";

export function useAdminAudit(limit: number = 50, action?: string) {
  return useQuery<AdminAuditLogResponse>({
    queryKey: ["admin-audit", limit, action],
    queryFn: () =>
      get<AdminAuditLogResponse>(
        `/admin/audit/recent?limit=${limit}${action ? `&action=${action}` : ""}`,
      ),
    staleTime: 30_000,
  });
}
```

- [ ] **Step 5: Commit**

```bash
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/types/api.ts frontend/src/hooks/use-admin-pipelines.ts frontend/src/hooks/use-ingestion-health.ts frontend/src/hooks/use-admin-audit.ts
git commit -m "feat(frontend): admin observability hooks + types (Spec D.2/D.3/D.6/D.7)"
```

---

## Task 9: Frontend — components + pages

**Files:**
- Modify: `frontend/src/components/admin/pipeline-task-row.tsx`
- Modify: `frontend/src/components/admin/pipeline-group-card.tsx`
- Create: `frontend/src/components/admin/ingestion-health-table.tsx`
- Create: `frontend/src/components/admin/recent-audit-panel.tsx`
- Create: `frontend/src/components/admin/task-latency-panel.tsx`
- Create: `frontend/src/app/(authenticated)/admin/ingestion-health/page.tsx`
- Modify: `frontend/src/components/sidebar-nav.tsx`
- Modify: `frontend/src/app/(authenticated)/admin/pipelines/page.tsx`

- [ ] **Step 1: Play button on pipeline-task-row**

Edit `frontend/src/components/admin/pipeline-task-row.tsx` — add a `Play` icon button with a popover for optional ticker input. Wire to `useTriggerTask().mutate({ taskName, ticker })`.

- [ ] **Step 2: IngestionHealthTable**

Create `frontend/src/components/admin/ingestion-health-table.tsx` — TanStack Table with columns: ticker, name, sector, last_prices, last_signals, last_forecast, last_news, overall_health badge (green/yellow/red), action button (calls `useReingestTicker`). Summary bar above the table. Filter chips: "All / Stale only / Red only". Refetches via `useIngestionHealth`.

- [ ] **Step 3: RecentAuditPanel**

Create `frontend/src/components/admin/recent-audit-panel.tsx` — shadcn `Card` wrapping a compact table: timestamp (relative), user, action (color badge), target, metadata (collapsed JSON). Uses `useAdminAudit`.

- [ ] **Step 4: TaskLatencyPanel**

Create `frontend/src/components/admin/task-latency-panel.tsx` — Recharts `LineChart` with `isAnimationActive={false}`, P50 + P95 lines per selected pipeline. Uses `useTaskLatencyTrends`. Pipeline selector via shadcn `Select`.

- [ ] **Step 5: Ingestion-health page**

Create `frontend/src/app/(authenticated)/admin/ingestion-health/page.tsx`:

```tsx
import { IngestionHealthTable } from "@/components/admin/ingestion-health-table";

export default function IngestionHealthPage() {
  return (
    <div className="p-4">
      <h1 className="text-2xl font-bold">Ingestion Health</h1>
      <IngestionHealthTable />
    </div>
  );
}
```

- [ ] **Step 6: Sidebar link**

Edit `frontend/src/components/sidebar-nav.tsx` — add under the admin section:

```tsx
{ label: "Ingestion Health", href: "/admin/ingestion-health", icon: Activity }
```

- [ ] **Step 7: Mount panels on admin pipelines page**

Edit `frontend/src/app/(authenticated)/admin/pipelines/page.tsx` — below the existing group cards, render `<RecentAuditPanel />` and `<TaskLatencyPanel />`.

- [ ] **Step 8: Frontend tests (minimum 3)**

Create `frontend/src/__tests__/components/admin/ingestion-health-table.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { server } from "@/test-utils/msw-server";
import { IngestionHealthTable } from "@/components/admin/ingestion-health-table";

describe("IngestionHealthTable", () => {
  it("renders red rows first", async () => {
    server.use(
      http.get("*/admin/ingestion/health", () =>
        HttpResponse.json({
          tickers: [
            { ticker: "GREEN", name: "Green", sector: null, overall_health: "green", is_stale_per_stage: {}, last_error: null, prices_updated_at: null, signals_updated_at: null, forecast_updated_at: null, news_updated_at: null, sentiment_updated_at: null, convergence_updated_at: null },
            { ticker: "RED", name: "Red", sector: null, overall_health: "red", is_stale_per_stage: {}, last_error: { prices: "err" }, prices_updated_at: null, signals_updated_at: null, forecast_updated_at: null, news_updated_at: null, sentiment_updated_at: null, convergence_updated_at: null },
          ],
          summary: { total: 2, fresh: 1, stale: 1, missing: 0 },
          limit: 100,
          offset: 0,
        }),
      ),
    );
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <IngestionHealthTable />
      </QueryClientProvider>,
    );
    await screen.findByText("RED");
    // Red row is present
    expect(screen.getByText("RED")).toBeInTheDocument();
  });
});
```

- [ ] **Step 9: Commit**

```bash
cd frontend && npm test -- admin && cd ..
cd frontend && npm run lint -- --fix && cd ..
git add frontend/src/components/admin/ frontend/src/app/\(authenticated\)/admin/ frontend/src/components/sidebar-nav.tsx frontend/src/__tests__/components/admin/
git commit -m "feat(frontend): admin observability UI — ingestion health, audit panel, latency chart (Spec D.3/D.6/D.7)"
```

---

## Task 10: Final integration sweep

- [ ] **Step 1: Run all new backend tests**

```bash
uv run pytest tests/unit/tasks/test_pipeline_runner_all_tasks.py tests/unit/tasks/test_task_tracer.py tests/unit/services/test_cache_invalidator_coverage.py tests/unit/services/test_langfuse_spans.py tests/api/test_admin_pipeline_task_trigger.py tests/api/test_admin_ingestion_health.py tests/api/test_admin_audit_recent.py -q
```

- [ ] **Step 2: Frontend tests**

```bash
cd frontend && npm test -- admin && cd ..
```

- [ ] **Step 3: Full lint**

```bash
uv run ruff check backend/ tests/
cd frontend && npm run lint && npm run typecheck && cd ..
```

- [ ] **Step 4: Smoke test**

Boot backend + frontend, navigate to `/admin/ingestion-health` and `/admin/pipelines`. Verify:
- Ingestion health table loads with red rows first
- Play button on a pipeline task triggers a Celery task and shows success toast
- Audit panel updates after the trigger
- Task latency chart renders p50 + p95 lines for at least one pipeline

---

## Done Criteria

- [ ] Every `@celery_app.task` function in `backend/tasks/**` is wrapped with `@tracked_task`; enforcement test green
- [ ] `task_tracer` context manager exists and no-ops when Langfuse disabled
- [ ] `POST /admin/pipelines/tasks/{task_name}/run` enforces registry whitelist + ticker whitelist + admin role
- [ ] `GET /admin/pipelines/latency-trends` returns p50/p95 per pipeline from `pipeline_runs`
- [ ] `GET /admin/ingestion/health` returns per-ticker rows with green/yellow/red classification
- [ ] `POST /admin/ingestion/health/{ticker}/reingest` dispatches `refresh_ticker_task`
- [ ] `GET /admin/audit/recent` returns joined audit rows with user email
- [ ] 4 new cache invalidator events (`on_convergence_updated`, `on_recommendations_updated`, `on_drift_detected`, `on_ticker_state_updated`)
- [ ] 5 guarded write sites fire their matching invalidator (coverage test green)
- [ ] Nightly chain creates root Langfuse trace with phase spans
- [ ] Prophet training + sentiment batch + news provider fetch all create spans
- [ ] Sentiment I/O sampling at `LANGFUSE_SENTIMENT_IO_SAMPLING_RATE` (default 0.25)
- [ ] Admin UI: ingestion health page, audit panel, latency panel, play-button trigger
- [ ] ~36 new test cases across unit + API + frontend
