"""Semantic search over ingested book chunks."""

from collections.abc import Sequence
from dataclasses import dataclass

from langchain_openai import OpenAIEmbeddings
from sqlalchemy import select
from sqlalchemy.orm import Session

from rag_library.catalog import normalize_book_ids
from rag_library.config import get_settings
from rag_library.database import Book, BookChunk, create_database_engine


@dataclass(frozen=True)
class SearchResult:
    """A matching chunk returned by semantic search."""

    book_title: str
    chunk_index: int
    text: str
    similarity: float
    chapter_number: int | None = None
    book_id: int | None = None


def semantic_search(
    query: str,
    limit: int = 5,
    chapters: Sequence[int] | None = None,
    *,
    book_ids: Sequence[int],
) -> list[SearchResult]:
    """Return the closest ingested chunks for a natural-language query."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    if limit < 1:
        raise ValueError("Search limit must be greater than zero")
    selected_ids = normalize_book_ids(book_ids)

    settings = get_settings()
    engine = create_database_engine(settings.database_url)
    try:
        # Reject invalid selections before paying for an embedding request.
        with Session(engine) as session:
            found = set(
                session.scalars(select(Book.id).where(Book.id.in_(selected_ids)))
            )
            missing = [book_id for book_id in selected_ids if book_id not in found]
            if missing:
                raise ValueError(f"Unknown book IDs: {missing}")
        embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        query_embedding = embeddings.embed_query(query)
        distance = BookChunk.embedding.cosine_distance(query_embedding).label(
            "distance"
        )
        statement = (
            select(
                Book.id,
                Book.title,
                BookChunk.chapter_number,
                BookChunk.chunk_index,
                BookChunk.text,
                distance,
            )
            .join(Book, Book.id == BookChunk.book_id)
            .where(BookChunk.book_id.in_(selected_ids))
            .order_by(distance)
            .limit(limit)
        )
        if chapters:
            statement = statement.where(BookChunk.chapter_number.in_(chapters))

        with Session(engine) as session:
            rows = session.execute(statement).all()
    finally:
        engine.dispose()

    return [
        SearchResult(
            book_title=title,
            book_id=book_id,
            chapter_number=chapter_number,
            chunk_index=chunk_index,
            text=text,
            similarity=1 - float(distance_value),
        )
        for book_id, title, chapter_number, chunk_index, text, distance_value in rows
    ]
