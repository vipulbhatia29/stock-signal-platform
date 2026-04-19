"""Alembic environment configuration for async SQLAlchemy."""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from backend.config import settings
from backend.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_mig_logger = logging.getLogger(__name__)


def _emit_migration_event(
    migration_id: str, version: str, status: str, duration_ms: int, error_message: str | None = None
) -> None:
    """Emit a SCHEMA_MIGRATION event via the obs SDK (sync).

    Args:
        migration_id: Alembic revision ID.
        version: Human-readable version label.
        status: Migration execution status (success, failed).
        duration_ms: Execution time in milliseconds.
        error_message: Error message if status is failed.
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.schema.db_cache_events import (
            MigrationStatus,
            SchemaMigrationEvent,
        )

        client = _maybe_get_obs_client()
        if client is None:
            return

        event = SchemaMigrationEvent(
            trace_id=uuid.uuid4(),
            span_id=uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=None,
            session_id=None,
            query_id=None,
            migration_id=migration_id,
            version=version,
            status=MigrationStatus(status),
            duration_ms=duration_ms,
            error_message=error_message,
        )
        client.emit_sync(event)
    except Exception:  # noqa: BLE001 — migration emission must not break migrations
        _mig_logger.debug("obs.schema_migration.emit_failed", exc_info=True)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations with the given connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    start = time.monotonic()
    try:
        with context.begin_transaction():
            context.run_migrations()
        duration_ms = int((time.monotonic() - start) * 1000)
        # Emit success for the overall migration run
        head = config.get_main_option("revision") or "head"
        _emit_migration_event(head, head, "success", duration_ms)
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        head = config.get_main_option("revision") or "head"
        _emit_migration_event(head, head, "failed", duration_ms, type(exc).__name__)
        raise


async def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
