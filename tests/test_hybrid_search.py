"""Offline checks of fusion arithmetic, source identity, and hybrid CLI routing."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from rag_library.cli.search import format_results, main
from rag_library.rag.hybrid_search import hybrid_search, reciprocal_rank_fusion
from rag_library.rag.search import SearchResult


def candidate(book_id, chunk_index, *, similarity=None, bm25_score=None):
    return SearchResult(
        book_title=f"Book {book_id}",
        book_id=book_id,
        chapter_number=3,
        chunk_index=chunk_index,
        text="Same passage text",
        similarity=similarity,
        bm25_score=bm25_score,
    )


class FusionTests(unittest.TestCase):
    def test_overlap_adds_both_ranks_and_preserves_original_scores(self):
        vector = [candidate(7, 0, similarity=0.99), candidate(7, 1, similarity=0.5)]
        bm25 = [candidate(7, 1, bm25_score=2.0), candidate(8, 0, bm25_score=100.0)]
        results = reciprocal_rank_fusion(vector, bm25)
        self.assertEqual(
            [(r.book_id, r.chunk_index) for r in results], [(7, 1), (7, 0), (8, 0)]
        )
        top = results[0]
        self.assertAlmostEqual(top.rrf_score, 1 / 62 + 1 / 61)
        self.assertEqual((top.vector_rank, top.bm25_rank), (2, 1))
        self.assertEqual((top.similarity, top.bm25_score), (0.5, 2.0))
        self.assertEqual(
            (top.book_title, top.chapter_number, top.text),
            ("Book 7", 3, "Same passage text"),
        )
        self.assertIsNone(results[1].bm25_score)
        self.assertIsNone(results[2].similarity)
        self.assertIsNone(vector[1].rrf_score)

    def test_identity_includes_book_and_ties_are_deterministic(self):
        results = reciprocal_rank_fusion(
            [candidate(8, 0, similarity=0.9)], [candidate(7, 0, bm25_score=1.0)]
        )
        self.assertEqual([r.book_id for r in results], [7, 8])
        self.assertEqual(results[0].rrf_score, results[1].rrf_score)
        self.assertEqual(len(reciprocal_rank_fusion(results[:1], [], limit=1)), 1)

    def test_duplicate_within_branch_contributes_only_once(self):
        result = candidate(7, 0, similarity=0.9)
        results = reciprocal_rank_fusion([result, result], [])
        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0].rrf_score, 1 / 61)
        self.assertEqual(results[0].vector_rank, 1)

    def test_final_limit_applied_after_fusion(self):
        results = reciprocal_rank_fusion(
            [candidate(7, 0), candidate(7, 1)], [candidate(7, 1)], limit=1
        )
        self.assertEqual([r.chunk_index for r in results], [1])

    def test_empty_branches_keep_available_ranking(self):
        for vector, bm25 in [
            ([candidate(7, 1), candidate(7, 0)], []),
            ([], [candidate(7, 1), candidate(7, 0)]),
        ]:
            results = reciprocal_rank_fusion(vector, bm25)
            self.assertEqual([r.chunk_index for r in results], [1, 0])
            self.assertAlmostEqual(results[0].rrf_score, 1 / 61)
        self.assertEqual(reciprocal_rank_fusion([], []), [])

    def test_missing_identity_and_invalid_limit_fail(self):
        with self.assertRaisesRegex(ValueError, "book ID"):
            reciprocal_rank_fusion([candidate(None, 0)], [])
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            reciprocal_rank_fusion([], [], limit=0)


class HybridSearchTests(unittest.TestCase):
    def setUp(self):
        self.vector = self.enterContext(
            patch("rag_library.rag.hybrid_search.semantic_search", return_value=[])
        )
        self.bm25 = self.enterContext(
            patch("rag_library.rag.hybrid_search.bm25_search", return_value=[])
        )

    def test_identical_query_scope_and_chapters_with_deeper_candidates(self):
        self.vector.return_value = [candidate(7, 0, similarity=0.8)]
        self.bm25.return_value = [candidate(7, 0, bm25_score=3.0)]
        results = hybrid_search("  cat  ", chapters=[3], book_ids=[7, 8, 7])
        for search in [self.vector, self.bm25]:
            search.assert_called_once_with("cat", 20, [3], book_ids=[7, 8])
        self.assertAlmostEqual(results[0].rrf_score, 2 / 61)

    def test_depth_increases_with_limit_and_supports_override(self):
        for limit, override, expected in [(30, None, 30), (5, 40, 40)]:
            hybrid_search("cat", limit=limit, candidate_limit=override, book_ids=[7])
            for search in [self.vector, self.bm25]:
                self.assertEqual(search.call_args.args[1], expected)

    def test_invalid_arguments_fail_before_retrieval(self):
        for kwargs in [
            {"query": " "},
            {"limit": 0},
            {"candidate_limit": 4},
            {"candidate_limit": 0},
            {"book_ids": []},
            {"book_ids": [-1]},
        ]:
            arguments = {"query": "cat", "book_ids": [7], **kwargs}
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                hybrid_search(**arguments)
        self.vector.assert_not_called()
        self.bm25.assert_not_called()

    def test_branch_errors_propagate_instead_of_returning_partial_results(self):
        self.vector.side_effect = RuntimeError("Embedding failed")
        with self.assertRaisesRegex(RuntimeError, "Embedding failed"):
            hybrid_search("cat", book_ids=[7])
        self.bm25.assert_not_called()
        self.vector.side_effect = None
        self.vector.return_value = [candidate(7, 0, similarity=0.8)]
        self.bm25.side_effect = RuntimeError("Index failed")
        with self.assertRaisesRegex(RuntimeError, "Index failed"):
            hybrid_search("cat", book_ids=[7])


class HybridCliTests(unittest.TestCase):
    @patch("rag_library.catalog.list_books", return_value=[{"id": 7}, {"id": 8}])
    @patch("rag_library.cli.search.hybrid_search", return_value=[])
    def test_cli_routes_attachments_filters_and_candidate_override(self, search, books):
        with (
            patch(
                "sys.argv",
                [
                    "search",
                    "cat",
                    "--method",
                    "hybrid",
                    "--book-id",
                    "7",
                    "--book-id",
                    "8",
                    "--limit",
                    "10",
                    "--candidate-limit",
                    "30",
                    "--chapter",
                    "2,3",
                ],
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        search.assert_called_once_with(
            "cat", 10, [2, 3], book_ids=[7, 8], candidate_limit=30
        )

    @patch("rag_library.cli.search.resolve_book_id", return_value=7)
    @patch(
        "rag_library.cli.search.hybrid_search",
        side_effect=RuntimeError("Embedding failed"),
    )
    def test_cli_reports_failure(self, search, resolve):
        output = io.StringIO()
        with (
            patch("sys.argv", ["search", "cat", "--method", "hybrid"]),
            redirect_stderr(output),
        ):
            self.assertEqual(main(), 1)
        self.assertIn("Search failed: Embedding failed", output.getvalue())
        search.assert_called_once_with(
            "cat", 5, None, book_ids=[7], candidate_limit=None
        )

    @patch("rag_library.cli.search.resolve_book_id")
    def test_invalid_candidate_options_fail_before_catalog_or_retrieval(self, resolve):
        for options in [
            ["--method", "hybrid", "--candidate-limit", "4"],
            ["--method", "hybrid", "--candidate-limit", "0"],
            ["--method", "bm25", "--candidate-limit", "20"],
        ]:
            with (
                patch("sys.argv", ["search", "cat", *options]),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main()
            self.assertEqual(error.exception.code, 2)
        resolve.assert_not_called()

    def test_verbose_reports_both_branch_ranks_and_original_scores(self):
        results = reciprocal_rank_fusion(
            [candidate(7, 0, similarity=0.9)],
            [candidate(7, 0, bm25_score=2.0), candidate(8, 0, bm25_score=1.0)],
        )
        compact = format_results(results)
        self.assertIn("RRF score", compact)
        self.assertIn("0.032787", compact)
        verbose = format_results(results, verbose=True)
        for text in [
            "Vector rank: 1",
            "Cosine similarity: 0.9",
            "BM25 rank: 1",
            "BM25 score: 2.0",
            "Vector rank: None",
            "book 8 · chapter 3 · chunk 0",
            "Same passage text",
        ]:
            self.assertIn(text, verbose)


if __name__ == "__main__":
    unittest.main()
