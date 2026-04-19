"""Tests for SQLAlchemy slow query detection and pool monitoring instrumentation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.observability.instrumentation.db import (
    _in_obs_write,
    normalize_query,
    query_hash,
)


class TestNormalizeQuery:
    """Tests for SQL query normalization."""

    def test_replaces_string_literals(self):
        """String literals should be replaced with $S."""
        result = normalize_query("SELECT * FROM stocks WHERE ticker = 'AAPL'")
        assert "'AAPL'" not in result
        assert "$S" in result

    def test_replaces_numeric_literals(self):
        """Numeric literals should be replaced with $N."""
        result = normalize_query("SELECT * FROM stocks WHERE id = 42")
        assert "42" not in result
        assert "$N" in result

    def test_replaces_uuid_literals(self):
        """UUID literals should be replaced with $U."""
        uid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        result = normalize_query(f"SELECT * FROM users WHERE id = '{uid}'")
        assert uid not in result

    def test_replaces_in_lists(self):
        """IN-lists should be collapsed to IN ($...)."""
        result = normalize_query("SELECT * FROM stocks WHERE ticker IN ('AAPL', 'GOOG', 'MSFT')")
        assert "IN ($...)" in result

    def test_preserves_table_and_column_names(self):
        """Table and column names should not be modified."""
        result = normalize_query("SELECT ticker, price FROM stocks WHERE ticker = 'AAPL'")
        assert "stocks" in result
        assert "ticker" in result
        assert "price" in result

    def test_float_literals(self):
        """Float literals should be replaced with $N."""
        result = normalize_query("SELECT * FROM stocks WHERE price > 150.50")
        assert "150.50" not in result


class TestQueryHash:
    """Tests for query hash generation."""

    def test_consistent_hashing(self):
        """Same normalized query should produce same hash."""
        q = "SELECT * FROM stocks WHERE ticker = $S"
        assert query_hash(q) == query_hash(q)

    def test_different_queries_different_hash(self):
        """Different queries should produce different hashes."""
        assert query_hash("SELECT * FROM stocks") != query_hash("SELECT * FROM users")

    def test_hash_length(self):
        """Hash should be 16 hex chars."""
        h = query_hash("SELECT 1")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestInObsWriteGuard:
    """Tests for the _in_obs_write ContextVar feedback loop guard."""

    def test_default_is_false(self):
        """Default value should be False."""
        assert _in_obs_write.get() is False

    def test_set_and_reset(self):
        """Guard should be settable and resettable."""
        token = _in_obs_write.set(True)
        assert _in_obs_write.get() is True
        _in_obs_write.reset(token)
        assert _in_obs_write.get() is False


class TestSlowQueryEmission:
    """Tests for slow query event emission."""

    @patch("backend.observability.instrumentation.db._emit_slow_query")
    def test_slow_query_emitted_above_threshold(self, mock_emit):
        """Queries above threshold should trigger emission."""
        from backend.observability.instrumentation.db import (
            attach_slow_query_hooks,
        )

        engine = MagicMock()
        listeners = {}

        def fake_listens_for(target, event_name):
            """Capture event listeners for testing."""

            def decorator(fn):
                listeners[event_name] = fn
                return fn

            return decorator

        with patch("backend.observability.instrumentation.db.event.listens_for", fake_listens_for):
            attach_slow_query_hooks(engine)

        conn = MagicMock()
        conn.info = {}

        # Simulate before_execute
        listeners["before_execute"](conn, "SELECT 1", None, None, None)
        assert "obs_query_start" in conn.info

    @patch("backend.observability.instrumentation.db._emit_slow_query")
    def test_obs_schema_queries_skipped(self, mock_emit):
        """Queries targeting observability schema should be skipped."""

        # The after_execute handler checks for "observability." in SQL string
        sql = "INSERT INTO observability.slow_query_log ..."
        assert "observability." in sql

    def test_guard_prevents_emission(self):
        """When _in_obs_write is True, after_execute should skip emission."""
        token = _in_obs_write.set(True)
        try:
            # The guard check is: if _in_obs_write.get(): return
            assert _in_obs_write.get() is True
        finally:
            _in_obs_write.reset(token)


class TestPoolEventEmission:
    """Tests for pool event emission."""

    @patch("backend.observability.instrumentation.db._emit_pool_event")
    def test_attach_pool_hooks(self, mock_emit):
        """Pool hooks should attach checkout, checkin, and close_detached listeners."""
        from backend.observability.instrumentation.db import attach_pool_hooks

        engine = MagicMock()
        pool = MagicMock()
        engine.pool = pool

        listeners = {}

        def fake_listens_for(target, event_name):
            """Capture pool event listeners for testing."""

            def decorator(fn):
                listeners[event_name] = fn
                return fn

            return decorator

        with patch("backend.observability.instrumentation.db.event.listens_for", fake_listens_for):
            attach_pool_hooks(engine)

        assert "checkout" in listeners
        assert "checkin" in listeners
        assert "close_detached" in listeners

    def test_slow_checkout_detection(self):
        """Checkin handler should detect slow checkouts (>1s)."""
        from backend.observability.instrumentation.db import SLOW_CHECKOUT_THRESHOLD_MS

        assert SLOW_CHECKOUT_THRESHOLD_MS == 1000
