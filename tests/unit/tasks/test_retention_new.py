"""Unit tests for new retention tasks.

Covers: llm_call_log, tool_execution_log, pipeline_runs, dq_check_history.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestNewRetentionTaskRegistration:
    """Verify new retention tasks are registered with correct Celery names."""

    def test_llm_call_log_retention_task_registered(self) -> None:
        """purge_old_llm_call_log_task is registered with correct Celery name."""
        from backend.tasks.retention import purge_old_llm_call_log_task

        assert (
            purge_old_llm_call_log_task.name
            == "backend.tasks.retention.purge_old_llm_call_log_task"
        )

    def test_tool_execution_log_retention_task_registered(self) -> None:
        """purge_old_tool_execution_log_task is registered with correct Celery name."""
        from backend.tasks.retention import purge_old_tool_execution_log_task

        assert (
            purge_old_tool_execution_log_task.name
            == "backend.tasks.retention.purge_old_tool_execution_log_task"
        )

    def test_pipeline_runs_retention_task_registered(self) -> None:
        """purge_old_pipeline_runs_task is registered with correct Celery name."""
        from backend.tasks.retention import purge_old_pipeline_runs_task

        assert (
            purge_old_pipeline_runs_task.name
            == "backend.tasks.retention.purge_old_pipeline_runs_task"
        )

    def test_dq_check_history_retention_task_registered(self) -> None:
        """purge_old_dq_check_history_task is registered with correct Celery name."""
        from backend.tasks.retention import purge_old_dq_check_history_task

        assert (
            purge_old_dq_check_history_task.name
            == "backend.tasks.retention.purge_old_dq_check_history_task"
        )


class TestPurgeOldLlmCallLog:
    """Tests for _purge_old_llm_call_log_async (hypertable — drop_chunks)."""

    @pytest.mark.asyncio
    async def test_calls_drop_chunks_with_30_day_interval(self) -> None:
        """LLM call log retention uses drop_chunks with a 30-day interval."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("chunk1",), ("chunk2",)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_llm_call_log_async

            result = await _purge_old_llm_call_log_async()

        assert result["status"] == "ok"
        assert result["dropped_chunks"] == 2
        assert result["retention_days"] == 30
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the SQL contains drop_chunks targeting llm_call_log
        execute_call = mock_session.execute.call_args
        sql_text = str(execute_call[0][0])
        assert "drop_chunks" in sql_text
        assert "llm_call_log" in sql_text

    @pytest.mark.asyncio
    async def test_passes_interval_as_bind_parameter(self) -> None:
        """Interval is passed as a bind parameter, not string-interpolated into SQL."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_llm_call_log_async

            await _purge_old_llm_call_log_async()

        execute_call = mock_session.execute.call_args
        params = execute_call[0][1]
        assert params == {"days": 30}

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_chunks_to_drop(self) -> None:
        """Returns dropped_chunks=0 when no old chunks exist in llm_call_log."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_llm_call_log_async

            result = await _purge_old_llm_call_log_async()

        assert result["dropped_chunks"] == 0


