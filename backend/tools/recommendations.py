"""Recommendation engine — re-exports from the service layer.

All recommendation logic (generation, position sizing, persistence) now lives
in ``backend.services.recommendations``. This file preserves the public API
so that existing imports (tools, tasks, tests, routers) continue to work
without changes.
"""

from backend.services.recommendations import (
    BUY_THRESHOLD as BUY_THRESHOLD,
)
from backend.services.recommendations import (
    MIN_TRADE_SIZE as MIN_TRADE_SIZE,
)
from backend.services.recommendations import (
    WATCH_THRESHOLD as WATCH_THRESHOLD,
)
from backend.services.recommendations import (
    Action as Action,
)
from backend.services.recommendations import (
    Confidence as Confidence,
)
from backend.services.recommendations import (
    PortfolioState as PortfolioState,
)
from backend.services.recommendations import (
    RecommendationResult as RecommendationResult,
)
from backend.services.recommendations import (
    calculate_position_size as calculate_position_size,
)
from backend.services.recommendations import (
    generate_recommendation as generate_recommendation,
)
from backend.services.recommendations import (
    store_recommendation as store_recommendation,
)

__all__ = [
    "Action",
    "BUY_THRESHOLD",
    "Confidence",
    "MIN_TRADE_SIZE",
    "PortfolioState",
    "RecommendationResult",
    "WATCH_THRESHOLD",
    "calculate_position_size",
    "generate_recommendation",
    "store_recommendation",
]
