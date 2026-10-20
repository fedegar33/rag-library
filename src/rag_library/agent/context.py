"""Application-owned book attachments for one agent invocation."""

from collections.abc import Sequence
from dataclasses import dataclass

from rag_library.catalog import CatalogBook, get_books_by_ids, normalize_book_ids


@dataclass(frozen=True)
class AgentContext:
    """A validated catalog snapshot; tools cannot widen this attachment scope."""

    books: tuple[CatalogBook, ...]

    def __post_init__(self):
        normalize_book_ids(self.book_ids)

    @property
    def book_ids(self) -> list[int]:
        return [book["id"] for book in self.books]

    @property
    def book_refs(self) -> list[str]:
        return [book["content_sha256"] for book in self.books]


def create_agent_context(book_ids: Sequence[int]) -> AgentContext:
    """Validate caller attachments against the catalog before invoking a model."""
    return AgentContext(books=tuple(get_books_by_ids(book_ids)))