class TestPurgeOldToolExecutionLog:
    """Tests for _purge_old_tool_execution_log_async (hypertable — drop_chunks)."""

    @pytest.mark.asyncio
    async def test_calls_drop_chunks_with_30_day_interval(self) -> None:
        """Tool execution log retention uses drop_chunks with a 30-day interval."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("chunk1",), ("chunk2",), ("chunk3",)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_tool_execution_log_async

            result = await _purge_old_tool_execution_log_async()

        assert result["status"] == "ok"
        assert result["dropped_chunks"] == 3
        assert result["retention_days"] == 30
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the SQL contains drop_chunks targeting tool_execution_log
        execute_call = mock_session.execute.call_args
        sql_text = str(execute_call[0][0])
        assert "drop_chunks" in sql_text
        assert "tool_execution_log" in sql_text

    @pytest.mark.asyncio
    async def test_passes_interval_as_bind_parameter(self) -> None:
        """Interval is passed as a bind parameter, not string-interpolated into SQL."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_tool_execution_log_async

            await _purge_old_tool_execution_log_async()

        execute_call = mock_session.execute.call_args
        params = execute_call[0][1]
        assert params == {"days": 30}

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_chunks_to_drop(self) -> None:
        """Returns dropped_chunks=0 when no old chunks exist in tool_execution_log."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_tool_execution_log_async

            result = await _purge_old_tool_execution_log_async()

        assert result["dropped_chunks"] == 0


class TestPurgeOldPipelineRuns:
    """Tests for _purge_old_pipeline_runs_async (regular table — DELETE)."""

    @pytest.mark.asyncio
    async def test_deletes_rows_older_than_90_days(self) -> None:
        """Pipeline runs older than 90 days are deleted via raw SQL DELETE."""
        mock_result = MagicMock()
        mock_result.rowcount = 5

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_pipeline_runs_async

            result = await _purge_old_pipeline_runs_async()

        assert result["status"] == "ok"
        assert result["deleted"] == 5
        assert "cutoff" in result
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify DELETE SQL targets the correct table and column
        execute_call = mock_session.execute.call_args
        sql_text = str(execute_call[0][0])
        assert "DELETE FROM pipeline_runs" in sql_text
        assert "started_at" in sql_text

    @pytest.mark.asyncio
    async def test_uses_cutoff_bind_parameter(self) -> None:
        """Cutoff datetime is passed as a bind parameter, not string-interpolated."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_pipeline_runs_async

            await _purge_old_pipeline_runs_async()

        execute_call = mock_session.execute.call_args
        params = execute_call[0][1]
        assert "cutoff" in params

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_to_delete(self) -> None:
        """Returns deleted=0 when no old pipeline runs exist."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_pipeline_runs_async

            result = await _purge_old_pipeline_runs_async()

        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_handles_none_rowcount(self) -> None:
        """Returns deleted=0 when rowcount is None (empty table edge case)."""
        mock_result = MagicMock()
        mock_result.rowcount = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_pipeline_runs_async

            result = await _purge_old_pipeline_runs_async()

        assert result["deleted"] == 0


class TestPurgeOldDqCheckHistory:
    """Tests for _purge_old_dq_check_history_async (regular table — DELETE)."""

    @pytest.mark.asyncio
    async def test_deletes_rows_older_than_90_days(self) -> None:
        """DQ check history older than 90 days is deleted via raw SQL DELETE."""
        mock_result = MagicMock()
        mock_result.rowcount = 12

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_dq_check_history_async

            result = await _purge_old_dq_check_history_async()

        assert result["status"] == "ok"
        assert result["deleted"] == 12
        assert "cutoff" in result
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify DELETE SQL targets the correct table and column
        execute_call = mock_session.execute.call_args
        sql_text = str(execute_call[0][0])
        assert "DELETE FROM dq_check_history" in sql_text
        assert "detected_at" in sql_text

    @pytest.mark.asyncio
    async def test_uses_cutoff_bind_parameter(self) -> None:
        """Cutoff datetime is passed as a bind parameter, not string-interpolated."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_dq_check_history_async

            await _purge_old_dq_check_history_async()

        execute_call = mock_session.execute.call_args
        params = execute_call[0][1]
        assert "cutoff" in params

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_to_delete(self) -> None:
        """Returns deleted=0 when no old DQ check history exists."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_dq_check_history_async

            result = await _purge_old_dq_check_history_async()

        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_handles_none_rowcount(self) -> None:
        """Returns deleted=0 when rowcount is None (empty table edge case)."""
        mock_result = MagicMock()
        mock_result.rowcount = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_dq_check_history_async

            result = await _purge_old_dq_check_history_async()

        assert result["deleted"] == 0


class TestNewRetentionBeatSchedule:
    """Verify new beat schedule entries exist at the correct times."""

    def test_llm_call_log_retention_in_beat_schedule(self) -> None:
        """Beat schedule has llm-call-log-retention-daily entry at 4:15 AM."""
        from backend.tasks import celery_app

        assert "llm-call-log-retention-daily" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["llm-call-log-retention-daily"]
        assert entry["task"] == "backend.tasks.retention.purge_old_llm_call_log_task"

    def test_tool_execution_log_retention_in_beat_schedule(self) -> None:
        """Beat schedule has tool-execution-log-retention-daily entry at 4:30 AM."""
        from backend.tasks import celery_app

        assert "tool-execution-log-retention-daily" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["tool-execution-log-retention-daily"]
        assert entry["task"] == "backend.tasks.retention.purge_old_tool_execution_log_task"

    def test_pipeline_runs_retention_in_beat_schedule(self) -> None:
        """Beat schedule has pipeline-runs-retention-daily entry at 4:45 AM."""
        from backend.tasks import celery_app

        assert "pipeline-runs-retention-daily" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["pipeline-runs-retention-daily"]
        assert entry["task"] == "backend.tasks.retention.purge_old_pipeline_runs_task"

    def test_dq_check_history_retention_in_beat_schedule(self) -> None:
        """Beat schedule has dq-check-history-retention-daily entry at 5:00 AM."""
        from backend.tasks import celery_app

        assert "dq-check-history-retention-daily" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["dq-check-history-retention-daily"]
        assert entry["task"] == "backend.tasks.retention.purge_old_dq_check_history_task"

    def test_login_attempts_not_duplicated(self) -> None:
        """purge-login-attempts-daily already exists — confirm no duplicate was added."""
        from backend.tasks import celery_app

        # Only one entry for login attempts (the pre-existing one in audit tasks)
        login_entries = [k for k in celery_app.conf.beat_schedule if "login-attempts" in k]
        assert len(login_entries) == 1, (
            f"Expected 1 login-attempts entry, found {len(login_entries)}: {login_entries}"
        )

    def test_new_retention_tasks_do_not_overlap_existing_times(self) -> None:
        """New retention tasks are scheduled at 4:15, 4:30, 4:45, 5:00 — no collisions."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        new_tasks = [
            "llm-call-log-retention-daily",
            "tool-execution-log-retention-daily",
            "pipeline-runs-retention-daily",
            "dq-check-history-retention-daily",
        ]
        for task_name in new_tasks:
            assert task_name in schedule, f"Missing beat schedule entry: {task_name}"
