"""Tests for SQLAlchemy connection pool statistics collector."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from backend.observability.metrics.db_pool import get_pool_stats


@pytest.fixture
def mock_engine() -> MagicMock:
    """Create a mock AsyncEngine with pool stats."""
    engine = MagicMock()
    pool = MagicMock()
    pool.size.return_value = 10
    pool.checkedout.return_value = 3
    pool.overflow.return_value = 0
    pool.checkedin.return_value = 7
    pool.status.return_value = "Pool size: 10  Connections in pool: 7"
    type(engine).pool = PropertyMock(return_value=pool)
    return engine


@pytest.mark.asyncio
async def test_get_pool_stats_happy_path(mock_engine: MagicMock) -> None:
    """Returns pool statistics when engine is healthy."""
    stats = await get_pool_stats(mock_engine)

    assert stats["pool_size"] == 10
    assert stats["checked_out"] == 3
    assert stats["overflow"] == 0
    assert stats["checked_in"] == 7
    assert "Pool size" in stats["pool_status"]


@pytest.mark.asyncio
async def test_get_pool_stats_engine_error() -> None:
    """Returns unavailable dict when pool access raises."""
    engine = MagicMock()
    type(engine).pool = PropertyMock(side_effect=RuntimeError("pool gone"))

    stats = await get_pool_stats(engine)

    assert stats["status"] == "unavailable"
    assert "error" in stats
