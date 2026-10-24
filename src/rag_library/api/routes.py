"""Streaming chat route and request-scoped dependency wiring."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response, StreamingResponse

from rag_library.agent.agent import get_agent
from rag_library.agent.context import AgentContext, create_agent_context
from rag_library.agent.models import AvailableBooksResult
from rag_library.api.schemas import ChatRequest
from rag_library.api.streaming import stream_chat
from rag_library.catalog import get_book_cover, list_books

logger = logging.getLogger(__name__)


def attachment_dependency(request: ChatRequest) -> AgentContext:
    """Resolve the retrieval scope before any agent is initialized."""
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
    """Require a resolved retrieval scope, then build a fresh streaming agent."""
    try:
        return get_agent(structured_output=False)
    except Exception as error:
        logger.exception("Chat agent initialization failed")
        raise HTTPException(503, "Agent service unavailable") from error


router = APIRouter()


@router.get("/books", tags=["books"], response_model=AvailableBooksResult)
def books() -> AvailableBooksResult:
    """Expose public catalog metadata without invoking the agent or retrieval."""
    try:
        return AvailableBooksResult(books=list_books())
    except Exception as error:
        logger.exception("Book catalog unavailable")
        raise HTTPException(503, "Book catalog unavailable") from error


@router.get("/books/{book_id}/cover", tags=["books"], response_class=Response)
def book_cover(book_id: Annotated[int, Path(gt=0)]) -> Response:
    """Serve stored cover bytes; missing books and missing covers return 404."""
    try:
        cover = get_book_cover(book_id)
    except Exception as error:
        logger.exception("Book cover unavailable")
        raise HTTPException(503, "Book cover unavailable") from error
    if cover is None:
        raise HTTPException(404, "Book cover not found")
    data, media_type = cover
    return Response(
        content=data,
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/chat", tags=["agent"], response_class=StreamingResponse)
async def chat(
    request: ChatRequest,
    context: Annotated[AgentContext, Depends(attachment_dependency)],
    agent: Annotated[Any, Depends(chat_agent_dependency)],
) -> StreamingResponse:
    """Stream the next answer using recent history and the current book scope."""
    return StreamingResponse(
        stream_chat(agent, request.to_messages(), context),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
