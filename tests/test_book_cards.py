"""EPUB assets, metadata-only persistence, and public card/cover contracts."""

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ebooklib import epub
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import JSON, MetaData, create_engine, event, select
from sqlalchemy.orm import Session
from test_attached_context import ScriptedModel, book

from rag_library.agent.agent import build_agent
from rag_library.agent.context import AgentContext
from rag_library.agent.tools import list_available_books
from rag_library.api.streaming import stream_chat
from rag_library.catalog import get_book_cover, list_books
from rag_library.database import Book, BookChunk
from rag_library.ingestion.metadata import extract_book_presentation
from rag_library.ingestion.pipeline import enrich_book, ingest_book, sha256_file
from rag_library.main import app

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/x8AAwMCAO+aX1sAAAAASUVORK5CYII="
)


def write_epub(folder, cover="epub3", categories=("Horror", "Fiction")):
    book = epub.EpubBook()
    book.set_identifier("card-test")
    book.set_title("Synthetic Book")
    book.set_language("en")
    book.add_author("A Writer")
    for category in categories:
        book.add_metadata("DC", "subject", category)
    chapter = epub.EpubHtml(uid="story", file_name="story.xhtml")
    chapter.content = "<h1>1</h1><p>A story about vanity.</p>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.toc = [epub.Link("story.xhtml", "1", "story")]
    book.add_item(epub.EpubNcx())
    if cover == "epub3":
        book.set_cover("images/cover.png", PNG, create_page=False)
        # Prove the manifest marker alone works, without legacy metadata.
        book.metadata.pop(None, None)
    elif cover in ("legacy", "guide", "unsupported"):
        image = epub.EpubImage(
            uid="front-image", file_name="images/front.png", media_type="image/png"
        )
        image.content = PNG if cover != "unsupported" else b"<svg/>"
        book.add_item(image)
        if cover == "guide":
            page = epub.EpubHtml(uid="cover-page", file_name="pages/cover.xhtml")
            page.content = '<img src="../images/front.png" />'
            book.add_item(page)
            book.guide = [{"type": "cover", "href": "pages/cover.xhtml#top"}]
        else:
            book.add_metadata(
                None, "meta", "", {"name": "cover", "content": "front-image"}
            )
    path = Path(folder) / "book.epub"
    epub.write_epub(str(path), book)
    return path


class PresentationTests(unittest.TestCase):
    def test_declared_cover_formats_and_all_subjects(self):
        for kind in ("epub3", "legacy", "guide"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                path = write_epub(
                    folder, cover=kind, categories=("Horror", "Maine", "Horror")
                )
                result = extract_book_presentation(path)
                self.assertEqual(result.cover_data, PNG)
                self.assertEqual(result.cover_media_type, "image/png")
                self.assertEqual(result.categories, ["Horror", "Maine", "Horror"])

    def test_missing_or_unsupported_cover_does_not_guess_an_image(self):
        for kind in (None, "unsupported"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as folder:
                result = extract_book_presentation(
                    write_epub(folder, cover=kind, categories=())
                )
                self.assertEqual(result.categories, [])
                self.assertIsNone(result.cover_data)
                self.assertIsNone(result.cover_media_type)


class CardPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        # Exercise real ORM transactions offline; only PostgreSQL-specific DDL
        # is adapted, and embeddings are still round-tripped through Vector.
        metadata = MetaData()
        for original in (Book.__table__, BookChunk.__table__):
            table = original.to_metadata(metadata)
            for column in table.c:
                if column.name in ("categories", "loader_metadata"):
                    column.type = JSON()
                if column.name == "categories":
                    column.server_default = None
        metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)

    def seed_book(self, path):
        with Session(self.engine) as session, session.begin():
            book = Book(
                title="Existing book",
                authors="An Author",
                source_filename=path.name,
                content_sha256=sha256_file(path),
            )
            session.add(book)
            session.flush()
            session.add(
                BookChunk(
                    book_id=book.id,
                    chunk_index=0,
                    chapter_number=1,
                    text="Existing passage",
                    embedding=[0.25] * 1536,
                )
            )
            return book.id

    @patch("rag_library.ingestion.pipeline.initialize_schema")
    @patch("rag_library.ingestion.pipeline.create_database_engine")
    @patch("rag_library.ingestion.pipeline.get_database_settings")
    @patch("rag_library.ingestion.pipeline.OpenAIEmbeddings")
    def test_enrichment_preserves_identity_chunks_and_vectors(
        self, embeddings, settings, engine, schema
    ):
        engine.return_value = self.engine
        settings.return_value = SimpleNamespace(database_url="unused")
        with tempfile.TemporaryDirectory() as folder:
            path = write_epub(folder)
            book_id = self.seed_book(path)
            # A normal pool dispose would discard this in-memory test database.
            with patch.object(self.engine, "dispose"):
                updated = enrich_book(path)
                self.assertEqual(updated.id, book_id)
                self.assertEqual(updated.title, "Existing book")
                with Session(self.engine) as session:
                    saved = session.get(Book, book_id)
                    chunks = session.scalars(select(BookChunk)).all()
                    self.assertEqual(saved.categories, ["Horror", "Fiction"])
                    self.assertEqual(saved.cover_data, PNG)
                    self.assertEqual(saved.cover_media_type, "image/png")
                    self.assertEqual(len(chunks), 1)
                    self.assertEqual(chunks[0].text, "Existing passage")
                    self.assertEqual(chunks[0].book_id, book_id)
                    self.assertEqual(list(chunks[0].embedding), [0.25] * 1536)
                # Repeated enrichment is safe and keeps the same ID.
                self.assertEqual(enrich_book(path).id, book_id)
        embeddings.assert_not_called()

    @patch("rag_library.ingestion.pipeline.initialize_schema")
    @patch("rag_library.ingestion.pipeline.create_database_engine")
    @patch("rag_library.ingestion.pipeline.get_database_settings")
    def test_enrichment_rejects_unmatched_epub_without_creating_books(
        self, settings, engine, schema
    ):
        engine.return_value = self.engine
        settings.return_value = SimpleNamespace(database_url="unused")
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(self.engine, "dispose"),
        ):
            with self.assertRaisesRegex(ValueError, "No ingested book"):
                enrich_book(write_epub(folder))
            with Session(self.engine) as session:
                self.assertEqual(session.scalars(select(Book)).all(), [])

    @patch("rag_library.ingestion.pipeline.initialize_schema")
    @patch("rag_library.ingestion.pipeline.create_database_engine")
    @patch("rag_library.ingestion.pipeline.get_settings")
    @patch("rag_library.ingestion.pipeline.OpenAIEmbeddings")
    def test_new_ingestion_persists_presentation(
        self, embeddings, settings, engine, schema
    ):
        engine.return_value = self.engine
        settings.return_value = SimpleNamespace(
            database_url="unused", openai_embedding_model="fake", openai_api_key="fake"
        )
        embeddings.return_value.embed_documents.return_value = [[0.25] * 1536]
        with tempfile.TemporaryDirectory() as folder:
            result = ingest_book(write_epub(folder))
        with Session(self.engine) as session:
            saved = session.get(Book, result.id)
            self.assertEqual(saved.categories, ["Horror", "Fiction"])
            self.assertEqual(saved.cover_data, PNG)

    @patch("rag_library.catalog.create_database_engine")
    @patch("rag_library.catalog.get_database_settings")
    def test_catalog_projection_excludes_image_bytes_and_serves_cover_separately(
        self, settings, engine
    ):
        engine.return_value = self.engine
        settings.return_value = SimpleNamespace(database_url="unused")
        with Session(self.engine) as session, session.begin():
            for title, cover in [("Z book", None), ("A book", PNG)]:
                session.add(
                    Book(
                        title=title,
                        source_filename=title,
                        content_sha256=title,
                        cover_data=cover,
                        cover_media_type="image/png" if cover else None,
                        categories=["Fiction"] if cover else [],
                    )
                )
        statements = []
        event.listen(
            self.engine,
            "before_cursor_execute",
            lambda conn, cursor, statement, *args: statements.append(statement),
        )
        with patch.object(self.engine, "dispose"):
            rows = list_books()
            self.assertEqual([row["title"] for row in rows], ["A book", "Z book"])
            self.assertEqual(rows[0]["categories"], ["Fiction"])
            self.assertEqual(rows[0]["cover_url"], f"/books/{rows[0]['id']}/cover")
            self.assertIsNone(rows[1]["cover_url"])
            self.assertNotIn("cover_data", rows[0])
            self.assertNotIn("books.cover_data,", statements[-1])
            self.assertEqual(get_book_cover(rows[0]["id"]), (PNG, "image/png"))
            self.assertIsNone(get_book_cover(rows[1]["id"]))
            self.assertIsNone(get_book_cover(999))


