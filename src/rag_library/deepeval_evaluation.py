"""DeepEval test cases and metrics for the full book agent."""

from dataclasses import asdict, dataclass
from pathlib import Path

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
            "tool_calls": [asdict(call) for call in response.tool_calls],
            **{
                key: case.get(key, [])
                for key in ("book_refs", "book_ids", "attached_books")
            },
        },
    )


def build_metrics() -> list:
    """Create the five metrics; 0.7 is an initial tunable threshold."""
    settings = get_settings()
    judge = OpenAIModel(
        model=settings.eval_judge_model or settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    options = {"model": judge, "threshold": 0.7, "async_mode": True}
    return [
        ContextualRelevancyMetric(**options, include_reason=True),
        ContextualRecallMetric(**options, include_reason=True),
        ContextualPrecisionMetric(**options, include_reason=True),
        FaithfulnessMetric(**options, include_reason=True),
        GEval(
            name="Answer Correctness",
            criteria=(
                "Evaluate whether the actual output correctly answers the input "
                "according to the expected output. Accept equivalent English "
                "wording and concise paraphrases. Penalize contradictions, "
                "missing essential facts, or an unsupported refusal. Do not "
                "require facts beyond the expected output."
            ),
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            **options,
        ),
    ]


def evaluate_cases(
    test_cases: list[LLMTestCase], results_folder: Path, max_concurrent: int = 4
):
    """Evaluate the whole batch concurrently using DeepEval's Python API."""
    return evaluate(
        test_cases=test_cases,
        metrics=build_metrics(),
        async_config=AsyncConfig(run_async=True, max_concurrent=max_concurrent),
        cache_config=CacheConfig(use_cache=False, write_cache=False),
        error_config=ErrorConfig(ignore_errors=True, skip_on_missing_params=False),
        display_config=DisplayConfig(
            results_folder=str(results_folder), inspect_after_run=False
        ),
    )


@dataclass(frozen=True)
class ScoringResult:
    evaluation: EvaluationResult | None
    errors: dict[str, str]

    @property
    def success(self) -> bool:
        return (
            not self.errors
            and self.evaluation is not None
            and bool(self.evaluation.test_results)
            and all(case.success for case in self.evaluation.test_results)
        )


def score_results(
    rows: list[dict], results_folder: Path, max_concurrent: int = 20
) -> ScoringResult:
    """Score saved answers without invoking the agent or retrieving again."""
    cases = []
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
        if not case.retrieval_context:
            errors[row["id"]] = "No book passages retrieved"
            continue
        cases.append(case)

    if not cases:
        return ScoringResult(None, errors)
    evaluation = evaluate_cases(cases, results_folder, max_concurrent)
    names = [result.name for result in evaluation.test_results]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate evaluation result IDs")
    expected_names = {case.name for case in cases}
    if set(names) != expected_names:
        raise ValueError("DeepEval results do not match the submitted case IDs")
    return ScoringResult(evaluation, errors)
