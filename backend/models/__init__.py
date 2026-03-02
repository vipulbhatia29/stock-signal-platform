"""Database models package — import all models so Alembic can discover them."""

from backend.models.base import Base
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User, UserPreference, UserRole

__all__ = [
    "Base",
    "RecommendationSnapshot",
    "SignalSnapshot",
    "Stock",
    "StockPrice",
    "User",
    "UserPreference",
    "UserRole",
    "Watchlist",
]
