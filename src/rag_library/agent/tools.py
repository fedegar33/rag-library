"""Agent tools backed by the reusable catalog and RAG workflows."""

from typing import Any

from langchain.tools import ToolRuntime, tool

from rag_library import catalog
from rag_library.agent.context import AgentContext
from rag_library.agent.models import AvailableBooksResult
from rag_library.rag.retriever import BookRetriever


@tool()
def list_available_books() -> dict[str, Any]:
    """List all books available in the database, regardless of chat attachments."""
    return AvailableBooksResult(books=catalog.list_books()).model_dump(mode="json")


@tool()
def answer_book_question(
    question: str, runtime: ToolRuntime[AgentContext]
) -> dict[str, Any]:
    """Retrieve evidence from attached books, or the whole library without attachments.

    Book scope is supplied by the application. Supply only the question; do not
    choose book IDs, infer attachments, or add guessed answer terms.
    """
    book_ids = list(runtime.context.attached_book_ids)
    if not book_ids:
        book_ids = [book["id"] for book in catalog.list_books()]
    if not book_ids:
        return {"sources": [], "message": "No books are available in the library."}
    documents = BookRetriever(
        k=5,
        book_ids=book_ids,
        method=runtime.context.retrieval_method,
        candidate_limit=runtime.context.candidate_limit,
        rerank=runtime.context.rerank,
    ).invoke(question)
    return {
        "sources": [
            {**document.metadata, "text": document.page_content}
            for document in documents
        ]
    }
