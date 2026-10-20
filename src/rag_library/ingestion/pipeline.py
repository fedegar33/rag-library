"""Core EPUB loading, chunking, embedding, and persistence workflow."""

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import select
from sqlalchemy.orm import Session

from rag_library.config import get_settings
from rag_library.database import (
    Book,
    BookChunk,
    create_database_engine,
    initialize_schema,
)
from rag_library.ingestion.epub import EpubExtractor

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
CHUNK_SEPARATORS = ["\n\n", "\n", " ", ""]


def validate_epub_path(file_path: str | Path) -> Path:
    """Validate and return an EPUB path."""
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise ValueError(f"EPUB file does not exist: {path}")
    if path.suffix.lower() != ".epub":
        raise ValueError(f"Input file must have an .epub extension: {path}")
    return path


def sha256_file(file_path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with file_path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _first_metadata(metadata: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if value is not None and value != "":
            if isinstance(value, list):
                return ", ".join(str(item) for item in value)
            return str(value)
    return None


def _book_metadata(documents: Sequence[Document], file_path: Path) -> dict[str, Any]:
    metadata = documents[0].metadata if documents else {}
    return {
        "title": _first_metadata(metadata, "title", "dc:title") or file_path.stem,
        "authors": _first_metadata(metadata, "creator", "author", "authors"),
        "language": _first_metadata(metadata, "language", "dc:language"),
        "publisher": _first_metadata(metadata, "publisher", "dc:publisher"),
        "identifier": _first_metadata(metadata, "identifier", "dc:identifier"),
    }


def chunk_documents(documents: Sequence[Document]) -> list[Document]:
    """Split chapter documents while preferring preserved block boundaries."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHUNK_SEPARATORS,
    )
    return splitter.split_documents(list(documents))


def ingest_book(
    file_path: str | Path,
) -> Book:
    """Ingest one EPUB and return its persisted book record."""
    path = validate_epub_path(file_path)
    settings = get_settings()
    content_hash = sha256_file(path)

    print(f"Loading EPUB: {path}")
    documents = EpubExtractor().load(path)
    if not documents:
        raise ValueError(f"EPUB contains no readable documents: {path}")

    chunks = chunk_documents(documents)
    if not chunks:
        raise ValueError(f"EPUB contains no text after chunking: {path}")
    print(f"Created {len(chunks)} text chunks")

    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    print(f"Creating embeddings with {settings.openai_embedding_model}")
    vectors = embeddings.embed_documents([chunk.page_content for chunk in chunks])

    engine = create_database_engine(settings.database_url)
    initialize_schema(engine)
    metadata = _book_metadata(documents, path)

    with Session(engine, expire_on_commit=False) as session, session.begin():
        existing_book = session.scalar(
            select(Book).where(Book.content_sha256 == content_hash).with_for_update()
        )
        if existing_book is not None:
            session.delete(existing_book)
            session.flush()

        book = Book(
            **metadata,
            source_filename=path.name,
            content_sha256=content_hash,
        )
        session.add(book)
        session.flush()
        session.add_all(
            BookChunk(
                book_id=book.id,
                chapter_number=chunk.metadata.get("chapter"),
                chunk_index=index,
                text=chunk.page_content,
                loader_metadata=chunk.metadata or None,
                embedding=vector,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        )
        session.flush()
        session.refresh(book)
        print(f"Persisted book {book.id} with {len(chunks)} chunks")
        chapter_count = len(
            {
                document.metadata["chapter"]
                for document in documents
                if document.metadata.get("chapter") is not None
            }
        )
        print()
        print("Book ingestion complete")
        print(f"  ID: {book.id}")
        print(f"  Title: {book.title}")
        print(f"  Author(s): {book.authors or 'Unknown'}")
        print(f"  Numbered chapters: {chapter_count}")
        print(f"  Chunks: {len(chunks)}")
        print(f"  Source: {book.source_filename}")
        return book
