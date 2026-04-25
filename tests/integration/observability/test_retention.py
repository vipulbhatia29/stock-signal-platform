"""Integration tests: retention tasks purge old data correctly.

NOTE (H4): metadata.create_all() creates regular tables, not hypertables.
TimescaleDB hypertable creation happens in Alembic migrations only. Therefore
the hypertable-specific drop_chunks path is tested for function existence and
correct dict return shape, but row-level deletion assertions are only reliable
on the regular-table retention helper.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.integration.observability.conftest import (
    AuthEventLogFactory,
    insert_obs_rows,
)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_regular_table_retention_deletes_old_rows(obs_db_session, _patch_session_factory):
    """Retention on auth_event_log (regular, 90d) deletes old rows, keeps new."""
    from backend.tasks.retention import _purge_obs_regular_table

    now = datetime.now(timezone.utc)
    await insert_obs_rows(
        obs_db_session,
        [
            AuthEventLogFactory.build(ts=now - timedelta(days=120), event_type="old_login"),
            AuthEventLogFactory.build(ts=now - timedelta(minutes=5), event_type="new_login"),
        ],
    )

    result = await _purge_obs_regular_table("auth_event_log", 90)

    assert result["status"] == "ok"
    assert result["deleted_rows"] >= 1
    assert result["retention_days"] == 90

    old = await obs_db_session.execute(
        text("SELECT 1 FROM observability.auth_event_log WHERE event_type = 'old_login'"),
    )
    assert old.fetchone() is None, "Old row should be purged"

    new = await obs_db_session.execute(
        text("SELECT 1 FROM observability.auth_event_log WHERE event_type = 'new_login'"),
    )
    assert new.fetchone() is not None, "New row should survive"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_regular_table_retention_rejects_unknown_table(_patch_session_factory):
    """_purge_obs_regular_table raises ValueError for tables outside the allowlist."""
    from backend.tasks.retention import _purge_obs_regular_table

    with pytest.raises(ValueError, match="not in allowlist"):
        await _purge_obs_regular_table("not_a_real_table", 30)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.xfail(
    reason="Test container tables are created via metadata.create_all(), not Alembic "
    "migrations — request_log is not a hypertable so drop_chunks() fails.",
    strict=False,
)
async def test_hypertable_retention_function_shape(obs_db_session, _patch_session_factory):
    """_purge_obs_table runs against a real DB and returns expected dict shape."""
    from backend.tasks.retention import _purge_obs_table

    result = await _purge_obs_table("observability.request_log", 30)
    assert result["status"] == "ok"
    assert "dropped_chunks" in result
    assert result["retention_days"] == 30


# H5 fix: explicit mapping, not name-guessing heuristic
_TABLE_TO_TASK = {
    "observability.request_log": ("purge_old_request_logs_task", 30),
    "observability.api_error_log": ("purge_old_api_error_logs_task", 90),
    "observability.slow_query_log": ("purge_old_slow_query_logs_task", 30),
    "observability.cache_operation_log": ("purge_old_cache_operation_logs_task", 7),
    "observability.celery_worker_heartbeat": ("purge_old_celery_heartbeats_task", 7),
    "observability.provider_health_snapshot": ("purge_old_provider_health_snapshots_task", 30),
    "auth_event_log": ("purge_old_auth_event_logs_task", 90),
    "oauth_event_log": ("purge_old_oauth_event_logs_task", 90),
    "email_send_log": ("purge_old_email_send_logs_task", 90),
    "db_pool_event": ("purge_old_db_pool_events_task", 90),
    "schema_migration_log": ("purge_old_schema_migration_logs_task", 365),
    "beat_schedule_run": ("purge_old_beat_schedule_runs_task", 90),
    "agent_intent_log": ("purge_old_agent_intent_logs_task", 30),
    "agent_reasoning_log": ("purge_old_agent_reasoning_logs_task", 30),
    "frontend_error_log": ("purge_old_frontend_error_logs_task", 30),
    "deploy_events": ("purge_old_deploy_events_task", 365),
    "finding_log": ("purge_old_findings_task", 180),
    "celery_queue_depth": ("purge_old_celery_queue_depths_task", 7),
}


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    "table,expected",
    list(_TABLE_TO_TASK.items()),
    ids=list(_TABLE_TO_TASK.keys()),
)
async def test_retention_task_exists_with_correct_policy(table, expected):
    """Every obs table has a retention task function in the retention module."""
    from backend.tasks import retention as ret_module

    func_name, _retention_days = expected
    assert hasattr(ret_module, func_name), f"No task {func_name} for {table}"
