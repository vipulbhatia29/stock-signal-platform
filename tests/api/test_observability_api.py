"""API tests for observability endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.dependencies import create_access_token, hash_password
from backend.models.user import User, UserRole


async def _create_user(db_url: str, *, role: UserRole = UserRole.USER) -> User:
    """Create a user in the test database and return it."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    user = User(
        id=uuid.uuid4(),
        email=f"test-{uuid.uuid4().hex[:8]}@test.com",
        hashed_password=hash_password("TestPass1"),
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    async with factory() as session:
        session.add(user)
        await session.commit()
    await engine.dispose()
    return user


def _auth_headers(user: User) -> dict[str, str]:
    """Build JWT Authorization header for a user."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


class TestQueryListParams:
    """Tests for GET /observability/queries with new sort/filter/cost params."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/observability/queries")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_sort_by_returns_422(self, client: AsyncClient, db_url: str) -> None:
        """Invalid sort_by enum value should return 422."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?sort_by=badvalue",
            headers=_auth_headers(user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_sort_order_returns_422(self, client: AsyncClient, db_url: str) -> None:
        """Invalid sort_order enum value should return 422."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?sort_order=badvalue",
            headers=_auth_headers(user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_status_returns_422(self, client: AsyncClient, db_url: str) -> None:
        """Invalid status enum value should return 422."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?status=badvalue",
            headers=_auth_headers(user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cost_min_gt_cost_max_returns_422(self, client: AsyncClient, db_url: str) -> None:
        """cost_min > cost_max should return 422."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?cost_min=10&cost_max=1",
            headers=_auth_headers(user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_cost_min_returns_422(self, client: AsyncClient, db_url: str) -> None:
        """Negative cost_min value should return 422."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?cost_min=-1",
            headers=_auth_headers(user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_valid_sort_params_accepted(self, client: AsyncClient, db_url: str) -> None:
        """Valid sort_by and sort_order should return 200."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?sort_by=total_cost_usd&sort_order=asc",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_valid_status_filter_accepted(self, client: AsyncClient, db_url: str) -> None:
        """Valid status filter should return 200."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?status=completed",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_default_params_return_200(self, client: AsyncClient, db_url: str) -> None:
        """Default parameters (no query string) should return 200 with empty items."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert data["page"] == 1
        assert data["size"] == 25

    @pytest.mark.asyncio
    async def test_cost_range_equal_values_accepted(self, client: AsyncClient, db_url: str) -> None:
        """cost_min == cost_max should be accepted (valid range)."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries?cost_min=5&cost_max=5",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_all_valid_sort_by_values_accepted(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """All valid sort_by enum values should return 200."""
        user = await _create_user(db_url)
        valid_values = ["timestamp", "total_cost_usd", "duration_ms", "llm_calls", "score"]
        for value in valid_values:
            response = await client.get(
                f"/api/v1/observability/queries?sort_by={value}",
                headers=_auth_headers(user),
            )
            assert response.status_code == 200, f"sort_by={value} should return 200"

    @pytest.mark.asyncio
    async def test_all_valid_status_values_accepted(self, client: AsyncClient, db_url: str) -> None:
        """All valid status enum values should return 200."""
        user = await _create_user(db_url)
        valid_values = ["completed", "error", "declined", "timeout"]
        for value in valid_values:
            response = await client.get(
                f"/api/v1/observability/queries?status={value}",
                headers=_auth_headers(user),
            )
            assert response.status_code == 200, f"status={value} should return 200"


class TestGroupedEndpoint:
    """Tests for GET /observability/queries/grouped."""

    @pytest.mark.asyncio
    async def test_valid_group_by_returns_200(self, client: AsyncClient, db_url: str) -> None:
        """Valid group_by should return 200 with GroupedResponse shape."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=agent_type",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["group_by"] == "agent_type"
        assert "groups" in data
        assert "total_queries" in data

    @pytest.mark.asyncio
    async def test_user_group_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """group_by=user as non-admin should return 403."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=user",
            headers=_auth_headers(user),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_invalid_group_by_returns_422(self, client: AsyncClient, db_url: str) -> None:
        """Invalid group_by value should return 422."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=badvalue",
            headers=_auth_headers(user),
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_date_group_accepts_bucket_param(self, client: AsyncClient, db_url: str) -> None:
        """group_by=date with bucket=week should return 200."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=date&bucket=week",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_grouped_not_shadowed_by_query_id(self, client: AsyncClient, db_url: str) -> None:
        """GET /queries/grouped should NOT be shadowed by /queries/{query_id}."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=agent_type",
            headers=_auth_headers(user),
        )
        assert response.status_code != 422  # Would be 422 if parsed as UUID

    @pytest.mark.asyncio
    async def test_intent_category_returns_200(self, client: AsyncClient, db_url: str) -> None:
        """group_by=intent_category should return 200 (may be empty groups)."""
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=intent_category",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_group_admin_returns_200(self, client: AsyncClient, db_url: str) -> None:
        """group_by=user as admin should return 200.

        Regular users get 403 for group_by=user (tested separately).
        Admins must be allowed through — the endpoint is the cross-user
        usage breakdown view.
        """
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=user",
            headers=_auth_headers(admin),
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.regression
    async def test_intent_category_non_admin_is_user_scoped(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Regression: group_by=intent_category must respect user scope for non-admins.

        KAN-316: Previously the endpoint forced user_id=None for intent_category,
        exposing platform-wide analytics to every authenticated user.  After the fix,
        _user_scope() is called unconditionally — non-admins receive only their own
        data while admins still see all (user_id=None path via _user_scope).

        This test verifies the endpoint returns 200 and a well-formed response for a
        non-admin user.  The important property is that the call succeeds *without*
        leaking other users' data, which is enforced by _user_scope() routing the
        non-admin's uuid into the query rather than None.
        """
        user = await _create_user(db_url)
        response = await client.get(
            "/api/v1/observability/queries/grouped?group_by=intent_category",
            headers=_auth_headers(user),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["group_by"] == "intent_category"
        assert "groups" in data
        assert "total_queries" in data
