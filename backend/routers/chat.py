"""Chat router — streaming chat endpoint + session management."""

from __future__ import annotations

import logging
import uuid
from contextvars import Token

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import async_session_factory, get_async_session
from backend.dependencies import get_current_user
from backend.models.chat import ChatMessage, ChatSession
from backend.models.user import User
from backend.request_context import (
    current_agent_instance_id,
    current_agent_type,
    current_query_id,
    current_session_id,
    current_user_id,
)
from backend.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatSessionResponse,
    FeedbackRequest,
)
from backend.tools.chat_session import (
    auto_title,
    build_context_window,
    create_session,
    deactivate_session,
    list_user_sessions,
    load_session_messages,
    save_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


async def _decline_stream(message: str):
    """Yield a decline NDJSON stream."""
    from backend.agents.stream import StreamEvent

    yield StreamEvent(type="decline", content=message).to_ndjson() + "\n"
    yield StreamEvent(type="done", usage={}).to_ndjson() + "\n"


async def _get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ChatSession:
    """Look up a chat session with ownership verification.

    Args:
        db: Async database session.
        session_id: The session ID to look up.
        user_id: The requesting user's ID.

    Returns:
        The ChatSession if found and owned by the user.

    Raises:
        HTTPException: 404 if session not found or not owned by user.
    """
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
    )
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post(
    "/stream",
    summary="Stream a chat response",
    description="Stream a chat response via NDJSON. Creates a new session if no session_id.",
    responses={401: {"description": "Not authenticated"}, 422: {"description": "Validation error"}},
)
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """Stream a chat response via NDJSON.

    Creates a new session if no session_id is provided (requires agent_type).
    Resumes an existing session if session_id is given.
    Uses the Plan→Execute→Synthesize graph.
    """
    # ── Input guard ──────────────────────────────────────────────────
    from backend.agents.guards import (
        detect_and_strip_pii,
        detect_injection,
        sanitize_input,
        validate_input_length,
    )

    length_err = validate_input_length(body.message)
    if length_err:
        return StreamingResponse(_decline_stream(length_err), media_type="application/x-ndjson")

    body.message = sanitize_input(body.message)

    body.message, pii_found = detect_and_strip_pii(body.message)
    if pii_found:
        logger.warning("PII redacted from chat message: %s", pii_found)

    # Resolve or create session
    if body.session_id:
        session_messages = await load_session_messages(db, body.session_id)
        chat_session = await _get_session(db, body.session_id, user.id)
    else:
        if not body.agent_type:
            raise HTTPException(status_code=422, detail="agent_type required for new session")
        title = auto_title(body.message)
        chat_session = await create_session(db, user.id, body.agent_type, title=title)
        session_messages = []

    # Injection detection (after session is available for decline tracking)
    if detect_injection(body.message):
        logger.warning("Prompt injection detected in session %s", chat_session.id)
        chat_session.decline_count = (chat_session.decline_count or 0) + 1
        db.add(chat_session)
        await db.commit()
        return StreamingResponse(
            _decline_stream(
                "I can only help with financial analysis and portfolio management. "
                "Please ask a question about stocks, markets, or your portfolio."
            ),
            media_type="application/x-ndjson",
        )

    # Session abuse check
    if (chat_session.decline_count or 0) >= 5:
        return StreamingResponse(
            _decline_stream(
                "This session has been flagged for repeated off-topic queries. "
                "Please start a new session with a financial analysis question."
            ),
            media_type="application/x-ndjson",
        )

    # Persist user message BEFORE streaming
    await save_message(db, chat_session.id, role="user", content=body.message)

    # Set request-scoped user context for tools (portfolio_exposure etc.)
    ctx_token_user = current_user_id.set(user.id)

    # Generate query_id for tracing and propagate session/query context
    query_id = uuid.uuid4()
    ctx_token_session = current_session_id.set(chat_session.id)
    ctx_token_query = current_query_id.set(query_id)
    ctx_token_agent_type = current_agent_type.set(chat_session.agent_type)
    ctx_token_agent_instance = current_agent_instance_id.set(str(uuid.uuid4()))

    return StreamingResponse(
        _event_generator(
            request,
            body,
            chat_session,
            session_messages,
            user,
            query_id,
            ctx_tokens=(
                ctx_token_user,
                ctx_token_session,
                ctx_token_query,
                ctx_token_agent_type,
                ctx_token_agent_instance,
            ),
        ),
        media_type="application/x-ndjson",
    )


