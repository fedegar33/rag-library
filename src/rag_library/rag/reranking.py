"""Optional Cohere reranking of already scoped hybrid candidates."""

import logging
from collections.abc import Sequence
from dataclasses import replace
from math import isfinite
from time import sleep

from cohere import ClientV2
from cohere.errors import TooManyRequestsError

from rag_library.config import get_settings
from rag_library.rag.search import SearchResult

RERANK_MODEL = "rerank-v5.0-pro"
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_WAIT_SECONDS = 60
logger = logging.getLogger(__name__)


def get_rerank_api_key() -> str:
    """Validate opt-in credentials before paying for retrieval."""
    key = get_settings().cohere_api_key
    if not key or not key.strip():
        raise ValueError("Set COHERE_API_KEY in .env to use --rerank")
    return key.strip()


def rerank_results(
    query: str,
    candidates: Sequence[SearchResult],
    limit: int = 5,
    *,
    api_key: str,
) -> list[SearchResult]:
    """Score the whole pool, mapping response indexes back to source chunks.

    Candidates arrive in RRF order. Preserve that rank and all retrieval scores;
    API failures propagate rather than silently returning the baseline ranking.
    """
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    if limit < 1:
        raise ValueError("Search limit must be greater than zero")
    if not candidates:
        return []
    top_n = min(limit, len(candidates))
    with ClientV2(api_key=api_key, timeout=60.0) as client:
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                response = client.rerank(
                    model=RERANK_MODEL,
                    query=query,
                    documents=[candidate.text for candidate in candidates],
                    top_n=top_n,
                    request_options={"max_retries": 0},
                )
                break
            except TooManyRequestsError:
                if attempt == RATE_LIMIT_RETRIES:
                    raise
                # Trial keys allow 10 calls/minute and may omit Retry-After.
                # Wait a full window; keep SDK retries off to bound attempts.
                logger.warning(
                    "Cohere rate limit reached; waiting %ss before retry %s/%s.",
                    RATE_LIMIT_WAIT_SECONDS,
                    attempt + 1,
                    RATE_LIMIT_RETRIES,
                )
                sleep(RATE_LIMIT_WAIT_SECONDS)
    if len(response.results) != top_n:
        raise ValueError("Reranker returned an unexpected number of results")
    results = []
    seen = set()
    for match in response.results:
        index = match.index
        if index < 0 or index >= len(candidates) or index in seen:
            raise ValueError("Reranker returned an invalid or duplicate document index")
        if not isfinite(match.relevance_score):
            raise ValueError("Reranker returned a non-finite relevance score")
        seen.add(index)
        results.append(
            replace(
                candidates[index],
                rerank_score=match.relevance_score,
                rrf_rank=index + 1,
            )
        )
    return results
