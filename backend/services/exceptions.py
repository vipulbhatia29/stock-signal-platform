"""Domain exceptions for the service layer.

Services raise these; callers (routers, tools, tasks) catch and translate
to their own error format (HTTPException, ToolResult, log + retry).
"""


class ServiceError(Exception):
    """Base exception for all service-layer errors."""


class StockNotFoundError(ServiceError):
    """Raised when a ticker is not in the stocks table."""

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"Stock not found: {ticker}")


class PortfolioNotFoundError(ServiceError):
    """Raised when a user has no portfolio."""

    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        super().__init__(f"Portfolio not found for user: {user_id}")


class DuplicateWatchlistError(ServiceError):
    """Raised when adding a ticker already on the watchlist."""

    def __init__(self, ticker: str) -> None:
        self.ticker = ticker
        super().__init__(f"Already on watchlist: {ticker}")


class IngestFailedError(ServiceError):
    """Raised when the ingest pipeline fails for a ticker."""

    def __init__(self, ticker: str, step: str) -> None:
        self.ticker = ticker
        self.step = step
        super().__init__(f"Ingest failed for {ticker} at step: {step}")
