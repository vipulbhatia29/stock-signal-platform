"""API tests for admin observability endpoints."""

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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
    """Build JWT Authorization header."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


class TestLLMMetrics:
    """Tests for GET /api/v1/admin/llm-metrics."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/llm-metrics")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Regular user should get 403."""
        user = await _create_user(db_url, role=UserRole.USER)
        response = await client.get("/api/v1/admin/llm-metrics", headers=_auth_headers(user))
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gets_metrics(self, client: AsyncClient, db_url: str) -> None:
        """Admin should get metrics dict with default empty values."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get("/api/v1/admin/llm-metrics", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert "requests_by_model" in data
        assert "cascade_count" in data
        assert "rpm_by_model" in data


class TestTierHealth:
    """Tests for GET /api/v1/admin/tier-health."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/tier-health")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_gets_health(self, client: AsyncClient, db_url: str) -> None:
        """Admin should get tier health dict with default empty values."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get("/api/v1/admin/tier-health", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert "tiers" in data
        assert "summary" in data


class TestTierToggle:
    """Tests for POST /api/v1/admin/tier-toggle."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.post(
            "/api/v1/admin/tier-toggle", json={"model": "x", "enabled": False}
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Regular user should get 403."""
        user = await _create_user(db_url, role=UserRole.USER)
        response = await client.post(
            "/api/v1/admin/tier-toggle",
            json={"model": "llama-3.3-70b", "enabled": False},
            headers=_auth_headers(user),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_toggle_returns_503_without_collector(
        self, client: AsyncClient, db_url: str
    ) -> None:
        """Admin toggle returns 503 when no collector is wired."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.post(
            "/api/v1/admin/tier-toggle",
            json={"model": "llama-3.3-70b", "enabled": False},
            headers=_auth_headers(admin),
        )
        assert response.status_code == 503


class TestLLMUsage:
    """Tests for GET /api/v1/admin/llm-usage."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/llm-usage")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_admin_gets_usage(self, client: AsyncClient, db_url: str) -> None:
        """Admin should get usage data with zero values for empty DB."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.get("/api/v1/admin/llm-usage", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "total_cost_usd" in data
        assert "escalation_rate" in data
        assert data["total_requests"] == 0
        assert data["escalation_rate"] == 0.0


class TestQueryCostEndpoint:
    """Tests for GET /admin/observability/query/{query_id}/cost."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        qid = str(uuid.uuid4())
        response = await client.get(f"/api/v1/admin/observability/query/{qid}/cost")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Non-admin user should get 403."""
        user = await _create_user(db_url, role=UserRole.USER)
        qid = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/admin/observability/query/{qid}/cost",
            headers=_auth_headers(user),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_unknown_query_returns_404(self, client: AsyncClient, db_url: str) -> None:
        """Random query_id with no data should return 404."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        qid = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/admin/observability/query/{qid}/cost",
            headers=_auth_headers(admin),
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_cost_breakdown(self, client: AsyncClient, db_url: str) -> None:
        """Should return cost breakdown when log rows exist for query."""
        from backend.models.logs import LLMCallLog, ToolExecutionLog

        admin = await _create_user(db_url, role=UserRole.ADMIN)
        qid = uuid.uuid4()

        # Seed log rows
        engine = create_async_engine(db_url, echo=False)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as db:
            db.add(
                LLMCallLog(
                    provider="groq",
                    model="llama-3.3-70b",
                    prompt_tokens=100,
                    completion_tokens=50,
                    cost_usd=0.0008,
                    latency_ms=150,
                    query_id=qid,
                    agent_type="stock",
                )
            )
            db.add(
                ToolExecutionLog(
                    tool_name="analyze_stock",
                    latency_ms=300,
                    status="ok",
                    query_id=qid,
                    cache_hit=False,
                )
            )
            db.add(
                ToolExecutionLog(
                    tool_name="analyze_stock",
                    latency_ms=0,
                    status="success",
                    query_id=qid,
                    cache_hit=True,
                )
            )
            await db.commit()
        await engine.dispose()

        response = await client.get(
            f"/api/v1/admin/observability/query/{qid}/cost",
            headers=_auth_headers(admin),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_cost_usd"] == 0.0008
        assert data["total_prompt_tokens"] == 100
        assert len(data["llm_calls"]) == 1
        assert data["llm_calls"][0]["agent_type"] == "stock"
        assert data["tool_calls"]["total"] == 2
        assert data["tool_calls"]["cache_hits"] == 1
        assert data["tool_calls"]["cache_hit_rate"] == 0.5
