"""Tests for the Redis-backed token blocklist service."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.services import token_blocklist


@pytest.fixture(autouse=True)
def _mock_redis():
    """Mock the Redis client for all tests in this module."""
    mock_redis = AsyncMock()
    # Default: key does not exist
    mock_redis.exists.return_value = 0
    with patch.object(token_blocklist, "_redis_client", mock_redis):
        yield mock_redis


class TestAddToBlocklist:
    """Tests for adding JTIs to the blocklist."""

    @pytest.mark.asyncio
    async def test_add_sets_key_with_ttl(self, _mock_redis: AsyncMock) -> None:
        """Adding a JTI should SET the key with the given TTL."""
        jti = str(uuid.uuid4())
        await token_blocklist.add_to_blocklist(jti, expires_in_seconds=3600)
        _mock_redis.set.assert_called_once_with(f"blocklist:jti:{jti}", "1", ex=3600)

    @pytest.mark.asyncio
    async def test_add_skips_expired_token(self, _mock_redis: AsyncMock) -> None:
        """Should not blocklist a token that is already expired (TTL <= 0)."""
        jti = str(uuid.uuid4())
        await token_blocklist.add_to_blocklist(jti, expires_in_seconds=0)
        _mock_redis.set.assert_not_called()

        await token_blocklist.add_to_blocklist(jti, expires_in_seconds=-10)
        _mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_idempotent(self, _mock_redis: AsyncMock) -> None:
        """Adding the same JTI twice should succeed without error."""
        jti = str(uuid.uuid4())
        await token_blocklist.add_to_blocklist(jti, expires_in_seconds=3600)
        await token_blocklist.add_to_blocklist(jti, expires_in_seconds=3600)
        assert _mock_redis.set.call_count == 2


class TestIsBlocklisted:
    """Tests for checking if a JTI is blocklisted."""

    @pytest.mark.asyncio
    async def test_blocklisted_jti_returns_true(self, _mock_redis: AsyncMock) -> None:
        """A blocklisted JTI should return True."""
        _mock_redis.exists.return_value = 1
        assert await token_blocklist.is_blocklisted("some-jti") is True

    @pytest.mark.asyncio
    async def test_unknown_jti_returns_false(self, _mock_redis: AsyncMock) -> None:
        """A JTI not in the blocklist should return False."""
        _mock_redis.exists.return_value = 0
        assert await token_blocklist.is_blocklisted("unknown-jti") is False

    @pytest.mark.asyncio
    async def test_checks_correct_key(self, _mock_redis: AsyncMock) -> None:
        """Should check the correct Redis key with prefix."""
        jti = "test-jti-123"
        await token_blocklist.is_blocklisted(jti)
        _mock_redis.exists.assert_called_once_with(f"blocklist:jti:{jti}")
