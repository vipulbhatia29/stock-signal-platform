"""API endpoint tests for admin LLM model config routes.

These tests verify the superuser-only admin endpoints for managing
LLM cascade model configurations. Each test:
  1. Sets up users (regular + admin) directly in the database
  2. Calls the API endpoint via HTTP client
  3. Asserts response status code and body

Test categories:
  - Auth: verify endpoints require JWT + admin role
  - Happy path: verify correct responses with valid data
  - Error path: verify correct error codes for invalid input
"""

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
from backend.models.llm_config import LLMModelConfig
from backend.models.user import User, UserRole

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


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


async def _insert_llm_config(db_url: str, **overrides) -> LLMModelConfig:
    """Insert an LLM model config row and return it."""
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.utcnow()  # noqa: DTZ003 — column is TIMESTAMP WITHOUT TIME ZONE
    defaults = {
        "provider": "groq",
        "model_name": "llama-3.3-70b-versatile",
        "tier": "planner",
        "priority": 1,
        "is_enabled": True,
        "tpm_limit": 6000,
        "rpm_limit": 30,
        "tpd_limit": None,
        "rpd_limit": None,
        "cost_per_1k_input": 0.00059,
        "cost_per_1k_output": 0.00079,
        "notes": "test config",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    config = LLMModelConfig(**defaults)
    async with factory() as session:
        session.add(config)
        await session.commit()
        await session.refresh(config)
    await engine.dispose()
    return config


def _auth_headers(user: User) -> dict[str, str]:
    """Build JWT Authorization header for a user."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestListLLMModels:
    """Tests for GET /api/v1/admin/llm-models."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.get("/api/v1/admin/llm-models")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Regular user should get 403 Forbidden."""
        user = await _create_user(db_url, role=UserRole.USER)
        response = await client.get("/api/v1/admin/llm-models", headers=_auth_headers(user))
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_lists_models(self, client: AsyncClient, db_url: str) -> None:
        """Admin user should get list of all model configs."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        config = await _insert_llm_config(db_url, tier="planner", priority=1)

        response = await client.get("/api/v1/admin/llm-models", headers=_auth_headers(admin))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Find the config we inserted
        match = [m for m in data if m["id"] == config.id]
        assert len(match) == 1
        assert match[0]["provider"] == "groq"
        assert match[0]["tier"] == "planner"
        assert match[0]["is_enabled"] is True


class TestUpdateLLMModel:
    """Tests for PATCH /api/v1/admin/llm-models/{model_id}."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.patch("/api/v1/admin/llm-models/1", json={"is_enabled": False})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Regular user should get 403 Forbidden."""
        user = await _create_user(db_url, role=UserRole.USER)
        response = await client.patch(
            "/api/v1/admin/llm-models/1",
            json={"is_enabled": False},
            headers=_auth_headers(user),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_updates_model(self, client: AsyncClient, db_url: str) -> None:
        """Admin should be able to partially update a model config."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        config = await _insert_llm_config(db_url, is_enabled=True, priority=1)

        response = await client.patch(
            f"/api/v1/admin/llm-models/{config.id}",
            json={"is_enabled": False, "priority": 5, "notes": "disabled for testing"},
            headers=_auth_headers(admin),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_enabled"] is False
        assert data["priority"] == 5
        assert data["notes"] == "disabled for testing"
        # Unchanged fields preserved
        assert data["provider"] == "groq"
        assert data["tier"] == "planner"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_404(self, client: AsyncClient, db_url: str) -> None:
        """Updating a non-existent model config should return 404."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        response = await client.patch(
            "/api/v1/admin/llm-models/99999",
            json={"is_enabled": False},
            headers=_auth_headers(admin),
        )
        assert response.status_code == 404


class TestReloadLLMModels:
    """Tests for POST /api/v1/admin/llm-models/reload."""

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient) -> None:
        """Unauthenticated request should return 401."""
        response = await client.post("/api/v1/admin/llm-models/reload")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, db_url: str) -> None:
        """Regular user should get 403 Forbidden."""
        user = await _create_user(db_url, role=UserRole.USER)
        response = await client.post("/api/v1/admin/llm-models/reload", headers=_auth_headers(user))
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_reload_succeeds(self, client: AsyncClient, db_url: str) -> None:
        """Admin should be able to reload model configs."""
        admin = await _create_user(db_url, role=UserRole.ADMIN)
        # Ensure at least one config exists
        await _insert_llm_config(db_url, tier="synthesizer", priority=1)

        response = await client.post(
            "/api/v1/admin/llm-models/reload", headers=_auth_headers(admin)
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "tiers" in data
        assert "models" in data
        assert data["models"] >= 1
