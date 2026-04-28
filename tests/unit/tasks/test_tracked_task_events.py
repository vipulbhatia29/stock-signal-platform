"""Tests for PIPELINE_LIFECYCLE events emitted by @tracked_task decorator."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.observability.schema.legacy_events import PipelineLifecycleEvent


@pytest.fixture
def mock_obs_client():
    """Return a mock ObservabilityClient with a sync emit_sync spy."""
    client = MagicMock()
    client.emit_sync = MagicMock()
    return client


class TestTrackedTaskLifecycleEvents:
    @pytest.mark.asyncio
    async def test_emits_started_and_terminal(self, mock_obs_client, monkeypatch):
        """Successful task emits exactly one 'started' + one terminal event."""
        monkeypatch.setattr("backend.tasks.pipeline._maybe_get_obs_client", lambda: mock_obs_client)
        monkeypatch.setattr("backend.tasks.pipeline.settings.OBS_LEGACY_DIRECT_WRITES", True)

        mock_runner = MagicMock()
        mock_runner.start_run = AsyncMock(return_value=uuid.uuid4())
        mock_runner.complete_run = AsyncMock(return_value="success")
        monkeypatch.setattr("backend.tasks.pipeline.PipelineRunner", lambda: mock_runner)

        from backend.tasks.pipeline import tracked_task

        @tracked_task("test_pipeline")
        async def _test_fn(*, run_id):
            return {"ok": True}

        await _test_fn()

        # Should have 2 emit_sync calls: started + terminal
        assert mock_obs_client.emit_sync.call_count == 2

        started_event = mock_obs_client.emit_sync.call_args_list[0][0][0]
        terminal_event = mock_obs_client.emit_sync.call_args_list[1][0][0]

        assert isinstance(started_event, PipelineLifecycleEvent)
        assert started_event.transition == "started"
        assert started_event.pipeline_name == "test_pipeline"
        assert started_event.duration_s is None  # no duration on started events

        assert isinstance(terminal_event, PipelineLifecycleEvent)
        assert terminal_event.transition == "success"
        assert terminal_event.duration_s is not None
        assert terminal_event.duration_s >= 0
        assert terminal_event.pipeline_name == "test_pipeline"

    @pytest.mark.asyncio
    async def test_emits_failed_on_exception(self, mock_obs_client, monkeypatch):
        """Task that raises emits 'started' + 'failed'."""
        monkeypatch.setattr("backend.tasks.pipeline._maybe_get_obs_client", lambda: mock_obs_client)
        monkeypatch.setattr("backend.tasks.pipeline.settings.OBS_LEGACY_DIRECT_WRITES", True)

        mock_runner = MagicMock()
        mock_runner.start_run = AsyncMock(return_value=uuid.uuid4())
        monkeypatch.setattr("backend.tasks.pipeline.PipelineRunner", lambda: mock_runner)

        # Mock async_session_factory for the exception handler's UPDATE
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr("backend.database.async_session_factory", lambda: mock_cm)

        from backend.tasks.pipeline import tracked_task

        @tracked_task("test_pipeline")
        async def _failing_fn(*, run_id):
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await _failing_fn()

        assert mock_obs_client.emit_sync.call_count == 2
        started_event = mock_obs_client.emit_sync.call_args_list[0][0][0]
        failed_event = mock_obs_client.emit_sync.call_args_list[1][0][0]

        assert started_event.transition == "started"
        assert failed_event.transition == "failed"
        assert failed_event.duration_s is not None
        assert failed_event.duration_s >= 0

    @pytest.mark.asyncio
    async def test_no_crash_when_no_obs_client(self, monkeypatch):
        """Lifecycle events are no-ops when obs client unavailable."""
        monkeypatch.setattr("backend.tasks.pipeline._maybe_get_obs_client", lambda: None)

        mock_runner = MagicMock()
        mock_runner.start_run = AsyncMock(return_value=uuid.uuid4())
        mock_runner.complete_run = AsyncMock(return_value="success")
        monkeypatch.setattr("backend.tasks.pipeline.PipelineRunner", lambda: mock_runner)

        from backend.tasks.pipeline import tracked_task

        @tracked_task("test_pipeline")
        async def _test_fn(*, run_id):
            return {"ok": True}

        result = await _test_fn()  # Should not crash
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_emission_failure_does_not_mask_task_result(self, monkeypatch):
        """Even if emit_sync raises, the task succeeds."""
        bad_client = MagicMock()
        bad_client.emit_sync = MagicMock(side_effect=RuntimeError("emit broke"))
        monkeypatch.setattr("backend.tasks.pipeline._maybe_get_obs_client", lambda: bad_client)
        monkeypatch.setattr("backend.tasks.pipeline.settings.OBS_LEGACY_DIRECT_WRITES", True)

        mock_runner = MagicMock()
        mock_runner.start_run = AsyncMock(return_value=uuid.uuid4())
        mock_runner.complete_run = AsyncMock(return_value="success")
        monkeypatch.setattr("backend.tasks.pipeline.PipelineRunner", lambda: mock_runner)

        from backend.tasks.pipeline import tracked_task

        @tracked_task("test_pipeline")
        async def _test_fn(*, run_id):
            return {"ok": True}

        result = await _test_fn()  # Should not crash even though emit raised
        assert result == {"ok": True}

    @pytest.mark.asyncio
    async def test_event_contains_correct_pipeline_name_and_trigger(
        self, mock_obs_client, monkeypatch
    ):
        """Events carry the correct pipeline_name and trigger from the decorator."""
        monkeypatch.setattr("backend.tasks.pipeline._maybe_get_obs_client", lambda: mock_obs_client)
        monkeypatch.setattr("backend.tasks.pipeline.settings.OBS_LEGACY_DIRECT_WRITES", False)

        mock_runner = MagicMock()
        mock_runner.start_run = AsyncMock(return_value=uuid.uuid4())
        mock_runner.complete_run = AsyncMock(return_value="no_op")
        monkeypatch.setattr("backend.tasks.pipeline.PipelineRunner", lambda: mock_runner)

        from backend.tasks.pipeline import tracked_task

        @tracked_task("price_refresh", trigger="manual")
        async def _test_fn(*, run_id):
            return {}

        await _test_fn()

        assert mock_obs_client.emit_sync.call_count == 2
        for call in mock_obs_client.emit_sync.call_args_list:
            event = call[0][0]
            assert event.pipeline_name == "price_refresh"
            assert event.trigger == "manual"

        terminal_event = mock_obs_client.emit_sync.call_args_list[1][0][0]
        assert terminal_event.transition == "no_op"

    @pytest.mark.asyncio
    async def test_started_event_has_no_duration(self, mock_obs_client, monkeypatch):
        """The 'started' event must have duration_s=None (not measured yet)."""
        monkeypatch.setattr("backend.tasks.pipeline._maybe_get_obs_client", lambda: mock_obs_client)
        monkeypatch.setattr("backend.tasks.pipeline.settings.OBS_LEGACY_DIRECT_WRITES", True)

        mock_runner = MagicMock()
        mock_runner.start_run = AsyncMock(return_value=uuid.uuid4())
        mock_runner.complete_run = AsyncMock(return_value="success")
        monkeypatch.setattr("backend.tasks.pipeline.PipelineRunner", lambda: mock_runner)

        from backend.tasks.pipeline import tracked_task

        @tracked_task("test_pipeline")
        async def _test_fn(*, run_id):
            return {}

        await _test_fn()

        started_event = mock_obs_client.emit_sync.call_args_list[0][0][0]
        assert started_event.duration_s is None
