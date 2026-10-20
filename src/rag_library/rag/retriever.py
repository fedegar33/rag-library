"""LangChain adapter for the application's scoped retrieval methods."""

from dataclasses import asdict
from typing import Annotated

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag_library.rag.hybrid_search import hybrid_search
from rag_library.rag.keyword_search import bm25_search
from rag_library.rag.search import RetrievalMethod, semantic_search


class BookRetriever(BaseRetriever):
    """Retrieve book chunks while preserving all method-specific provenance."""

    k: int = 5
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1)
    method: RetrievalMethod = "vector"
    candidate_limit: int | None = Field(default=None, ge=1)

    def _get_relevant_documents(self, query: str, *, run_manager) -> list[Document]:
        if self.k < 1:
            raise ValueError("k must be greater than zero")

        if self.method == "hybrid":
            results = hybrid_search(
                query,
                limit=self.k,
                book_ids=self.book_ids,
                candidate_limit=self.candidate_limit,
            )
        else:
            if self.candidate_limit is not None:
                raise ValueError("candidate_limit requires hybrid retrieval")
            search = semantic_search if self.method == "vector" else bm25_search
            results = search(query, limit=self.k, book_ids=self.book_ids)
        documents = []
        for result in results:
            metadata = asdict(result)
            text = metadata.pop("text")
            documents.append(Document(page_content=text, metadata=metadata))
        return documents
