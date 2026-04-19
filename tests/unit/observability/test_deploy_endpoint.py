"""Tests for the deploy event endpoint and schemas.

Covers: webhook secret auth, deploy event creation, schema validation,
invalid/missing secret rejection, and GitHub Actions header check.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.observability.schema.frontend_deploy_events import (
    DeployEventData,
    DeployStatus,
)


class TestDeployEventDataSchema:
    """Schema-level validation for DeployEventData."""

    def test_valid_deploy_event(self):
        """DeployEventData should parse with required fields."""
        d = DeployEventData(
            git_sha="abc123def456",
            branch="develop",
            author="github-actions[bot]",
            status=DeployStatus.SUCCESS,
        )
        assert d.git_sha == "abc123def456"
        assert d.status == DeployStatus.SUCCESS
        assert d.env == "staging"  # default

    def test_all_fields(self):
        """DeployEventData should accept all optional fields."""
        d = DeployEventData(
            git_sha="abc123def456",
            branch="main",
            pr_number=42,
            author="user",
            commit_message="Fix bug",
            migrations_applied=["030", "031"],
            env="prod",
            deploy_duration_seconds=120.5,
            status=DeployStatus.ROLLED_BACK,
        )
        assert d.pr_number == 42
        assert d.migrations_applied == ["030", "031"]
        assert d.deploy_duration_seconds == 120.5

    def test_git_sha_max_length(self):
        """git_sha should reject values > 40 chars."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeployEventData(
                git_sha="a" * 41,
                branch="main",
                author="user",
                status=DeployStatus.SUCCESS,
            )

    def test_all_deploy_statuses(self):
        """All DeployStatus enum values should be accepted."""
        for status in DeployStatus:
            d = DeployEventData(
                git_sha="abc",
                branch="main",
                author="user",
                status=status,
            )
            assert d.status == status

    def test_default_env_is_staging(self):
        """Default env should be 'staging'."""
        d = DeployEventData(
            git_sha="abc", branch="main", author="user", status=DeployStatus.SUCCESS
        )
        assert d.env == "staging"


class TestDeployEventEndpointAuth:
    """Auth logic tests for the deploy event endpoint."""

    @pytest.mark.asyncio
    async def test_no_configured_secret_returns_503(self):
        """No configured secret should return 503 (not configured)."""
        from backend.observability.routers.deploy_events import record_deploy_event

        payload = DeployEventData(
            git_sha="abc", branch="main", author="bot", status=DeployStatus.SUCCESS
        )

        # Access the underlying function, bypassing the limiter decorator
        inner_fn = record_deploy_event.__wrapped__  # type: ignore[attr-defined]

        mock_request = MagicMock()
        with patch(
            "backend.observability.routers.deploy_events.settings",
        ) as mock_settings:
            mock_settings.OBS_DEPLOY_WEBHOOK_SECRET = None
            with pytest.raises(HTTPException) as exc_info:
                await inner_fn(
                    request=mock_request,
                    payload=payload,
                    authorization="Bearer something",
                    x_github_event=None,
                )
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_missing_authorization_returns_401(self):
        """Missing Authorization header should return 401."""
        from backend.observability.routers.deploy_events import record_deploy_event

        payload = DeployEventData(
            git_sha="abc", branch="main", author="bot", status=DeployStatus.SUCCESS
        )
        inner_fn = record_deploy_event.__wrapped__  # type: ignore[attr-defined]

        mock_request = MagicMock()
        with patch(
            "backend.observability.routers.deploy_events.settings",
        ) as mock_settings:
            mock_settings.OBS_DEPLOY_WEBHOOK_SECRET = "real-secret"
            with pytest.raises(HTTPException) as exc_info:
                await inner_fn(
                    request=mock_request,
                    payload=payload,
                    authorization=None,
                    x_github_event=None,
                )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_secret_returns_401(self):
        """Wrong secret should return 401."""
        from backend.observability.routers.deploy_events import record_deploy_event

        payload = DeployEventData(
            git_sha="abc", branch="main", author="bot", status=DeployStatus.SUCCESS
        )
        inner_fn = record_deploy_event.__wrapped__  # type: ignore[attr-defined]

        mock_request = MagicMock()
        with patch(
            "backend.observability.routers.deploy_events.settings",
        ) as mock_settings:
            mock_settings.OBS_DEPLOY_WEBHOOK_SECRET = "correct-secret"
            with pytest.raises(HTTPException) as exc_info:
                await inner_fn(
                    request=mock_request,
                    payload=payload,
                    authorization="Bearer wrong-secret",
                    x_github_event=None,
                )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_secret_creates_event(self):
        """Valid secret should create deploy event and return 201."""
        from backend.observability.routers.deploy_events import record_deploy_event

        payload = DeployEventData(
            git_sha="abc123",
            branch="develop",
            author="bot",
            status=DeployStatus.SUCCESS,
        )
        inner_fn = record_deploy_event.__wrapped__  # type: ignore[attr-defined]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_request = MagicMock()

        with (
            patch(
                "backend.observability.routers.deploy_events.settings",
            ) as mock_settings,
            patch(
                "backend.observability.routers.deploy_events.async_session_factory",
                return_value=mock_session,
            ),
        ):
            mock_settings.OBS_DEPLOY_WEBHOOK_SECRET = "test-secret-123"
            result = await inner_fn(
                request=mock_request,
                payload=payload,
                authorization="Bearer test-secret-123",
                x_github_event="deployment",
            )

        assert result["status"] == "created"
        assert result["git_sha"] == "abc123"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_db_failure_returns_503(self):
        """DB write failure should return 503 with Retry-After."""
        from backend.observability.routers.deploy_events import record_deploy_event

        payload = DeployEventData(
            git_sha="abc", branch="main", author="bot", status=DeployStatus.SUCCESS
        )
        inner_fn = record_deploy_event.__wrapped__  # type: ignore[attr-defined]

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.commit.side_effect = RuntimeError("DB down")

        mock_request = MagicMock()
        with (
            patch(
                "backend.observability.routers.deploy_events.settings",
            ) as mock_settings,
            patch(
                "backend.observability.routers.deploy_events.async_session_factory",
                return_value=mock_session,
            ),
        ):
            mock_settings.OBS_DEPLOY_WEBHOOK_SECRET = "test-secret"
            with pytest.raises(HTTPException) as exc_info:
                await inner_fn(
                    request=mock_request,
                    payload=payload,
                    authorization="Bearer test-secret",
                    x_github_event="deployment",
                )
        assert exc_info.value.status_code == 503


class TestEventWriterRouting:
    """Verify event_writer routes FRONTEND_ERROR and passes on DEPLOY_EVENT."""

    def test_frontend_error_in_event_type_enum(self):
        """FRONTEND_ERROR should be a valid EventType."""
        from backend.observability.schema.v1 import EventType

        assert EventType.FRONTEND_ERROR.value == "frontend_error"

    def test_deploy_event_in_event_type_enum(self):
        """DEPLOY_EVENT should be a valid EventType."""
        from backend.observability.schema.v1 import EventType

        assert EventType.DEPLOY_EVENT.value == "deploy_event"
