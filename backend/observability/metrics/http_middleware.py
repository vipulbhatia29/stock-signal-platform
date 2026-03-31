"""Redis-backed HTTP request metrics middleware.

Tracks request counts, latency percentiles, and error rates using a
sliding-window approach backed by Redis hashes and sorted sets.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path normalisation
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_NUMERIC_RE = re.compile(r"^\d+$")
_TICKER_RE = re.compile(r"^[A-Z]{1,5}$")

_EXCLUDED_PREFIXES = (
    "/api/v1/admin/command-center",
    "/api/v1/health",
)


def normalize_path(path: str) -> str | None:
    """Normalize a request path for metric aggregation.

    Replaces UUIDs with ``{id}``, numeric segments with ``{num}``, and
    uppercase 1-5 char segments (tickers) with ``{param}``.

    Returns ``None`` for paths that should be excluded from metrics
    collection (admin command-center, health checks).
    """
    # Only track API paths — ignore static files, docs, etc.
    if not path.startswith("/api/"):
        return None

    for prefix in _EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return None

    # Replace UUIDs first (before splitting on /)
    path = _UUID_RE.sub("{id}", path)

    segments = path.split("/")
    normalised: list[str] = []
    for seg in segments:
        if seg == "{id}":
            normalised.append(seg)
        elif _NUMERIC_RE.match(seg):
            normalised.append("{num}")
        elif _TICKER_RE.match(seg):
            normalised.append("{param}")
        else:
            normalised.append(seg)
    return "/".join(normalised)


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------
class HttpMetricsCollector:
    """Redis-backed HTTP metrics with a sliding window.

    Stores request counts in Redis hashes and latency samples in a
    sorted set keyed by timestamp for efficient percentile computation.
    """

    # Redis key names
    _KEY_COUNT = "http_metrics:count"
    _KEY_LATENCY = "http_metrics:latency"
    _KEY_ERRORS = "http_metrics:errors"
    _KEY_TODAY = "http_metrics:today"
    _KEY_TODAY_ERR = "http_metrics:today_err"

    def __init__(self, redis: Redis, window_seconds: int = 300) -> None:
        self._redis = redis
        self._window = window_seconds

    async def record(self, method: str, path: str, status: int, latency_ms: float) -> None:
        """Record a single HTTP request (fire-and-forget).

        Writes to Redis via pipeline. Errors are logged at debug level
        and never raised.
        """
        try:
            now = time.time()
            field = f"{method}:{path}:{status}"
            member = f"{uuid.uuid4().hex[:12]}:{latency_ms:.2f}"

            pipe = self._redis.pipeline(transaction=False)
            pipe.hincrby(self._KEY_COUNT, field, 1)
            pipe.zadd(self._KEY_LATENCY, {member: now})
            pipe.incr(self._KEY_TODAY)

            if status >= 400:
                pipe.hincrby(self._KEY_ERRORS, field, 1)
                pipe.incr(self._KEY_TODAY_ERR)

            await pipe.execute()
        except Exception:
            logger.debug("Failed to record HTTP metrics", exc_info=True)

    async def get_stats(self) -> dict:
        """Return aggregated metrics for the current sliding window.

        Returns a dict with ``rps_avg``, ``latency_p50`` / ``p95`` /
        ``p99`` (``None`` when fewer than 20 samples), ``error_rate_pct``,
        ``total_requests_today``, ``total_errors_today``, and
        ``top_endpoints``.
        """
        try:
            now = time.time()
            window_start = now - self._window

            # Prune entries outside the window
            await self._redis.zremrangebyscore(self._KEY_LATENCY, "-inf", window_start)

            # Gather window data
            raw_members = await self._redis.zrangebyscore(
                self._KEY_LATENCY, window_start, "+inf", withscores=False
            )

            latencies: list[float] = []
            for m in raw_members:
                member_str = m if isinstance(m, str) else m.decode()
                try:
                    latencies.append(float(member_str.split(":")[1]))
                except (IndexError, ValueError):
                    continue

            sample_count = len(latencies)
            rps_avg = round(sample_count / self._window, 2) if self._window else 0

            # Percentiles (null when < 20 samples)
            if sample_count >= 20:
                latencies.sort()
                p50 = round(latencies[int(sample_count * 0.50)], 2)
                p95 = round(latencies[int(sample_count * 0.95)], 2)
                p99 = round(latencies[min(int(sample_count * 0.99), sample_count - 1)], 2)
            else:
                p50 = p95 = p99 = None

            # Error rate from count/errors hashes
            count_hash = await self._redis.hgetall(self._KEY_COUNT)
            error_hash = await self._redis.hgetall(self._KEY_ERRORS)

            total_count = sum(
                int(v if isinstance(v, (int, str)) else v.decode()) for v in count_hash.values()
            )
            total_errors = sum(
                int(v if isinstance(v, (int, str)) else v.decode()) for v in error_hash.values()
            )
            error_rate_pct = round((total_errors / total_count) * 100, 2) if total_count else 0.0

            # Top endpoints (top 10 by count)
            endpoint_counts: dict[str, int] = {}
            for k, v in count_hash.items():
                key_str = k if isinstance(k, str) else k.decode()
                val_int = int(v if isinstance(v, (int, str)) else v.decode())
                # key_str is "METHOD:path:status" — group by "METHOD:path"
                parts = key_str.rsplit(":", 1)
                ep = parts[0] if len(parts) == 2 else key_str
                endpoint_counts[ep] = endpoint_counts.get(ep, 0) + val_int

            top_endpoints = sorted(endpoint_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            # Daily totals
            today_raw = await self._redis.get(self._KEY_TODAY)
            today_err_raw = await self._redis.get(self._KEY_TODAY_ERR)
            total_today = int(today_raw) if today_raw else 0
            total_today_err = int(today_err_raw) if today_err_raw else 0

            return {
                "window_seconds": self._window,
                "sample_count": sample_count,
                "rps_avg": rps_avg,
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "latency_p99_ms": p99,
                "error_rate_pct": error_rate_pct,
                "total_requests_today": total_today,
                "total_errors_today": total_today_err,
                "top_endpoints": [{"endpoint": ep, "count": cnt} for ep, cnt in top_endpoints],
            }
        except Exception:
            logger.debug("Failed to get HTTP metrics stats", exc_info=True)
            return {
                "window_seconds": self._window,
                "sample_count": 0,
                "rps_avg": 0,
                "latency_p50_ms": None,
                "latency_p95_ms": None,
                "latency_p99_ms": None,
                "error_rate_pct": 0.0,
                "total_requests_today": 0,
                "total_errors_today": 0,
                "top_endpoints": [],
            }


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class HttpMetricsMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that records per-request HTTP metrics.

    Reads the ``HttpMetricsCollector`` from ``request.app.state.http_metrics``.
    Gracefully no-ops when the collector is not yet initialised (e.g. during
    startup before lifespan completes).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Measure request latency and dispatch to the collector."""
        collector: HttpMetricsCollector | None = getattr(request.app.state, "http_metrics", None)
        if collector is None:
            return await call_next(request)

        path = normalize_path(request.url.path)
        if path is None:
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        latency_ms = (time.monotonic() - start) * 1000

        asyncio.create_task(
            collector.record(request.method, path, response.status_code, latency_ms)
        )
        return response
