"""Unit tests for the nightly data quality scanner (KAN-446).

Verifies task registration, each check helper, persistence of findings,
and alert creation for critical findings. All DB I/O is mocked.

Patching at the lookup site:
  - backend.database.async_session_factory  (imported at module level in dq_scan)
  - backend.tasks.alerts._create_alert      (lazy import inside _dq_scan_async)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_execute_result(rows: list[tuple]) -> MagicMock:
    """Build a mock execute result that returns the given rows from .all()."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    return mock_result


def _make_mock_db(execute_results: list[MagicMock] | None = None) -> AsyncMock:
    """Build a mock AsyncSession with configurable execute() side-effects.

    Args:
        execute_results: Sequence of results returned by successive execute() calls.
            If None, all calls return an empty result.

    Returns:
        AsyncMock representing an async SQLAlchemy session.
    """
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    if execute_results is not None:
        mock_db.execute = AsyncMock(side_effect=execute_results)
    else:
        empty = _make_execute_result([])
        mock_db.execute = AsyncMock(return_value=empty)

    return mock_db


def _make_session_factory(mock_db: AsyncMock) -> MagicMock:
    """Wrap a mock DB session in a mock async context manager factory.

    Args:
        mock_db: The mock session to return from __aenter__.

    Returns:
        MagicMock that behaves like async_session_factory() context manager.
    """
    mock_factory = MagicMock()
    mock_factory.__aenter__ = AsyncMock(return_value=mock_db)
    mock_factory.__aexit__ = AsyncMock(return_value=False)
    return mock_factory


# ---------------------------------------------------------------------------
# 1. Task registration
# ---------------------------------------------------------------------------


class TestDqScanTaskRegistration:
    """Verify task is registered in Celery with the correct name."""

    def test_dq_scan_task_is_registered(self) -> None:
        """dq_scan_task is importable from backend.tasks.dq_scan."""
        from backend.tasks.dq_scan import dq_scan_task

        assert dq_scan_task is not None

    def test_dq_scan_task_celery_name(self) -> None:
        """dq_scan_task has the fully-qualified Celery task name."""
        from backend.tasks.dq_scan import dq_scan_task

        assert dq_scan_task.name == "backend.tasks.dq_scan.dq_scan_task"

    def test_dq_scan_in_beat_schedule(self) -> None:
        """Beat schedule has a 'dq-scan-daily' entry pointing to dq_scan_task."""
        from backend.tasks import celery_app

        schedule = celery_app.conf.beat_schedule
        assert "dq-scan-daily" in schedule
        assert schedule["dq-scan-daily"]["task"] == "backend.tasks.dq_scan.dq_scan_task"


# ---------------------------------------------------------------------------
# 2. _check_negative_prices
# ---------------------------------------------------------------------------


class TestCheckNegativePrices:
    """Tests for the _check_negative_prices async check helper."""

    @pytest.mark.asyncio
    async def test_check_negative_prices_finds_bad_rows(self) -> None:
        """_check_negative_prices returns one finding per bad row."""
        from backend.tasks.dq_scan import _check_negative_prices

        bad_rows = [("AAPL", "2026-01-01", -5.0), ("MSFT", "2026-01-02", -1.2)]
        mock_db = _make_mock_db([_make_execute_result(bad_rows)])

        findings = await _check_negative_prices(mock_db)

        assert len(findings) == 2
        assert all(f["check"] == "negative_prices" for f in findings)
        assert all(f["severity"] == "critical" for f in findings)
        assert findings[0]["ticker"] == "AAPL"
        assert findings[1]["ticker"] == "MSFT"

    @pytest.mark.asyncio
    async def test_check_negative_prices_no_findings_when_clean(self) -> None:
        """_check_negative_prices returns empty list when no bad rows exist."""
        from backend.tasks.dq_scan import _check_negative_prices

        mock_db = _make_mock_db([_make_execute_result([])])

        findings = await _check_negative_prices(mock_db)

        assert findings == []

    @pytest.mark.asyncio
    async def test_check_negative_prices_message_format(self) -> None:
        """_check_negative_prices includes ticker, time, and close in message."""
        from backend.tasks.dq_scan import _check_negative_prices

        mock_db = _make_mock_db([_make_execute_result([("TSLA", "2026-03-01", -3.5)])])

        findings = await _check_negative_prices(mock_db)

        assert "TSLA" in findings[0]["message"]
        assert "2026-03-01" in findings[0]["message"]
        assert "-3.5" in findings[0]["message"]


