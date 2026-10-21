"""Offline checks of candidate coverage, provenance, and rerank opt-in."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from rag_library.cli.search import format_results, main
from rag_library.rag.hybrid_search import hybrid_search, reciprocal_rank_fusion
from rag_library.rag.reranking import RERANK_MODEL, get_rerank_api_key, rerank_results
from rag_library.rag.search import SearchResult


def candidate(book_id, chunk_index):
    return SearchResult(
        book_title=f"Book {book_id}",
        book_id=book_id,
        chapter_number=1,
        chunk_index=chunk_index,
        text="Identical text across different sources",
        similarity=0.8,
        bm25_score=2.0,
    )


class RerankingTests(unittest.TestCase):
    def setUp(self):
        self.client = self.enterContext(
            patch("rag_library.rag.reranking.ClientV2")
        ).return_value
        self.client.__enter__.return_value = self.client
        self.pool = reciprocal_rank_fusion(
            [candidate(7, 0)], [candidate(8, 0), candidate(7, 0)]
        )

    def response(self, matches):
        self.client.rerank.return_value = SimpleNamespace(
            results=[
                SimpleNamespace(index=index, relevance_score=score)
                for index, score in matches
            ]
        )

    def test_response_indexes_preserve_identity_and_original_scores(self):
        self.response([(1, 0.95), (0, 0.4)])
        results = rerank_results(" cat ", self.pool, 5, api_key="test-key")
        self.client.rerank.assert_called_once_with(
            model="rerank-v5.0-pro",
            query="cat",
            documents=[r.text for r in self.pool],
            top_n=2,
            request_options={"max_retries": 0},
        )
        self.assertEqual(RERANK_MODEL, "rerank-v5.0-pro")
        self.assertEqual([r.book_id for r in results], [8, 7])
        for result, original, rank in zip(
            results, reversed(self.pool), [2, 1], strict=True
        ):
            self.assertEqual(result.rrf_rank, rank)
            self.assertEqual(
                replace(result, rerank_score=None, rrf_rank=None), original
            )
        self.assertIsNone(self.pool[0].rerank_score)
        verbose = format_results(results, verbose=True)
        self.assertIn("Rerank score: 0.950000", verbose)
        self.assertIn("RRF rank before reranking: 2", verbose)
        self.assertIn("BM25 rank: 1", verbose)

    def test_invalid_response_fails_instead_of_misattributing_sources(self):
        for matches in [
            [(2, 0.9)],
            [(-1, 0.9)],
            [(0, 0.9), (0, 0.8)],
            [(0, float("nan"))],
            [],
        ]:
            self.response(matches)
            with self.subTest(matches=matches), self.assertRaises(ValueError):
                rerank_results("cat", self.pool, len(matches) or 1, api_key="test")

    def test_empty_pool_skips_api_and_errors_propagate(self):
        self.assertEqual(rerank_results("cat", [], api_key="test"), [])
        self.client.rerank.assert_not_called()
        self.client.rerank.side_effect = RuntimeError("Cohere unavailable")
        with self.assertRaisesRegex(RuntimeError, "Cohere unavailable"):
            rerank_results("cat", self.pool, api_key="test")

    @patch("rag_library.rag.reranking.get_settings")
    def test_missing_key_reports_setup_instruction(self, settings):
        for key in [None, "", " "]:
            settings.return_value.cohere_api_key = key
            with self.assertRaisesRegex(ValueError, "COHERE_API_KEY"):
                get_rerank_api_key()


class HybridRerankTests(unittest.TestCase):
    def setUp(self):
        self.vector = self.enterContext(
            patch("rag_library.rag.hybrid_search.semantic_search", return_value=[])
        )
        self.bm25 = self.enterContext(
            patch("rag_library.rag.hybrid_search.bm25_search", return_value=[])
        )
        self.key = self.enterContext(
            patch(
                "rag_library.rag.hybrid_search.get_rerank_api_key", return_value="test"
            )
        )
        self.rerank = self.enterContext(
            patch("rag_library.rag.hybrid_search.rerank_results", return_value=[])
        )

    def test_entire_deduplicated_union_reaches_reranker_before_final_limit(self):
        self.vector.return_value = [candidate(7, i) for i in range(100)]
        self.bm25.return_value = [candidate(7, 0), candidate(8, 0)]
        hybrid_search(
            "cat",
            limit=5,
            book_ids=[7, 8],
            chapters=[1],
            candidate_limit=100,
            rerank=True,
        )
        for branch in [self.vector, self.bm25]:
            branch.assert_called_once_with("cat", 100, [1], book_ids=[7, 8])
        pool = self.rerank.call_args.args[1]
        self.assertEqual(len(pool), 101)
        self.assertEqual(len({(r.book_id, r.chunk_index) for r in pool}), 101)
        self.assertIn((7, 99), [(r.book_id, r.chunk_index) for r in pool])
        self.assertEqual(self.rerank.call_args.args[2], 5)
        self.assertEqual(self.rerank.call_args.kwargs, {"api_key": "test"})

    def test_explicit_disable_skips_credentials_and_reranking(self):
        hybrid_search("cat", book_ids=[7], rerank=False)
        self.key.assert_not_called()
        self.rerank.assert_not_called()

    def test_default_enables_reranking(self):
        hybrid_search("cat", book_ids=[7])
        self.key.assert_called_once_with()
        self.rerank.assert_called_once_with("cat", [], 5, api_key="test")

    def test_missing_credentials_fail_before_retrieval(self):
        self.key.side_effect = ValueError("Set COHERE_API_KEY")
        with self.assertRaisesRegex(ValueError, "COHERE_API_KEY"):
            hybrid_search("cat", book_ids=[7], rerank=True)
        self.vector.assert_not_called()
        self.bm25.assert_not_called()


class RerankCliTests(unittest.TestCase):
    @patch("rag_library.cli.search.resolve_book_id", return_value=18)
    @patch("rag_library.cli.search.hybrid_search", return_value=[])
    def test_cli_can_disable_default_reranking(self, search, resolve):
        with (
            patch("sys.argv", ["search", "cat", "--method", "hybrid", "--no-rerank"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        self.assertFalse(search.call_args.kwargs["rerank"])

    @patch("rag_library.cli.search.resolve_book_id", return_value=18)
    @patch("rag_library.cli.search.hybrid_search", return_value=[])
    def test_cli_enables_reranking(self, search, resolve):
        with (
            patch(
                "sys.argv",
                [
                    "search",
                    "cat",
                    "--method",
                    "hybrid",
                    "--rerank",
                    "--candidate-limit",
                    "100",
                ],
            ),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        search.assert_called_once_with(
            "cat", 5, None, book_ids=[18], candidate_limit=100, rerank=True
        )

    @patch("rag_library.cli.search.resolve_book_id")
    def test_other_methods_reject_rerank_before_catalog_access(self, resolve):
        for method in ["vector", "bm25"]:
            with (
                patch("sys.argv", ["search", "cat", "--method", method, "--rerank"]),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main()
            self.assertEqual(error.exception.code, 2)
        resolve.assert_not_called()
