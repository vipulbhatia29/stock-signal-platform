"""Application settings loaded from environment variables via Pydantic Settings."""

import logging
from datetime import timedelta
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_INSECURE_JWT_DEFAULT = "change-me-in-production"


class StalenessSLAs(BaseSettings):
    """Green-threshold freshness SLAs per pipeline stage.

    Yellow = 2x green. Red = >2x green. See services/ticker_state.py for
    the bucketing logic.

    Env-tunable: override any SLA via STALENESS_SLA_<FIELD>=<seconds>.
    Defaults are product decisions; override per-environment for tighter
    monitoring or relaxed staging thresholds.
    """

    model_config = SettingsConfigDict(
        env_prefix="STALENESS_SLA_",
        extra="ignore",
    )

    prices: timedelta = Field(default=timedelta(hours=4))
    signals: timedelta = Field(default=timedelta(hours=4))
    fundamentals: timedelta = Field(default=timedelta(hours=24))
    forecast: timedelta = Field(default=timedelta(hours=24))
    forecast_retrain: timedelta = Field(default=timedelta(days=14))
    news: timedelta = Field(default=timedelta(hours=6))
    sentiment: timedelta = Field(default=timedelta(hours=6))
    convergence: timedelta = Field(default=timedelta(hours=24))
    backtest: timedelta = Field(default=timedelta(days=7))
    recommendation: timedelta = Field(default=timedelta(hours=24))


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
    NEWS_SCORING_MAX_CONCURRENCY: int = 5  # max concurrent OpenAI batch requests

    # --- Backtesting ---
    BACKTEST_MIN_TRAIN_DAYS: int = 365
    BACKTEST_STEP_DAYS: int = 30
    BACKTEST_MIN_WINDOWS: int = 12

    # --- Black-Litterman ---
    BL_RISK_AVERSION: float = 3.07
    BL_MAX_VIEW_CONFIDENCE: float = 0.95

    # --- Monte Carlo ---
    MONTE_CARLO_SIMULATIONS: int = 10000

    # --- Feature Flags (rollback kill-switches for Spec B pipeline stages) ---
    CONVERGENCE_SNAPSHOT_ENABLED: bool = True
    BACKTEST_ENABLED: bool = True
    PROPHET_REAL_SENTIMENT_ENABLED: bool = True
    # Spec C.6 — auto-ingest on watchlist add (kill-switch: set False to revert to 404 behaviour)
    WATCHLIST_AUTO_INGEST: bool = True
    # NEWS_SCORING_MAX_CONCURRENCY controls concurrency (added in B4.2, see above)

    # --- Pipeline ---
    INTRADAY_REFRESH_CONCURRENCY: int = 5  # Spec E.3 — semaphore bound on fast path (= pool_size)
    PIPELINE_FAILURE_MODE: str = "continue"

    # --- Admin Seed ---
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: str = ""

    # --- Langfuse (optional — tracing + assessment) ---
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_BASEURL: str = "http://localhost:3001"

    # --- Spec D — Langfuse task tracking (non-agent paths) ---
    # Global kill switch for @tracked_task → Langfuse trace creation.
    # This flag is dead config in KAN-420 PR1 — it lands here so operators
    # can pre-configure environments, but enforcement ships with the
    # `@tracked_task` adoption in KAN-420 PR1.5. Once enforced, False will
    # cause `@tracked_task` to still write the PipelineRunner row (DB) but
    # skip Langfuse wiring. Also ignored when `LANGFUSE_SECRET_KEY` is
    # unset — `trace_task`'s no-op path (create_trace returning None) is
    # the governing behavior in that case.
    LANGFUSE_TRACK_TASKS: bool = True
    # Sampling rate for including prompt/response text in sentiment
    # generation spans. Defaults to 25% to bound Langfuse storage cost.
    # Bounds are enforced at Settings construction time: values outside
    # [0.0, 1.0] will raise at boot rather than silently mis-sampling.
    LANGFUSE_SENTIMENT_IO_SAMPLING_RATE: float = Field(default=0.25, ge=0.0, le=1.0)

    # --- Observability SDK (Obs 1a PR2a) ---
    OBS_ENABLED: bool = Field(
        default=True,
        description="Global kill switch — False makes all emit calls no-ops",
    )
    OBS_SPOOL_ENABLED: bool = Field(
        default=True,
        description="If True, overflow events go to OBS_SPOOL_DIR; else drop",
    )
    OBS_SPOOL_DIR: str = Field(
        default="/var/tmp/obs-spool",
        description="Per-worker append-only JSONL spool directory",
    )
    OBS_SPOOL_MAX_SIZE_MB: int = Field(default=100, ge=1, description="Per-worker spool cap")
    OBS_TARGET_TYPE: Literal["direct", "memory", "internal_http"] = Field(
        default="direct",
        description="Target adapter — direct DB write (default), self-HTTP, or memory (tests)",
    )
    OBS_TARGET_URL: str | None = Field(
        default=None,
        description="Base URL for internal_http / future external_http target. "
        "Required when OBS_TARGET_TYPE=internal_http.",
    )
    OBS_INGEST_SECRET: str | None = Field(
        default=None,
        description="Shared secret for POST /obs/v1/events X-Obs-Secret header. "
        "Required when OBS_TARGET_TYPE=internal_http; set via env in prod.",
    )
    OBS_FLUSH_INTERVAL_MS: int = Field(default=500, ge=50)
    OBS_BUFFER_SIZE: int = Field(default=10_000, ge=100)

    @field_validator("OBS_INGEST_SECRET")
    @classmethod
    def _secret_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and len(v) == 0:
            raise ValueError("OBS_INGEST_SECRET must not be empty string")
        return v

    @property
    def staleness_slas(self) -> StalenessSLAs:
        """Return env-tunable staleness SLAs (cached after first access).

        Override via STALENESS_SLA_PRICES=<seconds> etc. in .env or environment.
        """
        if not hasattr(self, "_staleness_slas_cache"):
            object.__setattr__(self, "_staleness_slas_cache", StalenessSLAs())
        return self._staleness_slas_cache  # type: ignore[return-value]

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    def validate_production_settings(self) -> None:
        """Validate security-critical settings.

        Raises ValueError in ALL environments if JWT secret is the insecure
        default or empty — the app must never start with a known secret.
        Raises RuntimeError in production/staging if COOKIE_SECURE is disabled.
        """
        if self.JWT_SECRET_KEY == _INSECURE_JWT_DEFAULT or not self.JWT_SECRET_KEY.strip():
            raise ValueError(
                "JWT_SECRET_KEY is using the insecure default or is empty. "
                "Set a strong secret (32+ chars) via environment variable or backend/.env. "
                "The application cannot start without a secure JWT secret."
            )

        is_prod = self.ENVIRONMENT in ("production", "staging")
        if not self.COOKIE_SECURE and is_prod:
            raise RuntimeError("COOKIE_SECURE must be True in production (requires HTTPS).")


settings = Settings()
settings.validate_production_settings()
