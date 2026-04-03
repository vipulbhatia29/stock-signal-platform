"""Tests for seed task wrappers and admin user seed.

Verifies task registration, naming, and admin user seeding logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import / registration tests
# ---------------------------------------------------------------------------


class TestSeedTaskImports:
    """Verify all seed tasks are importable with correct names."""

    def test_seed_sp500_task_importable(self) -> None:
        """seed_sp500_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_sp500_task

        assert seed_sp500_task is not None

    def test_seed_indexes_task_importable(self) -> None:
        """seed_indexes_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_indexes_task

        assert seed_indexes_task is not None

    def test_seed_etfs_task_importable(self) -> None:
        """seed_etfs_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_etfs_task

        assert seed_etfs_task is not None

    def test_seed_prices_task_importable(self) -> None:
        """seed_prices_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_prices_task

        assert seed_prices_task is not None

    def test_seed_dividends_task_importable(self) -> None:
        """seed_dividends_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_dividends_task

        assert seed_dividends_task is not None

    def test_seed_fundamentals_task_importable(self) -> None:
        """seed_fundamentals_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_fundamentals_task

        assert seed_fundamentals_task is not None

    def test_seed_forecasts_task_importable(self) -> None:
        """seed_forecasts_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_forecasts_task

        assert seed_forecasts_task is not None

    def test_seed_reason_tier_task_importable(self) -> None:
        """seed_reason_tier_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_reason_tier_task

        assert seed_reason_tier_task is not None

    def test_seed_portfolio_task_importable(self) -> None:
        """seed_portfolio_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_portfolio_task

        assert seed_portfolio_task is not None

    def test_seed_admin_user_task_importable(self) -> None:
        """seed_admin_user_task is importable from backend.tasks.seed_tasks."""
        from backend.tasks.seed_tasks import seed_admin_user_task

        assert seed_admin_user_task is not None


class TestSeedTaskNames:
    """Verify all seed tasks have the correct Celery task names."""

    def test_seed_sp500_task_name(self) -> None:
        """seed_sp500_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_sp500_task

        assert seed_sp500_task.name == "backend.tasks.seed_tasks.seed_sp500_task"

    def test_seed_indexes_task_name(self) -> None:
        """seed_indexes_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_indexes_task

        assert seed_indexes_task.name == "backend.tasks.seed_tasks.seed_indexes_task"

    def test_seed_etfs_task_name(self) -> None:
        """seed_etfs_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_etfs_task

        assert seed_etfs_task.name == "backend.tasks.seed_tasks.seed_etfs_task"

    def test_seed_prices_task_name(self) -> None:
        """seed_prices_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_prices_task

        assert seed_prices_task.name == "backend.tasks.seed_tasks.seed_prices_task"

    def test_seed_dividends_task_name(self) -> None:
        """seed_dividends_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_dividends_task

        assert seed_dividends_task.name == "backend.tasks.seed_tasks.seed_dividends_task"

    def test_seed_fundamentals_task_name(self) -> None:
        """seed_fundamentals_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_fundamentals_task

        assert seed_fundamentals_task.name == "backend.tasks.seed_tasks.seed_fundamentals_task"

    def test_seed_forecasts_task_name(self) -> None:
        """seed_forecasts_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_forecasts_task

        assert seed_forecasts_task.name == "backend.tasks.seed_tasks.seed_forecasts_task"

    def test_seed_reason_tier_task_name(self) -> None:
        """seed_reason_tier_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_reason_tier_task

        assert seed_reason_tier_task.name == "backend.tasks.seed_tasks.seed_reason_tier_task"

    def test_seed_portfolio_task_name(self) -> None:
        """seed_portfolio_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_portfolio_task

        assert seed_portfolio_task.name == "backend.tasks.seed_tasks.seed_portfolio_task"

    def test_seed_admin_user_task_name(self) -> None:
        """seed_admin_user_task has fully-qualified task name."""
        from backend.tasks.seed_tasks import seed_admin_user_task

        assert seed_admin_user_task.name == "backend.tasks.seed_tasks.seed_admin_user_task"


class TestSeedTaskRegistration:
    """Verify all seed tasks are registered with the Celery app."""

    def test_all_seed_tasks_registered(self) -> None:
        """All seed tasks appear in celery_app.tasks registry."""
        import backend.tasks.seed_tasks  # noqa: F401 — ensure module is loaded
        from backend.tasks import celery_app

        expected_names = [
            "backend.tasks.seed_tasks.seed_sp500_task",
            "backend.tasks.seed_tasks.seed_indexes_task",
            "backend.tasks.seed_tasks.seed_etfs_task",
            "backend.tasks.seed_tasks.seed_prices_task",
            "backend.tasks.seed_tasks.seed_dividends_task",
            "backend.tasks.seed_tasks.seed_fundamentals_task",
            "backend.tasks.seed_tasks.seed_forecasts_task",
            "backend.tasks.seed_tasks.seed_reason_tier_task",
            "backend.tasks.seed_tasks.seed_portfolio_task",
            "backend.tasks.seed_tasks.seed_admin_user_task",
        ]
        registered = set(celery_app.tasks.keys())
        for name in expected_names:
            assert name in registered, f"Task '{name}' not found in celery_app.tasks"

    def test_seed_tasks_in_include_list(self) -> None:
        """backend.tasks.seed_tasks is in celery_app include list."""
        from backend.tasks import celery_app

        assert "backend.tasks.seed_tasks" in celery_app.conf.include


# ---------------------------------------------------------------------------
# Admin user seed tests
# ---------------------------------------------------------------------------


def _make_mock_session(existing_user=None):
    """Build a mock async session that returns existing_user from execute()."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_user
    mock_session.execute.return_value = mock_result
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_factory_instance = AsyncMock()
    mock_factory_instance.__aenter__ = AsyncMock(return_value=mock_session)
    mock_factory_instance.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_factory_instance


