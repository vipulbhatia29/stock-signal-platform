"""Unit tests for backend.request_context ContextVars."""

from __future__ import annotations

import uuid

from backend.request_context import current_query_id, current_session_id, current_user_id


def test_current_user_id_default_is_none() -> None:
    """current_user_id ContextVar has a default value of None."""
    assert current_user_id.get() is None


def test_current_session_id_default_is_none() -> None:
    """current_session_id ContextVar has a default value of None."""
    assert current_session_id.get() is None


def test_current_query_id_default_is_none() -> None:
    """current_query_id ContextVar has a default value of None."""
    assert current_query_id.get() is None


def test_set_and_get_session_id() -> None:
    """Setting current_session_id is visible via get, and reset restores None."""
    session_id = uuid.uuid4()
    token = current_session_id.set(session_id)
    try:
        assert current_session_id.get() == session_id
    finally:
        current_session_id.reset(token)
    assert current_session_id.get() is None


def test_set_and_get_query_id() -> None:
    """Setting current_query_id is visible via get, and reset restores None."""
    query_id = uuid.uuid4()
    token = current_query_id.set(query_id)
    try:
        assert current_query_id.get() == query_id
    finally:
        current_query_id.reset(token)
    assert current_query_id.get() is None
