"""Unit tests for retention tasks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRetentionTaskRegistration:
    """Verify tasks are registered with correct Celery names."""

    def test_forecast_retention_task_registered(self) -> None:
        """purge_old_forecasts_task is registered with correct name."""
        from backend.tasks.retention import purge_old_forecasts_task

        assert purge_old_forecasts_task.name == "backend.tasks.retention.purge_old_forecasts_task"

    def test_news_retention_task_registered(self) -> None:
        """purge_old_news_articles_task is registered with correct name."""
        from backend.tasks.retention import purge_old_news_articles_task

        expected = "backend.tasks.retention.purge_old_news_articles_task"
        assert purge_old_news_articles_task.name == expected


class TestPurgeOldForecasts:
    """Tests for _purge_old_forecasts_async."""

    @pytest.mark.asyncio
    async def test_deletes_rows_older_than_30_days(self) -> None:
        """Forecasts older than 30 days are deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 42

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.retention.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_forecasts_async

            result = await _purge_old_forecasts_async()

        assert result["status"] == "ok"
        assert result["deleted"] == 42
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_zero_when_nothing_to_delete(self) -> None:
        """Returns deleted=0 when no old forecasts exist."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.retention.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_forecasts_async

            result = await _purge_old_forecasts_async()

        assert result["deleted"] == 0


class TestPurgeOldNewsArticles:
    """Tests for _purge_old_news_articles_async using drop_chunks."""

    @pytest.mark.asyncio
    async def test_calls_drop_chunks_with_90_day_interval(self) -> None:
        """News retention uses TimescaleDB drop_chunks instead of row-level DELETE."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("chunk1",), ("chunk2",), ("chunk3",)]

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.retention.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_news_articles_async

            result = await _purge_old_news_articles_async()

        assert result["status"] == "ok"
        assert result["dropped_chunks"] == 3
        assert result["retention_days"] == 90
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the SQL text contains drop_chunks
        execute_call = mock_session.execute.call_args
        sql_text = str(execute_call[0][0])
        assert "drop_chunks" in sql_text
        assert "news_articles" in sql_text

    @pytest.mark.asyncio
    async def test_passes_interval_as_parameter(self) -> None:
        """Interval is passed as a bind parameter, not interpolated."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.retention.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_news_articles_async

            await _purge_old_news_articles_async()

        execute_call = mock_session.execute.call_args
        params = execute_call[0][1]
        assert params == {"days": 90}

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_chunks_to_drop(self) -> None:
        """Returns dropped_chunks=0 when no old chunks exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.retention.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_news_articles_async

            result = await _purge_old_news_articles_async()

        assert result["dropped_chunks"] == 0


class TestRetentionBeatSchedule:
    """Verify beat schedule entries exist."""

    def test_forecast_retention_in_beat_schedule(self) -> None:
        """Beat schedule has forecast-retention-daily entry."""
        from backend.tasks import celery_app

        assert "forecast-retention-daily" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["forecast-retention-daily"]
        assert entry["task"] == "backend.tasks.retention.purge_old_forecasts_task"

    def test_news_retention_in_beat_schedule(self) -> None:
        """Beat schedule has news-retention-daily entry."""
        from backend.tasks import celery_app

        assert "news-retention-daily" in celery_app.conf.beat_schedule
        entry = celery_app.conf.beat_schedule["news-retention-daily"]
        assert entry["task"] == "backend.tasks.retention.purge_old_news_articles_task"


class TestCompressionMigration:
    """Tests for migration 028 compression policy configuration."""

    def test_compression_config_has_three_tables(self) -> None:
        """Migration covers exactly 3 hypertables."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.028_timescaledb_compression")
        assert len(mod.COMPRESSION_CONFIG) == 3

    def test_stock_prices_config(self) -> None:
        """stock_prices uses ticker segmentby and 180d threshold."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.028_timescaledb_compression")
        cfg = next(c for c in mod.COMPRESSION_CONFIG if c["table"] == "stock_prices")
        assert cfg["segmentby"] == "ticker"
        assert cfg["orderby"] == "time DESC"
        assert cfg["policy_interval"] == "180 days"

    def test_signal_snapshots_config(self) -> None:
        """signal_snapshots uses ticker segmentby and 180d threshold."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.028_timescaledb_compression")
        cfg = next(c for c in mod.COMPRESSION_CONFIG if c["table"] == "signal_snapshots")
        assert cfg["segmentby"] == "ticker"
        assert cfg["orderby"] == "computed_at DESC"
        assert cfg["policy_interval"] == "180 days"

    def test_news_articles_config(self) -> None:
        """news_articles uses ticker segmentby and 60d threshold."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.028_timescaledb_compression")
        cfg = next(c for c in mod.COMPRESSION_CONFIG if c["table"] == "news_articles")
        assert cfg["segmentby"] == "ticker"
        assert cfg["orderby"] == "published_at DESC"
        assert cfg["policy_interval"] == "60 days"

    def test_news_compression_before_retention(self) -> None:
        """Compression threshold (60d) < retention cutoff (90d) for storage savings."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.028_timescaledb_compression")
        from backend.tasks.retention import NEWS_RETENTION_DAYS

        cfg = next(c for c in mod.COMPRESSION_CONFIG if c["table"] == "news_articles")
        threshold_days = int(cfg["policy_interval"].split()[0])
        assert threshold_days < NEWS_RETENTION_DAYS, (
            f"Compression ({threshold_days}d) must be < retention ({NEWS_RETENTION_DAYS}d)"
        )

    def test_migration_revision_chain(self) -> None:
        """Migration 028 correctly chains from 027."""
        import importlib

        mod = importlib.import_module("backend.migrations.versions.028_timescaledb_compression")
        assert mod.down_revision == "f1a2b3c4d5e6"
        assert mod.revision == "a7b8c9d0e1f2"
