"""Complete book-card metadata without re-ingesting text or embeddings."""

import argparse
import sys

from rag_library.ingestion.pipeline import enrich_book


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Complete existing books' covers and categories without embeddings"
    )
    parser.add_argument(
        "--file", required=True, action="append", help="EPUB (repeatable)"
    )
    args = parser.parse_args()
    for path in args.file:
        try:
            book = enrich_book(path)
        except Exception as error:
            print(f"Metadata enrichment failed for {path}: {error}", file=sys.stderr)
            return 1
        print(f"Updated book {book.id}: {book.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
