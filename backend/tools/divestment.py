"""Divestment rules engine: pure function that checks positions against thresholds."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.user import UserPreference

logger = logging.getLogger(__name__)


def check_divestment_rules(
    position: dict,
    sector_allocations: list[dict],
    signal: dict | None,
    prefs: UserPreference,
) -> list[dict]:
    """Check divestment rules for a single position.

    Pure function — no DB calls, no side effects.  Receives all data
    it needs as arguments and returns a list of alert dicts.

    Args:
        position: Dict with keys: ticker, unrealized_pnl_pct,
            allocation_pct, sector.  Values may be None.
        sector_allocations: List of dicts with keys: sector, pct.
        signal: Dict with key composite_score (float | None),
            or None if no signal data available for this ticker.
        prefs: User's preference record with threshold fields
            (default_stop_loss_pct, max_position_pct, max_sector_pct).

    Returns:
        List of alert dicts, each with keys:
            rule (str), severity (str), message (str),
            value (float), threshold (float).
        Empty list if no rules fire.
    """
    alerts: list[dict] = []

    # 1. Stop-loss
    pnl_pct = position.get("unrealized_pnl_pct")
    if pnl_pct is not None:
        threshold = prefs.default_stop_loss_pct
        if pnl_pct <= -threshold:
            alerts.append(
                {
                    "rule": "stop_loss",
                    "severity": "critical",
                    "message": f"Down {abs(pnl_pct):.1f}% (limit: {threshold:.0f}%)",
                    "value": pnl_pct,
                    "threshold": threshold,
                }
            )

    # 2. Position concentration
    alloc_pct = position.get("allocation_pct")
    if alloc_pct is not None:
        threshold = prefs.max_position_pct
        if alloc_pct > threshold:
            alerts.append(
                {
                    "rule": "position_concentration",
                    "severity": "warning",
                    "message": f"{alloc_pct:.1f}% of portfolio (limit: {threshold:.0f}%)",
                    "value": alloc_pct,
                    "threshold": threshold,
                }
            )

    # 3. Sector concentration
    sector = position.get("sector")
    if sector is not None:
        threshold = prefs.max_sector_pct
        for sa in sector_allocations:
            if sa["sector"] == sector and sa["pct"] > threshold:
                alerts.append(
                    {
                        "rule": "sector_concentration",
                        "severity": "warning",
                        "message": f"{sector} at {sa['pct']:.1f}% (limit: {threshold:.0f}%)",
                        "value": sa["pct"],
                        "threshold": threshold,
                    }
                )
                break

    # 4. Weak fundamentals (composite score < 3)
    if signal is not None:
        score = signal.get("composite_score")
        if score is not None and score < 3:
            alerts.append(
                {
                    "rule": "weak_fundamentals",
                    "severity": "warning",
                    "message": f"Composite: {score:.1f}",
                    "value": score,
                    "threshold": 3.0,
                }
            )

    return alerts
