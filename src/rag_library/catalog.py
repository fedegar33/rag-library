"""Read-only access to the ingested book catalog."""

import re
from collections.abc import Sequence
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from rag_library.config import get_database_settings
from rag_library.database import Book, create_database_engine


class CatalogBook(TypedDict):
    id: int
    title: str
    authors: str | None
    language: str | None
    content_sha256: str
    categories: list[str]
    cover_url: str | None


def list_books() -> list[CatalogBook]:
    """Return all ingested books in title and ID order, without loading passages."""
    engine = create_database_engine(get_database_settings().database_url)
    try:
        with Session(engine) as session:
            rows = session.execute(
                select(
                    Book.id,
                    Book.title,
                    Book.authors,
                    Book.language,
                    Book.content_sha256,
                    Book.categories,
                    (
                        Book.cover_data.is_not(None)
                        & Book.cover_media_type.is_not(None)
                    ).label("has_cover"),
                ).order_by(Book.title, Book.id)
            ).mappings()
            return [
                CatalogBook(
                    id=row["id"],
                    title=row["title"],
                    authors=row["authors"],
                    language=row["language"],
                    content_sha256=row["content_sha256"],
                    categories=row["categories"],
                    cover_url=f"/books/{row['id']}/cover" if row["has_cover"] else None,
                )
                for row in rows
            ]
    finally:
        engine.dispose()


def get_book_cover(book_id: int) -> tuple[bytes, str] | None:
    """Load image bytes only on explicit cover requests, without model credentials."""
    engine = create_database_engine(get_database_settings().database_url)
    try:
        with Session(engine) as session:
            row = session.execute(
                select(Book.cover_data, Book.cover_media_type).where(Book.id == book_id)
            ).one_or_none()
            if row is None or not row[0] or not row[1]:
                return None
            return bytes(row[0]), row[1]
    finally:
        engine.dispose()


def normalize_book_ids(book_ids: Sequence[int]) -> list[int]:
    """Require explicit, positive attachment IDs and remove duplicates in order."""
    if not book_ids or any(type(value) is not int or value < 1 for value in book_ids):
        raise ValueError("Attach at least one book using positive integer book IDs")
    return list(dict.fromkeys(book_ids))


def validate_book_refs(book_refs: list[str]) -> None:
    """A stable eval reference identifies exact EPUB bytes, not a catalog row."""
    if (
        not isinstance(book_refs, list)
        or not book_refs
        or any(
            not isinstance(ref, str) or re.fullmatch(r"[0-9a-f]{64}", ref) is None
            for ref in book_refs
        )
    ):
        raise ValueError(
            "book_refs must be a nonempty list of lowercase content_sha256 values"
        )


def get_books_by_ids(book_ids: Sequence[int]) -> list[CatalogBook]:
    ids = normalize_book_ids(book_ids)
    books = {book["id"]: book for book in list_books()}
    missing = [book_id for book_id in ids if book_id not in books]
    if missing:
        raise ValueError(f"Unknown book IDs: {missing}")
    return [books[book_id] for book_id in ids]


def get_books_by_refs(book_refs: list[str]) -> list[CatalogBook]:
    """Resolve stable EPUB hashes to current IDs; never substitute another edition."""
    validate_book_refs(book_refs)
    books = {book["content_sha256"]: book for book in list_books()}
    missing = [ref for ref in book_refs if ref not in books]
    if missing:
        raise ValueError(f"No ingested book matches content_sha256: {missing}")
    return [books[ref] for ref in dict.fromkeys(book_refs)]


def resolve_book_id(book_id: int | None = None) -> int:
    """Validate a selection, or select automatically from a singleton catalog."""
    if book_id is not None and book_id < 1:
        raise ValueError("Book ID must be greater than zero")
    books = list_books()
    if not books:
        raise ValueError("No books are available; ingest a book first")
    if book_id is None and len(books) == 1:
        return books[0]["id"]
    if book_id is not None and any(book["id"] == book_id for book in books):
        return book_id
    available = "; ".join(
        f"{book['id']}: {book['title']} ({book['language'] or 'unknown language'})"
        for book in books
    )
    reason = (
        "Select one book" if book_id is None else f"Book ID {book_id} is unavailable"
    )
    raise ValueError(f"{reason}. Available books: {available}")
