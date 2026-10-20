"""Command-line semantic search over ingested book chunks."""

import argparse
import sys

from rag_library.catalog import resolve_book_id
from rag_library.rag.search import SearchResult, semantic_search


def parse_chapters(value: str) -> list[int]:
    """Parse a comma-separated list of positive chapter numbers."""
    try:
        chapters = [int(part.strip()) for part in value.split(",")]
    except ValueError as error:
        raise ValueError("Chapters must be comma-separated integers") from error
    if not chapters or any(chapter < 1 for chapter in chapters):
        raise ValueError("Chapter numbers must be greater than zero")
    return chapters


def format_results(results: list[SearchResult], verbose: bool = False) -> str:
    """Format search results for terminal output."""
    lines = [f"Top {len(results)} chunks found"]
    if results:
        lines.append("Chunk  Relevance  Preview")
        lines.append("-----  ---------  -------")
        for result in results:
            preview = " ".join(result.text.split())[:50]
            lines.append(
                f"{result.chunk_index:<5}  {result.similarity:>9.4f}  {preview}"
            )

    if verbose:
        for result in results:
            lines.extend(
                [
                    "",
                    f"--- {result.book_title} · chunk {result.chunk_index} ---",
                    result.text,
                ]
            )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search ingested books semantically")
    parser.add_argument("query", help="Natural-language search query")
    parser.add_argument(
        "--book-id",
        type=int,
        help="Select a catalog book; optional only when exactly one book is available",
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="Maximum number of matches to print"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the complete text for each matching chunk",
    )
    parser.add_argument(
        "--chapter",
        type=parse_chapters,
        help="Restrict search to comma-separated chapter numbers, e.g. 1,2,3",
    )
    args = parser.parse_args()

    try:
        book_id = resolve_book_id(args.book_id)
        results = semantic_search(
            args.query, args.limit, args.chapter, book_ids=[book_id]
        )
    except Exception as error:
        print(f"Search failed: {error}", file=sys.stderr)
        return 1

    print(format_results(results, verbose=args.verbose))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
