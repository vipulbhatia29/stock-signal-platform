"""Pydantic event schemas for DB + Cache layer observability (1b PR3).

Four event types:
- SlowQueryEvent — queries exceeding 500ms threshold
- DbPoolEvent — connection pool exhaustion/recovery/slow checkout
- SchemaMigrationEvent — Alembic migration execution tracking
- CacheOperationEvent — Redis cache operations (1% sampled, 100% on error)
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from backend.observability.schema.v1 import ObsEventBase


class DbPoolEventType(str, Enum):
    """Types of database connection pool events."""

    EXHAUSTED = "exhausted"
    RECOVERED = "recovered"
    SLOW_CHECKOUT = "slow_checkout"
    CONNECTION_ERROR = "connection_error"


class MigrationStatus(str, Enum):
    """Status of a schema migration execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CacheOperationType(str, Enum):
    """Types of cache operations."""

    GET = "get"
    SET = "set"
    DELETE = "delete"
    MGET = "mget"


class SlowQueryEvent(ObsEventBase):
    """Event emitted when a SQL query exceeds the slow query threshold (500ms).

    Attributes:
        event_type: Always SLOW_QUERY.
        query_text: Normalized query with literals replaced by $N placeholders.
        query_hash: SHA256 hash of normalized query for grouping.
        duration_ms: Query execution time in milliseconds.
        rows_affected: Number of rows returned or affected.
        source_file: Python source file that initiated the query (if available).
        source_line: Line number in source file (if available).
    """

    event_type: Literal["slow_query"] = "slow_query"  # type: ignore[assignment]
    query_text: str
    query_hash: str
    duration_ms: int
    rows_affected: int | None = None
    source_file: str | None = None
    source_line: int | None = None


class DbPoolEvent(ObsEventBase):
    """Event emitted on connection pool state changes.

    Attributes:
        event_type: Always DB_POOL_EVENT.
        pool_event_type: Type of pool event (exhausted, recovered, etc.).
        pool_size: Configured pool size.
        checked_out: Number of currently checked-out connections.
        overflow: Number of overflow connections in use.
        duration_ms: Duration of checkout wait (for slow_checkout events).
    """

    event_type: Literal["db_pool_event"] = "db_pool_event"  # type: ignore[assignment]
    pool_event_type: DbPoolEventType
    pool_size: int
    checked_out: int
    overflow: int
    duration_ms: int | None = None


class SchemaMigrationEvent(ObsEventBase):
    """Event emitted when an Alembic migration runs.

    Attributes:
        event_type: Always SCHEMA_MIGRATION.
        migration_id: Alembic revision ID.
        version: Human-readable version label (e.g. "034").
        status: Migration execution status.
        duration_ms: Execution time in milliseconds.
        error_message: Error message if status is FAILED.
    """

    event_type: Literal["schema_migration"] = "schema_migration"  # type: ignore[assignment]
    migration_id: str
    version: str
    status: MigrationStatus
    duration_ms: int
    error_message: str | None = None


class CacheOperationEvent(ObsEventBase):
    """Event emitted for Redis cache operations (sampled).

    Non-error operations are sampled at 1%. Error operations are always captured.

    Attributes:
        event_type: Always CACHE_OPERATION.
        operation: Cache operation type (get, set, delete, mget).
        key_pattern: Redacted cache key (UUIDs/IDs replaced with *).
        hit: Whether the cache operation was a hit (for get operations).
        latency_ms: Operation latency in milliseconds.
        value_bytes: Size of the cached value in bytes (for set operations).
        ttl_seconds: TTL set on the key (for set operations).
        error_reason: Error classification if the operation failed.
    """

    event_type: Literal["cache_operation"] = "cache_operation"  # type: ignore[assignment]
    operation: CacheOperationType
    key_pattern: str
    hit: bool | None = None
    latency_ms: int
    value_bytes: int | None = None
    ttl_seconds: int | None = None
    error_reason: str | None = None
