"""Chat router — streaming chat endpoint + session management."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatSessionResponse,
    FeedbackRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    request: Request,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Stream a chat response via NDJSON.

    Creates a new session if no session_id is provided (requires agent_type).
    Resumes an existing session if session_id is given.

    When AGENT_V2=true, uses the Plan→Execute→Synthesize graph.
    Otherwise, uses the V1 ReAct graph.
    """
    from backend.tools.chat_session import (
        auto_title,
        create_session,
        load_session_messages,
        save_message,
    )

    # Resolve or create session
    if body.session_id:
        session_messages = await load_session_messages(db, body.session_id)
        # Load agent_type from the session record
        from sqlalchemy import select

        from backend.models.chat import ChatSession

        stmt = select(ChatSession).where(
            ChatSession.id == body.session_id,
            ChatSession.user_id == user.id,
        )
        result = await db.execute(stmt)
        chat_session = result.scalar_one_or_none()
        if chat_session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        agent_type = chat_session.agent_type
    else:
        if not body.agent_type:
            raise HTTPException(status_code=422, detail="agent_type required for new session")
        title = auto_title(body.message)
        chat_session = await create_session(db, user.id, body.agent_type, title=title)
        session_messages = []
        agent_type = body.agent_type

    # Persist user message BEFORE streaming
    await save_message(db, chat_session.id, role="user", content=body.message)

    # Set request-scoped user context for tools (portfolio_exposure etc.)
    # Reset token stored so we can clear after streaming completes
    from backend.request_context import current_user_id

    _ctx_token = current_user_id.set(user.id)

    # Generate query_id for tracing
    query_id = uuid.uuid4()

    # Feature flag: select V1 or V2 graph
    from backend.config import settings

    use_v2 = settings.AGENT_V2 and hasattr(request.app.state, "agent_v2_graph")

    if use_v2:
        return StreamingResponse(
            _event_generator_v2(request, body, chat_session, session_messages, user, query_id),
            media_type="application/x-ndjson",
        )

    # V1 path (existing ReAct graph)
    graph = (
        request.app.state.stock_graph if agent_type == "stock" else request.app.state.general_graph
    )

    async def event_generator():
        """Yield NDJSON stream events and persist assistant message after."""
        from backend.agents.graph import AgentState
        from backend.agents.stream import stream_graph_events
        from backend.tools.chat_session import build_context_window, save_message

        # Build context from history + new message
        context = build_context_window(session_messages)
        context.append({"role": "user", "content": body.message})

        input_state = AgentState(
            messages=context,
            agent_type=agent_type,
            iteration=0,
            tool_results=[],
            usage={},
        )
        config = {"configurable": {"thread_id": str(chat_session.id)}}

        collected_tokens: list[str] = []
        collected_tool_calls: list[dict] = []

        async for event in stream_graph_events(graph, input_state, config):
            # Collect for persistence
            if event.type == "token" and event.content:
                collected_tokens.append(event.content)
            elif event.type == "tool_start":
                collected_tool_calls.append({"tool": event.tool, "params": event.params})
            elif event.type == "tool_result":
                # Update the last tool call with result
                if collected_tool_calls:
                    collected_tool_calls[-1]["status"] = event.status
                    collected_tool_calls[-1]["data"] = event.data

            yield event.to_ndjson() + "\n"

        # Persist assistant message AFTER stream completes
        final_content = "".join(collected_tokens) if collected_tokens else None
        tool_calls_json = collected_tool_calls if collected_tool_calls else None

        from backend.database import async_session_factory

        async with async_session_factory() as persist_db:
            await save_message(
                persist_db,
                chat_session.id,
                role="assistant",
                content=final_content,
                tool_calls=tool_calls_json,
            )

    return StreamingResponse(
        event_generator(),
        media_type="application/x-ndjson",
    )


async def _event_generator_v2(
    request: Request,
    body: ChatRequest,
    chat_session,
    session_messages: list,
    user,
    query_id: uuid.UUID,
):
    """Yield NDJSON events from the V2 Plan→Execute→Synthesize graph."""
    from backend.agents.graph_v2 import AgentStateV2
    from backend.agents.stream import stream_graph_v2_events
    from backend.agents.user_context import build_user_context
    from backend.database import async_session_factory
    from backend.tools.chat_session import build_context_window, save_message

    # Build user context for personalization
    async with async_session_factory() as ctx_db:
        user_context = await build_user_context(user.id, ctx_db)

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

    graph = request.app.state.agent_v2_graph

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


@router.patch(
    "/sessions/{session_id}/messages/{message_id}/feedback",
    response_model=dict,
)
async def set_feedback(
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    body: FeedbackRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Set thumbs up/down feedback on a chat message."""
    from sqlalchemy import select

    from backend.models.chat import ChatMessage, ChatSession

    # Verify session belongs to user
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user.id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

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


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_sessions(
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List user's active chat sessions."""
    from backend.tools.chat_session import list_user_sessions

    return await list_user_sessions(db, user.id)


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Get messages for a chat session (ownership verified)."""
    from sqlalchemy import select

    from backend.models.chat import ChatSession
    from backend.tools.chat_session import load_session_messages

    # Verify session belongs to user
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user.id,
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return await load_session_messages(db, session_id)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Soft-delete a chat session (set is_active=False)."""
    from backend.tools.chat_session import deactivate_session

    try:
        await deactivate_session(db, session_id, user.id)
    except ValueError as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=404, detail="Session not found")
        raise HTTPException(status_code=403, detail="Not authorized to delete this session")
    return {"status": "ok"}
