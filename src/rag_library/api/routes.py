"""Streaming chat route and request-scoped dependency wiring."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from rag_library.agent.agent import get_agent
from rag_library.agent.context import AgentContext, create_agent_context
from rag_library.api.schemas import ChatRequest
from rag_library.api.streaming import stream_chat

logger = logging.getLogger(__name__)


def attachment_dependency(request: ChatRequest) -> AgentContext:
    """Validate selected books before any agent is initialized."""
    try:
        return create_agent_context(request.book_ids)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Book catalog unavailable")
        raise HTTPException(503, "Book catalog unavailable") from error


def chat_agent_dependency(
    context: Annotated[AgentContext, Depends(attachment_dependency)],
):
    """Require validated attachments, then build a fresh streaming agent."""
    try:
        return get_agent(structured_output=False)
    except Exception as error:
        logger.exception("Chat agent initialization failed")
        raise HTTPException(503, "Agent service unavailable") from error


router = APIRouter()


@router.post("/chat", tags=["agent"], response_class=StreamingResponse)
async def chat(
    request: ChatRequest,
    context: Annotated[AgentContext, Depends(attachment_dependency)],
    agent: Annotated[Any, Depends(chat_agent_dependency)],
) -> StreamingResponse:
    """Stream one independent answer, tool activity, and retrieved sources."""
    return StreamingResponse(
        stream_chat(agent, request.message, context),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
