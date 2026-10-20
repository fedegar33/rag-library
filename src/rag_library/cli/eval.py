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
    parser.add_argument("--output", type=Path, default=Path("evals/basic_result.json"))
    parser.add_argument("--results-folder", type=Path, default=Path("evals/results"))
    parser.add_argument("--max-concurrent", type=int, default=20)
    parser.add_argument("--manual", action="store_true", help="Alias for generate")
    parser.add_argument(
        "--method",
        choices=["vector", "bm25", "hybrid"],
        help="Answer retrieval method for generation (default: hybrid)",
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
    if args.stage == "score" and (
        args.method is not None or args.candidate_limit is not None
    ):
        parser.error(
            "Retrieval options apply only to generation; score uses saved answers"
        )
    try:
        validate_retrieval_options(args.method or "hybrid", args.candidate_limit)
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
        rows = run_evaluation(
            args.dataset,
            args.output,
            on_progress=_print_progress,
            retrieval_method=method,
            candidate_limit=args.candidate_limit,
        )
        failures = sum(row["error"] is not None for row in rows)
        print(
            f"\nSaved {len(rows)} answers to {args.output} "
            f"({failures} failed) in {perf_counter() - started:.1f}s.",
            flush=True,
        )
        if args.stage == "generate":
            return 1 if failures else 0

    # Read the frozen answers so score never needs to run the RAG pipeline.
    rows = load_cases(args.output, require_book_refs=False)
    print(
        f"\nPreparing {len(rows)} saved answers for DeepEval "
        f"(max concurrent: {args.max_concurrent})...",
        flush=True,
    )
    scored = score_results(rows, args.results_folder, args.max_concurrent)
    for case_id, error in scored.errors.items():
        print(f"{case_id}: {error}", file=sys.stderr)
    return 0 if scored.success else 1
