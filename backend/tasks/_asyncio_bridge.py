"""Bridge for running async code from synchronous Celery tasks.

Celery prefork workers create the async SQLAlchemy engine at import time,
binding its connection pool to an event loop that may become stale.
When a task calls asyncio.run(), a new loop is created but the pool's
futures reference the old one → "Future attached to a different loop".

Fix: dispose the engine's connection pool before each asyncio.run() call
so fresh connections are created on the new loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine


def safe_asyncio_run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a Celery task safely.

    Disposes the engine's pooled connections before creating a new event
    loop, ensuring no stale futures from a previous loop cause errors.
    """
    from backend.database import engine

    engine.sync_engine.dispose()
    return asyncio.run(coro)
