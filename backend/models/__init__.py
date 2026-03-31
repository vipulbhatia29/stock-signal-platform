"""Database models package — import all models so Alembic can discover them."""

from backend.models.alert import InAppAlert
from backend.models.assessment import AssessmentResult, AssessmentRun
from backend.models.base import Base
from backend.models.chat import ChatMessage, ChatSession
from backend.models.dividend import DividendPayment
from backend.models.earnings import EarningsSnapshot
from backend.models.forecast import ForecastResult, ModelVersion, RecommendationOutcome
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.llm_config import LLMModelConfig
from backend.models.login_attempt import LoginAttempt
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.models.pipeline import PipelineRun, PipelineWatermark
from backend.models.portfolio import (  # noqa: F401
    Portfolio,
    PortfolioSnapshot,
    Position,
    Transaction,
)
from backend.models.portfolio_health import PortfolioHealthSnapshot
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.user import User, UserPreference, UserRole

__all__ = [
    "AssessmentResult",
    "AssessmentRun",
    "Base",
    "ChatMessage",
    "ChatSession",
    "DividendPayment",
    "EarningsSnapshot",
    "ForecastResult",
    "InAppAlert",
    "LLMCallLog",
    "LLMModelConfig",
    "LoginAttempt",
    "ModelVersion",
    "PipelineRun",
    "PipelineWatermark",
    "Portfolio",
    "PortfolioHealthSnapshot",
    "PortfolioSnapshot",
    "Position",
    "RecommendationOutcome",
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
