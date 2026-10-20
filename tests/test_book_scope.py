"""Offline checks that every retrieval uses a valid, explicit book scope."""

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from rag_library.catalog import resolve_book_id
from rag_library.cli.ask import main as ask_main
from rag_library.cli.search import main as search_main
from rag_library.rag.answering import AskResponse, ask_question
from rag_library.rag.retriever import BookRetriever
from rag_library.rag.search import SearchResult, semantic_search


class BookScopeTests(unittest.TestCase):
    @patch("rag_library.catalog.list_books")
    def test_catalog_selection_never_defaults_to_all_books(self, books):
        books.return_value = [{"id": 7, "title": "First", "language": "en"}]
        self.assertEqual(resolve_book_id(), 7)
        self.assertEqual(resolve_book_id(7), 7)
        books.return_value.append({"id": 8, "title": "Second", "language": "es"})
        with self.assertRaisesRegex(ValueError, "Select one book"):
            resolve_book_id()
        self.assertEqual(resolve_book_id(8), 8)
        with self.assertRaisesRegex(ValueError, "99 is unavailable"):
            resolve_book_id(99)
        books.return_value = []
        with self.assertRaisesRegex(ValueError, "No books"):
            resolve_book_id()

    @patch("rag_library.catalog.list_books")
    def test_invalid_id_fails_before_reading_catalog(self, books):
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            resolve_book_id(0)
        books.assert_not_called()

    @patch("rag_library.rag.search.get_settings")
    @patch("rag_library.rag.search.create_database_engine")
    @patch("rag_library.rag.search.Session")
    @patch("rag_library.rag.search.OpenAIEmbeddings")
    def test_sql_scope_and_content_only_embedding(
        self, embeddings, session, engine, settings
    ):
        settings.return_value = SimpleNamespace(
            database_url="unused",
            openai_embedding_model="unused",
            openai_api_key="unused",
        )
        connection = session.return_value.__enter__.return_value
        connection.scalars.return_value = [7, 8]
        connection.execute.return_value.all.return_value = [
            (8, "Second", 3, 10, "Evidence", 0.2)
        ]
        embeddings.return_value.embed_query.return_value = [0.1] * 1536
        results = semantic_search(
            "Which town do they move to?", chapters=[3], book_ids=[7, 8]
        )
        statement = connection.execute.call_args.args[0]
        self.assertEqual(statement.compile().params["book_id_1"], [7, 8])
        self.assertEqual(statement.compile().params["chapter_number_1"], [3])
        embeddings.return_value.embed_query.assert_called_once_with(
            "Which town do they move to?"
        )
        self.assertEqual(results[0].book_id, 8)
        self.assertEqual(statement.compile().params["param_1"], 5)
        self.assertAlmostEqual(results[0].similarity, 0.8)
        engine.return_value.dispose.assert_called_once()

    @patch("rag_library.rag.search.get_settings")
    @patch("rag_library.rag.search.create_database_engine")
    @patch("rag_library.rag.search.Session")
    @patch("rag_library.rag.search.OpenAIEmbeddings")
    def test_unknown_book_does_not_create_embeddings(
        self, embeddings, session, engine, settings
    ):
        session.return_value.__enter__.return_value.scalars.return_value = [7]
        with self.assertRaisesRegex(ValueError, "Unknown book IDs"):
            semantic_search("Question", book_ids=[7, 99])
        embeddings.assert_not_called()
        engine.return_value.dispose.assert_called_once()

    @patch("rag_library.rag.retriever.semantic_search")
    def test_retriever_preserves_scope_and_provenance(self, search):
        search.return_value = [SearchResult("First", 1, "Evidence", 0.8, 2, book_id=7)]
        documents = BookRetriever(book_ids=[7]).invoke("Question")
        search.assert_called_once_with("Question", limit=5, book_ids=[7])
        self.assertEqual(documents[0].metadata["book_id"], 7)
        with self.assertRaises(ValueError):
            BookRetriever()

    @patch("rag_library.rag.answering.BookRetriever")
    @patch("rag_library.rag.answering.ChatOpenAI")
    def test_answering_always_constructs_scoped_retriever(self, model, retriever):
        retriever.return_value.invoke.return_value = []
        self.assertEqual(ask_question("Question", book_ids=[7]).sources, [])
        retriever.assert_called_once_with(
            k=5, book_ids=[7], method="vector", candidate_limit=None
        )
        model.assert_not_called()

    @patch("rag_library.cli.ask.resolve_book_id", return_value=7)
    @patch("rag_library.cli.ask.ask_question", return_value=AskResponse("Answer", []))
    def test_ask_cli_uses_singleton_selection(self, ask, resolve):
        with patch("sys.argv", ["ask", "Question"]), redirect_stdout(io.StringIO()):
            self.assertEqual(ask_main(), 0)
        resolve.assert_called_once_with(None)
        ask.assert_called_once_with(
            "Question", 5, book_ids=[7], method="vector", candidate_limit=None
        )

    @patch("rag_library.cli.search.resolve_book_id", return_value=8)
    @patch("rag_library.cli.search.semantic_search", return_value=[])
    def test_search_cli_uses_explicit_selection(self, search, resolve):
        with (
            patch("sys.argv", ["search", "Question", "--book-id", "8"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(search_main(), 0)
        resolve.assert_called_once_with(8)
        search.assert_called_once_with("Question", 5, None, book_ids=[8])


if __name__ == "__main__":
    unittest.main()
