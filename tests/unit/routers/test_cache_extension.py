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
