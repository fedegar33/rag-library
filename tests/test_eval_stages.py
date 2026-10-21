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
    @patch("rag_library.cli.eval.load_cases", return_value=[answer("one")])
    @patch("rag_library.cli.eval.score_results")
    def test_cli_selects_default_core_or_all_metrics(self, score, load):
        score.return_value = SimpleNamespace(success=True, errors={})
        for options, mode in [([], "core"), (["--metrics", "all"], "all")]:
            with (
                patch("sys.argv", ["eval.py", "score", *options]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(score.call_args.kwargs["metrics"], mode)

    @patch("rag_library.cli.eval.run_evaluation")
    def test_generation_only_rejects_scoring_option_without_model_calls(self, generate):
        with (
            patch("sys.argv", ["eval.py", "generate", "--metrics", "all"]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            main()
        generate.assert_not_called()

    @patch("rag_library.deepeval_evaluation.evaluate_cases")
    def test_groups_use_separate_native_runs_and_metadata(self, evaluate):
        rows = [answer("fact"), answer("refusal")]
        rows[0]["answerable"] = True
        rows[1]["answerable"] = False

        def result(cases, folder, concurrency, *, metrics, answerable):
            self.assertEqual(metrics, "all")
            self.assertEqual(concurrency, 2)
            group = "answerable" if answerable else "unanswerable"
            self.assertEqual(folder, Path("unused") / group)
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].metadata["answerable"], answerable)
            self.assertEqual(
                cases[0].metadata["scoring"],
                {
                    "metrics": "all",
                    "group": group,
                },
            )
            return SimpleNamespace(test_results=[judged(cases[0].name, 1)])

        evaluate.side_effect = result
        scored = score_results(rows, Path("unused"), 2, metrics="all")
        self.assertEqual(list(scored.evaluations), ["answerable", "unanswerable"])
        self.assertTrue(scored.success)
        self.assertEqual(evaluate.call_count, 2)
        scored.evaluations["unanswerable"].test_results[0].success = False
        self.assertFalse(scored.success)

    @patch("rag_library.deepeval_evaluation.evaluate_cases")
    def test_invalid_answerability_or_metrics_fail_before_judge_calls(self, evaluate):
        row = {**answer("one"), "answerable": "false"}
        with self.assertRaisesRegex(ValueError, "boolean answerable"):
            score_results([row], Path("unused"))
        with self.assertRaisesRegex(ValueError, "core or all"):
            score_results([answer("one")], Path("unused"), metrics="wrong")
        evaluate.assert_not_called()

    @patch("rag_library.cli.eval.run_evaluation", return_value=[])
    def test_generation_cli_passes_repeated_case_ids(self, generate):
        with (
            patch("sys.argv", ["eval.py", "generate", "--id", "one", "--id", "two"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(generate.call_args.kwargs["case_ids"], ["one", "two"])

    @patch("rag_library.cli.eval.run_evaluation")
    @patch("rag_library.cli.eval.score_results")
    def test_score_selection_filters_saved_answers_without_regenerating(
        self, score, generate
    ):
        score.return_value = SimpleNamespace(success=True, errors={})
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "answers.json"
            saved.write_text(json.dumps([answer("one"), answer("two")]))
            original = saved.read_bytes()
            with (
                patch(
                    "sys.argv",
                    [
                        "eval.py",
                        "score",
                        "--output",
                        str(saved),
                        "--id",
                        "two",
                    ],
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual([row["id"] for row in score.call_args.args[0]], ["two"])
            self.assertEqual(saved.read_bytes(), original)
            generate.assert_not_called()
            score.reset_mock()
            with (
                patch(
                    "sys.argv",
                    [
                        "eval.py",
                        "score",
                        "--output",
                        str(saved),
                        "--id",
                        "unknown",
                    ],
                ),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit) as error,
            ):
                main()
            self.assertEqual(error.exception.code, 2)
            score.assert_not_called()
            self.assertEqual(saved.read_bytes(), original)

    @patch("rag_library.cli.eval.run_evaluation")
    @patch("rag_library.cli.eval.score_results")
    def test_all_stage_scores_only_selected_generated_answers(self, score, generate):
        score.return_value = SimpleNamespace(success=True, errors={})
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "answers.json"

            def generate_selected(*args, **kwargs):
                self.assertEqual(kwargs["case_ids"], ["two"])
                saved.write_text(json.dumps([answer("two")]))
                return [answer("two")]

            generate.side_effect = generate_selected
            with (
                patch(
                    "sys.argv",
                    [
                        "eval.py",
                        "all",
                        "--output",
                        str(saved),
                        "--id",
                        "two",
                    ],
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual([row["id"] for row in score.call_args.args[0]], ["two"])

    @patch("rag_library.cli.eval.run_evaluation", return_value=[])
    def test_generation_cli_passes_retrieval_options(self, generate):
        for method, depth in [("hybrid", "30"), ("vector", None)]:
            options = ["eval.py", "generate", "--method", method]
            if depth:
                options.extend(["--candidate-limit", depth])
            with patch("sys.argv", options), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            self.assertEqual(generate.call_args.kwargs["retrieval_method"], method)
            self.assertTrue(generate.call_args.kwargs["rerank"])
            self.assertEqual(
                generate.call_args.kwargs["candidate_limit"],
                int(depth) if depth else None,
            )

    @patch("rag_library.cli.eval.run_evaluation")
    def test_generation_cli_can_disable_reranking(self, generate):
        generate.return_value = []
        with (
            patch("sys.argv", ["eval.py", "generate", "--no-rerank"]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(), 0)
        self.assertFalse(generate.call_args.kwargs["rerank"])

    @patch("rag_library.cli.eval.run_evaluation")
    def test_score_rejects_rerank_flags(self, generate):
        for option in ["--rerank", "--no-rerank"]:
            with (
                patch("sys.argv", ["eval.py", "score", option]),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main()
        generate.assert_not_called()

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
        self.assertIs(scored.evaluations["answerable"], evaluate.return_value)
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
        self.assertEqual(scored.evaluations, {})
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