# ---------------------------------------------------------------------------
# 3. _check_negative_volume
# ---------------------------------------------------------------------------


class TestCheckNegativeVolume:
    """Tests for the _check_negative_volume async check helper."""

    @pytest.mark.asyncio
    async def test_check_negative_volume_finds_bad_rows(self) -> None:
        """_check_negative_volume returns critical findings for negative volume."""
        from backend.tasks.dq_scan import _check_negative_volume

        mock_db = _make_mock_db([_make_execute_result([("GOOG", "2026-01-03", -1000)])])

        findings = await _check_negative_volume(mock_db)

        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"
        assert findings[0]["ticker"] == "GOOG"

    @pytest.mark.asyncio
    async def test_check_negative_volume_no_findings_when_clean(self) -> None:
        """_check_negative_volume returns empty list when no negative volumes."""
        from backend.tasks.dq_scan import _check_negative_volume

        mock_db = _make_mock_db([_make_execute_result([])])

        findings = await _check_negative_volume(mock_db)

        assert findings == []


# ---------------------------------------------------------------------------
# 4. _check_rsi_out_of_range
# ---------------------------------------------------------------------------


class TestCheckRsiOutOfRange:
    """Tests for the _check_rsi_out_of_range async check helper."""

    @pytest.mark.asyncio
    async def test_check_rsi_finds_violations(self) -> None:
        """_check_rsi_out_of_range returns high-severity findings for bad RSI values."""
        from backend.tasks.dq_scan import _check_rsi_out_of_range

        rows = [("AAPL", "2026-01-01", 105.3), ("MSFT", "2026-01-01", -2.1)]
        mock_db = _make_mock_db([_make_execute_result(rows)])

        findings = await _check_rsi_out_of_range(mock_db)

        assert len(findings) == 2
        assert all(f["severity"] == "high" for f in findings)
        assert all(f["check"] == "rsi_out_of_range" for f in findings)

    @pytest.mark.asyncio
    async def test_check_rsi_no_violations(self) -> None:
        """_check_rsi_out_of_range returns empty list when all RSI values are in range."""
        from backend.tasks.dq_scan import _check_rsi_out_of_range

        mock_db = _make_mock_db([_make_execute_result([])])

        findings = await _check_rsi_out_of_range(mock_db)

        assert findings == []


# ---------------------------------------------------------------------------
# 5. _dq_scan_async: persistence
# ---------------------------------------------------------------------------


class TestDqScanPersistence:
    """Tests for finding persistence in _dq_scan_async."""

    @pytest.mark.asyncio
    async def test_dq_scan_persists_findings_to_history(self) -> None:
        """_dq_scan_async calls db.add() with DqCheckHistory for each finding."""
        from backend.models.dq_check_history import DqCheckHistory
        from backend.tasks.dq_scan import _dq_scan_async

        # One check returns one bad row (negative price → critical finding)
        # All other 9 checks return empty results
        bad_row_result = _make_execute_result([("AAPL", "2026-01-01", -5.0)])
        empty_result = _make_execute_result([])

        execute_results = [bad_row_result] + [empty_result] * 9

        mock_db = _make_mock_db(execute_results)
        mock_factory = _make_session_factory(mock_db)

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch("backend.tasks.alerts._create_alert", AsyncMock()),
        ):
            await _dq_scan_async()

        # db.add() was called once (one finding)
        assert mock_db.add.call_count == 1
        # The argument to add() is a DqCheckHistory instance
        add_arg = mock_db.add.call_args[0][0]
        assert isinstance(add_arg, DqCheckHistory)
        assert add_arg.check_name == "negative_prices"
        assert add_arg.severity == "critical"
        assert add_arg.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_dq_scan_commits_after_persisting(self) -> None:
        """_dq_scan_async calls db.commit() after persisting all findings."""
        from backend.tasks.dq_scan import _dq_scan_async

        empty_result = _make_execute_result([])
        mock_db = _make_mock_db([empty_result] * 10)
        mock_factory = _make_session_factory(mock_db)

        with patch("backend.database.async_session_factory", return_value=mock_factory):
            await _dq_scan_async()

        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_dq_scan_returns_findings_count(self) -> None:
        """_dq_scan_async returns dict with findings count matching actual findings."""
        from backend.tasks.dq_scan import _dq_scan_async

        # Two bad rows in negative_prices check
        bad_rows_result = _make_execute_result(
            [("AAPL", "2026-01-01", -5.0), ("TSLA", "2026-01-02", -2.0)]
        )
        empty_result = _make_execute_result([])
        execute_results = [bad_rows_result] + [empty_result] * 9

        mock_db = _make_mock_db(execute_results)
        mock_factory = _make_session_factory(mock_db)

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch("backend.tasks.alerts._create_alert", AsyncMock()),
        ):
            result = await _dq_scan_async()

        assert result["status"] == "ok"
        assert result["findings"] == 2
        assert result["critical"] == 2


