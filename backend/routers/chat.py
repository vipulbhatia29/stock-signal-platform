"""Chat router — streaming chat endpoint + session management."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.dependencies import get_current_user
from backend.schemas.chat import ChatMessageResponse, ChatRequest, ChatSessionResponse

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

        stmt = select(ChatSession).where(ChatSession.id == body.session_id)
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

    # Select the pre-built LangGraph from app.state
    graph = (
        request.app.state.stock_graph if agent_type == "stock" else request.app.state.general_graph
    )

    async def event_generator():
        """Yield NDJSON stream events and persist assistant message after."""
        from backend.agents.graph import AgentState
        from backend.agents.stream import stream_graph_events
        from backend.tools.chat_session import build_context_window

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

        # Use a new session for the post-stream write (original may be closed)
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
    """Get messages for a chat session."""
    from backend.tools.chat_session import load_session_messages

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
            raise HTTPException(status_code=404, detail=str(exc))
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "ok"}
