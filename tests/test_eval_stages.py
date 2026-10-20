"""Offline checks for independent generation and scoring stages."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from rag_library.cli.eval import main
from rag_library.deepeval_evaluation import score_results


def answer(case_id, error=None):
    return {
        "id": case_id,
        "question": f"Question {case_id}",
        "expected_answer": "Ludlow",
        "actual_answer": "Ludlow" if not error else None,
        "tool_calls": [
            {
                "name": "answer_book_question",
                "arguments": {},
                "result": {"sources": [{"text": "Ludlow, Maine"}]},
            }
        ],
        "error": error,
    }


def judged(case_id, score):
    return SimpleNamespace(
        name=case_id,
        success=score >= 0.7,
        metrics_data=[
            SimpleNamespace(
                name="Correctness",
                score=score,
                threshold=0.7,
                success=score >= 0.7,
                reason=f"Reason for {case_id}",
                error=None,
            )
        ],
    )


class EvalStageTests(unittest.TestCase):
    @patch("rag_library.cli.eval.run_evaluation", return_value=[])
    def test_generation_cli_passes_retrieval_options(self, generate):
        for method, depth in [("hybrid", "30"), ("vector", None)]:
            options = ["eval.py", "generate", "--method", method]
            if depth:
                options.extend(["--candidate-limit", depth])
            with patch("sys.argv", options), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            self.assertEqual(generate.call_args.kwargs["retrieval_method"], method)
            self.assertEqual(
                generate.call_args.kwargs["candidate_limit"],
                int(depth) if depth else None,
            )

    @patch("rag_library.cli.eval.run_evaluation")
    def test_score_rejects_retrieval_override_instead_of_relabeling_answers(
        self, generate
    ):
        with (
            patch("sys.argv", ["eval.py", "score", "--method", "hybrid"]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            main()
        self.assertEqual(error.exception.code, 2)
        generate.assert_not_called()

    @patch("rag_library.deepeval_evaluation.evaluate_cases")
    def test_scores_follow_ids_and_keep_failed_generation(self, evaluate):
        rows = [answer("one"), answer("two"), answer("failed", "Provider error")]
        evaluate.return_value = SimpleNamespace(
            test_results=[judged("two", 0.4), judged("one", 1.0)]
        )
        scored = score_results(rows, Path("unused"))
        self.assertIs(scored.evaluation, evaluate.return_value)
        self.assertEqual(scored.errors, {"failed": "Provider error"})
        self.assertFalse(scored.success)
        self.assertEqual(
            evaluate.call_args.args[0][0].retrieval_context, ["Ludlow, Maine"]
        )
        self.assertEqual(len(evaluate.call_args.args[0]), 2)
        self.assertNotIn("metrics", rows[0])

    @patch("rag_library.deepeval_evaluation.evaluate_cases")
    def test_missing_result_cannot_silently_misassign_scores(self, evaluate):
        evaluate.return_value = SimpleNamespace(test_results=[judged("unknown", 1)])
        with self.assertRaisesRegex(ValueError, "case IDs"):
            score_results([answer("one")], Path("unused"))

    @patch("rag_library.deepeval_evaluation.evaluate_cases")
    def test_missing_context_is_preserved_without_judge_calls(self, evaluate):
        row = answer("one")
        row["tool_calls"] = []
        scored = score_results([row], Path("unused"))
        evaluate.assert_not_called()
        self.assertEqual(scored.errors, {"one": "No book passages retrieved"})
        self.assertIsNone(scored.evaluation)
        self.assertFalse(scored.success)

    @patch("rag_library.cli.eval.run_evaluation")
    @patch("rag_library.deepeval_evaluation.evaluate_cases")
    def test_cli_score_does_not_regenerate_answers(self, evaluate, generate):
        generate.side_effect = AssertionError("Agent must not run")
        evaluate.return_value = SimpleNamespace(test_results=[judged("one", 1)])
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            answers = tmp / "answers.json"
            answers.write_text(json.dumps([answer("one")]))
            original = answers.read_bytes()
            options = [
                "--output",
                str(answers),
                "--results-folder",
                str(tmp / "reports"),
            ]
            with (
                patch("sys.argv", ["eval.py", "score", *options]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(answers.read_bytes(), original)
            evaluate.assert_called_once()
            generate.assert_not_called()
            self.assertEqual(
                sorted(path.name for path in tmp.iterdir()), ["answers.json"]
            )


if __name__ == "__main__":
    unittest.main()
