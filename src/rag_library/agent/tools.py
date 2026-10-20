"""Agent tools backed by the reusable catalog and RAG workflows."""

from dataclasses import asdict
from typing import Any, TypedDict

from langchain.tools import ToolRuntime, tool

from rag_library import catalog
from rag_library.agent.context import AgentContext
from rag_library.rag.answering import ask_question


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
    """Answer a content question using only the attached books, with source passages.

    Book scope is supplied by the application. Supply only the question; do not
    choose book IDs, infer attachments, or add guessed answer terms.
    """
    return asdict(ask_question(question, book_ids=runtime.context.book_ids))
