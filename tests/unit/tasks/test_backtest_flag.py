"""Unit test for BACKTEST_ENABLED feature flag (Spec B Final.1).

No database session required — the flag check is the first statement inside
_run_backtest_async, before any session is opened.
"""

import uuid
from unittest.mock import patch

import pytest

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


@pytest.mark.asyncio
async def test_backtest_disabled_returns_status():
    """When BACKTEST_ENABLED=False the function returns immediately.

    No DB session is opened and the result dict has status='disabled'.
    """
    from backend.tasks.forecasting import _run_backtest_async

    with patch("backend.tasks.forecasting.settings") as mock_settings:
        mock_settings.BACKTEST_ENABLED = False
        result = await bypass_tracked(_run_backtest_async)(
            ticker=None, horizon_days=90, run_id=uuid.uuid4()
        )

    assert result == {"status": "disabled"}
