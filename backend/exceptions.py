"""Domain exceptions for the application layer.

DomainError is the base class for all domain-level exceptions.
The ErrorHandlerMiddleware catches these and returns safe JSON responses.

Services raise ServiceError subclasses (in backend.services.exceptions).
ServiceError now inherits from DomainError so middleware catches both.

Usage::

    raise StockNotFoundError("AAPL")  # → 404
    raise ResourceNotFoundError("No backtest found for ticker")  # → 404
    raise ValidationError("Invalid ticker format")  # → 422
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level exceptions.

    Attributes:
        status_code: HTTP status code to return to the client.
        safe_message: User-facing message safe to expose (no stack traces,
            no internal paths, no ``str(exc)`` leakage).
    """

    status_code: int = 500
    safe_message: str = "An unexpected error occurred."

    def __init__(self, safe_message: str | None = None) -> None:
        """Initialise with an optional override for the safe message.

        Args:
            safe_message: Override the class-level default. Pass ``None``
                to use the class default.
        """
        if safe_message is not None:
            self.safe_message = safe_message
        super().__init__(self.safe_message)


class ResourceNotFoundError(DomainError):
    """Raised when a requested resource does not exist (404)."""

    status_code = 404
    safe_message = "Resource not found."

    def __init__(self, safe_message: str = "Resource not found.") -> None:
        """Initialise with an optional custom not-found message.

        Args:
            safe_message: Caller-supplied user-facing detail.
        """
        super().__init__(safe_message)


class ValidationError(DomainError):
    """Raised when input fails domain validation (422)."""

    status_code = 422
    safe_message = "Invalid input."

    def __init__(self, safe_message: str = "Invalid input.") -> None:
        """Initialise with an optional custom validation message.

        Args:
            safe_message: Caller-supplied user-facing detail.
        """
        super().__init__(safe_message)


class ConflictError(DomainError):
    """Raised when an action conflicts with existing state (409)."""

    status_code = 409
    safe_message = "Conflict with existing resource."

    def __init__(self, safe_message: str = "Conflict with existing resource.") -> None:
        """Initialise with an optional custom conflict message.

        Args:
            safe_message: Caller-supplied user-facing detail.
        """
        super().__init__(safe_message)


class ServiceUnavailableError(DomainError):
    """Raised when a downstream service is unavailable (503)."""

    status_code = 503
    safe_message = "Service temporarily unavailable."

    def __init__(self, safe_message: str = "Service temporarily unavailable.") -> None:
        """Initialise with an optional custom unavailability message.

        Args:
            safe_message: Caller-supplied user-facing detail.
        """
        super().__init__(safe_message)
