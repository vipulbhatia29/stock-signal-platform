"""Application settings loaded from environment variables via Pydantic Settings."""

import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_JWT_DEFAULT = "change-me-in-production"


class Settings(BaseSettings):
    """Application configuration.

    Loads from backend/.env file and environment variables.
    Environment variables take precedence over .env values.
    """

    model_config = SettingsConfigDict(
        env_file="backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Required ---
    DATABASE_URL: str = "postgresql+asyncpg://stocksignal:stocksignal@localhost:5432/stocksignal"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET_KEY: str = _INSECURE_JWT_DEFAULT
    JWT_ALGORITHM: str = "HS256"

    # --- Auth ---
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    COOKIE_SECURE: bool = False  # Set True in production (requires HTTPS)

    # --- Environment ---
    ENVIRONMENT: str = "development"  # development | staging | production

    # --- App ---
    CORS_ORIGINS: str = "http://localhost:3000"
    RATE_LIMIT_PER_MINUTE: int = 60
    USER_TIMEZONE: str = "America/New_York"

    # --- Optional API Keys ---
    ANTHROPIC_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    SERPAPI_API_KEY: str = ""
    FRED_API_KEY: str = ""
    ALPHA_VANTAGE_API_KEY: str = ""
    FINNHUB_API_KEY: str = ""

    # --- OIDC (Langfuse SSO) ---
    OIDC_CLIENT_ID: str = "stock-signal-langfuse"
    OIDC_CLIENT_SECRET: str = ""  # Empty = OIDC disabled; set in .env
    # Comma-separated whitelist of allowed OIDC redirect URIs
    OIDC_REDIRECT_URIS: str = "http://localhost:3001/api/auth/callback/custom"

    # --- Google OAuth ---
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8181/api/v1/auth/google/callback"

    # --- Email (Resend) ---
    RESEND_API_KEY: str = ""
    EMAIL_FROM_ADDRESS: str = "noreply@stocksignal.app"
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # --- Agent ---
    MCP_TOOLS: bool = True  # MCP stdio transport for agent tool calls (kill switch: set False)
    MAX_TOOL_RESULT_CHARS: int = 3000  # Truncate tool results before synthesis
    REACT_AGENT: bool = True  # Use ReAct loop instead of Plan→Execute→Synthesize pipeline

    # --- Database Pool ---
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE: int = 3600  # seconds — prevents stale connections

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    # --- News Sources ---
    EDGAR_USER_AGENT: str = "StockSignalPlatform admin@example.com"

    # --- Sentiment Scoring ---
    NEWS_SCORING_MODEL: str = "gpt-4o-mini"
    NEWS_SCORING_FALLBACK: str = "groq"
    NEWS_INGEST_LOOKBACK_HOURS: int = 6
    NEWS_MIN_ARTICLES_FOR_SCORE: int = 1

    # --- Backtesting ---
    BACKTEST_MIN_TRAIN_DAYS: int = 365
    BACKTEST_STEP_DAYS: int = 30
    BACKTEST_MIN_WINDOWS: int = 12

    # --- Black-Litterman ---
    BL_RISK_AVERSION: float = 3.07
    BL_MAX_VIEW_CONFIDENCE: float = 0.95

    # --- Monte Carlo ---
    MONTE_CARLO_SIMULATIONS: int = 10000

    # --- Pipeline ---
    PIPELINE_FAILURE_MODE: str = "continue"

    # --- Admin Seed ---
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # --- Langfuse (optional — tracing + assessment) ---
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_BASEURL: str = "http://localhost:3001"

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    def validate_production_settings(self) -> None:
        """Validate security-critical settings.

        Raises RuntimeError in production if JWT secret is the default
        or COOKIE_SECURE is disabled. Logs warnings in development.
        """
        is_prod = self.ENVIRONMENT in ("production", "staging")

        if self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT:
            msg = (
                "JWT_SECRET_KEY is using the insecure default. "
                "Set a strong secret (32+ chars) via environment variable."
            )
            if is_prod:
                raise RuntimeError(msg)
            logger.warning(msg)

        if not self.COOKIE_SECURE and is_prod:
            raise RuntimeError("COOKIE_SECURE must be True in production (requires HTTPS).")


settings = Settings()
settings.validate_production_settings()
