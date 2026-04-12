"""Portfolio service package — re-exports for backward compatibility.

External call sites continue to use:
    from backend.services.portfolio import get_or_create_portfolio
"""

from backend.services.portfolio.analytics import (
    VALID_STRATEGIES,
    _equal_weight_fallback,
    _optimize,
    compute_quantstats_portfolio,
    compute_rebalancing,
    materialize_rebalancing,
)
from backend.services.portfolio.core import (
    _group_sectors,
    get_all_portfolio_ids,
    get_health_history,
    get_or_create_portfolio,
    get_portfolio_history,
    get_portfolio_summary,
    snapshot_portfolio_value,
)
from backend.services.portfolio.fifo import (
    _get_transactions_for_ticker,
    _run_fifo,
    delete_transaction,
    get_positions_with_pnl,
    list_transactions,
    recompute_position,
)

__all__ = [
    # core
    "get_or_create_portfolio",
    "get_all_portfolio_ids",
    "get_portfolio_summary",
    "get_portfolio_history",
    "get_health_history",
    "snapshot_portfolio_value",
    "_group_sectors",
    # fifo
    "_run_fifo",
    "_get_transactions_for_ticker",
    "recompute_position",
    "get_positions_with_pnl",
    "list_transactions",
    "delete_transaction",
    # analytics
    "VALID_STRATEGIES",
    "compute_quantstats_portfolio",
    "compute_rebalancing",
    "materialize_rebalancing",
    "_optimize",
    "_equal_weight_fallback",
]
