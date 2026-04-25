"""Integration tests: anomaly detection → finding persistence → dedup → auto-close → JIRA draft.

Validates the full anomaly lifecycle against a real Postgres database:
- Rules query obs tables via async_session_factory (patched to test DB)
- Findings are persisted with dedup protection
- Auto-close resolves findings after 3 consecutive negative scans
- JIRA draft endpoint creates tickets and updates finding_log
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from tests.integration.observability.conftest import (
    ApiErrorLogFactory,
    CeleryHeartbeatFactory,
    FindingLogFactory,
    insert_obs_rows,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_http_5xx_rule_creates_finding(obs_db_session, _patch_session_factory):
    """Seeding >5 ApiErrorLog 5xx rows in last 5min triggers http_5xx_elevated finding."""
    from backend.observability.anomaly.engine import run_anomaly_scan
    from backend.observability.anomaly.persist import persist_findings
    from backend.observability.anomaly.rules.http_5xx_elevated import (
        Http5xxElevatedRule,
    )

    now = datetime.now(timezone.utc)
    # Seed 10 errors within 5-minute lookback window (threshold is >5)
    errors = [ApiErrorLogFactory.build(ts=now - timedelta(seconds=i * 10)) for i in range(10)]
    await insert_obs_rows(obs_db_session, errors)

    findings = await run_anomaly_scan(rules=[Http5xxElevatedRule()])
    assert len(findings) >= 1, "Expected at least 1 finding from 10 5xx errors"

    inserted, _skipped = await persist_findings(findings)
    assert inserted >= 1

    result = await obs_db_session.execute(
        text("SELECT kind, status FROM observability.finding_log WHERE kind = 'http_5xx_elevated'"),
    )
    row = result.fetchone()
    assert row is not None, "Finding not persisted to finding_log"
    assert row[1] == "open"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_worker_heartbeat_missing_creates_finding(obs_db_session, _patch_session_factory):
    """Stale heartbeat (>90s old) triggers worker_heartbeat_missing finding."""
    from backend.observability.anomaly.engine import run_anomaly_scan
    from backend.observability.anomaly.persist import persist_findings
    from backend.observability.anomaly.rules.worker_heartbeat_missing import (
        WorkerHeartbeatMissingRule,
    )

    # Seed a heartbeat 10 minutes ago — well past the 90s staleness threshold
    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    await insert_obs_rows(obs_db_session, [CeleryHeartbeatFactory.build(ts=stale_ts)])

    findings = await run_anomaly_scan(rules=[WorkerHeartbeatMissingRule()])
    assert len(findings) >= 1, "Expected stale heartbeat finding"

    inserted, _skipped = await persist_findings(findings)
    assert inserted >= 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_finding_dedup_no_duplicates(obs_db_session, _patch_session_factory):
    """Running anomaly scan twice on same data produces only 1 finding (dedup)."""
    from backend.observability.anomaly.engine import run_anomaly_scan
    from backend.observability.anomaly.persist import persist_findings
    from backend.observability.anomaly.rules.http_5xx_elevated import (
        Http5xxElevatedRule,
    )

    now = datetime.now(timezone.utc)
    errors = [ApiErrorLogFactory.build(ts=now - timedelta(seconds=i * 10)) for i in range(10)]
    await insert_obs_rows(obs_db_session, errors)

    # First scan — should insert
    findings1 = await run_anomaly_scan(rules=[Http5xxElevatedRule()])
    await persist_findings(findings1)

    # Second scan — same data, should skip (dedup_key already open)
    findings2 = await run_anomaly_scan(rules=[Http5xxElevatedRule()])
    _inserted, skipped = await persist_findings(findings2)
    assert skipped >= 1, "Second scan should skip duplicate finding"

    result = await obs_db_session.execute(
        text("SELECT count(*) FROM observability.finding_log WHERE kind = 'http_5xx_elevated'"),
    )
    assert result.scalar() == 1, "Dedup should prevent duplicate findings"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auto_close_after_three_negative_checks(obs_db_session, _patch_session_factory):
    """Finding with negative_check_count=2 auto-resolves on next negative scan."""
    from backend.observability.anomaly.persist import auto_close_findings

    # Seed a finding already at 2 negative checks (threshold is 3)
    finding = FindingLogFactory.build(status="open", negative_check_count=2)
    await insert_obs_rows(obs_db_session, [finding])

    # Empty fired_dedup_keys → this finding's key is NOT firing → negative check
    resolved, _incremented = await auto_close_findings(fired_dedup_keys=set())
    assert resolved >= 1, "Finding at 2 negative checks should auto-resolve on 3rd"

    result = await obs_db_session.execute(
        text("SELECT status FROM observability.finding_log WHERE id = :fid"),
        {"fid": finding.id},
    )
    assert result.fetchone()[0] == "resolved"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_jira_draft_updates_finding(
    client, admin_mutating_headers, obs_db_session, _patch_session_factory
):
    """POST /findings/{id}/jira-draft creates JIRA ticket and updates finding.jira_ticket_key.

    Mocks get_observed_http_client at the source module (lazy import in endpoint).
    Also mocks JIRA settings to avoid 503.
    """
    finding = FindingLogFactory.build()
    await insert_obs_rows(obs_db_session, [finding])

    # Build mock HTTP client that returns a JIRA-like response.
    # httpx Response.json() is SYNC — use MagicMock not AsyncMock for it.
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "key": "KAN-999",
        "self": "https://jira.example.com/issue/KAN-999",
    }
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    mock_http.aclose = AsyncMock()

    with (
        patch(
            "backend.services.http_client.get_observed_http_client",
            return_value=mock_http,
        ),
        patch("backend.config.settings.JIRA_API_EMAIL", "test@example.com"),
        patch("backend.config.settings.JIRA_API_TOKEN", "fake-token"),
        patch("backend.config.settings.JIRA_SITE_URL", "https://jira.example.com"),
        patch("backend.config.settings.JIRA_PROJECT_KEY", "KAN"),
    ):
        response = await client.post(
            f"/api/v1/observability/admin/findings/{finding.id}/jira-draft",
            headers=admin_mutating_headers,
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["jira_key"] == "KAN-999"
    assert body["already_exists"] is False

    # Verify DB was updated
    result = await obs_db_session.execute(
        text("SELECT jira_ticket_key FROM observability.finding_log WHERE id = :fid"),
        {"fid": finding.id},
    )
    assert result.fetchone()[0] == "KAN-999"
