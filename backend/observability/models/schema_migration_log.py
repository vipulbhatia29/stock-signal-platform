"""SQLAlchemy model for observability.schema_migration_log.

Records Alembic migration execution events. Regular table (not a hypertable) —
low volume. Retention enforced by Celery row-level DELETE task (365 days).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class SchemaMigrationLog(Base):
    """Per-migration-execution row in observability schema.

    Attributes:
        id: Surrogate primary key (UUID, server-generated).
        ts: Wall-clock timestamp of the migration execution (with timezone).
        trace_id: Distributed trace ID.
        span_id: Span ID for this migration.
        migration_id: Alembic revision ID.
        version: Human-readable version label (e.g. "034").
        status: Migration execution status (pending, running, success, failed, rolled_back).
        duration_ms: Execution time in milliseconds.
        error_message: Error message if status is failed.
        env: Deployment environment.
        git_sha: Git commit SHA of the running binary.
    """

    __tablename__ = "schema_migration_log"
    __table_args__ = {"schema": "observability"}

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    trace_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    span_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)

    migration_id: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    env: Mapped[str] = mapped_column(Text, nullable=False)
    git_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
