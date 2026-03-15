"""API tests for the preferences endpoints."""

import pytest

pytestmark = pytest.mark.asyncio


class TestGetPreferences:
    """Tests for GET /api/v1/preferences."""

    async def test_get_preferences_unauthenticated(self, client):
        """Unauthenticated request should return 401."""
        resp = await client.get("/api/v1/preferences")
        assert resp.status_code == 401

    async def test_get_preferences_creates_defaults(self, authenticated_client):
        """First call should create a preference row with default values."""
        resp = await authenticated_client.get("/api/v1/preferences")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_stop_loss_pct"] == 20.0
        assert data["max_position_pct"] == 5.0
        assert data["max_sector_pct"] == 30.0
        assert data["min_cash_reserve_pct"] == 10.0

    async def test_get_preferences_returns_existing(self, authenticated_client):
        """Subsequent calls should return the same saved values."""
        # First call creates defaults
        await authenticated_client.get("/api/v1/preferences")
        # Patch to change a value
        await authenticated_client.patch(
            "/api/v1/preferences",
            json={"default_stop_loss_pct": 15.0},
        )
        # Second GET should reflect the update
        resp = await authenticated_client.get("/api/v1/preferences")
        assert resp.status_code == 200
        assert resp.json()["default_stop_loss_pct"] == 15.0


class TestPatchPreferences:
    """Tests for PATCH /api/v1/preferences."""

    async def test_patch_preferences_unauthenticated(self, client):
        """Unauthenticated request should return 401."""
        resp = await client.patch(
            "/api/v1/preferences",
            json={"default_stop_loss_pct": 10.0},
        )
        assert resp.status_code == 401

    async def test_patch_preferences_partial_update(self, authenticated_client):
        """Only supplied fields should change; others keep defaults."""
        resp = await authenticated_client.patch(
            "/api/v1/preferences",
            json={"max_position_pct": 8.0, "max_sector_pct": 25.0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["max_position_pct"] == 8.0
        assert data["max_sector_pct"] == 25.0
        # Unchanged fields remain at defaults
        assert data["default_stop_loss_pct"] == 20.0
        assert data["min_cash_reserve_pct"] == 10.0

    async def test_patch_preferences_validation_error(self, authenticated_client):
        """Negative or >100 values should return 422."""
        # Negative
        resp = await authenticated_client.patch(
            "/api/v1/preferences",
            json={"default_stop_loss_pct": -5.0},
        )
        assert resp.status_code == 422

        # Over 100
        resp = await authenticated_client.patch(
            "/api/v1/preferences",
            json={"max_sector_pct": 150.0},
        )
        assert resp.status_code == 422

        # Zero (gt=0 means must be > 0)
        resp = await authenticated_client.patch(
            "/api/v1/preferences",
            json={"max_position_pct": 0},
        )
        assert resp.status_code == 422
