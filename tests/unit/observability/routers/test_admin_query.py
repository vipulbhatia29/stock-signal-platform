"""Tests for the admin observability query endpoints.

Each endpoint delegates to an MCP tool function and is admin-gated.
Tests verify auth gating and correct delegation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.models.user import UserRole
from backend.observability.routers.admin_query import router

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client() -> TestClient:
    """TestClient with admin user injected."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    from backend.dependencies import get_current_user

    user = MagicMock()
    user.role = UserRole.ADMIN
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def nonadmin_client() -> TestClient:
    """TestClient with non-admin user injected."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    from backend.dependencies import get_current_user

    user = MagicMock()
    user.role = UserRole.USER
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


_MOCK_ENVELOPE = {
    "tool": "mock_tool",
    "window": {"from": "2026-04-20T09:00:00Z", "to": "2026-04-20T10:00:00Z"},
    "result": {"test": True},
    "meta": {"total_count": 0, "truncated": False, "schema_version": "v1"},
}


# ---------------------------------------------------------------------------
# Auth gating tests
# ---------------------------------------------------------------------------


class TestAdminGating:
    """Verify all 8 endpoints reject non-admin users with 403."""

    def test_kpis_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /kpis."""
        resp = nonadmin_client.get("/api/v1/observability/admin/kpis")
        assert resp.status_code == 403

    def test_errors_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /errors."""
        resp = nonadmin_client.get("/api/v1/observability/admin/errors")
        assert resp.status_code == 403

    def test_findings_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /findings."""
        resp = nonadmin_client.get("/api/v1/observability/admin/findings")
        assert resp.status_code == 403

    def test_trace_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /trace/{trace_id}."""
        resp = nonadmin_client.get("/api/v1/observability/admin/trace/abc-123")
        assert resp.status_code == 403

    def test_externals_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /externals."""
        resp = nonadmin_client.get(
            "/api/v1/observability/admin/externals", params={"provider": "yfinance"}
        )
        assert resp.status_code == 403

    def test_costs_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /costs."""
        resp = nonadmin_client.get("/api/v1/observability/admin/costs")
        assert resp.status_code == 403

    def test_pipelines_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /pipelines."""
        resp = nonadmin_client.get(
            "/api/v1/observability/admin/pipelines",
            params={"pipeline_name": "nightly_price_refresh"},
        )
        assert resp.status_code == 403

    def test_dq_requires_admin(self, nonadmin_client: TestClient) -> None:
        """Non-admin should get 403 on /dq."""
        resp = nonadmin_client.get("/api/v1/observability/admin/dq")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Delegation tests — verify each endpoint calls the right MCP tool function
# ---------------------------------------------------------------------------


