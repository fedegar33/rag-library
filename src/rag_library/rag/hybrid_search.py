"""Combine attached-book vector and BM25 candidates with reciprocal rank fusion."""

from collections.abc import Sequence
from dataclasses import replace

from rag_library.catalog import normalize_book_ids
from rag_library.rag.keyword_search import bm25_search
from rag_library.rag.reranking import get_rerank_api_key, rerank_results
from rag_library.rag.search import SearchResult, semantic_search

RRF_CONSTANT = 60
DEFAULT_CANDIDATE_LIMIT = 20


def reciprocal_rank_fusion(
    vector_results: Sequence[SearchResult],
    bm25_results: Sequence[SearchResult],
    limit: int = 5,
) -> list[SearchResult]:
    """Sum 1/(60 + one-based rank), counting each chunk once per branch.

    Identity is (book_id, chunk_index), never text. Preserve branch scores/ranks
    for inspection; neither raw score is used in fusion. Ties use book/chunk
    order, independent of which branch supplied a candidate first.
    """
    if limit < 1:
        raise ValueError("Search limit must be greater than zero")
    matches: dict[tuple[int, int], SearchResult] = {}
    for method, results in (("vector", vector_results), ("bm25", bm25_results)):
        seen: set[tuple[int, int]] = set()
        for rank, result in enumerate(results, start=1):
            if result.book_id is None:
                raise ValueError("Hybrid candidates must include a book ID")
            key = (result.book_id, result.chunk_index)
            if key in seen:
                continue
            seen.add(key)
            match = matches.get(key)
            if match is None:
                match = replace(
                    result,
                    similarity=None,
                    bm25_score=None,
                    rrf_score=0.0,
                    vector_rank=None,
                    bm25_rank=None,
                )
            contribution = 1.0 / (RRF_CONSTANT + rank)
            matches[key] = replace(
                match,
                rrf_score=(match.rrf_score or 0.0) + contribution,
                similarity=result.similarity
                if method == "vector"
                else match.similarity,
                bm25_score=result.bm25_score if method == "bm25" else match.bm25_score,
                vector_rank=rank if method == "vector" else match.vector_rank,
                bm25_rank=rank if method == "bm25" else match.bm25_rank,
            )
    return sorted(
        matches.values(),
        key=lambda match: (-(match.rrf_score or 0.0), match.book_id, match.chunk_index),
    )[:limit]


def hybrid_search(
    query: str,
    limit: int = 5,
    chapters: Sequence[int] | None = None,
    *,
    book_ids: Sequence[int],
    candidate_limit: int | None = None,
    rerank: bool = True,
) -> list[SearchResult]:
    """Retrieve both branches, optionally reranking their full union before top-k.

    Both branches receive the same query and filters. Empty lists are valid;
    exceptions propagate so branch failures cannot silently look successful.
    """
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    if limit < 1:
        raise ValueError("Search limit must be greater than zero")
    selected_ids = normalize_book_ids(book_ids)
    depth = (
        max(DEFAULT_CANDIDATE_LIMIT, limit)
        if candidate_limit is None
        else candidate_limit
    )
    if depth < limit:
        raise ValueError("Candidate limit must be at least the search limit")

    api_key = get_rerank_api_key() if rerank else None
    vector_results = semantic_search(query, depth, chapters, book_ids=selected_ids)
    bm25_results = bm25_search(query, depth, chapters, book_ids=selected_ids)
    if api_key is not None:
        # Keep the entire union: a useful passage may sit below the RRF cutoff.
        pool = reciprocal_rank_fusion(
            vector_results,
            bm25_results,
            max(1, len(vector_results) + len(bm25_results)),
        )
        return rerank_results(query, pool, limit, api_key=api_key)
    return reciprocal_rank_fusion(vector_results, bm25_results, limit)
