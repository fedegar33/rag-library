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
        metrics.assert_called_once_with("core", answerable=True)
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
            "answerable": False,
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
        self.assertFalse(result.metadata["answerable"])

    def test_missing_retrieval_stays_empty(self):
        case = {"id": "one", "question": "Pregunta", "expected_answer": "Esperada"}
        result = build_test_case(case, AgentResult("No sé", []))
        self.assertEqual(result.retrieval_context, [])

    @patch("rag_library.deepeval_evaluation.get_settings")
    def test_core_and_all_metrics_use_judge_and_native_score_only_thresholds(self, get):
        get.return_value = Settings(
            _env_file=None,
            database_url="postgresql://unused",
            openai_api_key="offline-placeholder",
            openai_chat_model="gpt-4o-mini",
            eval_judge_model="gpt-4.1-mini",
        )
        metrics = build_metrics()
        self.assertEqual(len(metrics), 2)
        for metric in metrics:
            self.assertEqual(metric.model.get_model_name(), "gpt-4.1-mini")
            self.assertEqual(metric.threshold, 0.7)
        self.assertEqual(
            [param.value for param in metrics[-1].evaluation_params],
            ["input", "actual_output", "expected_output"],
        )
        self.assertIsNone(metrics[-1].criteria)
        self.assertTrue(metrics[-1].evaluation_steps)
        metrics = build_metrics("all")
        self.assertEqual(len(metrics), 5)
        self.assertEqual(
            [metric.threshold for metric in metrics], [None] * 3 + [0.7] * 2
        )
        for metric in metrics[:3]:
            metric.score = 0.01
            self.assertIsNone(metric.is_successful())
        metrics = build_metrics("all", answerable=False)
        self.assertEqual([metric.threshold for metric in metrics], [None] * 4 + [0.7])
        metrics[-2].score = 0.01
        self.assertIsNone(metrics[-2].is_successful())
        self.assertEqual(len(build_metrics(answerable=False)), 2)
        get.return_value.eval_judge_model = None
        self.assertEqual(build_metrics()[0].model.get_model_name(), "gpt-4o-mini")

    def test_invalid_metric_mode_fails_before_judge_setup(self):
        with self.assertRaisesRegex(ValueError, "core or all"):
            build_metrics("invalid")

    def test_native_case_verdict_ignores_score_only_metrics(self):
        from deepeval.test_run.api import LLMApiTestCase
        from deepeval.tracing.api import MetricData

        for answerable, faithful, correct, expected in [
            (True, True, True, True),
            (True, False, True, False),
            (True, True, False, False),
            (False, None, True, True),
            (False, None, False, False),
        ]:
            with self.subTest(
                answerable=answerable, faithful=faithful, correct=correct
            ):
                case = LLMApiTestCase(name="offline", input="Question", success=True)
                case.update_metric_data(
                    MetricData(
                        name="Faithfulness",
                        threshold=0.7 if answerable else None,
                        score=0.9 if faithful else 0.1,
                        success=faithful,
                    )
                )
                case.update_metric_data(
                    MetricData(
                        name="Answer Correctness",
                        threshold=0.7,
                        score=0.9 if correct else 0.1,
                        success=correct,
                    )
                )
                case.update_metric_data(
                    MetricData(
                        name="Contextual Relevancy",
                        threshold=None,
                        score=0.01,
                        success=None,
                    )
                )
                self.assertEqual(case.success, expected)
                self.assertEqual(case.metrics_data[-1].score, 0.01)


if __name__ == "__main__":
    unittest.main()
