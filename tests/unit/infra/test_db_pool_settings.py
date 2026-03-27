"""Tests for database pool configuration settings."""

from unittest.mock import patch

from backend.config import Settings


class TestDbPoolSettings:
    """Verify DB pool settings have correct defaults and are overridable."""

    def test_default_pool_size(self) -> None:
        """Default pool size is 5."""
        s = Settings()
        assert s.DB_POOL_SIZE == 5

    def test_default_max_overflow(self) -> None:
        """Default max overflow is 10."""
        s = Settings()
        assert s.DB_MAX_OVERFLOW == 10

    def test_default_pool_recycle(self) -> None:
        """Default pool recycle is 3600 seconds."""
        s = Settings()
        assert s.DB_POOL_RECYCLE == 3600

    def test_pool_settings_overridable_via_env(self) -> None:
        """Pool settings can be overridden via environment variables."""
        with patch.dict(
            "os.environ",
            {
                "DB_POOL_SIZE": "20",
                "DB_MAX_OVERFLOW": "40",
                "DB_POOL_RECYCLE": "1800",
            },
        ):
            s = Settings()
            assert s.DB_POOL_SIZE == 20
            assert s.DB_MAX_OVERFLOW == 40
            assert s.DB_POOL_RECYCLE == 1800
