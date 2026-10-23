"""Application-owned retrieval scope for one agent invocation."""

from collections.abc import Sequence
from dataclasses import dataclass

from rag_library import catalog
from rag_library.rag.search import RetrievalMethod


@dataclass(frozen=True)
class AgentContext:
    """A validated retrieval snapshot: attachments, or the entire catalog."""

    books: tuple[catalog.CatalogBook, ...]
    retrieval_method: RetrievalMethod = "hybrid"
    candidate_limit: int | None = None
    rerank: bool = True

    def __post_init__(self):
        if self.books:
            catalog.normalize_book_ids(self.book_ids)
        validate_retrieval_options(self.retrieval_method, self.candidate_limit)

    @property
    def book_ids(self) -> list[int]:
        return [book["id"] for book in self.books]

    @property
    def book_refs(self) -> list[str]:
        return [book["content_sha256"] for book in self.books]


def validate_retrieval_options(method: str, candidate_limit: int | None) -> None:
    """Validate agent retrieval before model calls; the tool returns five chunks."""
    if method not in ("vector", "bm25", "hybrid"):
        raise ValueError("Retrieval method must be vector, bm25, or hybrid")
    if candidate_limit is not None:
        if method != "hybrid":
            raise ValueError("candidate_limit requires hybrid retrieval")
        if type(candidate_limit) is not int or candidate_limit < 5:
            raise ValueError("Agent candidate_limit must be an integer at least 5")


def create_agent_context(
    book_ids: Sequence[int] = (),
    *,
    retrieval_method: RetrievalMethod = "hybrid",
    candidate_limit: int | None = None,
    rerank: bool = True,
) -> AgentContext:
    """Resolve attachments, or snapshot all available books when none are supplied."""
    validate_retrieval_options(retrieval_method, candidate_limit)
    return AgentContext(
        books=tuple(
            catalog.get_books_by_ids(book_ids) if book_ids else catalog.list_books()
        ),
        retrieval_method=retrieval_method,
        candidate_limit=candidate_limit,
        rerank=rerank,
    )
