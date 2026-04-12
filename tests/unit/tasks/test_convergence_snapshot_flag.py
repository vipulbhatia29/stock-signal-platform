"""Unit test for CONVERGENCE_SNAPSHOT_ENABLED feature flag (Spec B Final.1).

No database session required — the flag check is the first statement inside
_compute_convergence_snapshot_async, before any session is opened.
"""

import uuid
from unittest.mock import patch

import pytest

from tests.unit.tasks._tracked_helper_bypass import bypass_tracked


@pytest.mark.asyncio
async def test_convergence_snapshot_disabled_returns_status():
    """When CONVERGENCE_SNAPSHOT_ENABLED=False the function returns immediately.

    No DB session is opened and the result dict has status='disabled'.
    """
    from backend.tasks.convergence import _compute_convergence_snapshot_async

    with patch("backend.tasks.convergence.settings") as mock_settings:
        mock_settings.CONVERGENCE_SNAPSHOT_ENABLED = False
        result = await bypass_tracked(_compute_convergence_snapshot_async)(
            ticker="AAPL", run_id=uuid.uuid4()
        )

    assert result == {"status": "disabled"}
