"""Agent tools backed by the reusable catalog and RAG workflows."""

from typing import Any, TypedDict

from langchain.tools import ToolRuntime, tool

from rag_library import catalog
from rag_library.agent.context import AgentContext
from rag_library.rag.retriever import BookRetriever


class ListBooksResult(TypedDict):
    books: list[catalog.CatalogBook]


@tool()
def list_books(runtime: ToolRuntime[AgentContext]) -> ListBooksResult:
    """List the books attached to this request, with catalog metadata."""
    return {"books": list(runtime.context.books)}


@tool()
def answer_book_question(
    question: str, runtime: ToolRuntime[AgentContext]
) -> dict[str, Any]:
    """Retrieve evidence to answer a content question from the attached books.

    Book scope is supplied by the application. Supply only the question; do not
    choose book IDs, infer attachments, or add guessed answer terms.
    """
    documents = BookRetriever(
        k=5,
        book_ids=runtime.context.book_ids,
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