class CardContractTests(unittest.TestCase):
    @patch("rag_library.catalog.list_books")
    def test_real_graph_streams_public_card_data_without_internal_fields(self, catalog):
        catalog.return_value = [
            {**book(), "categories": ["Horror"], "cover_url": "/books/7/cover"}
        ]
        graph = build_agent(
            ScriptedModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            dict(name="list_available_books", args={}, id="cards")
                        ],
                    ),
                    AIMessage(content="These are the available books."),
                ]
            ),
            structured_output=False,
        )

        async def collect():
            return [
                frame
                async for frame in stream_chat(
                    graph, "Which books?", AgentContext((7,))
                )
            ]

        frames = asyncio.run(collect())
        events = [
            json.loads(frame.removeprefix("data: ").strip()) for frame in frames[:-1]
        ]
        output = next(
            event["output"]
            for event in events
            if event["type"] == "tool-output-available"
        )
        self.assertEqual(
            output,
            {
                "books": [
                    {
                        "id": 7,
                        "title": "Book",
                        "authors": None,
                        "categories": ["Horror"],
                        "cover_url": "/books/7/cover",
                    }
                ]
            },
        )
        self.assertNotIn("content_sha256", json.dumps(output))
        self.assertEqual(events[-1]["type"], "finish")

    @patch("rag_library.catalog.list_books")
    def test_invalid_card_metadata_is_rejected(self, catalog):
        catalog.return_value = [{**book(), "categories": "Horror"}]
        with self.assertRaises(ValueError):
            list_available_books.func()

    @patch("rag_library.api.routes.get_book_cover", return_value=(PNG, "image/png"))
    def test_cover_endpoint_serves_exact_bytes_and_content_type(self, cover):
        response = TestClient(app).get("/books/7/cover")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PNG)
        self.assertEqual(response.headers["content-type"], "image/png")
        cover.assert_called_once_with(7)

    @patch("rag_library.api.routes.get_book_cover", return_value=None)
    def test_missing_cover_and_invalid_id(self, cover):
        client = TestClient(app)
        self.assertEqual(client.get("/books/7/cover").status_code, 404)
        self.assertEqual(client.get("/books/0/cover").status_code, 422)
        cover.assert_called_once_with(7)

    @patch("rag_library.api.routes.get_book_cover", side_effect=RuntimeError("secret"))
    def test_cover_database_failure_is_generic(self, cover):
        with self.assertLogs("rag_library.api.routes", level="ERROR"):
            response = TestClient(app).get("/books/7/cover")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.text)