class TestKpis:
    """Zone 1: System health KPIs."""

    def test_delegates_to_platform_health(self, admin_client: TestClient) -> None:
        """Should call get_platform_health with window_min."""
        with patch(
            "backend.observability.mcp.platform_health.get_platform_health",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get("/api/v1/observability/admin/kpis", params={"window_min": 120})
            assert resp.status_code == 200
            mock.assert_awaited_once_with(window_min=120)

    def test_default_window(self, admin_client: TestClient) -> None:
        """Default window_min should be 60."""
        with patch(
            "backend.observability.mcp.platform_health.get_platform_health",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get("/api/v1/observability/admin/kpis")
            assert resp.status_code == 200
            mock.assert_awaited_once_with(window_min=60)


class TestErrors:
    """Zone 2: Live error stream."""

    def test_delegates_to_recent_errors(self, admin_client: TestClient) -> None:
        """Should call get_recent_errors with all filter params."""
        with patch(
            "backend.observability.mcp.recent_errors.get_recent_errors",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get(
                "/api/v1/observability/admin/errors",
                params={"subsystem": "http", "severity": "error", "since": "24h", "limit": 100},
            )
            assert resp.status_code == 200
            mock.assert_awaited_once_with(
                subsystem="http",
                severity="error",
                user_id=None,
                ticker=None,
                since="24h",
                limit=100,
            )

    def test_defaults(self, admin_client: TestClient) -> None:
        """Default params should be since=1h, limit=50, rest=None."""
        with patch(
            "backend.observability.mcp.recent_errors.get_recent_errors",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get("/api/v1/observability/admin/errors")
            assert resp.status_code == 200
            mock.assert_awaited_once_with(
                subsystem=None,
                severity=None,
                user_id=None,
                ticker=None,
                since="1h",
                limit=50,
            )


class TestFindings:
    """Zone 3: Anomaly findings."""

    def test_delegates_to_get_anomalies(self, admin_client: TestClient) -> None:
        """Should call get_anomalies with filters."""
        with patch(
            "backend.observability.mcp.anomalies.get_anomalies",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get(
                "/api/v1/observability/admin/findings",
                params={"severity": "critical", "status": "open"},
            )
            assert resp.status_code == 200
            mock.assert_awaited_once_with(
                status="open",
                since=None,
                severity="critical",
                attribution_layer=None,
                limit=50,
            )


class TestTrace:
    """Zone 4: Trace explorer."""

    def test_delegates_to_get_trace(self, admin_client: TestClient) -> None:
        """Should call get_trace with trace_id from path."""
        with patch(
            "backend.observability.mcp.trace.get_trace",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get("/api/v1/observability/admin/trace/abc-123")
            assert resp.status_code == 200
            mock.assert_awaited_once_with(trace_id="abc-123")


class TestExternals:
    """Zone 5: External API dashboard."""

    def test_delegates_to_external_api_stats(self, admin_client: TestClient) -> None:
        """Should call get_external_api_stats with provider and window."""
        with patch(
            "backend.observability.mcp.external_api_stats.get_external_api_stats",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get(
                "/api/v1/observability/admin/externals",
                params={"provider": "yfinance", "window_min": 120},
            )
            assert resp.status_code == 200
            mock.assert_awaited_once_with(provider="yfinance", window_min=120, compare_to=None)

    def test_provider_required(self, admin_client: TestClient) -> None:
        """Provider is a required query param."""
        resp = admin_client.get("/api/v1/observability/admin/externals")
        assert resp.status_code == 422


class TestCosts:
    """Zone 6: Cost + budget."""

    def test_delegates_to_cost_breakdown(self, admin_client: TestClient) -> None:
        """Should call get_cost_breakdown with dimensions."""
        with patch(
            "backend.observability.mcp.cost_breakdown.get_cost_breakdown",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get(
                "/api/v1/observability/admin/costs",
                params={"window": "30d", "by": "model"},
            )
            assert resp.status_code == 200
            mock.assert_awaited_once_with(window="30d", by="model", compare_to=None, limit=50)


class TestPipelines:
    """Zone 7: Pipeline health."""

    def test_delegates_to_diagnose_pipeline(self, admin_client: TestClient) -> None:
        """Should call diagnose_pipeline with pipeline_name."""
        with patch(
            "backend.observability.mcp.diagnose_pipeline.diagnose_pipeline",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get(
                "/api/v1/observability/admin/pipelines",
                params={"pipeline_name": "nightly_price_refresh", "recent_n": 10},
            )
            assert resp.status_code == 200
            mock.assert_awaited_once_with(pipeline_name="nightly_price_refresh", recent_n=10)

    def test_pipeline_name_required(self, admin_client: TestClient) -> None:
        """Pipeline name is a required query param."""
        resp = admin_client.get("/api/v1/observability/admin/pipelines")
        assert resp.status_code == 422


class TestDq:
    """Zone 8: DQ scanner."""

    def test_delegates_to_dq_findings(self, admin_client: TestClient) -> None:
        """Should call get_dq_findings with filters."""
        with patch(
            "backend.observability.mcp.dq_findings.get_dq_findings",
            new_callable=AsyncMock,
            return_value=_MOCK_ENVELOPE,
        ) as mock:
            resp = admin_client.get(
                "/api/v1/observability/admin/dq",
                params={"severity": "critical", "since": "7d"},
            )
            assert resp.status_code == 200
            mock.assert_awaited_once_with(
                severity="critical", check=None, ticker=None, since="7d", limit=50
            )
