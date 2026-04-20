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


# ---------------------------------------------------------------------------
# Auto-close tests
# ---------------------------------------------------------------------------


class TestAutoCloseFindings:
    """Tests for auto_close_findings()."""

    @pytest.mark.asyncio
    async def test_increments_negative_check_count(self) -> None:
        """Open finding not in fired_dedup_keys gets negative_check_count incremented."""
        from backend.observability.anomaly.persist import auto_close_findings

        finding_row = MagicMock()
        finding_row.id = "f1"
        finding_row.dedup_key = "some_rule:layer:entity"
        finding_row.negative_check_count = 1
        finding_row.status = "open"

        mock_session = AsyncMock()
        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[finding_row])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        factory_mock = MagicMock()
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.observability.anomaly.persist.async_session_factory", factory_mock):
            resolved, incremented = await auto_close_findings(fired_dedup_keys=set())

        assert incremented == 1
        assert resolved == 0
        assert finding_row.negative_check_count == 2

    @pytest.mark.asyncio
    async def test_resolves_after_three_consecutive_clears(self) -> None:
        """Finding with negative_check_count=2 (will become 3) gets auto-resolved."""
        from backend.observability.anomaly.persist import auto_close_findings

        finding_row = MagicMock()
        finding_row.id = "f2"
        finding_row.dedup_key = "some_rule:layer:entity"
        finding_row.negative_check_count = 2
        finding_row.status = "open"
        finding_row.resolved_at = None

        mock_session = AsyncMock()
        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[finding_row])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        factory_mock = MagicMock()
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.observability.anomaly.persist.async_session_factory", factory_mock):
            resolved, incremented = await auto_close_findings(fired_dedup_keys=set())

        assert resolved == 1
        assert incremented == 0
        assert finding_row.status == "resolved"
        assert finding_row.resolved_at is not None

    @pytest.mark.asyncio
    async def test_resets_counter_when_refired(self) -> None:
        """Finding whose dedup_key is in fired_dedup_keys gets counter reset to 0."""
        from backend.observability.anomaly.persist import auto_close_findings

        finding_row = MagicMock()
        finding_row.id = "f3"
        finding_row.dedup_key = "some_rule:layer:entity"
        finding_row.negative_check_count = 2
        finding_row.status = "open"

        mock_session = AsyncMock()
        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[finding_row])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        factory_mock = MagicMock()
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.observability.anomaly.persist.async_session_factory", factory_mock):
            resolved, incremented = await auto_close_findings(
                fired_dedup_keys={"some_rule:layer:entity"}
            )

        assert resolved == 0
        assert incremented == 0
        assert finding_row.negative_check_count == 0

    @pytest.mark.asyncio
    async def test_no_open_findings_returns_zeros(self) -> None:
        """No open/acknowledged findings → (0, 0) returned."""
        from backend.observability.anomaly.persist import auto_close_findings

        mock_session = AsyncMock()
        scalars_proxy = MagicMock()
        scalars_proxy.all = MagicMock(return_value=[])
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=scalars_proxy)
        mock_session.execute = AsyncMock(return_value=mock_result)

        factory_mock = MagicMock()
        factory_mock.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        factory_mock.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.observability.anomaly.persist.async_session_factory", factory_mock):
            resolved, incremented = await auto_close_findings(fired_dedup_keys=set())

        assert resolved == 0
        assert incremented == 0
