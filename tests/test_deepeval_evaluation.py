"""Offline checks for DeepEval wiring; no agent, database, or judge calls."""

import unittest
from unittest.mock import patch

from rag_library.agent.models import AgentResult, ToolCallRecord
from rag_library.config import Settings
from rag_library.deepeval_evaluation import (
    build_metrics,
    build_test_case,
    evaluate_cases,
)


class DeepEvalTests(unittest.TestCase):
    @patch("rag_library.deepeval_evaluation.build_metrics")
    @patch("rag_library.deepeval_evaluation.evaluate")
    def test_evaluates_whole_batch_with_async_concurrency(self, evaluate, metrics):
        from pathlib import Path

        cases = ["one", "two"]
        result = evaluate_cases(cases, Path("evals/results"), max_concurrent=4)
        self.assertIs(result, evaluate.return_value)
        kwargs = evaluate.call_args.kwargs
        self.assertEqual(kwargs["test_cases"], cases)
        self.assertIs(kwargs["metrics"], metrics.return_value)
        self.assertTrue(kwargs["async_config"].run_async)
        self.assertEqual(kwargs["async_config"].max_concurrent, 4)
        self.assertEqual(kwargs["display_config"].results_folder, "evals/results")

    def test_uses_final_answer_and_actual_passages_in_order(self):
        sources = [
            {"book_title": "Libro", "chapter_number": 1, "chunk_index": 2, "text": "A"},
            {"book_title": "Libro", "chapter_number": 2, "chunk_index": 3, "text": "B"},
        ]
        calls = [
            ToolCallRecord("list_books", {}, {"books": []}),
            ToolCallRecord(
                "answer_book_question", {}, {"answer": "Inner", "sources": sources}
            ),
            ToolCallRecord("answer_book_question", {}, {"sources": [sources[0]]}),
        ]
        case = {
            "id": "one",
            "question": "Pregunta",
            "expected_answer": "Esperada",
            "book_refs": ["a" * 64],
            "book_ids": [7],
            "attached_books": [{"id": 7, "title": "Book"}],
            "retrieval": {
                "method": "hybrid",
                "top_k": 5,
                "candidate_limit": 20,
                "rrf_constant": 60,
            },
        }
        result = build_test_case(case, AgentResult("Final", calls))
        self.assertEqual(result.name, "one")
        self.assertEqual(result.input, "Pregunta")
        self.assertEqual(result.expected_output, "Esperada")
        self.assertEqual(result.actual_output, "Final")
        self.assertEqual(result.retrieval_context, ["A", "B", "A"])
        self.assertEqual(result.metadata["tool_calls"][1]["result"]["sources"], sources)
        for key in ("book_refs", "book_ids", "attached_books", "retrieval"):
            self.assertEqual(result.metadata[key], case[key])
        self.assertIsNone(result.context)

    def test_missing_retrieval_stays_empty(self):
        case = {"id": "one", "question": "Pregunta", "expected_answer": "Esperada"}
        result = build_test_case(case, AgentResult("No sé", []))
        self.assertEqual(result.retrieval_context, [])

    @patch("rag_library.deepeval_evaluation.get_settings")
    def test_five_metrics_use_configured_judge_and_references(self, get):
        get.return_value = Settings(
            _env_file=None,
            database_url="postgresql://unused",
            openai_api_key="offline-placeholder",
            openai_chat_model="gpt-4o-mini",
            eval_judge_model="gpt-4.1-mini",
        )
        metrics = build_metrics()
        self.assertEqual(len(metrics), 5)
        for metric in metrics:
            self.assertEqual(metric.model.get_model_name(), "gpt-4.1-mini")
            self.assertEqual(metric.threshold, 0.7)
        self.assertEqual(
            [param.value for param in metrics[-1].evaluation_params],
            ["input", "actual_output", "expected_output"],
        )
        self.assertIsNone(metrics[-1].criteria)
        self.assertTrue(metrics[-1].evaluation_steps)
        get.return_value.eval_judge_model = None
        self.assertEqual(build_metrics()[0].model.get_model_name(), "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
