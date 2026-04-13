"""Domain exceptions for the service layer.

Services raise these; callers (routers, tools, tasks) catch and translate
to their own error format (HTTPException, ToolResult, log + retry).

All classes inherit from DomainError so ErrorHandlerMiddleware can catch
them automatically when they propagate out of a router unhandled.
"""

from backend.exceptions import DomainError


class ServiceError(DomainError):
    """Base exception for all service-layer errors."""

    status_code = 500
    safe_message = "A service error occurred."


class StockNotFoundError(ServiceError):
    """Raised when a ticker is not in the stocks table (404)."""

    status_code = 404
    safe_message = "Stock not found."

    def __init__(self, ticker: str) -> None:
        """Initialise with the missing ticker symbol.

        Args:
            ticker: The ticker symbol that was not found.
        """
        self.ticker = ticker
        # Call DomainError.__init__ with a safe message (not str(exc))
        super().__init__(f"Stock not found: {ticker}")


class PortfolioNotFoundError(ServiceError):
    """Raised when a user has no portfolio (404)."""

    status_code = 404
    safe_message = "Portfolio not found."

    def __init__(self, user_id: str) -> None:
        """Initialise with the user ID whose portfolio is missing.

        Args:
            user_id: The user whose portfolio was not found.
        """
        self.user_id = user_id
        super().__init__(f"Portfolio not found for user: {user_id}")


class DuplicateWatchlistError(ServiceError):
    """Raised when adding a ticker already on the watchlist (409)."""

    status_code = 409
    safe_message = "Ticker already on watchlist."

    def __init__(self, ticker: str) -> None:
        """Initialise with the duplicate ticker symbol.

        Args:
            ticker: The ticker that is already on the watchlist.
        """
        self.ticker = ticker
        super().__init__(f"Already on watchlist: {ticker}")


class IngestFailedError(ServiceError):
    """Raised when the ingest pipeline fails for a ticker (404)."""

    status_code = 404
    safe_message = "Failed to fetch price data."

    def __init__(self, ticker: str, step: str) -> None:
        """Initialise with the failed ticker and pipeline step.

        Args:
            ticker: The ticker symbol that failed to ingest.
            step: The pipeline step where the failure occurred.
        """
        self.ticker = ticker
        self.step = step
        super().__init__(f"Ingest failed for {ticker} at step: {step}")


class IngestInProgressError(ServiceError):
    """Another caller is already ingesting this ticker."""

    status_code = 409
    safe_message = "Ingestion already in progress for this ticker, please retry shortly."

    def __init__(self, ticker: str) -> None:
        """Initialise with the ticker being ingested.

        Args:
            ticker: The ticker symbol that is currently being ingested.
        """
        super().__init__(f"Ingestion in progress for {ticker}")
        self.ticker = ticker
