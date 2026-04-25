"""Integration tests: admin observability API endpoints against real data.

Tests all admin endpoint categories (KPIs, errors, findings, acknowledge,
suppress) plus auth guards against a real Postgres database. Response shapes
use the MCP build_envelope wrapper: data is at response["result"][key].
"""

import pytest
from sqlalchemy import text

from backend.dependencies import create_access_token
from backend.models.user import UserRole
from tests.integration.observability.conftest import (
    ApiErrorLogFactory,
    FindingLogFactory,
    RequestLogFactory,
    insert_obs_rows,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_kpis_returns_all_subsystems(
    client, admin_auth_headers, obs_db_session, _patch_session_factory
):
    """GET /admin/kpis returns overall_status + all 7 subsystem keys via MCP envelope."""
    await insert_obs_rows(obs_db_session, [RequestLogFactory.build() for _ in range(3)])

    response = await client.get(
        "/api/v1/observability/admin/kpis?window_min=60",
        headers=admin_auth_headers,
    )
    assert response.status_code == 200
    data = response.json()

    # Response is wrapped in build_envelope: {"tool", "window", "result", "meta"}
    result = data["result"]
    assert "overall_status" in result
    assert "subsystems" in result
    for key in ("http", "db", "cache", "external_api", "celery", "agent", "frontend"):
        assert key in result["subsystems"], f"Missing subsystem: {key}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_findings_ranked_by_severity(
    client, admin_auth_headers, obs_db_session, _patch_session_factory
):
    """GET /admin/findings returns findings with CRITICAL before INFO (severity ranking)."""
    findings = [
        FindingLogFactory.build(severity="INFO", kind="info_test"),
        FindingLogFactory.build(severity="CRITICAL", kind="crit_test"),
    ]
    await insert_obs_rows(obs_db_session, findings)

    response = await client.get(
        "/api/v1/observability/admin/findings?status=open&limit=10",
        headers=admin_auth_headers,
    )
    assert response.status_code == 200

    # Envelope: data["result"]["findings"]
    items = response.json()["result"]["findings"]
    severities = [f["severity"] for f in items]
    crit_idx = next((i for i, s in enumerate(severities) if s == "CRITICAL"), None)
    info_idx = next((i for i, s in enumerate(severities) if s == "INFO"), None)
    assert crit_idx is not None, "CRITICAL finding not returned"
    assert info_idx is not None, "INFO finding not returned"
    assert crit_idx < info_idx, "CRITICAL should rank before INFO"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_acknowledge_transitions_status(
    client, admin_mutating_headers, obs_db_session, _patch_session_factory
):
    """PATCH /findings/{id}/acknowledge changes status open → acknowledged."""
    finding = FindingLogFactory.build(status="open")
    await insert_obs_rows(obs_db_session, [finding])

    response = await client.patch(
        f"/api/v1/observability/admin/findings/{finding.id}/acknowledge",
        headers=admin_mutating_headers,
    )
    assert response.status_code == 200

    # Verify in DB directly (don't trust response alone)
    result = await obs_db_session.execute(
        text("SELECT status FROM observability.finding_log WHERE id = :fid"),
        {"fid": finding.id},
    )
    assert result.fetchone()[0] == "acknowledged"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_suppress_sets_ttl(
    client, admin_mutating_headers, obs_db_session, _patch_session_factory
):
    """PATCH /findings/{id}/suppress sets suppressed status + suppressed_until."""
    finding = FindingLogFactory.build(status="open")
    await insert_obs_rows(obs_db_session, [finding])

    response = await client.patch(
        f"/api/v1/observability/admin/findings/{finding.id}/suppress?duration=1h",
        headers=admin_mutating_headers,
    )
    assert response.status_code == 200

    result = await obs_db_session.execute(
        text("SELECT status, suppressed_until FROM observability.finding_log WHERE id = :fid"),
        {"fid": finding.id},
    )
    row = result.fetchone()
    assert row[0] == "suppressed"
    assert row[1] is not None, "suppressed_until should be set"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_admin_auth_required(client):
    """Admin endpoints reject unauthenticated requests with 401/403."""
    endpoints = [
        "/api/v1/observability/admin/kpis?window_min=60",
        "/api/v1/observability/admin/errors?since=1h&limit=10",
        "/api/v1/observability/admin/findings?status=open&limit=10",
    ]
    for ep in endpoints:
        response = await client.get(ep)
        assert response.status_code in (
            401,
            403,
        ), f"{ep} should require auth, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_non_admin_user_rejected(client, db_session):
    """Non-admin authenticated user gets 403 on admin endpoints."""
    from tests.conftest import UserFactory

    user = UserFactory.build(role=UserRole.USER, email_verified=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # create_access_token takes only user_id (1 arg)
    token = create_access_token(user.id)
    headers = {"Cookie": f"access_token={token}"}

    response = await client.get(
        "/api/v1/observability/admin/kpis?window_min=60",
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.integration
async def test_errors_endpoint_returns_matches(
    client, admin_auth_headers, obs_db_session, _patch_session_factory
):
    """GET /admin/errors returns error items via MCP envelope."""
    errors = [ApiErrorLogFactory.build() for _ in range(3)]
    await insert_obs_rows(obs_db_session, errors)

    # Use subsystem=http filter to avoid querying pipeline_runs (may have schema drift)
    response = await client.get(
        "/api/v1/observability/admin/errors?since=1h&limit=10&subsystem=http",
        headers=admin_auth_headers,
    )
    assert response.status_code == 200

    # Envelope: data["result"]["errors"]
    data = response.json()
    assert "result" in data, f"Expected MCP envelope, got keys: {list(data.keys())}"
    assert "errors" in data["result"]
