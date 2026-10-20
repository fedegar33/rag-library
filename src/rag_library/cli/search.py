"""Command-line vector, BM25, or hybrid search over ingested book chunks."""

import argparse
import sys

from rag_library.catalog import get_books_by_ids, resolve_book_id
from rag_library.rag.hybrid_search import hybrid_search
from rag_library.rag.keyword_search import bm25_search
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
        if results[0].rrf_score is not None:
            score_label = "RRF score"
        elif results[0].bm25_score is not None:
            score_label = "BM25 score"
        else:
            score_label = "Cosine similarity"
        lines.append(f"Book  Chapter  Chunk  {score_label}  Preview")
        for result in results:
            preview = " ".join(result.text.split())[:50]
            if result.rrf_score is not None:
                score = result.rrf_score
            elif result.bm25_score is not None:
                score = result.bm25_score
            else:
                score = result.similarity
            lines.append(
                f"{result.book_id!s:<4}  {result.chapter_number!s:<7}  "
                f"{result.chunk_index:<5}  {score:>10.6f}  {preview}"
            )

    if verbose:
        for result in results:
            lines.extend(
                [
                    "",
                    f"--- {result.book_title} · book {result.book_id} · "
                    f"chapter {result.chapter_number} · chunk {result.chunk_index} ---",
                ]
            )
            if result.rrf_score is not None:
                lines.append(
                    f"RRF score: {result.rrf_score:.6f} | "
                    f"Vector rank: {result.vector_rank} | "
                    f"Cosine similarity: {result.similarity} | "
                    f"BM25 rank: {result.bm25_rank} | BM25 score: {result.bm25_score}"
                )
            lines.append(result.text)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search ingested books by vector, BM25, or hybrid RRF"
    )
    parser.add_argument("query", help="Natural-language search query")
    parser.add_argument(
        "--book-id",
        type=int,
        action="append",
        help="Attach a book (repeat for multiple); optional for a singleton catalog",
    )
    parser.add_argument(
        "--method",
        choices=["vector", "bm25", "hybrid"],
        default="vector",
        help="Retrieval method (default: vector)",
    )
    parser.add_argument(
        "--limit", type=int, default=5, help="Maximum number of matches to print"
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="Hybrid candidates per method (default: max(20, --limit)); >= --limit",
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
    if args.candidate_limit is not None:
        if args.method != "hybrid":
            parser.error("--candidate-limit requires --method hybrid")
        if args.candidate_limit < max(1, args.limit):
            parser.error("--candidate-limit must be positive and at least --limit")

    try:
        if args.book_id is None or len(args.book_id) == 1:
            book_ids = [resolve_book_id(args.book_id[0] if args.book_id else None)]
        else:
            book_ids = [book["id"] for book in get_books_by_ids(args.book_id)]
        if args.method == "hybrid":
            results = hybrid_search(
                args.query,
                args.limit,
                args.chapter,
                book_ids=book_ids,
                candidate_limit=args.candidate_limit,
            )
        else:
            search = bm25_search if args.method == "bm25" else semantic_search
            results = search(args.query, args.limit, args.chapter, book_ids=book_ids)
    except Exception as error:
        print(f"Search failed: {error}", file=sys.stderr)
        return 1

    print(format_results(results, verbose=args.verbose))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
