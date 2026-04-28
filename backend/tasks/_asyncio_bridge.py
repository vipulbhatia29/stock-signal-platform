"""Bridge for running async code from synchronous Celery tasks.

Celery prefork workers import the async SQLAlchemy engine at module load,
creating an asyncpg connection pool bound to an event loop that may not
match the loop created by asyncio.run(). This causes:
  "Future attached to a different loop"

Fix: recreate the engine + session factory for each asyncio.run() call,
ensuring all connections are created on the correct loop.
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine


def safe_asyncio_run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from a Celery task safely.

    Recreates the async engine and rebinds the session factory so all
    connections are created on the new event loop. The fresh engine is
    disposed inside the same event loop that created it.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    import backend.database as db_module
    from backend.config import settings

    # Create a fresh engine for this run
    fresh_engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=5,
        max_overflow=2,
        pool_recycle=300,
    )

    # Rebind the module-level session factory to the fresh engine
    db_module.async_session_factory = async_sessionmaker(
        fresh_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def _run_and_cleanup() -> Any:
        try:
            return await coro
        finally:
            await fresh_engine.dispose()

    return asyncio.run(_run_and_cleanup())
