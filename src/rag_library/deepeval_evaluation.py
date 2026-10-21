"""DeepEval test cases and metrics for the full book agent."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from deepeval import evaluate
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig, ErrorConfig
from deepeval.evaluate.types import EvaluationResult
from deepeval.metrics import (
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    ContextualRelevancyMetric,
    FaithfulnessMetric,
    GEval,
)
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

from rag_library.agent.models import AgentResult, ToolCallRecord
from rag_library.config import get_settings
from rag_library.evaluation import get_retrieval_context

MetricMode = Literal["core", "all"]


def build_test_case(case: dict, response: AgentResult) -> LLMTestCase:
    """Capture the final answer and actual retrieved passages in execution order.

    Do not perform another retrieval or use expected answers as context. Keep
    complete tool records alongside the plain passage text for provenance.
    """
    return LLMTestCase(
        name=case["id"],
        input=case["question"],
        expected_output=case["expected_answer"],
        actual_output=response.answer,
        retrieval_context=get_retrieval_context(response),
        metadata={
            "answerable": case.get("answerable", True),
            "answerable_source": "saved" if "answerable" in case else "legacy_default",
            "tool_calls": [asdict(call) for call in response.tool_calls],
            **({"retrieval": case["retrieval"]} if "retrieval" in case else {}),
            **{
                key: case.get(key, [])
                for key in ("book_refs", "book_ids", "attached_books")
            },
        },
    )


def build_metrics(mode: MetricMode = "core", *, answerable: bool = True) -> list:
    """Gate on answer quality; retrieval metrics have scores without verdicts."""
    if mode not in ("core", "all"):
        raise ValueError("Metrics must be core or all")
    settings = get_settings()
    judge = OpenAIModel(
        model=settings.eval_judge_model or settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    options = {"model": judge, "threshold": 0.7, "async_mode": True}
    metrics = [
        FaithfulnessMetric(
            **{**options, "threshold": 0.7 if answerable else None},
            include_reason=True,
        ),
        GEval(
            name="Answer Correctness",
            evaluation_steps=[
                "Read the input to identify the requested facts. Treat the expected "
                "output as the minimum required factual content, not a required "
                "response format or an exhaustive list of permissible details.",
                "Compare the actual output with the expected output for factual "
                "agreement. Accept semantically equivalent wording and unambiguous "
                "name variants; do not require a verbatim match.",
                "Do not deduct points solely for answer length, complete sentences, "
                "citations, or additional information absent from the expected "
                "output. A correctly answered question should receive a high score "
                "when the additional wording does not contradict the required facts.",
                "Penalize missing requested facts, wrong requested facts, and "
                "contradictory or incompatible alternatives, even if the correct "
                "answer also appears somewhere in the actual output. Preserve "
                "essential distinctions such as entity, relationship, location, "
                "time, and a proposed event versus an actual event.",
                "If the expected output explicitly says the information is not "
                "specified or unavailable, accept an equivalent abstention that "
                "does not invent the missing detail. If the expected output "
                "provides an answer, an abstention omits the requested fact and "
                "must be penalized.",
                "Use only the input, expected output, and actual output for this "
                "judgment. Do not assume extra claims are false merely because "
                "the expected output omits them, and do not use outside knowledge "
                "to verify them. Support from retrieved passages is assessed "
                "separately by Faithfulness.",
                "Explain the score in terms of factual agreement, omissions, or "
                "contradictions. Do not justify deductions using verbosity, style, "
                "or failure to copy the expected answer's wording.",
            ],
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            **options,
        ),
    ]
    if mode == "all":
        diagnostics = {**options, "threshold": None, "include_reason": True}
        metrics = [
            ContextualRelevancyMetric(**diagnostics),
            ContextualRecallMetric(**diagnostics),
            ContextualPrecisionMetric(**diagnostics),
            *metrics,
        ]
    return metrics


def evaluate_cases(
    test_cases: list[LLMTestCase],
    results_folder: Path,
    max_concurrent: int = 4,
    *,
    metrics: MetricMode = "core",
    answerable: bool = True,
):
    """Evaluate the whole batch concurrently using DeepEval's Python API."""
    return evaluate(
        test_cases=test_cases,
        metrics=build_metrics(metrics, answerable=answerable),
        async_config=AsyncConfig(run_async=True, max_concurrent=max_concurrent),
        cache_config=CacheConfig(use_cache=False, write_cache=False),
        error_config=ErrorConfig(ignore_errors=True, skip_on_missing_params=False),
        display_config=DisplayConfig(
            results_folder=str(results_folder), inspect_after_run=False
        ),
    )


@dataclass(frozen=True)
class ScoringResult:
    evaluations: dict[str, EvaluationResult]
    errors: dict[str, str]

    @property
    def success(self) -> bool:
        return (
            not self.errors
            and bool(self.evaluations)
            and all(
                bool(evaluation.test_results)
                and all(case.success for case in evaluation.test_results)
                for evaluation in self.evaluations.values()
            )
        )


def score_results(
    rows: list[dict],
    results_folder: Path,
    max_concurrent: int = 20,
    *,
    metrics: MetricMode = "core",
) -> ScoringResult:
    """Score saved answers without invoking the agent or retrieving again."""
    if metrics not in ("core", "all"):
        raise ValueError("Metrics must be core or all")
    for row in rows:
        if type(row.get("answerable", True)) is not bool:
            raise ValueError(f"Case {row['id']} needs a boolean answerable field")
    groups = {True: [], False: []}
    errors = {}
    for row in rows:
        if row["error"]:
            errors[row["id"]] = row["error"]
            continue
        response = AgentResult(
            row["actual_answer"],
            [ToolCallRecord(**call) for call in row["tool_calls"]],
        )
        case = build_test_case(row, response)
        case.metadata["scoring"] = {
            "metrics": metrics,
            "group": "answerable" if row.get("answerable", True) else "unanswerable",
        }
        if not case.retrieval_context:
            errors[row["id"]] = "No book passages retrieved"
            continue
        groups[row.get("answerable", True)].append(case)

    evaluations = {}
    for answerable, cases in groups.items():
        if not cases:
            continue
        group = "answerable" if answerable else "unanswerable"
        print(
            f"\nDeepEval: {group} cases ({len(cases)}), metrics={metrics}", flush=True
        )
        evaluation = evaluate_cases(
            cases,
            Path(results_folder) / group,
            max_concurrent,
            metrics=metrics,
            answerable=answerable,
        )
        names = [result.name for result in evaluation.test_results]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate evaluation result IDs")
        expected_names = {case.name for case in cases}
        if set(names) != expected_names:
            raise ValueError("DeepEval results do not match the submitted case IDs")
        evaluations[group] = evaluation
    return ScoringResult(evaluations, errors)
