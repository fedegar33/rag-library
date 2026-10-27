"""Offline graph and scoring checks for synthetic agent behavior cases."""

import contextlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from deepeval.test_case import ToolCall
from langchain_core.messages import AIMessage
from test_attached_context import ScriptedModel

from rag_library.agent.agent import build_agent
from rag_library.behavior_evaluation import (
    BehaviorDataset,
    load_behavior_dataset,
    run_behavior_evaluation,
)
from rag_library.cli.eval import main
from rag_library.config import Settings
from rag_library.deepeval_behavior import (
    build_behavior_case,
    build_behavior_metrics,
    score_behavior_results,
)

DATASET = Path(__file__).resolve().parents[1] / "evals/agent_behavior.json"


def frozen_row(index=0, calls=None):
    data = load_behavior_dataset(DATASET)
    case = data.cases[index]
    return {
        **case.model_dump(),
        "suite": data.suite,
        "suite_version": data.version,
        "fixture_data": data.fixtures[case.fixture].model_dump(),
        "response_instructions": data.response_instructions,
        "configuration": {"model": "offline"},
        "dataset_sha256": "a" * 64,
        "actual_answer": "These are the available books.",
        "tool_calls": calls or [],
        "error": None,
    }


class BehaviorGenerationTests(unittest.TestCase):
    def test_dataset_selection_preserves_order_and_deduplicates(self):
        data = load_behavior_dataset(DATASET)
        self.assertEqual(len(data.cases), 14)
        self.assertEqual(len({case.category for case in data.cases}), 5)
        ids = [data.cases[3].id, data.cases[0].id, data.cases[3].id]
        selected = load_behavior_dataset(DATASET, case_ids=ids)
        self.assertEqual([case.id for case in selected.cases], [ids[1], ids[0]])

    def test_invalid_fixture_definitions_fail_before_execution(self):
        original = json.loads(DATASET.read_text())
        for mutation in ("duplicate", "scope", "reference", "source"):
            value = deepcopy(original)
            if mutation == "duplicate":
                value["cases"].append(value["cases"][0])
            elif mutation == "scope":
                value["cases"][0]["book_ids"] = [999]
            elif mutation == "reference":
                value["cases"][0]["fixture"] = "missing"
            else:
                value["fixtures"]["library"]["sources"][0]["book_id"] = 999
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                BehaviorDataset.model_validate(value)

    @patch("rag_library.behavior_evaluation.get_settings")
    @patch("rag_library.behavior_evaluation.get_agent")
    def test_unknown_ids_do_not_initialize_agent_or_overwrite_output(self, agent, get):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "answers.json"
            output.write_text("keep")
            with self.assertRaises(ValueError):
                run_behavior_evaluation(DATASET, output, case_ids=["missing"])
            self.assertEqual(output.read_text(), "keep")
        get.assert_not_called()
        agent.assert_not_called()

    @patch(
        "rag_library.agent.tools.BookRetriever", side_effect=AssertionError("live RAG")
    )
    @patch("rag_library.catalog.list_books", side_effect=AssertionError("live DB"))
    @patch("rag_library.behavior_evaluation.get_settings")
    @patch("rag_library.behavior_evaluation.get_agent")
    def test_real_graph_uses_fixtures_and_runtime_scope(
        self, get_agent, get, catalog, rag
    ):
        get.return_value = SimpleNamespace(openai_chat_model="offline")
        scenarios = [
            ("catalog-02", "list_available_books", {}),
            (
                "content-01",
                "answer_book_question",
                {"question": "Where does Elena work?"},
            ),
            ("content-04", "answer_book_question", {"question": "Where?"}),
            ("social-01", None, {}),
        ]

        def create(**kwargs):
            _, name, args = scenarios[get_agent.call_count - 1]
            responses = []
            if name:
                responses.append(
                    AIMessage(
                        content="",
                        tool_calls=[{"id": "call-1", "name": name, "args": args}],
                    )
                )
            responses.append(AIMessage(content="Final answer"))
            return build_agent(ScriptedModel(responses=responses), **kwargs)

        get_agent.side_effect = create
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            output = Path(directory) / "answers.json"
            rows = run_behavior_evaluation(
                DATASET, output, case_ids=[item[0] for item in scenarios]
            )
            self.assertEqual(json.loads(output.read_text()), rows)
        self.assertEqual([row["error"] for row in rows], [None] * 4)
        self.assertEqual(len(rows[0]["tool_calls"][0]["result"]["books"]), 2)
        sources = rows[1]["tool_calls"][0]["result"]["sources"]
        self.assertEqual([source["book_id"] for source in sources], [101])
        self.assertEqual(rows[1]["retrieval_context"], [sources[0]["text"]])
        self.assertIn("No books", rows[2]["tool_calls"][0]["result"]["message"])
        self.assertEqual(rows[3]["tool_calls"], [])
        self.assertEqual(rows[0]["configuration"]["response_format"], "text")
        self.assertEqual(rows[0]["fixture_data"]["books"][1]["id"], 102)
        catalog.assert_not_called()
        rag.assert_not_called()

    @patch("rag_library.behavior_evaluation.get_settings")
    @patch("rag_library.behavior_evaluation.get_agent")
    def test_generation_errors_are_saved_and_next_case_runs(self, get_agent, get):
        get.return_value = SimpleNamespace(openai_chat_model="offline")
        get_agent.side_effect = [
            RuntimeError("failed"),
            SimpleNamespace(
                invoke=lambda *a, **kw: {"messages": [AIMessage(content="Hello")]}
            ),
        ]
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            rows = run_behavior_evaluation(
                DATASET,
                Path(directory) / "out.json",
                case_ids=["social-01", "social-02"],
            )
        self.assertIn("RuntimeError: failed", rows[0]["error"])
        self.assertIsNone(rows[1]["error"])


