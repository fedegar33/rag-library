"""HTTP routes and dependency wiring for the catalog agent."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from rag_library.agent.agent import get_agent, run_agent
from rag_library.agent.context import AgentContext, create_agent_context
from rag_library.api.schemas import AgentRequest, AgentResponse
from rag_library.catalog import CatalogBook, list_books

logger = logging.getLogger(__name__)


def attachment_dependency(request: AgentRequest) -> AgentContext:
    try:
        return create_agent_context(request.book_ids)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Book catalog unavailable")
        raise HTTPException(503, "Book catalog unavailable") from error


def agent_dependency(context: Annotated[AgentContext, Depends(attachment_dependency)]):
    try:
        return get_agent()
    except Exception as error:
        logger.exception("Catalog agent initialization failed")
        raise HTTPException(503, "Agent service unavailable") from error


router = APIRouter()


@router.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    """Return a small service welcome response."""
    return {"message": "RAG Library API"}


@router.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Report whether the service is ready to receive requests."""
    return {"status": "ok"}


@router.post("/agent", response_model=AgentResponse, tags=["agent"])
def ask_agent(
    request: AgentRequest,
    context: Annotated[AgentContext, Depends(attachment_dependency)],
    agent: Annotated[Any, Depends(agent_dependency)],
) -> AgentResponse:
    """Answer an independent message and report the tool executions used."""
    try:
        result = run_agent(agent, request.message, context=context)
        return AgentResponse(answer=result.answer, tool_calls=result.tool_calls)
    except Exception as error:
        logger.exception("Catalog agent execution failed")
        raise HTTPException(503, "Agent service unavailable") from error


@router.get("/books", response_model=list[CatalogBook], tags=["books"])
def available_books() -> list[CatalogBook]:
    """Expose current IDs and stable references for the attachment picker."""
    try:
        return list_books()
    except Exception as error:
        logger.exception("Book catalog unavailable")
        raise HTTPException(503, "Book catalog unavailable") from error
