"""Database models package — import all models so Alembic can discover them."""

from backend.models.alert import InAppAlert
from backend.models.assessment import AssessmentResult, AssessmentRun
from backend.models.audit import AdminAuditLog
from backend.models.backtest import BacktestRun
from backend.models.base import Base
from backend.models.chat import ChatMessage, ChatSession
from backend.models.convergence import SignalConvergenceDaily
from backend.models.dividend import DividendPayment
from backend.models.dq_check_history import DqCheckHistory  # noqa: F401
from backend.models.earnings import EarningsSnapshot
from backend.models.forecast import ForecastResult, ModelVersion, RecommendationOutcome
from backend.models.index import StockIndex, StockIndexMembership
from backend.models.llm_config import LLMModelConfig
from backend.models.login_attempt import LoginAttempt
from backend.models.logs import LLMCallLog, ToolExecutionLog
from backend.models.news_sentiment import NewsArticle, NewsSentimentDaily
from backend.models.oauth_account import OAuthAccount
from backend.models.pipeline import PipelineRun, PipelineWatermark
from backend.models.portfolio import (  # noqa: F401
    Portfolio,
    PortfolioSnapshot,
    Position,
    RebalancingSuggestion,
    Transaction,
)
from backend.models.portfolio_health import PortfolioHealthSnapshot
from backend.models.price import StockPrice
from backend.models.recommendation import RecommendationSnapshot
from backend.models.signal import SignalSnapshot
from backend.models.stock import Stock, Watchlist
from backend.models.ticker_ingestion_state import TickerIngestionState
from backend.models.user import User, UserPreference, UserRole

__all__ = [
    "AdminAuditLog",
    "AssessmentResult",
    "AssessmentRun",
    "BacktestRun",
    "Base",
    "ChatMessage",
    "ChatSession",
    "DividendPayment",
    "DqCheckHistory",
    "SignalConvergenceDaily",
    "EarningsSnapshot",
    "ForecastResult",
    "InAppAlert",
    "LLMCallLog",
    "LLMModelConfig",
    "LoginAttempt",
    "ModelVersion",
    "NewsArticle",
    "NewsSentimentDaily",
    "OAuthAccount",
    "PipelineRun",
    "PipelineWatermark",
    "Portfolio",
    "PortfolioHealthSnapshot",
    "PortfolioSnapshot",
    "Position",
    "RebalancingSuggestion",
    "RecommendationOutcome",
    "RecommendationSnapshot",
    "SignalSnapshot",
    "Stock",
    "StockIndex",
    "StockIndexMembership",
    "StockPrice",
    "TickerIngestionState",
    "ToolExecutionLog",
    "Transaction",
    "User",
    "UserPreference",
    "UserRole",
    "Watchlist",
]
