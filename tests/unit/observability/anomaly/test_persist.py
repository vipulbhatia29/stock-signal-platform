"""Tests for finding persistence and dedup logic."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.observability.anomaly.base import Finding
from backend.observability.anomaly.persist import persist_findings


class TestPersistFindings:
    @pytest.mark.asyncio
    async def test_new_finding_is_inserted(self) -> None:
        """New finding with no existing open/acknowledged record is inserted and committed."""
        finding = Finding(
            kind="test_rule",
            attribution_layer="test",
            severity="warning",
            title="Test",
            evidence={"x": 1},
            dedup_key="test_rule:test:entity1",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("backend.observability.anomaly.persist.async_session_factory") as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            inserted, skipped = await persist_findings([finding])

        assert inserted == 1
        assert skipped == 0
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_finding_is_skipped(self) -> None:
        """Finding with matching dedup_key in open/acknowledged status is skipped without insert."""
        finding = Finding(
            kind="test_rule",
            attribution_layer="test",
            severity="warning",
            title="Test",
            evidence={"x": 1},
            dedup_key="test_rule:test:entity1",
        )
        existing_row = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_row)
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("backend.observability.anomaly.persist.async_session_factory") as factory:
            factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            factory.return_value.__aexit__ = AsyncMock(return_value=False)
            inserted, skipped = await persist_findings([finding])

        assert inserted == 0
        assert skipped == 1
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_list_is_noop(self) -> None:
        """Empty findings list returns (0, 0) without touching the database."""
        inserted, skipped = await persist_findings([])
        assert inserted == 0
        assert skipped == 0
