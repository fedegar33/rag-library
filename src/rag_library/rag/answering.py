"""Grounded question-answering over ingested books."""

from dataclasses import dataclass

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from rag_library.config import get_settings
from rag_library.rag.retriever import BookRetriever
from rag_library.rag.search import RetrievalMethod, SearchResult

FALLBACK_ANSWER = "I couldn't find that in the ingested books."
SYSTEM_PROMPT = (
    "You answer questions in English using only the supplied book context.\n"
    "Do not use general knowledge or invent facts. If the context does not answer "
    f"the question, reply exactly: {FALLBACK_ANSWER}\n"
    "Keep the answer concise and directly answer the question when the context "
    "supports it."
)


@dataclass(frozen=True)
class AskResponse:
    """An answer and the chunks supplied to the chat model."""

    answer: str
    sources: list[SearchResult]


def _format_documents(documents) -> str:
    def relevance(metadata):
        if metadata.get("rrf_score") is not None:
            return f"RRF score: {metadata['rrf_score']:.6f}"
        if metadata.get("bm25_score") is not None:
            return f"BM25 score: {metadata['bm25_score']:.4f}"
        return f"Relevance: {float(metadata.get('similarity') or 0):.4f}"

    return "\n\n".join(
        f"[Book: {document.metadata.get('book_title', '?')}; "
        f"Chapter: {document.metadata.get('chapter_number') or '?'}; "
        f"Chunk: {document.metadata.get('chunk_index', '?')}; "
        f"{relevance(document.metadata)}]\n"
        f"{document.page_content}"
        for document in documents
    )


def _documents_to_results(documents) -> list[SearchResult]:
    return [
        SearchResult(
            book_title=document.metadata["book_title"],
            book_id=document.metadata.get("book_id"),
            chapter_number=document.metadata.get("chapter_number"),
            chunk_index=document.metadata["chunk_index"],
            text=document.page_content,
            similarity=document.metadata["similarity"],
            bm25_score=document.metadata.get("bm25_score"),
            rrf_score=document.metadata.get("rrf_score"),
            vector_rank=document.metadata.get("vector_rank"),
            bm25_rank=document.metadata.get("bm25_rank"),
        )
        for document in documents
    ]


def ask_question(
    question: str,
    top_k: int = 5,
    *,
    book_ids: list[int],
    method: RetrievalMethod = "vector",
    candidate_limit: int | None = None,
) -> AskResponse:
    """Answer one question using the most relevant book chunks."""
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")
    if top_k < 1:
        raise ValueError("top_k must be greater than zero")

    documents = BookRetriever(
        k=top_k,
        book_ids=book_ids,
        method=method,
        candidate_limit=candidate_limit,
    ).invoke(question)
    sources = _documents_to_results(documents)
    if not documents:
        return AskResponse(FALLBACK_ANSWER, sources)

    settings = get_settings()
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", "Question:\n{question}\n\nBook context:\n{context}"),
        ]
    )
    messages = prompt.invoke(
        {
            "question": question,
            "context": _format_documents(documents),
        }
    )
    response = ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
    ).invoke(messages)
    return AskResponse(str(response.content).strip(), sources)
