"""Application-owned retrieval scope for one agent invocation."""

from collections.abc import Sequence
from dataclasses import dataclass

from rag_library import catalog
from rag_library.rag.search import RetrievalMethod


@dataclass(frozen=True)
class AgentContext:
    """Caller-selected IDs and retrieval options; no attachments means all books."""

    attached_book_ids: tuple[int, ...] = ()
    retrieval_method: RetrievalMethod = "hybrid"
    candidate_limit: int | None = None
    rerank: bool = True

    def __post_init__(self):
        ids = tuple(self.attached_book_ids)
        if ids:
            ids = tuple(catalog.normalize_book_ids(ids))
        object.__setattr__(self, "attached_book_ids", ids)
        validate_retrieval_options(self.retrieval_method, self.candidate_limit)


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
    """Validate supplied attachments before model execution; keep empty scope empty."""
    context = AgentContext(
        attached_book_ids=tuple(book_ids),
        retrieval_method=retrieval_method,
        candidate_limit=candidate_limit,
        rerank=rerank,
    )
    if context.attached_book_ids:
        catalog.get_books_by_ids(context.attached_book_ids)
    return context
