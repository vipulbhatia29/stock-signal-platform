"""Fundamentals tool — fetch and score fundamental financial metrics.

Business logic has been extracted to backend.services.stock_data.
This module re-exports the public API for backward compatibility.
"""

from backend.services.stock_data import (
    FundamentalResult as FundamentalResult,
)
from backend.services.stock_data import (
    compute_piotroski as compute_piotroski,
)
from backend.services.stock_data import (
    fetch_analyst_data as fetch_analyst_data,
)
from backend.services.stock_data import (
    fetch_earnings_history as fetch_earnings_history,
)
from backend.services.stock_data import (
    fetch_fundamentals as fetch_fundamentals,
)
from backend.services.stock_data import (
    persist_earnings_snapshots as persist_earnings_snapshots,
)
from backend.services.stock_data import (
    persist_enriched_fundamentals as persist_enriched_fundamentals,
)

__all__ = [
    "FundamentalResult",
    "compute_piotroski",
    "fetch_analyst_data",
    "fetch_earnings_history",
    "fetch_fundamentals",
    "persist_earnings_snapshots",
    "persist_enriched_fundamentals",
]
