"""Unit test for CONVERGENCE_SNAPSHOT_ENABLED feature flag (Spec B Final.1).

No database session required — the flag check is the first statement inside
_compute_convergence_snapshot_async, before any session is opened.
"""

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_convergence_snapshot_disabled_returns_status():
    """When CONVERGENCE_SNAPSHOT_ENABLED=False the function returns immediately.

    No DB session is opened and the result dict has status='disabled'.
    """
    from backend.tasks.convergence import _compute_convergence_snapshot_async

    with patch("backend.tasks.convergence.settings") as mock_settings:
        mock_settings.CONVERGENCE_SNAPSHOT_ENABLED = False
        result = await _compute_convergence_snapshot_async(ticker="AAPL")

    assert result == {"status": "disabled"}
