"""HTTP observability middleware — emits REQUEST_LOG and API_ERROR_LOG events.

Sits INSIDE TraceIdMiddleware (uses trace_id set there).
Sits OUTSIDE ErrorHandlerMiddleware to capture both handled and unhandled errors.
Execution order: TraceId → ObsHttp → ErrorHandler → routes
"""

from __future__ import annotations

import hashlib
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.config import settings
from backend.observability.context import span_id_var, trace_id_var
from backend.observability.instrumentation.env_snapshot import collect_env_snapshot
from backend.observability.instrumentation.pii_redact import redact_message as _redact_message
from backend.observability.metrics.http_middleware import normalize_path
from backend.observability.schema.http_events import (
    ApiErrorLogEvent,
    ErrorType,
    RequestLogEvent,
)

logger = logging.getLogger(__name__)

# Paths excluded from request logging (high-frequency, low-value)
_EXCLUDED_PREFIXES = ("/api/v1/health", "/docs", "/openapi.json", "/obs/v1/events")


def _classify_error(status_code: int) -> ErrorType:
    """Map status code to ErrorType enum.

    Args:
        status_code: HTTP response status code.

    Returns:
        ErrorType classification for the given status code.
    """
    if status_code in (401, 403):
        return ErrorType.AUTH
    if status_code == 404:
        return ErrorType.NOT_FOUND
    if status_code == 422:
        return ErrorType.VALIDATION
    if status_code == 429:
        return ErrorType.RATE_LIMIT
    if status_code >= 500:
        return ErrorType.INTERNAL_SERVER
    return ErrorType.DOMAIN


class ObsHttpMiddleware(BaseHTTPMiddleware):
    """Emit REQUEST_LOG on every response and API_ERROR_LOG on 4xx/5xx.

    Middleware must never mask HTTP errors — all emissions happen in the
    finally block or after call_next, per spec constraint §HC-4.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize ObsHttpMiddleware.

        Args:
            app: The ASGI application to wrap.
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """Process a request and emit observability events.

        Args:
            request: The incoming HTTP request.
            call_next: Callable to pass the request to the next middleware/handler.

        Returns:
            The HTTP response from the downstream handler.
        """
        if not settings.OBS_ENABLED:
            return await call_next(request)

        # Skip excluded paths
        raw_path = request.url.path
        if any(raw_path.startswith(p) for p in _EXCLUDED_PREFIXES):
            return await call_next(request)

        start = time.monotonic()
        exc_captured: BaseException | None = None
        response: Response | None = None

        try:
            response = await call_next(request)
        except Exception as exc:
            exc_captured = exc
            raise
        finally:
            latency_ms = int((time.monotonic() - start) * 1000)
            self._emit_request_log(request, response, latency_ms, raw_path)
            if exc_captured or (response and response.status_code >= 400):
                self._emit_error_log(request, response, exc_captured, raw_path)

        return response

    def _emit_request_log(
        self,
        request: Request,
        response: Response | None,
        latency_ms: int,
        raw_path: str,
    ) -> None:
        """Emit a REQUEST_LOG event for this request.

        Args:
            request: The incoming HTTP request.
            response: The HTTP response (may be None if an exception was raised).
            latency_ms: Round-trip latency in milliseconds.
            raw_path: Original unmodified request path.
        """
        try:
            obs_client = getattr(request.app.state, "obs_client", None)
            if not obs_client:
                return

            trace_id = trace_id_var.get(None) or uuid.uuid4()
            span_id = span_id_var.get(None) or uuid.uuid4()
            normalized = normalize_path(raw_path) or raw_path
            status_code = response.status_code if response else 500

            # Capture user_id from request state if auth middleware set it
            user_id = getattr(request.state, "user_id", None) if hasattr(request, "state") else None

            event = RequestLogEvent(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                ts=datetime.now(timezone.utc),
                env=getattr(settings, "APP_ENV", "dev"),
                git_sha=getattr(settings, "GIT_SHA", None),
                user_id=user_id,
                session_id=None,
                query_id=None,
                method=request.method,
                path=normalized,
                raw_path=raw_path,
                status_code=status_code,
                latency_ms=latency_ms,
                request_bytes=int(request.headers.get("content-length", 0)) or None,
                ip_address=request.client.host if request.client else None,
                user_agent=(request.headers.get("user-agent", "") or "")[:500] or None,
                referer=request.headers.get("referer"),
                environment_snapshot=collect_env_snapshot(),
            )
            obs_client.emit_sync(event)
        except Exception:
            logger.warning("Failed to emit REQUEST_LOG", exc_info=True)

    def _emit_error_log(
        self,
        request: Request,
        response: Response | None,
        exc: BaseException | None,
        raw_path: str,
    ) -> None:
        """Emit an API_ERROR_LOG event for this error response.

        Stack traces are only captured for status_code >= 500 per spec constraint §HC-10.

        Args:
            request: The incoming HTTP request.
            response: The HTTP response (may be None if an exception was raised).
            exc: The exception that was raised, if any.
            raw_path: Original unmodified request path.
        """
        try:
            obs_client = getattr(request.app.state, "obs_client", None)
            if not obs_client:
                return

            trace_id = trace_id_var.get(None) or uuid.uuid4()
            span_id = span_id_var.get(None) or uuid.uuid4()
            status_code = response.status_code if response else 500
            user_id = getattr(request.state, "user_id", None) if hasattr(request, "state") else None

            stack_trace = None
            stack_hash = None
            exception_class = None
            if exc and status_code >= 500:
                raw_trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                stack_trace = raw_trace[:5120]  # Cap at 5KB
                stack_hash = hashlib.sha256(stack_trace.encode()).hexdigest()
                exception_class = type(exc).__qualname__

            event = ApiErrorLogEvent(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=None,
                ts=datetime.now(timezone.utc),
                env=getattr(settings, "APP_ENV", "dev"),
                git_sha=getattr(settings, "GIT_SHA", None),
                user_id=user_id,
                session_id=None,
                query_id=None,
                status_code=status_code,
                error_type=_classify_error(status_code),
                error_message=_redact_message(str(exc)[:500]) if exc else None,
                stack_trace=stack_trace,
                stack_hash=stack_hash,
                exception_class=exception_class,
            )
            obs_client.emit_sync(event)
        except Exception:
            logger.warning("Failed to emit API_ERROR_LOG", exc_info=True)
