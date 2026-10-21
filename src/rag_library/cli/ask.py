"""Command-line grounded question answering over ingested books."""

import argparse
import sys

from rag_library.catalog import resolve_book_id
from rag_library.rag.answering import ask_question


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask a question about ingested books")
    parser.add_argument("question", help="Question to ask about the ingested books")
    parser.add_argument(
        "--book-id",
        type=int,
        help="Select a catalog book; optional only when exactly one book is available",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of book chunks to retrieve (default: 5)",
    )
    parser.add_argument(
        "--method",
        choices=["vector", "bm25", "hybrid"],
        default="vector",
        help="Retrieval method (default: vector; agent/evals default to hybrid)",
    )
    parser.add_argument(
        "--rerank",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Rerank hybrid candidates with Cohere (default: enabled)",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="Hybrid candidates per method (default: max(20, --top-k))",
    )
    args = parser.parse_args()
    if args.rerank and args.method != "hybrid":
        parser.error("--rerank requires --method hybrid")
    if args.candidate_limit is not None:
        if args.method != "hybrid" or args.candidate_limit < max(1, args.top_k):
            parser.error(
                "--candidate-limit requires hybrid and must be at least --top-k"
            )

    try:
        book_id = resolve_book_id(args.book_id)
        response = ask_question(
            args.question,
            args.top_k,
            book_ids=[book_id],
            method=args.method,
            candidate_limit=args.candidate_limit,
            rerank=args.rerank is not False,
        )
    except Exception as error:
        print(f"Ask failed: {error}", file=sys.stderr)
        return 1

    print("Answer:")
    print(response.answer)
    print()
    print("Sources:")
    if response.sources:
        for source in response.sources:
            chapter = source.chapter_number or "?"
            if source.rerank_score is not None:
                score = f"rerank score {source.rerank_score:.6f}"
            elif source.rrf_score is not None:
                score = f"RRF score {source.rrf_score:.6f}"
            elif source.bm25_score is not None:
                score = f"BM25 score {source.bm25_score:.4f}"
            else:
                score = f"relevance {source.similarity:.4f}"
            print(
                f"- {source.book_title} (book {source.book_id}), chapter {chapter}, "
                f"chunk {source.chunk_index}, {score}"
            )
    else:
        print("- None")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
