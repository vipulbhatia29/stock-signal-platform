"""Chat session management — pure functions for session CRUD and context windowing."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import tiktoken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.chat import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# Use cl100k_base encoding (GPT-4/Claude compatible token counting)
_ENCODING = tiktoken.get_encoding("cl100k_base")


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    agent_type: str,
    title: str | None = None,
) -> ChatSession:
    """Create a new chat session.

    Args:
        db: Async database session.
        user_id: The ID of the user creating the session.
        agent_type: Agent type ('stock' or 'general').
        title: Optional session title.

    Returns:
        The newly created ChatSession.
    """
    session = ChatSession(
        user_id=user_id,
        agent_type=agent_type,
        title=title,
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    logger.info("Created chat session %s for user %s", session.id, user_id)
    return session


async def load_session_messages(
    db: AsyncSession,
    session_id: uuid.UUID,
    limit: int = 20,
) -> list[dict]:
    """Load messages for a session, ordered by created_at ascending.

    Args:
        db: Async database session.
        session_id: The chat session ID.
        limit: Max messages to return (most recent).

    Returns:
        List of message dicts with role, content, and tool_calls.
    """
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return [
        {
            "role": msg.role,
            "content": msg.content,
            "tool_calls": msg.tool_calls,
        }
        for msg in messages
    ]


async def list_user_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[ChatSession]:
    """List active chat sessions for a user, ordered by most recent first.

    Args:
        db: Async database session.
        user_id: The user's ID.

    Returns:
        List of active ChatSession objects.
    """
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id, ChatSession.is_active.is_(True))
        .order_by(ChatSession.last_active_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def deactivate_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Soft-delete a chat session by setting is_active=False.

    Args:
        db: Async database session.
        session_id: The session to deactivate.
        user_id: The requesting user (for ownership validation).

    Raises:
        ValueError: If session not found or user doesn't own it.
    """
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if session is None:
        raise ValueError(f"Session {session_id} not found")
    if session.user_id != user_id:
        raise ValueError(f"User {user_id} not authorized to delete session {session_id}")

    session.is_active = False
    await db.commit()
    logger.info("Deactivated chat session %s", session_id)


async def expire_inactive_sessions(
    db: AsyncSession,
    max_age_hours: int = 24,
) -> int:
    """Mark sessions inactive if they haven't been used within max_age_hours.

    Args:
        db: Async database session.
        max_age_hours: Hours of inactivity before expiration.

    Returns:
        Number of sessions expired.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stmt = (
        update(ChatSession)
        .where(
            ChatSession.is_active.is_(True),
            ChatSession.last_active_at < cutoff,
        )
        .values(is_active=False)
    )
    result = await db.execute(stmt)
    await db.commit()
    count = result.rowcount
    logger.info("Expired %d inactive sessions (cutoff: %s)", count, cutoff)
    return count


def build_context_window(
    messages: list[dict],
    max_tokens: int = 16000,
) -> list[dict]:
    """Truncate conversation history to fit within a token budget.

    Keeps the most recent messages, dropping oldest first when the total
    token count exceeds max_tokens. Uses tiktoken cl100k_base encoding
    for token counting (compatible with GPT-4 and Claude tokenizers).

    Args:
        messages: List of message dicts with 'role' and 'content'.
        max_tokens: Maximum token budget for the context window.

    Returns:
        Truncated list of messages fitting within the budget.
    """
    if not messages:
        return []

    # Count tokens per message
    token_counts = []
    for msg in messages:
        content = msg.get("content") or ""
        # ~4 tokens overhead per message for role/formatting
        tokens = len(_ENCODING.encode(content)) + 4
        token_counts.append(tokens)

    total = sum(token_counts)
    if total <= max_tokens:
        return messages

    # Drop oldest messages until under budget
    start_idx = 0
    while total > max_tokens and start_idx < len(messages) - 1:
        total -= token_counts[start_idx]
        start_idx += 1

    return messages[start_idx:]


def auto_title(first_message: str) -> str:
    """Generate a session title from the first user message.

    Truncates to ~100 characters at a word boundary.

    Args:
        first_message: The user's first message in the session.

    Returns:
        A short title string.
    """
    if not first_message.strip():
        return "New Chat"

    text = first_message.strip()
    if len(text) <= 100:
        return text

    # Truncate at word boundary
    truncated = text[:100]
    last_space = truncated.rfind(" ")
    if last_space > 50:
        truncated = truncated[:last_space]
    return truncated + "..."


async def save_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    role: str,
    content: str | None,
    tool_calls: list[dict] | None = None,
    model_used: str | None = None,
    tokens_used: int | None = None,
) -> ChatMessage:
    """Persist a single chat message to the database.

    Args:
        db: Async database session.
        session_id: The chat session this message belongs to.
        role: Message role ('user' or 'assistant').
        content: Message text content.
        tool_calls: Optional JSONB tool call data.
        model_used: Optional LLM model identifier.
        tokens_used: Optional total token count.

    Returns:
        The persisted ChatMessage.
    """
    message = ChatMessage(
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        model_used=model_used,
        tokens_used=tokens_used,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    logger.info("Saved %s message for session %s", role, session_id)
    return message
