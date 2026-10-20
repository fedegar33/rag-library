"""LangChain retriever backed by the application's semantic search."""

from typing import Annotated

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag_library.rag.search import semantic_search


class BookRetriever(BaseRetriever):
    """Retrieve book chunks through the existing pgvector search."""

    k: int = 5
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1)

    def _get_relevant_documents(self, query: str, *, run_manager) -> list[Document]:
        if self.k < 1:
            raise ValueError("k must be greater than zero")

        results = semantic_search(query, limit=self.k, book_ids=self.book_ids)
        return [
            Document(
                page_content=result.text,
                metadata={
                    "book_title": result.book_title,
                    "book_id": result.book_id,
                    "chapter_number": result.chapter_number,
                    "chunk_index": result.chunk_index,
                    "similarity": result.similarity,
                },
            )
            for result in results
        ]
