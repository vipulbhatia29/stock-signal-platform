"""Unit tests for AdminAuditLog model instantiation."""

import uuid

from backend.models.audit import AdminAuditLog


def test_audit_log_instantiation():
    """AdminAuditLog can be instantiated with metadata_ mapped to JSONB column."""
    log = AdminAuditLog(
        user_id=uuid.uuid4(),
        action="cache_clear_all",
        target="convergence:*",
        metadata_={"keys_deleted": 42},
    )
    assert log.action == "cache_clear_all"
    assert log.metadata_ == {"keys_deleted": 42}


def test_audit_log_repr():
    """AdminAuditLog repr includes action and target."""
    log = AdminAuditLog(action="pipeline_trigger", target="backtest_all")
    assert "pipeline_trigger" in repr(log)
