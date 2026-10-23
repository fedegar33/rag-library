"""Database engine, models, and schema initialization."""

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
    func,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIMENSION = 1536


class Base(DeclarativeBase):
    """Base class for application models."""


class Book(Base):
    """An ingested EPUB and its normalized metadata."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(500), nullable=True)
    identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    categories: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    cover_data: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    cover_media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(1000))
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["BookChunk"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )


class BookChunk(Base):
    """A text chunk and its embedding belonging to a book."""

    __tablename__ = "book_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), index=True
    )
    chapter_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    loader_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION))

    book: Mapped[Book] = relationship(back_populates="chunks")

    __table_args__ = (Index("ix_book_chunks_chapter_number", "chapter_number"),)


def create_database_engine(database_url: str):
    """Create a SQLAlchemy engine for PostgreSQL."""
    return create_engine(database_url, pool_pre_ping=True)


def initialize_schema(engine) -> None:
    """Enable pgvector and create application tables if needed."""
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        if inspect(connection).has_table("books"):
            columns = {
                column["name"] for column in inspect(connection).get_columns("books")
            }
            additions = {
                "categories": "JSONB NOT NULL DEFAULT '[]'::jsonb",
                "cover_data": "BYTEA",
                "cover_media_type": "VARCHAR(64)",
            }
            for name, definition in additions.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE books ADD COLUMN {name} {definition}")
                    )
        if inspect(connection).has_table("book_chunks"):
            columns = {
                column["name"]
                for column in inspect(connection).get_columns("book_chunks")
            }
            if "chapter_number" not in columns:
                connection.execute(
                    text("ALTER TABLE book_chunks ADD COLUMN chapter_number INTEGER")
                )
        Base.metadata.create_all(connection)
        for index in BookChunk.__table__.indexes:
            index.create(connection, checkfirst=True)