class TestSeedAdminUser:
    """Tests for _seed_admin_user async function."""

    @pytest.mark.asyncio
    async def test_creates_admin_when_none_exists(self) -> None:
        """Creates a new admin user when none exists in the database."""
        mock_session, mock_factory_instance = _make_mock_session(existing_user=None)

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_factory_instance,
            ),
            patch("backend.config.settings") as mock_settings,
            patch("bcrypt.hashpw", return_value=b"hashed"),
            patch("bcrypt.gensalt", return_value=b"salt"),
        ):
            mock_settings.ADMIN_EMAIL = "admin@example.com"
            mock_settings.ADMIN_PASSWORD = "securepassword"

            from backend.tasks.seed_tasks import _seed_admin_user

            result = await _seed_admin_user()

        assert result["status"] == "created"
        assert result["email"] == "admin@example.com"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_admin_already_exists(self) -> None:
        """Returns 'exists' status when an admin user is already present."""
        from backend.models.user import UserRole

        existing = MagicMock()
        existing.role = UserRole.ADMIN

        mock_session, mock_factory_instance = _make_mock_session(existing_user=existing)

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_factory_instance,
            ),
            patch("backend.config.settings") as mock_settings,
        ):
            mock_settings.ADMIN_EMAIL = "admin@example.com"
            mock_settings.ADMIN_PASSWORD = "securepassword"

            from backend.tasks.seed_tasks import _seed_admin_user

            result = await _seed_admin_user()

        assert result["status"] == "exists"
        assert result["email"] == "admin@example.com"
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_promotes_existing_user_to_admin(self) -> None:
        """Promotes an existing non-admin user to admin role."""
        from backend.models.user import UserRole

        existing = MagicMock()
        existing.role = UserRole.USER

        mock_session, mock_factory_instance = _make_mock_session(existing_user=existing)

        with (
            patch(
                "backend.database.async_session_factory",
                return_value=mock_factory_instance,
            ),
            patch("backend.config.settings") as mock_settings,
        ):
            mock_settings.ADMIN_EMAIL = "user@example.com"
            mock_settings.ADMIN_PASSWORD = "securepassword"

            from backend.tasks.seed_tasks import _seed_admin_user

            result = await _seed_admin_user()

        assert result["status"] == "promoted"
        assert result["email"] == "user@example.com"
        assert existing.role == UserRole.ADMIN
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skips_when_admin_email_empty(self) -> None:
        """Returns 'skipped' when ADMIN_EMAIL is not set."""
        with patch("backend.config.settings") as mock_settings:
            mock_settings.ADMIN_EMAIL = ""
            mock_settings.ADMIN_PASSWORD = "securepassword"

            from backend.tasks.seed_tasks import _seed_admin_user

            result = await _seed_admin_user()

        assert result["status"] == "skipped"
        assert "ADMIN_EMAIL" in result["reason"]

    @pytest.mark.asyncio
    async def test_skips_when_admin_password_empty(self) -> None:
        """Returns 'skipped' when ADMIN_PASSWORD is not set."""
        with patch("backend.config.settings") as mock_settings:
            mock_settings.ADMIN_EMAIL = "admin@example.com"
            mock_settings.ADMIN_PASSWORD = ""

            from backend.tasks.seed_tasks import _seed_admin_user

            result = await _seed_admin_user()

        assert result["status"] == "skipped"
        assert "ADMIN_PASSWORD" in result["reason"]

    @pytest.mark.asyncio
    async def test_skips_when_both_credentials_empty(self) -> None:
        """Returns 'skipped' when both ADMIN_EMAIL and ADMIN_PASSWORD are missing."""
        with patch("backend.config.settings") as mock_settings:
            mock_settings.ADMIN_EMAIL = ""
            mock_settings.ADMIN_PASSWORD = ""

            from backend.tasks.seed_tasks import _seed_admin_user

            result = await _seed_admin_user()

        assert result["status"] == "skipped"
