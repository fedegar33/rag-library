"""In-memory BM25 retrieval over the existing attached-book chunks."""

from collections.abc import Sequence

import bm25s
from sqlalchemy import select
from sqlalchemy.orm import Session

from rag_library.catalog import normalize_book_ids
from rag_library.config import get_database_settings
from rag_library.database import Book, BookChunk, create_database_engine
from rag_library.rag.search import SearchResult


def _tokenize(texts: list[str]) -> list[list[str]]:
    """Use identical preprocessing and discard any library empty-token sentinel."""
    tokens = bm25s.tokenize(
        texts,
        lower=True,
        stopwords="en",
        stemmer=None,
        return_ids=False,
        show_progress=False,
    )
    return [[token for token in document if token] for document in tokens]


def bm25_search(
    query: str,
    limit: int = 5,
    chapters: Sequence[int] | None = None,
    *,
    book_ids: Sequence[int],
) -> list[SearchResult]:
    """Rank chunks using English tokens and attachment-wide BM25 statistics.

    Rebuild on every call so the index reflects current stored chunks. Chapter
    restrictions affect eligible results, not the corpus used for term rarity
    and average document length. No embeddings or model calls are needed.
    """
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    if limit < 1:
        raise ValueError("Search limit must be greater than zero")
    selected_ids = normalize_book_ids(book_ids)

    engine = create_database_engine(get_database_settings().database_url)
    try:
        with Session(engine) as session:
            found = set(
                session.scalars(select(Book.id).where(Book.id.in_(selected_ids)))
            )
            missing = [book_id for book_id in selected_ids if book_id not in found]
            if missing:
                raise ValueError(f"Unknown book IDs: {missing}")
            rows = session.execute(
                select(
                    Book.id,
                    Book.title,
                    BookChunk.chapter_number,
                    BookChunk.chunk_index,
                    BookChunk.text,
                )
                .join(Book, Book.id == BookChunk.book_id)
                .where(BookChunk.book_id.in_(selected_ids))
                .order_by(Book.id, BookChunk.chunk_index, BookChunk.id)
            ).all()
    finally:
        engine.dispose()

    if not rows:
        return []

    # Token strings keep query/corpus vocabulary alignment explicit.
    query_tokens = _tokenize([query])[0]
    if not query_tokens:
        return []
    corpus_tokens = _tokenize([row[4] for row in rows])
    if not any(corpus_tokens):
        return []

    index = bm25s.BM25(method="lucene", k1=1.5, b=0.75, backend="numpy")
    index.index(corpus_tokens, show_progress=False)
    scores = index.get_scores(query_tokens)
    # Filter before slicing top-k. Python's stable sort preserves the SQL order
    # for tied scores, making repeated comparisons reproducible.
    eligible = [
        (row, float(score))
        for row, score in zip(rows, scores, strict=True)
        if score > 0 and (not chapters or row[2] in chapters)
    ]
    eligible.sort(key=lambda match: match[1], reverse=True)
    return [
        SearchResult(
            book_id=book_id,
            book_title=title,
            chapter_number=chapter,
            chunk_index=chunk_index,
            text=text,
            similarity=None,
            bm25_score=score,
        )
        for (book_id, title, chapter, chunk_index, text), score in eligible[:limit]
    ]
