"""Database models package — import all models so Alembic can discover them."""

from backend.models.base import Base
from backend.models.dividend import DividendPayment
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.portfolio import (  # noqa: F401
    Portfolio,
    PortfolioSnapshot,
    Position,
    Transaction,
)
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User, UserPreference, UserRole

__all__ = [
    "Base",
    "DividendPayment",
    "Portfolio",
    "PortfolioSnapshot",
    "Position",
    "RecommendationSnapshot",
    "SignalSnapshot",
    "Stock",
    "StockIndex",
    "StockIndexMembership",
    "StockPrice",
    "Transaction",
    "User",
    "UserPreference",
    "UserRole",
    "Watchlist",
]
