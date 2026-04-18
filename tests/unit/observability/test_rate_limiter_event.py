"""Unit tests for rate-limiter observability event emission.

Each test constructs a test-scoped ObservabilityClient backed by MemoryTarget,
monkeypatches ``_maybe_get_obs_client`` in the ``rate_limiter`` module, and
verifies that the correct RateLimiterEventPayload fields are emitted on each
permissive-fallback path.

No real Redis is needed — Redis interactions are patched with lightweight async mocks.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from backend.observability.client import ObservabilityClient
from backend.observability.schema.rate_limiter_events import RateLimiterEventPayload
from backend.observability.targets.memory import MemoryTarget
from backend.services.rate_limiter import TokenBucketLimiter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_obs_client(tmp_path: Path) -> ObservabilityClient:
    """Create a lightweight ObservabilityClient backed by MemoryTarget.

    Args:
        tmp_path: Temporary directory for spool (disabled but required by API).

    Returns:
        A fully configured ObservabilityClient with MemoryTarget.
    """
    target = MemoryTarget()
    return ObservabilityClient(
        target=target,
        spool_dir=tmp_path,
        spool_enabled=False,
        flush_interval_ms=50,
        buffer_size=100,
        enabled=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def obs_and_target(tmp_path: Path):
    """Provide a started ObservabilityClient + its MemoryTarget.

    Yields:
        Tuple of (ObservabilityClient, MemoryTarget).
    """
    target = MemoryTarget()
    client = ObservabilityClient(
        target=target,
        spool_dir=tmp_path,
        spool_enabled=False,
        flush_interval_ms=50,
        buffer_size=100,
        enabled=True,
    )
    await client.start()
    yield client, target
    await client.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limiter_emits_on_redis_down(obs_and_target, monkeypatch) -> None:
    """When Redis is unreachable, a fallback_permissive/redis_down event is emitted."""
    obs_client, target = obs_and_target

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: obs_client,
    )

    async def _broken_redis() -> None:
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _broken_redis)

    limiter = TokenBucketLimiter("test_redis_down", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire()

    assert result is True  # permissive fallback
    await obs_client.flush()

    assert len(target.events) == 1
    event = target.events[0]
    assert isinstance(event, RateLimiterEventPayload)
    assert event.limiter_name == "test_redis_down"
    assert event.action == "fallback_permissive"
    assert event.reason_if_fallback == "redis_down"
    assert event.wait_time_ms is None


@pytest.mark.asyncio
async def test_rate_limiter_emits_on_script_load_failure(obs_and_target, monkeypatch) -> None:
    """When script_load fails, a fallback_permissive/script_load_failed event is emitted."""
    obs_client, target = obs_and_target

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: obs_client,
    )

    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(side_effect=ConnectionError("script_load failed"))

    async def _get_redis_mock():
        return mock_redis

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _get_redis_mock)

    limiter = TokenBucketLimiter("test_script_load", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire()

    assert result is True  # permissive fallback
    await obs_client.flush()

    assert len(target.events) == 1
    event = target.events[0]
    assert isinstance(event, RateLimiterEventPayload)
    assert event.limiter_name == "test_script_load"
    assert event.action == "fallback_permissive"
    assert event.reason_if_fallback == "script_load_failed"


@pytest.mark.asyncio
async def test_rate_limiter_emits_on_redis_error_response(obs_and_target, monkeypatch) -> None:
    """When evalsha raises a non-NOSCRIPT ResponseError, a redis_error event is emitted."""
    obs_client, target = obs_and_target

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: obs_client,
    )

    from redis.exceptions import ResponseError

    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(return_value="deadbeef")
    mock_redis.evalsha = AsyncMock(side_effect=ResponseError("ERR some redis error"))

    async def _get_redis_mock():
        return mock_redis

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _get_redis_mock)

    limiter = TokenBucketLimiter("test_redis_error", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire()

    assert result is True  # permissive fallback
    await obs_client.flush()

    assert len(target.events) == 1
    event = target.events[0]
    assert isinstance(event, RateLimiterEventPayload)
    assert event.limiter_name == "test_redis_error"
    assert event.action == "fallback_permissive"
    assert event.reason_if_fallback == "redis_error"


@pytest.mark.asyncio
async def test_rate_limiter_emits_on_generic_exception(obs_and_target, monkeypatch) -> None:
    """When evalsha raises a generic Exception, a redis_error event is emitted."""
    obs_client, target = obs_and_target

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: obs_client,
    )

    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(return_value="deadbeef")
    mock_redis.evalsha = AsyncMock(side_effect=RuntimeError("unexpected redis failure"))

    async def _get_redis_mock():
        return mock_redis

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _get_redis_mock)

    limiter = TokenBucketLimiter("test_generic_error", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire()

    assert result is True  # permissive fallback
    await obs_client.flush()

    assert len(target.events) == 1
    event = target.events[0]
    assert isinstance(event, RateLimiterEventPayload)
    assert event.limiter_name == "test_generic_error"
    assert event.action == "fallback_permissive"
    assert event.reason_if_fallback == "redis_error"


@pytest.mark.asyncio
async def test_rate_limiter_emits_on_timeout(obs_and_target, monkeypatch) -> None:
    """When acquire times out waiting for tokens, a timeout event is emitted."""
    obs_client, target = obs_and_target

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: obs_client,
    )

    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(return_value="deadbeef")
    # evalsha always returns 0 — no tokens available
    mock_redis.evalsha = AsyncMock(return_value=0)

    async def _get_redis_mock():
        return mock_redis

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _get_redis_mock)

    # Very short timeout so the test runs quickly
    timeout_s = 0.05
    limiter = TokenBucketLimiter("test_timeout", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire(timeout=timeout_s)

    assert result is False  # actually timed out — does NOT allow through
    await obs_client.flush()

    assert len(target.events) == 1
    event = target.events[0]
    assert isinstance(event, RateLimiterEventPayload)
    assert event.limiter_name == "test_timeout"
    assert event.action == "timeout"
    assert event.reason_if_fallback is None
    assert event.wait_time_ms == int(timeout_s * 1000)


@pytest.mark.asyncio
async def test_rate_limiter_no_emission_on_success(obs_and_target, monkeypatch) -> None:
    """Normal token acquisition does NOT emit any event."""
    obs_client, target = obs_and_target

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: obs_client,
    )

    mock_redis = AsyncMock()
    mock_redis.script_load = AsyncMock(return_value="deadbeef")
    # evalsha returns 1 — token acquired immediately
    mock_redis.evalsha = AsyncMock(return_value=1)

    async def _get_redis_mock():
        return mock_redis

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _get_redis_mock)

    limiter = TokenBucketLimiter("test_success", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire()

    assert result is True
    await obs_client.flush()

    # No events should have been emitted on the success path
    assert len(target.events) == 0


@pytest.mark.asyncio
async def test_emission_failure_does_not_break_rate_limiter(monkeypatch) -> None:
    """When the emission helper raises internally, the rate limiter still returns True."""

    def _exploding_obs_client():
        boom = MagicMock()
        boom.emit_sync = MagicMock(side_effect=RuntimeError("emit kaboom"))
        return boom

    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        _exploding_obs_client,
    )

    async def _broken_redis() -> None:
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _broken_redis)

    limiter = TokenBucketLimiter("test_emit_safe", capacity=10, refill_per_sec=1.0)
    # Must NOT raise despite exploding emission path
    result = await limiter.acquire()
    assert result is True


@pytest.mark.asyncio
async def test_no_obs_client_does_not_raise(monkeypatch) -> None:
    """When _maybe_get_obs_client returns None, the rate limiter proceeds without error."""
    monkeypatch.setattr(
        "backend.observability.bootstrap._maybe_get_obs_client",
        lambda: None,
    )

    async def _broken_redis() -> None:
        raise ConnectionError("Redis unavailable")

    monkeypatch.setattr("backend.services.rate_limiter.get_redis", _broken_redis)

    limiter = TokenBucketLimiter("test_no_client", capacity=10, refill_per_sec=1.0)
    result = await limiter.acquire()
    assert result is True  # permissive fallback, no exception
