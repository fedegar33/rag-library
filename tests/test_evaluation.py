"""Offline checks for the eval workflow and book tool; no provider calls."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rag_library.agent.context import AgentContext
from rag_library.agent.models import AgentResult, ToolCallRecord
from rag_library.agent.tools import answer_book_question
from rag_library.evaluation import run_evaluation
from rag_library.rag.search import SearchResult


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.dataset = Path(self.directory.name) / "basic.json"
        self.output = Path(self.directory.name) / "basic_result.json"
        self.cases = [
            {"id": "one", "question": "¿Quién?", "expected_answer": "Nicolas"},
            {"id": "two", "question": "¿Dónde?", "expected_answer": "Ludlow"},
        ]
        self.book = {
            "id": 7,
            "title": "Book",
            "authors": None,
            "language": "en",
            "content_sha256": "a" * 64,
        }
        for case in self.cases:
            case["book_refs"] = ["a" * 64]
        self.cases[0]["answerable"] = True
        self.cases[1]["answerable"] = False
        resolver = patch(
            "rag_library.evaluation.get_books_by_refs", return_value=[self.book]
        )
        self.resolve = resolver.start()
        self.addCleanup(resolver.stop)
        self.dataset.write_text(json.dumps(self.cases), encoding="utf-8")

    @patch("rag_library.evaluation.get_agent")
    @patch("rag_library.evaluation.run_agent")
    def test_saves_each_case_and_preserves_dataset_and_sources(self, run, get):
        original = self.dataset.read_bytes()
        calls = [
            ToolCallRecord(
                "answer_book_question", {}, {"sources": [{"text": "chapter 1"}]}
            )
        ]

        def answer(agent, question, *, context):
            self.assertEqual(context.book_ids, [7])
            self.assertIs(agent, get.return_value)
            completed = json.loads(self.output.read_text())
            self.assertEqual(len(completed), run.call_count - 1)
            return AgentResult("Una respuesta", calls)

        run.side_effect = answer
        results = run_evaluation(self.dataset, self.output)
        self.assertEqual(self.dataset.read_bytes(), original)
        self.assertEqual(json.loads(self.output.read_text()), results)
        self.assertEqual(
            [call.args[1] for call in run.call_args_list],
            [case["question"] for case in self.cases],
        )
        self.assertEqual(results[0]["actual_answer"], "Una respuesta")
        self.assertTrue(results[0]["answerable"])
        self.assertFalse(results[1]["answerable"])
        self.assertEqual(
            results[0]["tool_calls"][0]["result"]["sources"], [{"text": "chapter 1"}]
        )
        self.assertEqual(results[0]["retrieval_context"], ["chapter 1"])
        self.assertIsNone(results[0]["error"])
        self.assertEqual(results[0]["book_ids"], [7])
        self.assertEqual(results[0]["book_refs"], ["a" * 64])
        self.assertEqual(results[0]["attached_books"], [self.book])
        self.assertEqual(
            results[0]["retrieval"],
            {
                "method": "hybrid",
                "top_k": 5,
                "candidate_limit": 20,
                "rrf_constant": 60,
                "rerank": True,
                "rerank_model": "rerank-v5.0-pro",
            },
        )
        self.assertEqual(run.call_args.kwargs["context"].retrieval_method, "hybrid")

    @patch("rag_library.evaluation.get_agent")
    @patch("rag_library.evaluation.run_agent")
    def test_records_failure_and_continues(self, run, get):
        run.side_effect = [RuntimeError("retrieval failed"), AgentResult("Ludlow", [])]
        progress = []

        def observe(event):
            progress.append(event)
            if event.elapsed_seconds is None:
                self.assertEqual(run.call_count, event.index - 1)
            else:
                self.assertEqual(len(json.loads(self.output.read_text())), event.index)

        results = run_evaluation(self.dataset, self.output, on_progress=observe)
        self.assertIsNone(results[0]["actual_answer"])
        self.assertIn("retrieval failed", results[0]["error"])
        self.assertEqual(results[1]["actual_answer"], "Ludlow")
        self.assertEqual(len(json.loads(self.output.read_text())), 2)
        self.assertEqual([event.index for event in progress], [1, 1, 2, 2])
        self.assertIn("retrieval failed", progress[1].case["error"])
        self.assertIsNotNone(progress[3].elapsed_seconds)

    @patch("rag_library.evaluation.get_agent")
    @patch("rag_library.evaluation.run_agent")
    def test_missing_ref_records_failure_without_agent_execution(self, run, get):
        self.resolve.side_effect = ValueError("No ingested book matches content_sha256")
        rows = run_evaluation(self.dataset, self.output)
        run.assert_not_called()
        self.assertTrue(all("No ingested book" in row["error"] for row in rows))

    @patch("rag_library.evaluation.get_agent")
    def test_dataset_requires_nonempty_valid_book_refs(self, get):
        for refs in [None, [], ["title"], ["A" * 64]]:
            self.cases[0]["book_refs"] = refs
            self.dataset.write_text(json.dumps(self.cases))
            with self.assertRaisesRegex(ValueError, "book_refs"):
                run_evaluation(self.dataset, self.output)
        get.assert_not_called()

    @patch("rag_library.evaluation.get_agent")
    def test_non_boolean_answerable_fails_before_overwriting_answers(self, get):
        self.cases[0]["answerable"] = "false"
        self.dataset.write_text(json.dumps(self.cases))
        self.output.write_text("preserve this")
        with self.assertRaisesRegex(ValueError, "boolean answerable"):
            run_evaluation(self.dataset, self.output)
        get.assert_not_called()
        self.assertEqual(self.output.read_text(), "preserve this")

    def test_cannot_overwrite_question_set(self):
        with self.assertRaisesRegex(ValueError, "separately"):
            run_evaluation(self.dataset, self.dataset)

    @patch("rag_library.evaluation.get_agent")
    @patch("rag_library.evaluation.run_agent", return_value=AgentResult("Answer", []))
    def test_vector_override_is_recorded_in_saved_answers_and_context(self, run, get):
        rows = run_evaluation(self.dataset, self.output, retrieval_method="vector")
        self.assertEqual(run.call_args.kwargs["context"].retrieval_method, "vector")
        self.assertEqual(
            rows[0]["retrieval"],
            {
                "method": "vector",
                "top_k": 5,
                "candidate_limit": None,
                "rrf_constant": None,
                "rerank": False,
                "rerank_model": None,
            },
        )

    @patch("rag_library.evaluation.get_agent")
    @patch("rag_library.evaluation.run_agent", return_value=AgentResult("Answer", []))
    def test_rerank_disable_and_candidate_depth_are_saved(self, run, get):
        rows = run_evaluation(
            self.dataset, self.output, candidate_limit=100, rerank=False
        )
        context = run.call_args.kwargs["context"]
        self.assertFalse(context.rerank)
        self.assertEqual(context.candidate_limit, 100)
        self.assertFalse(rows[0]["retrieval"]["rerank"])
        self.assertIsNone(rows[0]["retrieval"]["rerank_model"])
        self.assertEqual(rows[0]["retrieval"]["candidate_limit"], 100)

    @patch("rag_library.evaluation.get_agent")
    def test_invalid_retrieval_options_preserve_existing_output(self, get):
        self.output.write_text("preserve this")
        with self.assertRaises(ValueError):
            run_evaluation(self.dataset, self.output, candidate_limit=4)
        get.assert_not_called()
        self.assertEqual(self.output.read_text(), "preserve this")

    @patch("rag_library.evaluation.get_agent")
    @patch("rag_library.evaluation.run_agent", return_value=AgentResult("Answer", []))
    def test_selected_ids_run_once_in_dataset_order_and_save_only_subset(
        self, run, get
    ):
        progress = []
        rows = run_evaluation(
            self.dataset,
            self.output,
            case_ids=["two", "one", "two"],
            on_progress=progress.append,
        )
        self.assertEqual([row["id"] for row in rows], ["one", "two"])
        self.assertEqual(run.call_count, 2)
        run.reset_mock()
        progress.clear()
        rows = run_evaluation(
            self.dataset, self.output, case_ids=["two"], on_progress=progress.append
        )
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1], "¿Dónde?")
        self.assertEqual([row["id"] for row in rows], ["two"])
        self.assertEqual(json.loads(self.output.read_text()), rows)
        self.assertEqual(
            [(event.index, event.total) for event in progress], [(1, 1)] * 2
        )

    @patch("rag_library.evaluation.get_agent")
    def test_unknown_or_empty_selection_preserves_output_before_agent_calls(self, get):
        self.output.write_text("previous results")
        for selection in [["one", "unknown"], []]:
            with self.subTest(selection=selection), self.assertRaises(ValueError):
                run_evaluation(self.dataset, self.output, case_ids=selection)
        get.assert_not_called()
        self.resolve.assert_not_called()
        self.assertEqual(self.output.read_text(), "previous results")

    @patch("rag_library.evaluation.get_agent")
    def test_duplicate_ids_fail_before_agent_calls(self, get):
        self.cases[1]["id"] = "one"
        self.dataset.write_text(json.dumps(self.cases))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            run_evaluation(self.dataset, self.output)
        get.assert_not_called()

    @patch("rag_library.rag.retriever.hybrid_search")
    def test_book_tool_reuses_retrieval_and_preserves_provenance(self, search):
        search.return_value = [
            SearchResult("Cementerio de animales", 4, "Un pasaje", 0.8, 1, book_id=7)
        ]
        result = answer_book_question.func(
            question="¿Dónde viven los Creed?",
            runtime=SimpleNamespace(context=AgentContext((self.book,))),
        )
        search.assert_called_once_with(
            "¿Dónde viven los Creed?",
            limit=5,
            book_ids=[7],
            candidate_limit=None,
            rerank=True,
        )
        self.assertNotIn("answer", result)
        self.assertEqual(result["sources"][0]["chapter_number"], 1)
        self.assertEqual(result["sources"][0]["chunk_index"], 4)
        self.assertEqual(result["sources"][0]["text"], "Un pasaje")
        self.assertEqual(result["sources"][0]["book_id"], 7)
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
