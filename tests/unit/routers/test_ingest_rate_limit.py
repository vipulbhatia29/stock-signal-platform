"""Tests verifying rate limit decorator on ingest endpoint."""

from __future__ import annotations


class TestIngestRateLimitDecorator:
    """Verify the ingest endpoint has slowapi rate limiting configured."""

    def test_ingest_endpoint_registered_with_limiter(self) -> None:
        """The ingest_ticker function should be registered in the limiter's route limits."""
        from backend.rate_limit import limiter
        from backend.routers.stocks import search  # noqa: F401 — registers routes

        key = "backend.routers.stocks.search.ingest_ticker"
        assert key in limiter._route_limits, (
            "ingest_ticker is not registered in limiter._route_limits; "
            "missing @limiter.limit decorator"
        )

    def test_ingest_rate_limit_is_20_per_hour(self) -> None:
        """Rate limit should be 20 requests per hour."""
        from backend.rate_limit import limiter
        from backend.routers.stocks import search  # noqa: F401 — registers routes

        key = "backend.routers.stocks.search.ingest_ticker"
        limits = limiter._route_limits.get(key, [])
        assert limits, "No limits registered for ingest_ticker"
        limit_strings = [str(lim.limit) for lim in limits]
        assert any("20" in s and "hour" in s for s in limit_strings), (
            f"Expected '20/hour' limit on ingest_ticker, got: {limit_strings}"
        )
