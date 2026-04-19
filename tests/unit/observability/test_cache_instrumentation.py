"""Tests for cache operation instrumentation — sampling, key redaction, emission."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.observability.instrumentation.cache import (
    SAMPLE_RATE,
    _emit_cache_op,
    observe_cache_delete,
    observe_cache_error,
    observe_cache_get,
    observe_cache_set,
    redact_key,
)


class TestRedactKey:
    """Tests for cache key redaction."""

    def test_redacts_uuid(self):
        """UUID segments in cache keys should be redacted."""
        key = "user:a1b2c3d4-e5f6-7890-abcd-ef1234567890:profile"
        result = redact_key(key)
        assert "a1b2c3d4" not in result
        assert "user:" in result
        assert ":profile" in result

    def test_redacts_hex_ids(self):
        """Long hex strings should be redacted."""
        key = "app:signals:abcdef12"
        result = redact_key(key)
        assert "abcdef12" not in result
        assert "app:signals:" in result

    def test_redacts_numeric_ids(self):
        """Numeric IDs between colons should be redacted."""
        key = "session:12345:data"
        result = redact_key(key)
        assert "12345" not in result
        assert "session:" in result
        assert ":data" in result

    def test_preserves_namespace(self):
        """Namespace prefix should be preserved."""
        key = "app:price:AAPL"
        result = redact_key(key)
        assert "app:price:" in result

    def test_short_keys_unchanged(self):
        """Short non-sensitive keys should not be modified."""
        key = "app:health"
        result = redact_key(key)
        assert result == "app:health"


class TestSampling:
    """Tests for cache operation sampling."""

    def test_sample_rate_is_one_percent(self):
        """Sample rate should be 1%."""
        assert SAMPLE_RATE == 0.01

    @patch("backend.observability.instrumentation.cache._emit_cache_op")
    @patch("backend.observability.instrumentation.cache.random.random", return_value=0.005)
    def test_get_sampled_when_below_rate(self, mock_random, mock_emit):
        """GET operations should emit when random < SAMPLE_RATE."""
        observe_cache_get("test:key", "value", 2)
        mock_emit.assert_called_once_with("get", "test:key", hit=True, latency_ms=2)

    @patch("backend.observability.instrumentation.cache._emit_cache_op")
    @patch("backend.observability.instrumentation.cache.random.random", return_value=0.5)
    def test_get_not_sampled_when_above_rate(self, mock_random, mock_emit):
        """GET operations should not emit when random >= SAMPLE_RATE."""
        observe_cache_get("test:key", "value", 2)
        mock_emit.assert_not_called()

    @patch("backend.observability.instrumentation.cache._emit_cache_op")
    @patch("backend.observability.instrumentation.cache.random.random", return_value=0.005)
    def test_get_miss_recorded(self, mock_random, mock_emit):
        """Cache miss (result=None) should be recorded as hit=False."""
        observe_cache_get("test:key", None, 3)
        mock_emit.assert_called_once_with("get", "test:key", hit=False, latency_ms=3)

    @patch("backend.observability.instrumentation.cache._emit_cache_op")
    @patch("backend.observability.instrumentation.cache.random.random", return_value=0.005)
    def test_set_sampled(self, mock_random, mock_emit):
        """SET operations should emit with value_bytes and ttl_seconds."""
        observe_cache_set("test:key", "hello", 300, 5)
        mock_emit.assert_called_once_with(
            "set",
            "test:key",
            latency_ms=5,
            value_bytes=5,
            ttl_seconds=300,
        )

    @patch("backend.observability.instrumentation.cache._emit_cache_op")
    @patch("backend.observability.instrumentation.cache.random.random", return_value=0.005)
    def test_delete_sampled(self, mock_random, mock_emit):
        """DELETE operations should emit when sampled."""
        observe_cache_delete("test:key", 1)
        mock_emit.assert_called_once_with("delete", "test:key", latency_ms=1)

    @patch("backend.observability.instrumentation.cache._emit_cache_op")
    def test_error_always_emitted(self, mock_emit):
        """Error operations should always emit (no sampling)."""
        observe_cache_error("get", "test:key", 5000)
        mock_emit.assert_called_once_with(
            "get", "test:key", latency_ms=5000, error_reason="connection_error"
        )


class TestEmitCacheOp:
    """Tests for the _emit_cache_op helper."""

    @patch("backend.observability.bootstrap._maybe_get_obs_client", return_value=None)
    def test_noop_when_no_client(self, mock_client):
        """Should silently no-op when obs client is not available."""
        # Should not raise
        _emit_cache_op("get", "test:key", latency_ms=1)

    @patch("backend.observability.bootstrap._maybe_get_obs_client")
    def test_emits_event_with_redacted_key(self, mock_get_client):
        """Should emit event with redacted key pattern."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        _emit_cache_op(
            "get",
            "user:a1b2c3d4-e5f6-7890-abcd-ef1234567890:profile",
            hit=True,
            latency_ms=2,
        )

        mock_client.emit_sync.assert_called_once()
        event = mock_client.emit_sync.call_args[0][0]
        assert "a1b2c3d4" not in event.key_pattern
        assert event.hit is True
        assert event.latency_ms == 2
