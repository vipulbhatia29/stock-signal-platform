"""Tests for chat session management functions."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.tools.chat_session import (
    auto_title,
    build_context_window,
    create_session,
    deactivate_session,
    expire_inactive_sessions,
    list_user_sessions,
    load_session_messages,
)


def test_build_context_window_under_budget():
    """Messages under token budget are returned as-is."""
    messages = [
        {"role": "user", "content": "Analyze AAPL"},
        {"role": "assistant", "content": "AAPL looks strong."},
    ]
    result = build_context_window(messages, max_tokens=16000)
    assert len(result) == 2


def test_build_context_window_truncates():
    """Messages exceeding budget drop oldest first."""
    messages = [{"role": "user", "content": "x " * 2000} for _ in range(10)]
    result = build_context_window(messages, max_tokens=1000)
    assert len(result) < len(messages)
    # Most recent messages should be preserved
    assert result[-1] == messages[-1]


def test_build_context_window_empty():
    """Empty messages list returns empty."""
    result = build_context_window([], max_tokens=16000)
    assert result == []


def test_build_context_window_preserves_order():
    """Returned messages maintain chronological order."""
    messages = [{"role": "user", "content": f"message {i}"} for i in range(5)]
    result = build_context_window(messages, max_tokens=16000)
    for i, msg in enumerate(result):
        assert msg["content"] == f"message {i}"


def test_auto_title_short_message():
    """Short messages become titles directly."""
    assert auto_title("Analyze AAPL") == "Analyze AAPL"


def test_auto_title_long_message():
    """Long messages are truncated to ~100 chars at word boundary."""
    long = "This is a very long message " * 10
    result = auto_title(long)
    assert len(result) <= 103  # 100 + "..."
    assert result.endswith("...")


def test_auto_title_empty():
    """Empty message returns 'New Chat'."""
    assert auto_title("") == "New Chat"


@pytest.mark.asyncio
async def test_create_session():
    """create_session inserts a new ChatSession."""
    mock_db = AsyncMock()
    user_id = uuid.uuid4()

    session = await create_session(mock_db, user_id, "stock")

    assert session.user_id == user_id
    assert session.agent_type == "stock"
    assert session.is_active is True
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_session_messages():
    """load_session_messages returns messages ordered by created_at."""
    mock_db = AsyncMock()
    session_id = uuid.uuid4()

    # Simulate SQLAlchemy result
    mock_msg = MagicMock()
    mock_msg.role = "user"
    mock_msg.content = "Hello"
    mock_msg.tool_calls = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_msg]
    mock_db.execute.return_value = mock_result

    messages = await load_session_messages(mock_db, session_id, limit=20)
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"


@pytest.mark.asyncio
async def test_list_user_sessions():
    """list_user_sessions returns active sessions for a user."""
    mock_db = AsyncMock()
    user_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.id = uuid.uuid4()
    mock_session.agent_type = "stock"
    mock_session.is_active = True

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session]
    mock_db.execute.return_value = mock_result

    sessions = await list_user_sessions(mock_db, user_id)
    assert len(sessions) == 1


@pytest.mark.asyncio
async def test_deactivate_session():
    """deactivate_session sets is_active=False."""
    mock_db = AsyncMock()
    session_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.user_id = user_id
    mock_session.is_active = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_session
    mock_db.execute.return_value = mock_result

    await deactivate_session(mock_db, session_id, user_id)
    assert mock_session.is_active is False
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_deactivate_session_not_found():
    """deactivate_session raises ValueError when session not found."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="not found"):
        await deactivate_session(mock_db, uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_deactivate_session_wrong_owner():
    """deactivate_session raises ValueError when user doesn't own session."""
    mock_db = AsyncMock()
    session_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.user_id = uuid.uuid4()  # different user
    mock_session.is_active = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_session
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="not authorized"):
        await deactivate_session(mock_db, session_id, uuid.uuid4())


@pytest.mark.asyncio
async def test_expire_inactive_sessions():
    """expire_inactive_sessions updates stale sessions."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 3
    mock_db.execute.return_value = mock_result

    count = await expire_inactive_sessions(mock_db, max_age_hours=24)
    assert count == 3
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_message():
    """save_message inserts a ChatMessage and returns it."""
    from backend.tools.chat_session import save_message

    mock_db = AsyncMock()
    session_id = uuid.uuid4()

    msg = await save_message(
        mock_db,
        session_id=session_id,
        role="user",
        content="Analyze AAPL",
    )

    assert msg.session_id == session_id
    assert msg.role == "user"
    assert msg.content == "Analyze AAPL"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_awaited_once()
    mock_db.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_message_called_with_correct_role():
    """save_message stores role and content correctly for both user and assistant."""
    from backend.tools.chat_session import save_message

    mock_db = AsyncMock()
    session_id = uuid.uuid4()

    user_msg = await save_message(mock_db, session_id, "user", "Hello")
    assert user_msg.role == "user"

    assistant_msg = await save_message(
        mock_db, session_id, "assistant", "Hi there", tool_calls={"calls": []}
    )
    assert assistant_msg.role == "assistant"
    assert assistant_msg.tool_calls == {"calls": []}
