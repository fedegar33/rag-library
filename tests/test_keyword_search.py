"""Offline BM25 ranking and CLI comparisons, with only database I/O mocked."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from rag_library.cli.search import format_results, main
from rag_library.config import DatabaseSettings
from rag_library.rag.keyword_search import bm25_search
from rag_library.rag.search import SearchResult


class KeywordSearchTests(unittest.TestCase):
    def setUp(self):
        settings = self.enterContext(
            patch("rag_library.rag.keyword_search.get_database_settings")
        )
        settings.return_value = SimpleNamespace(database_url="unused")
        self.engine = self.enterContext(
            patch("rag_library.rag.keyword_search.create_database_engine")
        ).return_value
        session = self.enterContext(patch("rag_library.rag.keyword_search.Session"))
        self.connection = session.return_value.__enter__.return_value
        self.connection.scalars.return_value = [7, 8]
        self.rows = [
            (7, "First", 1, 0, "Winston Churchill is the cat's full name."),
            (7, "First", 2, 1, "Church is a cat. Ellie owns Church."),
            (8, "Second", None, 0, "A quiet road near the house."),
        ]
        self.connection.execute.return_value.all.side_effect = lambda: self.rows
        self.embeddings = self.enterContext(
            patch("rag_library.rag.search.OpenAIEmbeddings")
        )

    def tearDown(self):
        self.embeddings.assert_not_called()

    def test_real_ranking_and_source_provenance(self):
        matches = bm25_search("WINSTON Churchill", limit=20, book_ids=[7, 8])
        self.assertEqual(len(matches), 1)
        result = matches[0]
        self.assertEqual(
            (
                result.book_id,
                result.book_title,
                result.chapter_number,
                result.chunk_index,
                result.text,
            ),
            self.rows[0],
        )
        self.assertGreater(result.bm25_score, 0)
        self.assertIsNone(result.similarity)
        self.engine.dispose.assert_called_once()

    def test_attachment_filter_in_sql_without_embeddings_or_early_limit(self):
        bm25_search("cat", chapters=[2], limit=1, book_ids=[7, 8, 7])
        statement = self.connection.execute.call_args.args[0]
        self.assertEqual(statement.compile().params["book_id_1"], [7, 8])
        self.assertNotIn("chapter_number_1", statement.compile().params)
        self.assertIsNone(statement._limit_clause)
        self.assertNotIn("embedding", str(statement))
        self.assertIn("ORDER BY books.id", str(statement))

    def test_chapter_filter_precedes_top_k_and_keeps_corpus_statistics(self):
        self.rows = [
            (7, "First", 1, 0, "churchill churchill"),
            (7, "First", 2, 1, "churchill and the long road near a house"),
            (8, "Second", 3, 0, "a quiet garden"),
        ]
        unrestricted = bm25_search("churchill", book_ids=[7, 8])
        self.assertEqual(unrestricted[0].chapter_number, 1)
        restricted = bm25_search("churchill", chapters=[2], limit=1, book_ids=[7, 8])
        self.assertEqual(len(restricted), 1)
        self.assertEqual(restricted[0].chapter_number, 2)
        self.assertEqual(restricted[0].bm25_score, unrestricted[1].bm25_score)
        self.assertEqual(bm25_search("churchill", chapters=[99], book_ids=[7]), [])

    def test_selected_books_are_scored_together(self):
        self.rows = [
            (7, "First", 1, 0, "cat"),
            (8, "Second", 1, 0, "cat"),
            (8, "Second", 1, 1, "road"),
        ]
        together = bm25_search("cat", book_ids=[7, 8])
        self.assertEqual([result.book_id for result in together], [7, 8])
        self.assertEqual(together[0].bm25_score, together[1].bm25_score)
        self.rows = self.rows[:1]
        alone = bm25_search("cat", book_ids=[7])
        self.assertNotEqual(alone[0].bm25_score, together[0].bm25_score)

    def test_no_matches_and_empty_tokens_do_not_return_arbitrary_chunks(self):
        for query in ["unseenword", "the and", "!!!"]:
            with self.subTest(query=query):
                self.assertEqual(bm25_search(query, book_ids=[7]), [])
        for rows in [
            [],
            [(7, "First", None, 0, "the and !!!")],
            [(7, "First", None, 0, "!!!")],
        ]:
            self.rows = rows
            self.assertEqual(bm25_search("Churchill", book_ids=[7]), [])

    def test_empty_chunk_preserves_index_alignment_and_no_stemming(self):
        self.rows = [
            (7, "First", None, 0, "!!!"),
            (7, "First", 2, 1, "cats"),
            (8, "Second", 3, 0, "cat"),
        ]
        matches = bm25_search("cat", book_ids=[7, 8])
        self.assertEqual([(r.book_id, r.chunk_index) for r in matches], [(8, 0)])

    def test_rebuild_observes_changed_database_chunks(self):
        self.assertTrue(bm25_search("Churchill", book_ids=[7]))
        self.rows = [(7, "First", 1, 0, "An entirely different passage")]
        self.assertEqual(bm25_search("Churchill", book_ids=[7]), [])

    def test_unknown_attachment_fails_without_loading_chunks(self):
        with self.assertRaisesRegex(ValueError, "Unknown book IDs:.*99"):
            bm25_search("Churchill", book_ids=[7, 99])
        self.connection.execute.assert_not_called()
        self.engine.dispose.assert_called_once()

    def test_invalid_inputs_fail_before_database_access(self):
        for arguments in [
            {"query": "  ", "book_ids": [7]},
            {"query": "cat", "limit": 0, "book_ids": [7]},
            {"query": "cat", "book_ids": []},
            {"query": "cat", "book_ids": [0]},
        ]:
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                bm25_search(**arguments)
        self.engine.dispose.assert_not_called()


class SearchCliTests(unittest.TestCase):
    @patch("rag_library.catalog.list_books")
    @patch("rag_library.cli.search.semantic_search", return_value=[])
    @patch("rag_library.cli.search.bm25_search", return_value=[])
    def test_repeated_attachments_dispatch_both_methods(self, bm25, vector, books):
        books.return_value = [
            {"id": 7, "title": "First", "language": "en"},
            {"id": 8, "title": "Second", "language": "en"},
        ]
        for method, search in [("bm25", bm25), ("vector", vector)]:
            with (
                patch(
                    "sys.argv",
                    [
                        "search",
                        "cat",
                        "--method",
                        method,
                        "--book-id",
                        "7",
                        "--book-id",
                        "8",
                        "--book-id",
                        "7",
                        "--chapter",
                        "1,2",
                        "--limit",
                        "10",
                    ],
                ),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            search.assert_called_once_with("cat", 10, [1, 2], book_ids=[7, 8])

    @patch("rag_library.cli.search.resolve_book_id", return_value=7)
    @patch("rag_library.cli.search.bm25_search", return_value=[])
    def test_bm25_singleton_selection(self, bm25, resolve):
        with (
            patch("sys.argv", ["search", "cat", "--method", "bm25"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        resolve.assert_called_once_with(None)
        bm25.assert_called_once_with("cat", 5, None, book_ids=[7])

    @patch("rag_library.catalog.list_books", return_value=[{"id": 7}])
    @patch("rag_library.cli.search.bm25_search")
    def test_invalid_attachment_aborts_before_search(self, bm25, books):
        output = io.StringIO()
        with (
            patch(
                "sys.argv",
                [
                    "search",
                    "cat",
                    "--method",
                    "bm25",
                    "--book-id",
                    "7",
                    "--book-id",
                    "99",
                ],
            ),
            redirect_stderr(output),
        ):
            self.assertEqual(main(), 1)
        self.assertIn("Unknown book IDs", output.getvalue())
        bm25.assert_not_called()

    def test_output_labels_scores_and_preserves_provenance(self):
        for similarity, bm25_score, label in [
            (0.8, None, "Cosine similarity"),
            (None, 2.5, "BM25 score"),
        ]:
            result = SearchResult("First", 42, "Evidence", similarity, 3, 7, bm25_score)
            compact = format_results([result])
            self.assertIn(label, compact)
            self.assertIn("7", compact)
            self.assertIn("42", compact)
            verbose = format_results([result], verbose=True)
            self.assertIn("First · book 7 · chapter 3 · chunk 42", verbose)

    def test_database_only_settings_need_no_model_credentials(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = DatabaseSettings(database_url="unused", _env_file=None)
        self.assertEqual(settings.database_url, "unused")


if __name__ == "__main__":
    unittest.main()
