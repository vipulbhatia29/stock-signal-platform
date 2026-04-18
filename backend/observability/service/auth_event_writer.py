"""Batch writers for auth layer events: auth_event_log, oauth_event_log, email_send_log.

Each persist_* function opens a single session and batch-inserts all events in the list.
Writer errors are caught by the caller (event_writer.py) — they must not propagate.
"""

from __future__ import annotations

import logging

from backend.database import async_session_factory
from backend.observability.models.auth_event_log import AuthEventLog
from backend.observability.models.email_send_log import EmailSendLog
from backend.observability.models.oauth_event_log import OAuthEventLog
from backend.observability.schema.auth_events import (
    AuthEventLogEvent,
    EmailSendEvent,
    OAuthEventLogEvent,
)

logger = logging.getLogger(__name__)


async def persist_auth_events(events: list[AuthEventLogEvent]) -> None:
    """Persist auth event rows to observability.auth_event_log.

    Maps auth_event_type (the Pydantic subtype enum) to the event_type DB column.
    The SDK event_type field is always "auth_event" and is NOT stored; the column
    holds the specific AuthEventType value (e.g. "jwt_verify_failure").

    Args:
        events: List of AuthEventLogEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                AuthEventLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id) if event.trace_id else None,
                    span_id=str(event.span_id) if event.span_id else None,
                    user_id=str(event.user_id) if event.user_id else None,
                    # auth_event_type → event_type column (NOT event.event_type="auth_event")
                    event_type=event.auth_event_type.value,
                    outcome=event.outcome.value,
                    failure_reason=event.failure_reason,
                    ip_address=event.ip_address,
                    user_agent=event.user_agent,
                    method=event.method,
                    path=event.path,
                    metadata=event.metadata,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        await session.commit()
    logger.debug("Persisted %d auth_event_log rows", len(events))


async def persist_oauth_events(events: list[OAuthEventLogEvent]) -> None:
    """Persist OAuth event rows to observability.oauth_event_log.

    Args:
        events: List of OAuthEventLogEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                OAuthEventLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id) if event.trace_id else None,
                    user_id=str(event.user_id) if event.user_id else None,
                    provider=event.provider,
                    action=event.action.value,
                    status=event.status,
                    error_reason=event.error_reason,
                    attempt_number=event.attempt_number,
                    metadata=event.metadata,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        await session.commit()
    logger.debug("Persisted %d oauth_event_log rows", len(events))


async def persist_email_sends(events: list[EmailSendEvent]) -> None:
    """Persist email send event rows to observability.email_send_log.

    The recipient_hash field is expected to be pre-computed by the emit helper
    (SHA256 of lowercased email). This writer stores it as-is.

    Args:
        events: List of EmailSendEvent instances to persist. No-op for empty list.
    """
    if not events:
        return

    async with async_session_factory() as session:
        for event in events:
            session.add(
                EmailSendLog(
                    ts=event.ts,
                    trace_id=str(event.trace_id) if event.trace_id else None,
                    user_id=str(event.user_id) if event.user_id else None,
                    recipient_hash=event.recipient_hash,
                    email_type=event.email_type.value,
                    status=event.status,
                    error_reason=event.error_reason,
                    resend_message_id=event.resend_message_id,
                    env=event.env,
                    git_sha=event.git_sha,
                )
            )
        await session.commit()
    logger.debug("Persisted %d email_send_log rows", len(events))