# ---------------------------------------------------------------------------
# 6. _dq_scan_async: alert creation
# ---------------------------------------------------------------------------


class TestDqScanAlerts:
    """Tests for alert creation in _dq_scan_async."""

    @pytest.mark.asyncio
    async def test_dq_scan_creates_alerts_for_critical_findings(self) -> None:
        """_dq_scan_async calls _create_alert for each critical finding."""
        from backend.tasks.dq_scan import _dq_scan_async

        # negative_prices → critical
        bad_row_result = _make_execute_result([("AAPL", "2026-01-01", -5.0)])
        empty_result = _make_execute_result([])
        execute_results = [bad_row_result] + [empty_result] * 9

        mock_db_main = _make_mock_db(execute_results)
        mock_db_alert = _make_mock_db()

        call_count = 0

        def factory_side_effect() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_session_factory(mock_db_main)
            return _make_session_factory(mock_db_alert)

        mock_create_alert = AsyncMock(return_value=True)

        with (
            patch(
                "backend.database.async_session_factory",
                side_effect=factory_side_effect,
            ),
            patch("backend.tasks.alerts._create_alert", mock_create_alert),
        ):
            result = await _dq_scan_async()

        assert result["critical"] == 1
        mock_create_alert.assert_called_once()
        # Verify the alert was called with correct args
        call_kwargs = mock_create_alert.call_args[1]
        assert call_kwargs["alert_type"] == "data_quality"
        assert call_kwargs["severity"] == "critical"
        assert call_kwargs["ticker"] == "AAPL"
        assert "dq:negative_prices:AAPL" == call_kwargs["dedup_key"]

    @pytest.mark.asyncio
    async def test_dq_scan_skips_alerts_when_no_critical(self) -> None:
        """_dq_scan_async does not call _create_alert when there are no critical findings."""
        from backend.tasks.dq_scan import _dq_scan_async

        # All checks return empty — no findings at all
        empty_result = _make_execute_result([])
        mock_db = _make_mock_db([empty_result] * 10)
        mock_factory = _make_session_factory(mock_db)

        mock_create_alert = AsyncMock(return_value=True)

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch("backend.tasks.alerts._create_alert", mock_create_alert),
        ):
            result = await _dq_scan_async()

        assert result["critical"] == 0
        mock_create_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_dq_scan_skips_alerts_for_medium_severity(self) -> None:
        """_dq_scan_async does not create alerts for medium/high severity findings."""
        from backend.tasks.dq_scan import _dq_scan_async

        # null_sectors check → medium severity (4th check, index 3)
        empty_result = _make_execute_result([])
        null_sector_result = _make_execute_result([("IBM",)])

        # negative_prices(0), rsi(1), composite(2), null_sectors(3), rest empty
        execute_results = [
            empty_result,  # negative_prices
            empty_result,  # rsi
            empty_result,  # composite_score
            null_sector_result,  # null_sectors → medium
            empty_result,  # forecast_extreme
            empty_result,  # orphan_positions
            empty_result,  # duplicate_signals
            empty_result,  # stale_universe
            empty_result,  # negative_volume
            empty_result,  # bollinger
        ]

        mock_db = _make_mock_db(execute_results)
        mock_factory = _make_session_factory(mock_db)
        mock_create_alert = AsyncMock(return_value=True)

        with (
            patch("backend.database.async_session_factory", return_value=mock_factory),
            patch("backend.tasks.alerts._create_alert", mock_create_alert),
        ):
            result = await _dq_scan_async()

        assert result["findings"] == 1
        assert result["critical"] == 0
        mock_create_alert.assert_not_called()
