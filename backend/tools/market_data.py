"""Market data tool — fetch OHLCV prices from yfinance and store to TimescaleDB.

Business logic has been extracted to backend.services.stock_data.
This module re-exports the public API for backward compatibility.
"""

from backend.services.stock_data import (
    ensure_stock_exists as ensure_stock_exists,
)
from backend.services.stock_data import (
    fetch_prices as fetch_prices,
)
from backend.services.stock_data import (
    fetch_prices_delta as fetch_prices_delta,
)
from backend.services.stock_data import (
    get_latest_price as get_latest_price,
)
from backend.services.stock_data import (
    load_prices_df as load_prices_df,
)
from backend.services.stock_data import (
    update_last_fetched_at as update_last_fetched_at,
)

__all__ = [
    "ensure_stock_exists",
    "fetch_prices",
    "fetch_prices_delta",
    "get_latest_price",
    "load_prices_df",
    "update_last_fetched_at",
]
