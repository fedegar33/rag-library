"""List current book IDs for scoped search and answering commands."""

from rag_library.catalog import list_books


def main() -> int:
    books = list_books()
    for book in books:
        print(
            f"{book['id']}: {book['title']} | {book['language'] or '?'} | "
            f"{book['content_sha256']}"
        )
    if not books:
        print("No books available. Ingest a book first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
