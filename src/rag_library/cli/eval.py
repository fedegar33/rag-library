"""Generate agent answers and score them with DeepEval."""

import argparse
import sys
from pathlib import Path
from time import perf_counter

from rag_library.agent.context import validate_retrieval_options
from rag_library.deepeval_evaluation import score_results
from rag_library.evaluation import EvaluationProgress, load_cases, run_evaluation


def _print_progress(progress: EvaluationProgress) -> None:
    case = progress.case
    if progress.elapsed_seconds is None:
        print(f"\n[{progress.index}/{progress.total}] {case['id']}", flush=True)
        print(f"  Question: {case['question']}", flush=True)
        print("  Running agent...", flush=True)
        return
    elapsed = f"{progress.elapsed_seconds:.1f}s"
    if case["error"]:
        print(f"  FAILED in {elapsed} | {case['error']} | saved", flush=True)
        return
    tools = " -> ".join(call["name"] for call in case["tool_calls"]) or "none"
    passages = len(case["retrieval_context"])
    print(
        f"  Done in {elapsed} | tools: {tools} | passages: {passages} | saved",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        nargs="?",
        choices=["all", "generate", "score"],
        default="all",
    )
    parser.add_argument("--dataset", type=Path, default=Path("evals/basic.json"))
    parser.add_argument(
        "--id",
        dest="case_ids",
        action="append",
        help="Run only this exact case ID (repeat to select several cases)",
    )
    parser.add_argument("--output", type=Path, default=Path("evals/basic_result.json"))
    parser.add_argument("--results-folder", type=Path, default=Path("evals/results"))
    parser.add_argument("--max-concurrent", type=int, default=20)
    parser.add_argument(
        "--metrics",
        choices=["core", "all"],
        default=None,
        help="Scoring metrics: core (default: Correctness + Faithfulness) or all five",
    )
    parser.add_argument("--manual", action="store_true", help="Alias for generate")
    parser.add_argument(
        "--method",
        choices=["vector", "bm25", "hybrid"],
        help="Answer retrieval method for generation (default: hybrid)",
    )
    parser.add_argument(
        "--rerank",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Rerank hybrid candidates with Cohere (default: enabled)",
    )
    parser.add_argument(
        "--candidate-limit",
        type=int,
        help="Hybrid candidates per method (default: 20; at least 5)",
    )
    args = parser.parse_args()
    if args.max_concurrent < 1:
        parser.error("--max-concurrent must be greater than zero")
    if args.manual and args.stage not in ("all", "generate"):
        parser.error("--manual cannot be combined with score")
    if args.manual:
        args.stage = "generate"
    if args.stage == "generate" and args.metrics is not None:
        parser.error("--metrics applies only to all or score; generate does not score")
    if args.stage == "score" and (
        args.method is not None
        or args.candidate_limit is not None
        or args.rerank is not None
    ):
        parser.error(
            "Retrieval options apply only to generation; score uses saved answers"
        )
    try:
        validate_retrieval_options(args.method or "hybrid", args.candidate_limit)
        if args.rerank and (args.method or "hybrid") != "hybrid":
            raise ValueError("--rerank requires --method hybrid")
    except ValueError as error:
        parser.error(str(error))
    paths = [args.dataset, args.output]
    if len({path.resolve() for path in paths}) != len(paths):
        parser.error("Dataset and answers must use separate files")

    if args.stage in ("all", "generate"):
        method = args.method or "hybrid"
        print(
            f"Loading {args.dataset} and initializing the agent ({method})...",
            flush=True,
        )
        started = perf_counter()
        try:
            rows = run_evaluation(
                args.dataset,
                args.output,
                on_progress=_print_progress,
                retrieval_method=method,
                candidate_limit=args.candidate_limit,
                rerank=args.rerank is not False,
                case_ids=args.case_ids,
            )
        except ValueError as error:
            parser.error(str(error))
        failures = sum(row["error"] is not None for row in rows)
        print(
            f"\nSaved {len(rows)} answers to {args.output} "
            f"({failures} failed) in {perf_counter() - started:.1f}s.",
            flush=True,
        )
        if args.stage == "generate":
            return 1 if failures else 0

    # Read the frozen answers so score never needs to run the RAG pipeline.
    try:
        rows = load_cases(args.output, require_book_refs=False, case_ids=args.case_ids)
    except ValueError as error:
        parser.error(str(error))
    print(
        f"\nPreparing {len(rows)} saved answers for DeepEval "
        f"(max concurrent: {args.max_concurrent})...",
        flush=True,
    )
    legacy_count = sum("answerable" not in row for row in rows)
    if legacy_count:
        print(
            f"{legacy_count} saved cases have no answerable field; treating them as "
            "answerable. Generate fresh answers to preserve dataset labels.",
            flush=True,
        )
    scored = score_results(
        rows, args.results_folder, args.max_concurrent, metrics=args.metrics or "core"
    )
    for case_id, error in scored.errors.items():
        print(f"{case_id}: {error}", file=sys.stderr)
    return 0 if scored.success else 1
