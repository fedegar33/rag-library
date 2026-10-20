"""Small, sequential agent evaluation for manual review; no automated scoring."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from rag_library.agent.agent import get_agent, run_agent
from rag_library.agent.context import AgentContext, validate_retrieval_options
from rag_library.agent.models import AgentResult
from rag_library.catalog import get_books_by_refs, validate_book_refs
from rag_library.rag.hybrid_search import DEFAULT_CANDIDATE_LIMIT, RRF_CONSTANT
from rag_library.rag.search import RetrievalMethod


@dataclass(frozen=True)
class EvaluationProgress:
    """A case starting, or completing once its result is saved to disk."""

    index: int
    total: int
    case: dict
    elapsed_seconds: float | None = None


def get_retrieval_context(response: AgentResult) -> list[str]:
    """Return actual book passages, preserving tool execution and retrieval order."""
    return [
        source["text"]
        for call in response.tool_calls
        if call.name == "answer_book_question"
        for source in call.result["sources"]
    ]


def load_cases(dataset_path: Path, *, require_book_refs: bool = True) -> list[dict]:
    """Read the curated question set shared by manual and DeepEval runners."""
    cases = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Question set must be a nonempty JSON list")
    ids = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each case must be a JSON object")
        for key in ("id", "question", "expected_answer"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError(f"Each case needs a nonempty string {key}")
        if case["id"] in ids:
            raise ValueError(f"Duplicate case ID: {case['id']}")
        ids.add(case["id"])
        if require_book_refs or "book_refs" in case:
            validate_book_refs(case.get("book_refs"))
    return cases


def run_evaluation(
    dataset_path: Path,
    output_path: Path,
    *,
    on_progress: Callable[[EvaluationProgress], None] | None = None,
    retrieval_method: RetrievalMethod = "hybrid",
    candidate_limit: int | None = None,
) -> list[dict]:
    """Run a fresh manual evaluation, saving completed cases after each question.

    Each question is an independent agent invocation. Failed cases have a null
    actual_answer and an error; the remaining questions still run. Re-running
    replaces the previous output, without modifying the source question set.
    """
    dataset_path = Path(dataset_path)
    validate_retrieval_options(retrieval_method, candidate_limit)
    output_path = Path(output_path)
    if dataset_path.resolve() == output_path.resolve():
        raise ValueError("Results must be saved separately from the question set")
    cases = load_cases(dataset_path)

    agent = get_agent()
    results = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("[]\n", encoding="utf-8")
    for index, case in enumerate(cases, start=1):
        if on_progress is not None:
            on_progress(EvaluationProgress(index, len(cases), case))
        started = perf_counter()
        row = {
            key: case[key] for key in ("id", "question", "expected_answer", "book_refs")
        }
        row.update(
            actual_answer=None,
            tool_calls=[],
            retrieval_context=[],
            error=None,
            book_ids=[],
            attached_books=[],
            retrieval={
                "method": retrieval_method,
                "top_k": 5,
                "candidate_limit": (candidate_limit or DEFAULT_CANDIDATE_LIMIT)
                if retrieval_method == "hybrid"
                else None,
                "rrf_constant": RRF_CONSTANT if retrieval_method == "hybrid" else None,
            },
        )
        try:
            context = AgentContext(
                books=tuple(get_books_by_refs(case["book_refs"])),
                retrieval_method=retrieval_method,
                candidate_limit=candidate_limit,
            )
            row["book_ids"] = context.book_ids
            row["attached_books"] = list(context.books)
            response = run_agent(agent, case["question"], context=context)
            row["actual_answer"] = response.answer
            row["tool_calls"] = [asdict(call) for call in response.tool_calls]
            row["retrieval_context"] = get_retrieval_context(response)
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
        results.append(row)
        output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if on_progress is not None:
            on_progress(
                EvaluationProgress(index, len(cases), row, perf_counter() - started)
            )
    return results
