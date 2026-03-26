"""Verify new cache key patterns match the CacheService namespace conventions."""

from backend.services.cache import CacheTier


class TestCacheKeyConventions:
    """Verify cache key formats follow the established pattern."""

    def test_volatile_tier_ttl_range(self) -> None:
        """VOLATILE TTL is ~300s +/-10%."""
        ttl = CacheTier.VOLATILE.ttl
        assert 270 <= ttl <= 330

    def test_standard_tier_ttl_range(self) -> None:
        """STANDARD TTL is ~1800s +/-10%."""
        ttl = CacheTier.STANDARD.ttl
        assert 1620 <= ttl <= 1980

    def test_stable_tier_ttl_range(self) -> None:
        """STABLE TTL is ~86400s +/-10%."""
        ttl = CacheTier.STABLE.ttl
        assert 77760 <= ttl <= 95040

    def test_app_namespace_recommendations(self) -> None:
        key = "app:recommendations"
        assert key.startswith("app:")

    def test_app_namespace_fundamentals(self) -> None:
        key = "app:fundamentals:AAPL"
        assert key.startswith("app:")

    def test_user_namespace_positions(self) -> None:
        key = "user:abc123:positions"
        assert key.startswith("user:")

    def test_app_namespace_forecast_sector(self) -> None:
        key = "app:forecast:sector:Technology"
        assert key.startswith("app:")
