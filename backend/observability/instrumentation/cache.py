"""Cache operation instrumentation — latency tracking + sampled emission.

Non-error operations are sampled at 1% (random.random() < 0.01).
Error operations are always captured (100%).

Key pattern redaction: UUIDs and numeric IDs in cache keys are replaced with
``*`` to prevent PII leakage while preserving key structure for grouping.
E.g., ``user:abc123:profile`` → ``user:*:profile``.
"""

from __future__ import annotations

import logging
import random
import re
import uuid
from datetime import datetime, timezone

from backend.config import settings

logger = logging.getLogger(__name__)

# Sampling rate for non-error cache operations
SAMPLE_RATE = 0.01

# Key redaction patterns: UUIDs, hex strings ≥8 chars, numeric IDs
_KEY_REDACT_PATTERNS = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I), "*"),
    (re.compile(r"[0-9a-f]{8,}"), "*"),
    (re.compile(r"(?<=:)\d+(?=:|$)"), "*"),
]


def redact_key(key: str) -> str:
    """Redact sensitive portions of a cache key for observability.

    Args:
        key: Raw cache key (e.g., "user:abc123:profile").

    Returns:
        Redacted key pattern (e.g., "user:*:profile").
    """
    result = key
    for pattern, replacement in _KEY_REDACT_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def _emit_cache_op(
    operation: str,
    key: str,
    *,
    hit: bool | None = None,
    latency_ms: int = 0,
    value_bytes: int | None = None,
    ttl_seconds: int | None = None,
    error_reason: str | None = None,
) -> None:
    """Emit a CACHE_OPERATION event via the obs SDK.

    Args:
        operation: Cache operation type (get, set, delete).
        key: Raw cache key (will be redacted).
        hit: Cache hit/miss for GET operations.
        latency_ms: Operation latency in milliseconds.
        value_bytes: Size of cached value in bytes (for SET).
        ttl_seconds: TTL applied to the key (for SET).
        error_reason: Error classification if the operation failed.
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
            CacheOperationEvent,
            CacheOperationType,
        )

        client = _maybe_get_obs_client()
        if client is None:
            return

        event = CacheOperationEvent(
            trace_id=current_trace_id() or uuid.uuid4(),
            span_id=current_span_id() or uuid.uuid4(),
            parent_span_id=None,
            ts=datetime.now(timezone.utc),
            env=getattr(settings, "APP_ENV", "dev"),
            git_sha=getattr(settings, "GIT_SHA", None),
            user_id=current_user_id.get(),
            session_id=current_session_id.get(),
            query_id=None,
            operation=CacheOperationType(operation),
            key_pattern=redact_key(key),
            hit=hit,
            latency_ms=latency_ms,
            value_bytes=value_bytes,
            ttl_seconds=ttl_seconds,
            error_reason=error_reason,
        )
        client.emit_sync(event)
    except Exception:  # noqa: BLE001 — instrumentation must not break cache ops
        logger.debug("obs.cache_op.emit_failed", exc_info=True)


def observe_cache_get(key: str, result: str | None, latency_ms: int) -> None:
    """Observe a cache GET operation (sampled at 1%).

    Args:
        key: Cache key.
        result: Value returned (None = miss).
        latency_ms: Operation latency in milliseconds.
    """
    if random.random() < SAMPLE_RATE:
        _emit_cache_op("get", key, hit=result is not None, latency_ms=latency_ms)


def observe_cache_set(key: str, value: str, ttl: int, latency_ms: int) -> None:
    """Observe a cache SET operation (sampled at 1%).

    Args:
        key: Cache key.
        value: Value being cached.
        ttl: TTL in seconds.
        latency_ms: Operation latency in milliseconds.
    """
    if random.random() < SAMPLE_RATE:
        _emit_cache_op(
            "set",
            key,
            latency_ms=latency_ms,
            value_bytes=len(value.encode()) if value else None,
            ttl_seconds=ttl,
        )


def observe_cache_delete(key: str, latency_ms: int) -> None:
    """Observe a cache DELETE operation (sampled at 1%).

    Args:
        key: Cache key.
        latency_ms: Operation latency in milliseconds.
    """
    if random.random() < SAMPLE_RATE:
        _emit_cache_op("delete", key, latency_ms=latency_ms)


def observe_cache_error(operation: str, key: str, latency_ms: int) -> None:
    """Observe a cache error (always captured, 100%).

    Args:
        operation: Cache operation that failed (get, set, delete).
        key: Cache key.
        latency_ms: Operation latency in milliseconds.
    """
    _emit_cache_op(operation, key, latency_ms=latency_ms, error_reason="connection_error")
