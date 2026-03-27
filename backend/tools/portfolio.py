"""Portfolio tool: FIFO cost basis, P&L, summary, position recompute.

All business logic now lives in backend.services.portfolio.
This module re-exports the public API so existing callers (routers, tasks,
agents) continue to work without changes.
"""

from backend.services.portfolio import (
    _get_transactions_for_ticker as _get_transactions_for_ticker,
)
from backend.services.portfolio import (
    _group_sectors as _group_sectors,
)
from backend.services.portfolio import (
    _run_fifo as _run_fifo,
)
from backend.services.portfolio import (
    get_all_portfolio_ids as get_all_portfolio_ids,
)
from backend.services.portfolio import (
    get_or_create_portfolio as get_or_create_portfolio,
)
from backend.services.portfolio import (
    get_portfolio_history as get_portfolio_history,
)
from backend.services.portfolio import (
    get_portfolio_summary as get_portfolio_summary,
)
from backend.services.portfolio import (
    get_positions_with_pnl as get_positions_with_pnl,
)
from backend.services.portfolio import (
    recompute_position as recompute_position,
)
from backend.services.portfolio import (
    snapshot_portfolio_value as snapshot_portfolio_value,
)

__all__ = [
    "_get_transactions_for_ticker",
    "_group_sectors",
    "_run_fifo",
    "get_all_portfolio_ids",
    "get_or_create_portfolio",
    "get_portfolio_history",
    "get_portfolio_summary",
    "get_positions_with_pnl",
    "recompute_position",
    "snapshot_portfolio_value",
]
