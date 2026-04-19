"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
)

# Attach observability hooks to the sync engine underlying the async wrapper.
# Import is deferred to avoid circular imports at module level.
try:
    from backend.observability.instrumentation.db import (
        attach_pool_hooks,
        attach_slow_query_hooks,
    )

    attach_slow_query_hooks(engine.sync_engine)
    attach_pool_hooks(engine.sync_engine)
except Exception:  # noqa: BLE001 — obs hooks must not break startup
    import logging as _logging

    _logging.getLogger(__name__).warning(
        "obs.db.hook_attach_failed — slow query/pool monitoring disabled",
        exc_info=True,
    )

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for FastAPI dependency injection."""
    async with async_session_factory() as session:
        yield session