class BehaviorScoringTests(unittest.TestCase):
    @patch("rag_library.deepeval_behavior.get_settings")
    def test_native_metrics_exact_gate_and_score_only_diagnostics(self, get):
        get.return_value = Settings(
            _env_file=None,
            database_url="postgresql://unused",
            openai_api_key="unused",
            openai_chat_model="gpt-4o-mini",
        )
        for has_tools in (True, False):
            metrics = build_behavior_metrics(
                ["Keep catalog introductions brief"], has_tools=has_tools
            )
            self.assertEqual(
                [m.threshold for m in metrics], [1.0] + [None] * (3 if has_tools else 2)
            )
            self.assertTrue(metrics[0].should_exact_match)
            test_case = build_behavior_case(frozen_row(8))
            metrics[0].async_mode = False
            metrics[0].measure(test_case, _show_indicator=False)
            self.assertEqual(metrics[0].score, 1)
            test_case.tools_called.append(ToolCall(name="list_available_books"))
            metrics[0].measure(test_case, _show_indicator=False)
            self.assertEqual(metrics[0].score, 0)

    def test_case_uses_actual_arguments_outputs_and_frozen_expectations(self):
        call = {
            "name": "answer_book_question",
            "arguments": {"question": "Where?"},
            "result": {"sources": []},
        }
        row = frozen_row(4, [call])
        case = build_behavior_case(row)
        self.assertEqual(case.tools_called[0].input_parameters, call["arguments"])
        self.assertEqual(case.tools_called[0].output, call["result"])
        self.assertEqual(case.expected_output, row["expected_answer"])
        self.assertEqual(
            build_behavior_case(frozen_row(8)).metadata["not_applicable"],
            ["Argument Correctness"],
        )

    @patch("rag_library.deepeval_behavior.build_behavior_metrics", return_value=[])
    @patch("rag_library.deepeval_behavior.evaluate")
    def test_scoring_groups_and_generation_errors(self, evaluate, metrics):
        rows = [
            frozen_row(
                0,
                [
                    {
                        "name": "list_available_books",
                        "arguments": {},
                        "result": {"books": []},
                    }
                ],
            ),
            frozen_row(8),
            frozen_row(9),
        ]
        rows[2]["error"] = "provider failed"
        evaluate.side_effect = lambda **kw: SimpleNamespace(
            test_results=[
                SimpleNamespace(name=case.name, success=True, metrics_data=[])
                for case in kw["test_cases"]
            ]
        )
        result = score_behavior_results(rows, Path("unused"), 2)
        self.assertEqual(evaluate.call_count, 2)
        self.assertFalse(result.success)
        self.assertEqual(result.errors, {rows[2]["id"]: "provider failed"})
        self.assertEqual(
            [c.kwargs["has_tools"] for c in metrics.call_args_list], [True, False]
        )
        self.assertEqual(evaluate.call_args.kwargs["async_config"].max_concurrent, 2)

    @patch("rag_library.deepeval_behavior.build_behavior_metrics", return_value=[])
    @patch("rag_library.deepeval_behavior.evaluate")
    def test_metric_errors_and_mismatched_ids_fail(self, evaluate, metrics):
        row = frozen_row(8)
        metric = SimpleNamespace(name="Judge", error="unavailable")
        evaluate.return_value = SimpleNamespace(
            test_results=[
                SimpleNamespace(name=row["id"], success=True, metrics_data=[metric])
            ]
        )
        result = score_behavior_results([row], Path("unused"))
        self.assertFalse(result.success)
        self.assertIn("unavailable", result.errors[row["id"]])
        evaluate.return_value.test_results[0].name = "other"
        with self.assertRaises(ValueError):
            score_behavior_results([row], Path("unused"))


class BehaviorCliTests(unittest.TestCase):
    @patch("rag_library.cli.eval.score_behavior_results")
    @patch("rag_library.cli.eval.run_behavior_evaluation", return_value=[])
    def test_generate_and_manual_do_not_score(self, generate, score):
        for options in (["generate"], ["--manual"]):
            with (
                patch("sys.argv", ["eval.py", *options, "--suite", "agent"]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(), 0)
            self.assertEqual(
                generate.call_args.args[:2],
                (
                    Path("evals/agent_behavior.json"),
                    Path("evals/results/agent-behavior/answers.json"),
                ),
            )
        score.assert_not_called()

    @patch("rag_library.cli.eval.run_behavior_evaluation")
    @patch("rag_library.cli.eval.score_behavior_results")
    def test_score_reads_only_saved_selected_answers(self, score, generate):
        score.return_value = SimpleNamespace(success=True, errors={})
        rows = [frozen_row(8), frozen_row(9)]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "answers.json"
            output.write_text(json.dumps(rows))
            with patch(
                "sys.argv",
                [
                    "eval.py",
                    "score",
                    "--suite",
                    "agent",
                    "--output",
                    str(output),
                    "--id",
                    rows[1]["id"],
                ],
            ):
                self.assertEqual(main(), 0)
        self.assertEqual(score.call_args.args[0], [rows[1]])
        generate.assert_not_called()

    @patch("rag_library.cli.eval.run_behavior_evaluation")
    def test_retrieval_and_metric_overrides_are_rejected(self, generate):
        for options in (
            ["--method", "vector"],
            ["--no-rerank"],
            ["--metrics", "all"],
            ["--candidate-limit", "20"],
        ):
            with (
                patch("sys.argv", ["eval.py", "--suite", "agent", *options]),
                contextlib.redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                main()
        generate.assert_not_called()
