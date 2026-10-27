"""Tool gates and score-only semantic diagnostics for frozen behavior runs."""

from collections import defaultdict
from pathlib import Path

from deepeval import evaluate
from deepeval.evaluate import AsyncConfig, CacheConfig, DisplayConfig, ErrorConfig
from deepeval.metrics import (
    ArgumentCorrectnessMetric,
    GEval,
    PromptAlignmentMetric,
    ToolCorrectnessMetric,
)
from deepeval.models import OpenAIModel
from deepeval.test_case import LLMTestCase, SingleTurnParams, ToolCall

from rag_library.behavior_evaluation import SUITE, BehaviorCase, LibraryFixture
from rag_library.config import get_settings
from rag_library.deepeval_evaluation import ScoringResult


def build_behavior_case(row: dict) -> LLMTestCase:
    if row.get("suite") != SUITE or row.get("suite_version") != 1:
        raise ValueError("Expected frozen agent-behavior version 1 answers")
    BehaviorCase.model_validate({key: row[key] for key in BehaviorCase.model_fields})
    LibraryFixture.model_validate(row["fixture_data"])
    return LLMTestCase(
        name=row["id"],
        input=row["question"],
        actual_output=row["actual_answer"],
        expected_output=row["expected_answer"],
        tools_called=[
            ToolCall(
                name=call["name"],
                input_parameters=call["arguments"],
                output=call["result"],
            )
            for call in row["tool_calls"]
        ],
        expected_tools=[ToolCall(name=name) for name in row["expected_tools"]],
        metadata={
            "suite": SUITE,
            "category": row["category"],
            "book_ids": row["book_ids"],
            "dataset_sha256": row["dataset_sha256"],
            "configuration": row["configuration"],
            "not_applicable": [] if row["tool_calls"] else ["Argument Correctness"],
        },
    )


def build_behavior_metrics(instructions: list[str], *, has_tools: bool) -> list:
    settings = get_settings()
    judge = OpenAIModel(
        model=settings.eval_judge_model or settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    diagnostics = {"model": judge, "threshold": None, "async_mode": True}
    metrics = [
        ToolCorrectnessMetric(
            model=judge, threshold=1.0, should_exact_match=True, async_mode=True
        )
    ]
    if has_tools:
        metrics.append(ArgumentCorrectnessMetric(**diagnostics))
    metrics.extend(
        [
            GEval(
                name="Agent Response Correctness",
                evaluation_steps=[
                    "Identify the requested outcome using the input and expected "
                    "output. The "
                    "expected output describes minimum behavior, not literal wording.",
                    "Evaluate factual agreement and completeness, accepting equivalent "
                    "wording and additional details supported by actual tool outputs.",
                    "For factual book answers, verify support in the actual "
                    "tools_called "
                    "outputs. Penalize invented facts, guessed missing metadata, and "
                    "contradictions. Do not use outside knowledge.",
                    "For greetings, redirects, or clarification requests, do not "
                    "require tool "
                    "evidence or a factual book answer. For empty or insufficient tool "
                    "results, accept an honest abstention.",
                    "Do not penalize answer length or style here; presentation is "
                    "scored "
                    "separately. Explain factual errors, omissions, or unsupported "
                    "assertions.",
                ],
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.EXPECTED_OUTPUT,
                    SingleTurnParams.TOOLS_CALLED,
                ],
                **diagnostics,
            ),
            PromptAlignmentMetric(prompt_instructions=instructions, **diagnostics),
        ]
    )
    return metrics


def score_behavior_results(
    rows: list[dict], results_folder: Path, max_concurrent: int = 20
) -> ScoringResult:
    """Read only frozen data: no agent, database, retrieval, or current dataset."""
    groups = defaultdict(list)
    errors = {}
    for row in rows:
        if row.get("suite") != SUITE or row.get("suite_version") != 1:
            raise ValueError("Expected frozen agent-behavior version 1 answers")
        if row["error"]:
            errors[row["id"]] = row["error"]
            continue
        instructions = row["response_instructions"]
        if (
            not isinstance(instructions, list)
            or not instructions
            or any(
                not isinstance(item, str) or not item.strip() for item in instructions
            )
        ):
            raise ValueError("Saved response instructions must be nonempty strings")
        groups[(tuple(instructions), bool(row["tool_calls"]))].append(
            build_behavior_case(row)
        )
    evaluations = {}
    for index, ((instructions, has_tools), cases) in enumerate(groups.items(), start=1):
        group = f"{index}-{'with-tools' if has_tools else 'without-tools'}"
        evaluation = evaluate(
            test_cases=cases,
            metrics=build_behavior_metrics(list(instructions), has_tools=has_tools),
            async_config=AsyncConfig(run_async=True, max_concurrent=max_concurrent),
            cache_config=CacheConfig(use_cache=False, write_cache=False),
            error_config=ErrorConfig(ignore_errors=True, skip_on_missing_params=False),
            display_config=DisplayConfig(
                results_folder=str(Path(results_folder) / group),
                inspect_after_run=False,
            ),
        )
        names = [result.name for result in evaluation.test_results]
        if len(names) != len(set(names)) or set(names) != {case.name for case in cases}:
            raise ValueError(
                "DeepEval results do not match submitted behavior case IDs"
            )
        for result in evaluation.test_results:
            for metric in result.metrics_data or []:
                if metric.error:
                    errors[result.name] = f"{metric.name}: {metric.error}"
        evaluations[group] = evaluation
    return ScoringResult(evaluations, errors)
