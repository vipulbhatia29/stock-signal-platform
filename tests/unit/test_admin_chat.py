"""Tests for admin chat audit trail endpoints (KAN-153)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.models.user import UserRole
from backend.schemas.chat import (
    AdminChatSessionListResponse,
    AdminChatSessionSummary,
    AdminChatStatsResponse,
    AdminChatTranscriptResponse,
)

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def admin_user() -> MagicMock:
    """Mock admin user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "admin@example.com"
    user.role = UserRole.ADMIN
    user.is_active = True
    return user


@pytest.fixture
def regular_user() -> MagicMock:
    """Mock non-admin user."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "user@example.com"
    user.role = UserRole.USER
    user.is_active = True
    return user


@pytest.fixture
def now() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture
def mock_session_row(now: datetime) -> MagicMock:
    """Mock row from the session list query (joined result)."""
    row = MagicMock()
    row.ChatSession.id = uuid.uuid4()
    row.ChatSession.agent_type = "stock"
    row.ChatSession.title = "Test session"
    row.ChatSession.is_active = True
    row.ChatSession.decline_count = 0
    row.ChatSession.created_at = now
    row.ChatSession.last_active_at = now
    row.user_email = "testuser@example.com"
    row.message_count = 5
    return row


@pytest.fixture
def mock_message() -> MagicMock:
    """Mock ChatMessage ORM object."""
    msg = MagicMock()
    msg.id = uuid.uuid4()
    msg.role = "user"
    msg.content = "Hello"
    msg.tool_calls = None
    msg.model_used = None
    msg.tokens_used = None
    msg.prompt_tokens = None
    msg.completion_tokens = None
    msg.latency_ms = None
    msg.feedback = None
    msg.created_at = datetime.now(timezone.utc)
    return msg


# ── Schema tests ────────────────────────────────────────────────────────────


class TestAdminChatSchemas:
    def test_session_summary_fields(self, now: datetime) -> None:
        """AdminChatSessionSummary has all required fields."""
        summary = AdminChatSessionSummary(
            id=uuid.uuid4(),
            agent_type="stock",
            title="Test",
            is_active=True,
            decline_count=0,
            user_email="user@example.com",
            message_count=3,
            created_at=now,
            last_active_at=now,
        )
        assert summary.user_email == "user@example.com"
        assert summary.message_count == 3

    def test_list_response(self, now: datetime) -> None:
        """AdminChatSessionListResponse wraps total + sessions."""
        resp = AdminChatSessionListResponse(total=0, sessions=[])
        assert resp.total == 0
        assert resp.sessions == []

    def test_transcript_response(self, now: datetime) -> None:
        """AdminChatTranscriptResponse wraps session + messages."""
        summary = AdminChatSessionSummary(
            id=uuid.uuid4(),
            agent_type="general",
            title=None,
            is_active=False,
            decline_count=1,
            user_email="user@example.com",
            message_count=0,
            created_at=now,
            last_active_at=now,
        )
        resp = AdminChatTranscriptResponse(session=summary, messages=[])
        assert resp.session.agent_type == "general"

    def test_stats_response(self) -> None:
        """AdminChatStatsResponse has all stat fields."""
        stats = AdminChatStatsResponse(
            total_sessions=10,
            total_messages=50,
            active_sessions=3,
            feedback_up=20,
            feedback_down=5,
        )
        assert stats.total_sessions == 10
        assert stats.feedback_up == 20


# ── Admin guard tests ───────────────────────────────────────────────────────


class TestAdminGuard:
    def test_non_admin_rejected(self, regular_user: MagicMock) -> None:
        """Non-admin user gets 403."""
        from backend.dependencies import require_admin

        with pytest.raises(HTTPException) as exc_info:
            require_admin(regular_user)
        assert exc_info.value.status_code == 403

    def test_admin_allowed(self, admin_user: MagicMock) -> None:
        """Admin user passes through."""
        from backend.dependencies import require_admin

        result = require_admin(admin_user)
        assert result is admin_user


# ── Endpoint tests ──────────────────────────────────────────────────────────


class TestListChatSessions:
    @pytest.mark.asyncio
    async def test_returns_paginated_sessions(
        self, admin_user: MagicMock, mock_session_row: MagicMock
    ) -> None:
        """List sessions returns paginated results."""
        from backend.observability.routers.admin import list_chat_sessions

        mock_db = AsyncMock()
        # First call: count query → returns 1
        # Second call: paginated results → returns rows
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        rows_result = MagicMock()
        rows_result.all.return_value = [mock_session_row]
        mock_db.execute.side_effect = [count_result, rows_result]

        with patch("backend.observability.routers.admin.require_admin", return_value=admin_user):
            result = await list_chat_sessions(
                user=admin_user, db=mock_db, user_id=None, agent_type=None, limit=50, offset=0
            )

        assert result.total == 1
        assert len(result.sessions) == 1
        assert result.sessions[0].user_email == "testuser@example.com"

    @pytest.mark.asyncio
    async def test_non_admin_forbidden(self, regular_user: MagicMock) -> None:
        """Non-admin user gets 403."""
        from backend.observability.routers.admin import list_chat_sessions

        mock_db = AsyncMock()
        with pytest.raises(HTTPException) as exc_info:
            await list_chat_sessions(
                user=regular_user, db=mock_db, user_id=None, agent_type=None, limit=50, offset=0
            )
        assert exc_info.value.status_code == 403


class TestGetChatTranscript:
    @pytest.mark.asyncio
    async def test_session_not_found(self, admin_user: MagicMock) -> None:
        """Missing session returns 404."""
        from backend.observability.routers.admin import get_chat_transcript

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await get_chat_transcript(session_id=uuid.uuid4(), user=admin_user, db=mock_db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_transcript(
        self, admin_user: MagicMock, mock_session_row: MagicMock, mock_message: MagicMock
    ) -> None:
        """Returns session summary + ordered messages."""
        from backend.observability.routers.admin import get_chat_transcript

        mock_db = AsyncMock()
        # First call: session query
        session_result = MagicMock()
        session_result.one_or_none.return_value = mock_session_row
        # Second call: messages query
        msg_scalars = MagicMock()
        msg_scalars.all.return_value = [mock_message]
        msg_result = MagicMock()
        msg_result.scalars.return_value = msg_scalars
        mock_db.execute.side_effect = [session_result, msg_result]

        result = await get_chat_transcript(
            session_id=mock_session_row.ChatSession.id, user=admin_user, db=mock_db
        )
        assert result.session.user_email == "testuser@example.com"
        assert len(result.messages) == 1


class TestGetChatStats:
    @pytest.mark.asyncio
    async def test_returns_counts(self, admin_user: MagicMock) -> None:
        """Stats endpoint returns aggregate counts."""
        from backend.observability.routers.admin import get_chat_stats

        mock_db = AsyncMock()
        # 5 sequential scalar queries
        mock_db.execute.side_effect = [
            MagicMock(scalar=MagicMock(return_value=10)),  # total_sessions
            MagicMock(scalar=MagicMock(return_value=50)),  # total_messages
            MagicMock(scalar=MagicMock(return_value=3)),  # active_sessions
            MagicMock(scalar=MagicMock(return_value=20)),  # feedback_up
            MagicMock(scalar=MagicMock(return_value=5)),  # feedback_down
        ]

        result = await get_chat_stats(user=admin_user, db=mock_db)
        assert result.total_sessions == 10
        assert result.total_messages == 50
        assert result.active_sessions == 3
        assert result.feedback_up == 20
        assert result.feedback_down == 5
