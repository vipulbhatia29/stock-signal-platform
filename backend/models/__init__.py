"""Database models package — import all models so Alembic can discover them."""

from backend.models.base import Base
from backend.models.chat import ChatMessage, ChatSession
from backend.models.dividend import DividendPayment
from backend.models.earnings import EarningsSnapshot
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.logs import LLMCallLog, ToolExecutionLog
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
    "ChatMessage",
    "ChatSession",
    "DividendPayment",
    "EarningsSnapshot",
    "LLMCallLog",
    "Portfolio",
    "PortfolioSnapshot",
    "Position",
    "RecommendationSnapshot",
    "SignalSnapshot",
    "Stock",
    "StockIndex",
    "StockIndexMembership",
    "StockPrice",
    "ToolExecutionLog",
    "Transaction",
    "User",
    "UserPreference",
    "UserRole",
    "Watchlist",
]
