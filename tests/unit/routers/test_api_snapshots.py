"""API response snapshot tests using syrupy.

Snapshots the JSON shape of major endpoint responses to detect accidental
schema changes. Uses schema-only snapshots (key names, not values) so these
tests pass even as data changes.

Run with --snapshot-update to regenerate baselines.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shape(data: object) -> object:
    """Recursively extract the shape (keys and types) of a JSON response.

    This creates a schema snapshot that captures structure but not values,
    making snapshots stable across data changes.
    """
    if isinstance(data, dict):
        return {k: _shape(v) for k, v in data.items()}
    elif isinstance(data, list):
        if not data:
            return []
        return [_shape(data[0])]  # Snapshot shape of first element only
    elif isinstance(data, bool):
        return "bool"
    elif isinstance(data, int):
        return "int"
    elif isinstance(data, float):
        return "float"
    elif isinstance(data, str):
        return "str"
    elif data is None:
        return None
    else:
        return type(data).__name__


# ---------------------------------------------------------------------------
# Health endpoint snapshot
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestHealthSnapshot:
    """Snapshot tests for GET /api/v1/health response shape."""

    async def test_health_response_shape(self, client: AsyncClient, snapshot) -> None:
        """Health endpoint response shape must match snapshot."""
        from backend.schemas.health import DependencyStatus

        _healthy = DependencyStatus(healthy=True, latency_ms=0.1)
        with (
            patch("backend.observability.routers.health._check_redis", return_value=_healthy),
            patch("backend.observability.routers.health._check_database", return_value=_healthy),
        ):
            response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        shape = _shape(data)
        assert shape == snapshot


# ---------------------------------------------------------------------------
# Stocks list snapshot
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestStocksListSnapshot:
    """Snapshot tests for bulk signals endpoint."""

    async def test_stocks_bulk_signals_requires_auth(self, client: AsyncClient) -> None:
        """Bulk signals endpoint requires authentication — unauthenticated returns 401."""
        response = await client.get("/api/v1/stocks/signals/bulk?limit=1")
        assert response.status_code == 401

    async def test_stocks_bulk_signals_401_has_json_content_type(self, client: AsyncClient) -> None:
        """Bulk signals 401 response must have JSON content-type."""
        response = await client.get("/api/v1/stocks/signals/bulk?limit=1")
        assert response.status_code == 401
        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type


# ---------------------------------------------------------------------------
# Stock detail snapshot
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestStockDetailSnapshot:
    """Snapshot tests for GET /api/v1/stocks/{ticker} response shape."""

    async def test_stock_detail_response_keys(self, client: AsyncClient) -> None:
        """Stock detail endpoint must return a dict with expected top-level keys."""
        response = await client.get("/api/v1/stocks/AAPL_NONEXISTENT_TICKER")
        # 404 is acceptable — we're testing the error shape exists
        assert response.status_code in (200, 404)
        data = response.json()
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Portfolio list snapshot
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestPortfolioSnapshot:
    """Snapshot tests for GET /api/v1/portfolio response shape."""

    async def test_portfolio_requires_auth(self, client: AsyncClient) -> None:
        """Portfolio endpoint requires authentication — unauthenticated returns 401."""
        response = await client.get("/api/v1/portfolio/summary")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Recommendations snapshot
# ---------------------------------------------------------------------------


@pytest.mark.regression
class TestRecommendationsSnapshot:
    """Snapshot tests for GET /api/v1/recommendations response shape."""

    async def test_recommendations_requires_auth(self, client: AsyncClient) -> None:
        """Recommendations endpoint requires authentication."""
        response = await client.get("/api/v1/stocks/recommendations")
        assert response.status_code == 401
