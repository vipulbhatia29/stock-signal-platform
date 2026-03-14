"""Database models package — import all models so Alembic can discover them."""

from backend.models.base import Base
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.portfolio import Portfolio, Position, Transaction  # noqa: F401
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User, UserPreference, UserRole

__all__ = [
    "Base",
    "Portfolio",
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
