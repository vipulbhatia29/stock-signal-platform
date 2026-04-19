"""SQLAlchemy event hooks for slow query detection and connection pool monitoring.

Attaches to engine-level events:
- ``before_execute`` / ``after_execute`` — measure query duration, emit SLOW_QUERY
  for queries exceeding the threshold (default 500ms).
- ``checkout`` / ``checkin`` / ``close_detached`` — monitor pool state, emit
  DB_POOL_EVENT on exhaustion or slow checkout (>1s).

CRITICAL: The ``after_execute`` hook fires on observability writer INSERTs too.
A ``_in_obs_write`` ContextVar guard prevents feedback loops — writers set it
``True`` before committing, and the hook skips emission when it's set.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import Pool

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Feedback loop guard ────────────────────────────────────────────────────
_in_obs_write: ContextVar[bool] = ContextVar("_in_obs_write", default=False)

# ── Slow query threshold ──────────────────────────────────────────────────
SLOW_QUERY_THRESHOLD_MS = 500

# ── Pool slow checkout threshold ──────────────────────────────────────────
SLOW_CHECKOUT_THRESHOLD_MS = 1000

# ── Query normalization ───────────────────────────────────────────────────
# Replace string literals, numeric literals, UUIDs, and IN-lists with placeholders
_PATTERNS = [
    (re.compile(r"'[^']*'"), "$S"),  # string literals
    (re.compile(r"\b\d+\.?\d*\b"), "$N"),  # numeric literals
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "$U"),
    (re.compile(r"\bIN\s*\([^)]+\)", re.I), "IN ($...)"),  # IN-lists
]


def normalize_query(sql: str) -> str:
    """Replace literal values in SQL with placeholders for grouping.

    Args:
        sql: Raw SQL query string.

    Returns:
        Normalized query string with literals replaced by $N/$S/$U placeholders.
    """
    result = sql
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def query_hash(normalized: str) -> str:
    """Compute a short hash of a normalized query for grouping.

    Args:
        normalized: Normalized SQL query string.

    Returns:
        First 16 hex chars of SHA256 hash.
    """
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _emit_slow_query(
    normalized: str,
    hash_val: str,
    duration_ms: int,
    rows_affected: int | None,
) -> None:
    """Emit a SLOW_QUERY event via the obs SDK.

    Args:
        normalized: Normalized query text.
        hash_val: SHA256 hash prefix for grouping.
        duration_ms: Query execution time in milliseconds.
        rows_affected: Number of rows returned or affected.
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.context import (
            current_session_id,
            current_span_id,
            current_trace_id,
            current_user_id,
        )
        from backend.observability.schema.db_cache_events import SlowQueryEvent

        client = _maybe_get_obs_client()
        if client is None:
            return

        event_obj = SlowQueryEvent(
            trace_id=current_trace_id() or uuid.uuid4(),
            span_id=current_span_id() or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=current_user_id.get(),
            session_id=current_session_id.get(),
            query_id=None,
            query_text=normalized,
            query_hash=hash_val,
            duration_ms=duration_ms,
            rows_affected=rows_affected,
        )
        client.emit_sync(event_obj)
    except Exception:  # noqa: BLE001 — instrumentation must not break queries
        logger.debug("obs.slow_query.emit_failed", exc_info=True)


def _emit_pool_event(
    pool_event_type: str,
    pool: Pool,
    duration_ms: int | None = None,
) -> None:
    """Emit a DB_POOL_EVENT via the obs SDK.

    Args:
        pool_event_type: Type of pool event (exhausted, slow_checkout, etc.).
        pool: SQLAlchemy connection pool instance.
        duration_ms: Duration of checkout wait for slow_checkout events.
    """
    try:
        from backend.observability.bootstrap import _maybe_get_obs_client
        from backend.observability.context import (
            current_session_id,
            current_span_id,
            current_trace_id,
            current_user_id,
        )
        from backend.observability.schema.db_cache_events import (
            DbPoolEvent,
            DbPoolEventType,
        )

        client = _maybe_get_obs_client()
        if client is None:
            return

        event_obj = DbPoolEvent(
            trace_id=current_trace_id() or uuid.uuid4(),
            span_id=current_span_id() or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=current_user_id.get(),
            session_id=current_session_id.get(),
            query_id=None,
            pool_event_type=DbPoolEventType(pool_event_type),
            pool_size=pool.size(),
            checked_out=pool.checkedout(),
            overflow=pool.overflow(),
            duration_ms=duration_ms,
        )
        client.emit_sync(event_obj)
    except Exception:  # noqa: BLE001 — instrumentation must not break pool ops
        logger.debug("obs.db_pool_event.emit_failed", exc_info=True)


# ── Connection info key for timing ────────────────────────────────────────
_QUERY_START_KEY = "obs_query_start"


def attach_slow_query_hooks(engine: Engine) -> None:
    """Attach before_execute/after_execute hooks for slow query detection.

    Args:
        engine: SQLAlchemy engine to instrument.
    """

    @event.listens_for(engine, "before_execute")
    def _before_execute(conn: Connection, clauseelement, multiparams, params, execution_options):  # type: ignore[no-untyped-def]
        """Record query start time on connection info dict."""
        conn.info[_QUERY_START_KEY] = time.monotonic()

    @event.listens_for(engine, "after_execute")
    def _after_execute(
        conn: Connection, clauseelement, multiparams, params, execution_options, result
    ):  # type: ignore[no-untyped-def]
        """Check query duration and emit SLOW_QUERY if above threshold."""
        # Feedback loop guard: skip obs writer queries
        if _in_obs_write.get():
            return

        start = conn.info.pop(_QUERY_START_KEY, None)
        if start is None:
            return

        duration_ms = int((time.monotonic() - start) * 1000)
        if duration_ms < SLOW_QUERY_THRESHOLD_MS:
            return

        # Skip queries targeting the observability schema
        sql_str = str(clauseelement)
        if "observability." in sql_str:
            return

        normalized = normalize_query(sql_str)
        hash_val = query_hash(normalized)
        rows_affected = result.rowcount if hasattr(result, "rowcount") else None

        _emit_slow_query(normalized, hash_val, duration_ms, rows_affected)


def attach_pool_hooks(engine: Engine) -> None:
    """Attach pool event listeners for monitoring.

    Args:
        engine: SQLAlchemy engine to instrument.
    """
    pool = engine.pool

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):  # type: ignore[no-untyped-def]
        """Track checkout timing — emit on slow checkout."""
        connection_record.info["obs_checkout_start"] = time.monotonic()

    @event.listens_for(pool, "checkin")
    def _on_checkin(dbapi_conn, connection_record):  # type: ignore[no-untyped-def]
        """Check for slow checkout on connection return."""
        start = connection_record.info.pop("obs_checkout_start", None)
        if start is None:
            return
        duration_ms = int((time.monotonic() - start) * 1000)
        if duration_ms > SLOW_CHECKOUT_THRESHOLD_MS:
            _emit_pool_event("slow_checkout", pool, duration_ms=duration_ms)

    @event.listens_for(pool, "close_detached")
    def _on_close_detached(dbapi_conn):  # type: ignore[no-untyped-def]
        """Emit connection_error when a detached connection is closed."""
        _emit_pool_event("connection_error", pool)
