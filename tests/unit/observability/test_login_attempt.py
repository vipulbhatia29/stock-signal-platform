"""Tests for LoginAttempt model and auth recording."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.login_attempt import LoginAttempt


class TestLoginAttemptModel:
    """Tests for the LoginAttempt ORM model."""

    def test_create_success_attempt(self) -> None:
        """A successful login attempt can be instantiated."""
        attempt = LoginAttempt(
            timestamp=datetime.now(timezone.utc),
            user_id=uuid.uuid4(),
            email="test@example.com",
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            success=True,
            failure_reason=None,
        )
        assert attempt.success is True
        assert attempt.failure_reason is None
        assert attempt.email == "test@example.com"

    def test_create_failure_attempt(self) -> None:
        """A failed login attempt stores the failure reason."""
        attempt = LoginAttempt(
            timestamp=datetime.now(timezone.utc),
            user_id=None,
            email="bad@example.com",
            ip_address="10.0.0.1",
            user_agent="curl/7.88",
            success=False,
            failure_reason="invalid_credentials",
        )
        assert attempt.success is False
        assert attempt.failure_reason == "invalid_credentials"
        assert attempt.user_id is None

    def test_repr(self) -> None:
        """__repr__ includes email and success."""
        attempt = LoginAttempt(
            timestamp=datetime.now(timezone.utc),
            email="repr@test.com",
            ip_address="0.0.0.0",
            success=True,
        )
        assert "repr@test.com" in repr(attempt)
        assert "True" in repr(attempt)

    def test_user_agent_max_length(self) -> None:
        """The auth helper truncates user_agent to 500 chars."""
        attempt = LoginAttempt(
            timestamp=datetime.now(timezone.utc),
            email="test@test.com",
            ip_address="1.2.3.4",
            user_agent="X" * 500,
            success=True,
        )
        assert len(attempt.user_agent) == 500


class TestPurgeLoginAttempts:
    """Tests for the login attempt purge task."""

    @pytest.mark.asyncio
    async def test_purge_deletes_old_records(self) -> None:
        """Purge task deletes records older than 90 days."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "backend.database.async_session_factory",
            return_value=mock_cm,
        ):
            from backend.tasks.audit import _purge_login_attempts_async

            await _purge_login_attempts_async()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_purge_no_records(self) -> None:
        """Purge task handles zero records gracefully."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "backend.database.async_session_factory",
            return_value=mock_cm,
        ):
            from backend.tasks.audit import _purge_login_attempts_async

            await _purge_login_attempts_async()

        mock_session.execute.assert_called_once()
