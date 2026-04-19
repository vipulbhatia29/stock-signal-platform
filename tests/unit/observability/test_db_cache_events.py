"""Tests for DB + Cache layer event schemas (1b PR3)."""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.observability.schema.db_cache_events import (
    CacheOperationEvent,
    CacheOperationType,
    DbPoolEvent,
    DbPoolEventType,
    MigrationStatus,
    SchemaMigrationEvent,
    SlowQueryEvent,
)
from backend.observability.schema.v1 import EventType


def _base_fields() -> dict:
    """Return a valid base event payload."""
    return {
        "trace_id": uuid.uuid4(),
        "span_id": uuid.uuid4(),
        "parent_span_id": None,
        "ts": datetime.now(timezone.utc),
        "env": "dev",
        "git_sha": "abc123",
        "user_id": None,
        "session_id": None,
        "query_id": None,
    }


class TestSlowQueryEvent:
    """Tests for SlowQueryEvent schema."""

    def test_valid_event(self):
        """SlowQueryEvent should parse with required fields and correct event_type."""
        e = SlowQueryEvent(
            **_base_fields(),
            query_text="SELECT * FROM stocks WHERE ticker = $1",
            query_hash="a1b2c3",
            duration_ms=1200,
        )
        assert e.event_type == EventType.SLOW_QUERY
        assert e.duration_ms == 1200
        assert e.query_hash == "a1b2c3"
        assert e.rows_affected is None

    def test_with_optional_fields(self):
        """SlowQueryEvent should accept optional source location fields."""
        e = SlowQueryEvent(
            **_base_fields(),
            query_text="INSERT INTO prices ...",
            query_hash="d4e5f6",
            duration_ms=800,
            rows_affected=42,
            source_file="backend/services/data.py",
            source_line=123,
        )
        assert e.rows_affected == 42
        assert e.source_file == "backend/services/data.py"
        assert e.source_line == 123

    def test_missing_required_field(self):
        """SlowQueryEvent should reject missing query_text."""
        with pytest.raises(ValidationError):
            SlowQueryEvent(
                **_base_fields(),
                query_hash="abc",
                duration_ms=500,
            )

    def test_ts_must_be_tz_aware(self):
        """SlowQueryEvent should reject naive datetime."""
        fields = _base_fields()
        fields["ts"] = datetime(2026, 1, 1)  # naive
        with pytest.raises(ValidationError, match="tz-aware"):
            SlowQueryEvent(
                **fields,
                query_text="SELECT 1",
                query_hash="abc",
                duration_ms=500,
            )


class TestDbPoolEvent:
    """Tests for DbPoolEvent schema."""

    def test_valid_event(self):
        """DbPoolEvent should parse with required fields and correct event_type."""
        e = DbPoolEvent(
            **_base_fields(),
            pool_event_type=DbPoolEventType.EXHAUSTED,
            pool_size=10,
            checked_out=10,
            overflow=5,
        )
        assert e.event_type == EventType.DB_POOL_EVENT
        assert e.pool_event_type == DbPoolEventType.EXHAUSTED
        assert e.duration_ms is None

    def test_slow_checkout_with_duration(self):
        """DbPoolEvent should accept duration_ms for slow_checkout events."""
        e = DbPoolEvent(
            **_base_fields(),
            pool_event_type=DbPoolEventType.SLOW_CHECKOUT,
            pool_size=10,
            checked_out=8,
            overflow=2,
            duration_ms=1500,
        )
        assert e.duration_ms == 1500

    def test_all_event_types(self):
        """All DbPoolEventType values should be valid."""
        for evt_type in DbPoolEventType:
            e = DbPoolEvent(
                **_base_fields(),
                pool_event_type=evt_type,
                pool_size=5,
                checked_out=3,
                overflow=0,
            )
            assert e.pool_event_type == evt_type


class TestSchemaMigrationEvent:
    """Tests for SchemaMigrationEvent schema."""

    def test_valid_success_event(self):
        """SchemaMigrationEvent should parse a successful migration."""
        e = SchemaMigrationEvent(
            **_base_fields(),
            migration_id="f2a3b4c5d6e7",
            version="033",
            status=MigrationStatus.SUCCESS,
            duration_ms=450,
        )
        assert e.event_type == EventType.SCHEMA_MIGRATION
        assert e.status == MigrationStatus.SUCCESS
        assert e.error_message is None

    def test_failed_with_error_message(self):
        """SchemaMigrationEvent should accept error_message for failed migrations."""
        e = SchemaMigrationEvent(
            **_base_fields(),
            migration_id="abc123",
            version="034",
            status=MigrationStatus.FAILED,
            duration_ms=100,
            error_message="relation already exists",
        )
        assert e.status == MigrationStatus.FAILED
        assert e.error_message == "relation already exists"

    def test_all_statuses(self):
        """All MigrationStatus values should be valid."""
        for status in MigrationStatus:
            e = SchemaMigrationEvent(
                **_base_fields(),
                migration_id="rev123",
                version="034",
                status=status,
                duration_ms=100,
            )
            assert e.status == status


class TestCacheOperationEvent:
    """Tests for CacheOperationEvent schema."""

    def test_valid_get_hit(self):
        """CacheOperationEvent should parse a cache GET hit."""
        e = CacheOperationEvent(
            **_base_fields(),
            operation=CacheOperationType.GET,
            key_pattern="app:signals:*",
            hit=True,
            latency_ms=2,
        )
        assert e.event_type == EventType.CACHE_OPERATION
        assert e.operation == CacheOperationType.GET
        assert e.hit is True

    def test_valid_set_with_bytes_and_ttl(self):
        """CacheOperationEvent should accept value_bytes and ttl_seconds for SET."""
        e = CacheOperationEvent(
            **_base_fields(),
            operation=CacheOperationType.SET,
            key_pattern="app:price:*",
            latency_ms=5,
            value_bytes=4096,
            ttl_seconds=1800,
        )
        assert e.value_bytes == 4096
        assert e.ttl_seconds == 1800
        assert e.hit is None

    def test_error_event(self):
        """CacheOperationEvent should accept error_reason for failed operations."""
        e = CacheOperationEvent(
            **_base_fields(),
            operation=CacheOperationType.GET,
            key_pattern="user:*:profile",
            latency_ms=5000,
            error_reason="connection_error",
        )
        assert e.error_reason == "connection_error"
        assert e.hit is None

    def test_all_operations(self):
        """All CacheOperationType values should be valid."""
        for op in CacheOperationType:
            e = CacheOperationEvent(
                **_base_fields(),
                operation=op,
                key_pattern="test:*",
                latency_ms=1,
            )
            assert e.operation == op

    def test_missing_required_field(self):
        """CacheOperationEvent should reject missing key_pattern."""
        with pytest.raises(ValidationError):
            CacheOperationEvent(
                **_base_fields(),
                operation=CacheOperationType.GET,
                latency_ms=1,
            )
