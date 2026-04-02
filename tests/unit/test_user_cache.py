"""Tests for get_current_user Redis caching (KAN-182)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.dependencies import (
    CachedUser,
    _get_cached_user,
    _set_cached_user,
    _user_cache_key,
    get_current_user,
)
from backend.models.user import UserRole

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def fake_user(user_id: uuid.UUID, now: datetime) -> MagicMock:
    """Mock ORM User with all fields CachedUser expects."""
    user = MagicMock()
    user.id = user_id
    user.email = "test@example.com"
    user.role = UserRole.USER
    user.is_active = True
    user.created_at = now
    user.updated_at = now
    user.hashed_password = "$2b$12$fakehash"
    user.email_verified = True
    return user


@pytest.fixture
def cached_user(user_id: uuid.UUID, now: datetime) -> CachedUser:
    return CachedUser(
        id=user_id,
        email="test@example.com",
        role=UserRole.USER,
        is_active=True,
        email_verified=True,
        has_password=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def mock_cache() -> AsyncMock:
    return AsyncMock()


# ── CachedUser model ───────────────────────────────────────────────────────


class TestCachedUser:
    def test_from_orm_excludes_password(self, fake_user: MagicMock) -> None:
        """CachedUser should not include hashed_password."""
        cu = CachedUser.model_validate(fake_user)
        assert not hasattr(cu, "hashed_password")
        assert cu.email == "test@example.com"

    def test_role_is_enum(self, cached_user: CachedUser) -> None:
        """Role should remain a UserRole enum after deserialization."""
        assert isinstance(cached_user.role, UserRole)
        assert cached_user.role == UserRole.USER

    def test_json_roundtrip(self, cached_user: CachedUser) -> None:
        """Serialize → deserialize should preserve all fields."""
        json_str = cached_user.model_dump_json()
        restored = CachedUser.model_validate_json(json_str)
        assert restored.id == cached_user.id
        assert restored.email == cached_user.email
        assert isinstance(restored.role, UserRole)
        assert restored.role == UserRole.USER

    def test_admin_role_preserved(self, user_id: uuid.UUID, now: datetime) -> None:
        cu = CachedUser(
            id=user_id,
            email="admin@example.com",
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True,
            has_password=True,
            created_at=now,
            updated_at=now,
        )
        restored = CachedUser.model_validate_json(cu.model_dump_json())
        assert restored.role == UserRole.ADMIN


# ── Cache key ──────────────────────────────────────────────────────────────


class TestCacheKey:
    def test_format(self, user_id: uuid.UUID) -> None:
        assert _user_cache_key(user_id) == f"user:{user_id}:auth"


# ── Cache helpers ──────────────────────────────────────────────────────────


class TestGetCachedUser:
    @pytest.mark.asyncio
    async def test_cache_miss(self, mock_cache: AsyncMock, user_id: uuid.UUID) -> None:
        mock_cache.get.return_value = None
        result = await _get_cached_user(mock_cache, user_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, mock_cache: AsyncMock, cached_user: CachedUser) -> None:
        mock_cache.get.return_value = cached_user.model_dump_json()
        result = await _get_cached_user(mock_cache, cached_user.id)
        assert result is not None
        assert result.id == cached_user.id
        assert result.role == UserRole.USER

    @pytest.mark.asyncio
    async def test_corrupted_data(self, mock_cache: AsyncMock, user_id: uuid.UUID) -> None:
        """Corrupted cache data returns None (graceful degradation)."""
        mock_cache.get.return_value = "not-valid-json"
        result = await _get_cached_user(mock_cache, user_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_error(self, mock_cache: AsyncMock, user_id: uuid.UUID) -> None:
        """Redis error returns None (graceful degradation)."""
        mock_cache.get.side_effect = ConnectionError("Redis down")
        result = await _get_cached_user(mock_cache, user_id)
        assert result is None


class TestSetCachedUser:
    @pytest.mark.asyncio
    async def test_stores_without_password(
        self, mock_cache: AsyncMock, fake_user: MagicMock
    ) -> None:
        await _set_cached_user(mock_cache, fake_user)
        mock_cache.set.assert_called_once()
        stored_json = mock_cache.set.call_args[0][1]
        assert "hashed_password" not in stored_json
        assert "test@example.com" in stored_json

    @pytest.mark.asyncio
    async def test_redis_error_silent(self, mock_cache: AsyncMock, fake_user: MagicMock) -> None:
        """Redis set failure is silently swallowed."""
        mock_cache.set.side_effect = ConnectionError("Redis down")
        await _set_cached_user(mock_cache, fake_user)  # no exception


# ── get_current_user integration ───────────────────────────────────────────


class TestGetCurrentUser:
    """Test the full get_current_user dependency with caching."""

    def _make_request(self, token: str, cache: AsyncMock | None = None) -> MagicMock:
        """Build a mock Request with auth header and optional cache."""
        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        request.cookies = {}
        if cache is not None:
            request.app.state.cache = cache
        else:
            request.app.state.cache = None
        return request

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db_and_caches(
        self, fake_user: MagicMock, user_id: uuid.UUID
    ) -> None:
        """On cache miss: query DB, store in cache, return user."""
        mock_cache = AsyncMock()
        mock_cache.get.return_value = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result

        token = "fake.jwt.token"
        request = self._make_request(token, mock_cache)

        with patch("backend.dependencies.decode_token") as mock_decode:
            from backend.dependencies import TokenPayload

            mock_decode.return_value = TokenPayload(user_id=user_id)
            result = await get_current_user(request, mock_db)

        assert result is fake_user
        mock_db.execute.assert_called_once()
        mock_cache.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, cached_user: CachedUser, user_id: uuid.UUID) -> None:
        """On cache hit: return cached user, no DB query."""
        mock_cache = AsyncMock()
        mock_cache.get.return_value = cached_user.model_dump_json()

        mock_db = AsyncMock()

        token = "fake.jwt.token"
        request = self._make_request(token, mock_cache)

        with patch("backend.dependencies.decode_token") as mock_decode:
            from backend.dependencies import TokenPayload

            mock_decode.return_value = TokenPayload(user_id=user_id)
            result = await get_current_user(request, mock_db)

        assert isinstance(result, CachedUser)
        assert result.id == user_id
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_cache_falls_back_to_db(
        self, fake_user: MagicMock, user_id: uuid.UUID
    ) -> None:
        """When cache is None, fall back to DB."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_user
        mock_db.execute.return_value = mock_result

        token = "fake.jwt.token"
        request = self._make_request(token, cache=None)

        with patch("backend.dependencies.decode_token") as mock_decode:
            from backend.dependencies import TokenPayload

            mock_decode.return_value = TokenPayload(user_id=user_id)
            result = await get_current_user(request, mock_db)

        assert result is fake_user
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_inactive_cached_user_rejected(self, user_id: uuid.UUID, now: datetime) -> None:
        """Inactive user in cache should still be rejected."""
        inactive = CachedUser(
            id=user_id,
            email="inactive@example.com",
            role=UserRole.USER,
            is_active=False,
            email_verified=True,
            has_password=True,
            created_at=now,
            updated_at=now,
        )
        mock_cache = AsyncMock()
        mock_cache.get.return_value = inactive.model_dump_json()

        mock_db = AsyncMock()
        token = "fake.jwt.token"
        request = self._make_request(token, mock_cache)

        with patch("backend.dependencies.decode_token") as mock_decode:
            from backend.dependencies import TokenPayload

            mock_decode.return_value = TokenPayload(user_id=user_id)

            with pytest.raises(Exception) as exc_info:
                await get_current_user(request, mock_db)
            assert exc_info.value.status_code == 401

        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_token_returns_401(self) -> None:
        """Missing token should return 401."""
        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        mock_db = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await get_current_user(request, mock_db)
        assert exc_info.value.status_code == 401
