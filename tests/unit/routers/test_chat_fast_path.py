"""Unit tests for the fast path wiring in _event_generator (chat router).

Tests verify that out_of_scope and simple_lookup intents are handled
before the agent graph is invoked.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_chat_session(session_id: uuid.UUID | None = None) -> MagicMock:
    """Create a minimal ChatSession mock."""
    session = MagicMock()
    session.id = session_id or uuid.uuid4()
    session.agent_type = "general"
    session.decline_count = 0
    return session


def _make_user(user_id: uuid.UUID | None = None) -> MagicMock:
    """Create a minimal User mock."""
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    return user


def _make_request(tool_executor=None) -> MagicMock:
    """Create a minimal FastAPI Request mock with app.state."""
    request = MagicMock()
    request.app.state.agent_graph = None
    request.app.state.tool_executor = tool_executor
    return request


def _make_body(message: str) -> MagicMock:
    """Create a minimal ChatRequest mock."""
    body = MagicMock()
    body.message = message
    return body


async def _collect_events(gen) -> list[str]:
    """Drain an async generator and return lines."""
    lines = []
    async for line in gen:
        lines.append(line)
    return lines


@pytest.mark.asyncio
async def test_fast_path_out_of_scope_yields_decline_event():
    """out_of_scope intent yields a decline event and returns early."""
    from backend.routers.chat import _event_generator

    session = _make_chat_session()
    user = _make_user()
    body = _make_body("What is the weather today?")
    request = _make_request(tool_executor=None)

    # Patch DB interactions so the test is fully isolated
    mock_ctx_db = AsyncMock()
    mock_ctx_db.__aenter__ = AsyncMock(return_value=mock_ctx_db)
    mock_ctx_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "backend.routers.chat.async_session_factory",
            return_value=mock_ctx_db,
        ),
        patch(
            "backend.agents.user_context.build_user_context",
            new=AsyncMock(return_value={"positions": []}),
        ),
        patch("backend.routers.chat.save_message", new=AsyncMock()),
    ):
        events = await _collect_events(
            _event_generator(
                request,
                body,
                session,
                [],
                user,
                uuid.uuid4(),
                ctx_tokens=None,
            )
        )

    # Should yield exactly 2 lines: decline + done
    assert len(events) == 2, f"Expected 2 events, got {len(events)}: {events}"
    assert '"decline"' in events[0], f"First event should be decline: {events[0]}"
    assert '"done"' in events[1], f"Second event should be done: {events[1]}"


@pytest.mark.asyncio
async def test_fast_path_simple_lookup_uses_tool_executor():
    """simple_lookup fast path calls tool_executor and yields token+done."""
    from backend.routers.chat import _event_generator

    session = _make_chat_session()
    user = _make_user()
    body = _make_body("AAPL price")
    request = _make_request(tool_executor=None)

    # Set up a fake tool executor that returns a dict-like result
    fake_result = SimpleNamespace(data={"ticker": "AAPL", "price": 195.50})

    async def _fake_tool_executor(tool_name: str, params: dict):
        assert tool_name == "analyze_stock"
        assert params["ticker"] == "AAPL"
        return fake_result

    request.app.state.tool_executor = _fake_tool_executor

    mock_ctx_db = AsyncMock()
    mock_ctx_db.__aenter__ = AsyncMock(return_value=mock_ctx_db)
    mock_ctx_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "backend.routers.chat.async_session_factory",
            return_value=mock_ctx_db,
        ),
        patch(
            "backend.agents.user_context.build_user_context",
            new=AsyncMock(return_value={"positions": []}),
        ),
        patch("backend.routers.chat.save_message", new=AsyncMock()),
    ):
        events = await _collect_events(
            _event_generator(
                request,
                body,
                session,
                [],
                user,
                uuid.uuid4(),
                ctx_tokens=None,
            )
        )

    # Should yield exactly 2 lines: token + done
    assert len(events) == 2, f"Expected 2 events, got {len(events)}: {events}"
    assert '"token"' in events[0], f"First event should be token: {events[0]}"
    assert '"done"' in events[1], f"Second event should be done: {events[1]}"


@pytest.mark.asyncio
async def test_fast_path_simple_lookup_falls_through_without_tool_executor():
    """simple_lookup without tool_executor falls through to the graph path."""
    from backend.routers.chat import _event_generator

    session = _make_chat_session()
    user = _make_user()
    body = _make_body("AAPL price")
    request = _make_request(tool_executor=None)
    # No tool_executor on app.state — should fall through to graph path
    request.app.state.tool_executor = None
    request.app.state.agent_graph = None  # graph also absent → error event

    mock_ctx_db = AsyncMock()
    mock_ctx_db.__aenter__ = AsyncMock(return_value=mock_ctx_db)
    mock_ctx_db.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "backend.routers.chat.async_session_factory",
            return_value=mock_ctx_db,
        ),
        patch(
            "backend.agents.user_context.build_user_context",
            new=AsyncMock(return_value={"positions": []}),
        ),
        patch("backend.routers.chat.save_message", new=AsyncMock()),
    ):
        events = await _collect_events(
            _event_generator(
                request,
                body,
                session,
                [],
                user,
                uuid.uuid4(),
                ctx_tokens=None,
            )
        )

    # Falls through to graph path; graph=None → error event
    assert len(events) >= 1
    assert '"error"' in events[0], f"Expected error event when graph is None, got: {events[0]}"
