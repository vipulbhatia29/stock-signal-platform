"""Unit tests for backend.services.ingest_lock — Redis SETNX dedup lock."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.services.ingest_lock import (
    IN_FLIGHT_KEY,
    LOCK_TTL_SECONDS,
    acquire_ingest_lock,
    release_ingest_lock,
)

# ---------------------------------------------------------------------------
# acquire_ingest_lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_lock_returns_true_on_success() -> None:
    """Returns True when SETNX succeeds (key did not exist)."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True

    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        result = await acquire_ingest_lock("AAPL")

    assert result is True


@pytest.mark.asyncio
async def test_acquire_lock_returns_false_when_held() -> None:
    """Returns False when SETNX fails because the key already exists."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = None  # redis.set nx=True returns None on key exists

    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        result = await acquire_ingest_lock("AAPL")

    assert result is False


@pytest.mark.asyncio
async def test_acquire_lock_sets_ttl_60s() -> None:
    """The SETNX call passes ex=60 and nx=True."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True

    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        await acquire_ingest_lock("AAPL")

    mock_redis.set.assert_called_once_with(
        IN_FLIGHT_KEY.format(ticker="AAPL"),
        "1",
        ex=LOCK_TTL_SECONDS,
        nx=True,
    )


@pytest.mark.asyncio
async def test_release_lock_deletes_key() -> None:
    """Calls redis.delete with the correct key on release."""
    mock_redis = AsyncMock()

    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        await release_ingest_lock("AAPL")

    mock_redis.delete.assert_called_once_with(IN_FLIGHT_KEY.format(ticker="AAPL"))


@pytest.mark.asyncio
async def test_acquire_lock_redis_down_returns_true() -> None:
    """Fail-open: returns True (allow operation) when Redis raises an exception."""

    async def broken_get_redis() -> None:
        raise ConnectionError("Redis is down")

    with patch("backend.services.ingest_lock.get_redis", side_effect=broken_get_redis):
        result = await acquire_ingest_lock("AAPL")

    assert result is True


@pytest.mark.asyncio
async def test_release_lock_redis_down_no_raise() -> None:
    """Release silently swallows exceptions when Redis is unavailable."""

    async def broken_get_redis() -> None:
        raise ConnectionError("Redis is down")

    with patch("backend.services.ingest_lock.get_redis", side_effect=broken_get_redis):
        # Should not raise
        await release_ingest_lock("AAPL")


@pytest.mark.asyncio
async def test_lock_key_format_uppercased() -> None:
    """Ticker is uppercased when building the Redis key."""
    mock_redis = AsyncMock()
    mock_redis.set.return_value = True

    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        await acquire_ingest_lock("aapl")

    expected_key = IN_FLIGHT_KEY.format(ticker="AAPL")
    call_args = mock_redis.set.call_args
    assert call_args[0][0] == expected_key


@pytest.mark.asyncio
async def test_decode_responses_compat() -> None:
    """bool(True) == True and bool(None) == False — decode_responses=True compat."""
    mock_redis = AsyncMock()

    # Simulate decode_responses=True: set returns True (str "1" coerced) or None
    mock_redis.set.return_value = True
    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        result_acquired = await acquire_ingest_lock("TSLA")
    assert result_acquired is True

    mock_redis.set.return_value = None
    with patch("backend.services.ingest_lock.get_redis", return_value=mock_redis):
        result_not_acquired = await acquire_ingest_lock("TSLA")
    assert result_not_acquired is False