async def _event_generator(
    request: Request,
    body: ChatRequest,
    chat_session: ChatSession,
    session_messages: list[dict],
    user: User,
    query_id: uuid.UUID,
    ctx_tokens: tuple[Token, Token, Token, Token, Token] | None = None,
):
    """Yield NDJSON events from the Plan→Execute→Synthesize graph.

    Args:
        request: The FastAPI request object.
        body: The chat request body.
        chat_session: The resolved or newly-created chat session.
        session_messages: Previous messages for context window.
        user: The authenticated user.
        query_id: Unique query ID for tracing.
        ctx_tokens: Tuple of ContextVar tokens (user, session, query) to
            reset when streaming completes, preventing stale state leaking
            across async tasks.
    """
    try:
        from backend.agents.graph import AgentStateV2
        from backend.agents.stream import stream_graph_v2_events
        from backend.agents.user_context import build_user_context

        # Build user context for personalization
        async with async_session_factory() as ctx_db:
            user_context = await build_user_context(user.id, ctx_db)

        # ── Fast path: intent classifier ─────────────────────────────────────
        from backend.agents.intent_classifier import classify_intent
        from backend.agents.simple_formatter import format_simple_result
        from backend.agents.stream import StreamEvent

        classified = classify_intent(
            body.message,
            held_tickers=[p.get("ticker") for p in user_context.get("positions", [])],
        )

        if classified.intent == "out_of_scope":
            decline_msg = classified.decline_message or (
                "I can only help with financial analysis and portfolio management. "
                "Please ask a question about stocks, markets, or your portfolio."
            )
            yield StreamEvent(type="decline", content=decline_msg).to_ndjson() + "\n"
            yield StreamEvent(type="done", usage={}).to_ndjson() + "\n"
            async with async_session_factory() as persist_db:
                await save_message(
                    persist_db, chat_session.id, role="assistant", content=decline_msg
                )
            return

        if classified.fast_path and classified.tickers:
            tool_executor = getattr(request.app.state, "tool_executor", None)
            if tool_executor:
                result = await tool_executor("analyze_stock", {"ticker": classified.tickers[0]})
                formatted = format_simple_result(
                    "analyze_stock", result.data if hasattr(result, "data") else result
                )
                yield StreamEvent(type="token", content=formatted).to_ndjson() + "\n"
                yield StreamEvent(type="done", usage={}).to_ndjson() + "\n"
                async with async_session_factory() as persist_db:
                    await save_message(
                        persist_db, chat_session.id, role="assistant", content=formatted
                    )
                return
            # If no tool_executor available, fall through to graph path

        # Build message context
        context = build_context_window(session_messages)
        context.append({"role": "user", "content": body.message})

        input_state = AgentStateV2(
            messages=context,
            phase="plan",
            plan={},
            tool_results=[],
            synthesis={},
            iteration=0,
            replan_count=0,
            start_time=0.0,
            user_context=user_context,
            query_id=str(query_id),
            skip_synthesis=False,
            response_text="",
            decline_message="",
        )

        graph = getattr(request.app.state, "agent_graph", None)
        if graph is None:
            from backend.agents.stream import StreamEvent

            yield (
                StreamEvent(
                    type="error",
                    error="Chat service is starting up. Please try again in a moment.",
                ).to_ndjson()
                + "\n"
            )
            return

        collected_tokens: list[str] = []
        collected_tool_calls: list[dict] = []

        async for event in stream_graph_v2_events(graph, input_state):
            if event.type == "token" and event.content:
                collected_tokens.append(event.content)
            elif event.type == "tool_result":
                collected_tool_calls.append(
                    {"tool": event.tool, "status": event.status, "data": event.data}
                )
            elif event.type == "tool_error":
                collected_tool_calls.append(
                    {"tool": event.tool, "status": "error", "error": event.error}
                )

            yield event.to_ndjson() + "\n"

        # Persist assistant message
        final_content = "".join(collected_tokens) if collected_tokens else None
        tool_calls_json = collected_tool_calls if collected_tool_calls else None

        async with async_session_factory() as persist_db:
            await save_message(
                persist_db,
                chat_session.id,
                role="assistant",
                content=final_content,
                tool_calls=tool_calls_json,
            )
    finally:
        if ctx_tokens is not None:
            current_user_id.reset(ctx_tokens[0])
            current_session_id.reset(ctx_tokens[1])
            current_query_id.reset(ctx_tokens[2])
            current_agent_type.reset(ctx_tokens[3])
            current_agent_instance_id.reset(ctx_tokens[4])


@router.patch(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    response_model=dict,
    summary="Set message feedback",
    description="Set thumbs up/down feedback on a chat message.",
    responses={404: {"description": "Session or message not found"}},
)
async def set_feedback(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Set thumbs up/down feedback on a chat message."""
    # Verify session belongs to user
    await _get_session(db, session_id, user.id)

    # Find message
    stmt = select(ChatMessage).where(
        ChatMessage.id == message_id,
        ChatMessage.session_id == session_id,
    )
    result = await db.execute(stmt)
    message = result.scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="Message not found")

    message.feedback = body.feedback
    db.add(message)
    await db.commit()

    return {"status": "ok", "feedback": body.feedback}


@router.get(
    "/sessions",
    response_model=list[ChatSessionResponse],
    summary="List chat sessions",
    description="List the current user's active chat sessions, ordered by most recent first.",
)
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[ChatSessionResponse]:
    """List user's active chat sessions."""
    return await list_user_sessions(db, user.id)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
    summary="Get session messages",
    description="Get messages for a chat session. Ownership is verified.",
    responses={404: {"description": "Session not found"}},
)
async def get_session_messages(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> list[ChatMessageResponse]:
    """Get messages for a chat session (ownership verified)."""
    await _get_session(db, session_id, user.id)
    return await load_session_messages(db, session_id)


@router.delete(
    "/sessions/{session_id}",
    summary="Delete a chat session",
    description="Soft-delete a chat session (set is_active=False).",
    responses={404: {"description": "Session not found"}, 403: {"description": "Not authorized"}},
)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Soft-delete a chat session (set is_active=False)."""
    try:
        await deactivate_session(db, session_id, user.id)
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail="Session not found")
        raise HTTPException(status_code=403, detail="Not authorized to delete this session")
    return {"status": "ok"}
