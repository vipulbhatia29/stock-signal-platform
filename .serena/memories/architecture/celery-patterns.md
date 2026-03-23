---
scope: project
category: architecture
---

# Celery Patterns

## Entry Points

- `backend/tasks/__init__.py` — Celery app factory, imports all task modules, beat schedule
- `backend/tasks/market_data.py` — nightly signal + price computation tasks
- `backend/tasks/portfolio.py` — daily portfolio snapshot task
- `backend/tasks/pipeline.py` — PipelineRunner, watermark, gap detection, retry (Phase 5)
- `backend/tasks/forecasting.py` — Prophet retrain/refresh tasks (Phase 5)
- `backend/tasks/evaluation.py` — forecast eval, drift detection, recommendation eval (Phase 5)
- `backend/tasks/alerts.py` — alert generation from pipeline events (Phase 5)
- `backend/tasks/recommendations.py` — nightly recommendation generation (Phase 5)

## Running Celery

```bash
uv run celery -A backend.tasks worker --loglevel=info   # Worker
uv run celery -A backend.tasks beat --loglevel=info     # Beat scheduler
```

## Key Design Rules

- **Celery tasks are synchronous** — they run in a thread pool, not an async event loop.
- **Bridge pattern for async code**: if a task needs to call an async function, use `asyncio.run()`:

```python
import asyncio
from backend.database import async_session_factory

@celery_app.task
def compute_nightly_signals():
    asyncio.run(_async_compute())

async def _async_compute():
    async with async_session_factory() as session:
        # ... async DB work here
```

- **Never** `await` inside a Celery task body directly — it will silently fail or raise.
- **Never** call `get_event_loop()` — use `asyncio.run()` which creates a fresh loop.

## Beat Schedule

Nightly signal computation runs via Celery Beat. Schedule defined in `backend/tasks/__init__.py`
under `beat_schedule`. Signals are pre-computed so the dashboard reads cached results (not on-demand).

## Task Naming Convention

```python
@celery_app.task(name="tasks.compute_signals_for_ticker")
def compute_signals_for_ticker(ticker: str) -> dict:
    ...
```

Always use explicit `name=` to avoid import-path-based task naming breaking on refactors.

## Redis as Broker

- Celery uses Redis as both broker and result backend.
- `REDIS_URL=redis://localhost:6380/0` — note non-default port 6380.
- Redis DB 0 for Celery; app cache can use DB 1 if needed.
