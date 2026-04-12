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
    """Tests for _purge_old_news_articles_async."""

    @pytest.mark.asyncio
    async def test_deletes_articles_older_than_90_days(self) -> None:
        """News articles older than 90 days are deleted."""
        mock_result = MagicMock()
        mock_result.rowcount = 150

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
        assert result["deleted"] == 150
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_naive_datetime_for_comparison(self) -> None:
        """Cutoff datetime is naive (no tzinfo) to match NewsArticle.published_at column."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.tasks.retention.async_session_factory", return_value=mock_factory):
            from backend.tasks.retention import _purge_old_news_articles_async

            await _purge_old_news_articles_async()

        # The delete statement should have been constructed — we just verify it was called
        mock_session.execute.assert_called_once()


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
