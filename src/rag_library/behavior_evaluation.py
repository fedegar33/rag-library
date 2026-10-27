"""Single-turn agent evaluation against synthetic, database-free tool fixtures."""

import hashlib
import json
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, Literal

from langchain.agents.middleware import wrap_tool_call
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from rag_library.agent.agent import get_agent
from rag_library.agent.context import AgentContext
from rag_library.agent.models import AgentResult, BookCard, ToolCallRecord
from rag_library.agent.prompts import SYSTEM_PROMPT
from rag_library.agent.tools import answer_book_question, list_available_books
from rag_library.config import get_settings
from rag_library.evaluation import get_retrieval_context

ToolName = Literal["list_available_books", "answer_book_question"]
SUITE = "agent-behavior"


class FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FixtureSource(FixtureModel):
    book_id: int = Field(gt=0, strict=True)
    book_title: str
    chapter_number: int | None
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)


class LibraryFixture(FixtureModel):
    books: list[BookCard]
    sources: list[FixtureSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_sources(self):
        books = {book.id: book for book in self.books}
        if len(books) != len(self.books):
            raise ValueError("Fixture book IDs must be unique")
        for source in self.sources:
            if (
                source.book_id not in books
                or source.book_title != books[source.book_id].title
            ):
                raise ValueError("Fixture sources must refer to the fixture's books")
        return self

    def middleware(self):
        """Override results, preserving registered tools, arguments, and runtime."""
        fixture = self

        @wrap_tool_call
        def fixture_results(request, handler):
            call = request.tool_call
            if call["name"] == "list_available_books":
                if call["args"]:
                    raise ValueError("Catalog tool received unexpected arguments")
                output = {"books": [book.model_dump() for book in fixture.books]}
            elif call["name"] == "answer_book_question":
                if set(call["args"]) != {"question"} or not isinstance(
                    call["args"]["question"], str
                ):
                    raise ValueError("Answer tool requires only a question argument")
                ids = request.runtime.context.attached_book_ids
                scope = set(ids) if ids else {book.id for book in fixture.books}
                output = {
                    "sources": [
                        source.model_dump()
                        for source in fixture.sources
                        if source.book_id in scope
                    ][:5]
                }
                if not fixture.books:
                    output["message"] = "No books are available in the library."
            else:
                # Never delegate to a production tool in fixture mode.
                raise ValueError(f"Unknown fixture tool: {call['name']}")
            return ToolMessage(
                content=json.dumps(output, ensure_ascii=False),
                tool_call_id=call["id"],
                name=call["name"],
            )

        return fixture_results


class BehaviorCase(FixtureModel):
    id: str = Field(min_length=1)
    category: Literal["catalog", "content", "social", "out_of_scope", "clarification"]
    question: str = Field(min_length=1, max_length=4000)
    fixture: str
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list
    )
    expected_tools: list[ToolName]
    expected_answer: str = Field(min_length=1)


class BehaviorDataset(FixtureModel):
    suite: Literal["agent-behavior"]
    version: Literal[1]
    response_instructions: list[str] = Field(min_length=1)
    fixtures: dict[str, LibraryFixture]
    cases: list[BehaviorCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_cases(self):
        seen = set()
        for case in self.cases:
            if case.id in seen:
                raise ValueError(f"Duplicate case ID: {case.id}")
            seen.add(case.id)
            if case.fixture not in self.fixtures:
                raise ValueError(f"Unknown fixture: {case.fixture}")
            ids = {book.id for book in self.fixtures[case.fixture].books}
            if not set(case.book_ids) <= ids:
                raise ValueError(f"Unknown attached fixture book in case {case.id}")
        return self


def load_behavior_dataset(
    path: Path, *, case_ids: Sequence[str] | None = None
) -> BehaviorDataset:
    dataset = BehaviorDataset.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )
    if case_ids is None:
        return dataset
    selected = set(case_ids)
    missing = selected - {case.id for case in dataset.cases}
    if not selected or missing:
        raise ValueError(f"Unknown or empty case IDs: {', '.join(sorted(missing))}")
    return dataset.model_copy(
        update={"cases": [case for case in dataset.cases if case.id in selected]}
    )


def _plain_result(state: dict[str, Any]) -> tuple[AgentResult, list[str]]:
    """Collect actual graph executions and final prose, not a generated JSON answer."""
    calls = {}
    records = []
    prose = []
    for message in state["messages"]:
        if isinstance(message, AIMessage):
            prose.append(message.text)
            calls.update({call["id"]: call for call in message.tool_calls})
        elif isinstance(message, ToolMessage):
            if message.status == "error":
                raise ValueError("Agent tool execution failed")
            call = calls.pop(message.tool_call_id)
            records.append(
                ToolCallRecord(call["name"], call["args"], json.loads(message.content))
            )
    if (
        calls
        or not state["messages"]
        or not isinstance(state["messages"][-1], AIMessage)
    ):
        raise ValueError("Agent did not finish its tool execution")
    return AgentResult(state["messages"][-1].text, records), prose


def run_behavior_evaluation(
    dataset_path: Path,
    output_path: Path,
    *,
    case_ids: Sequence[str] | None = None,
) -> list[dict]:
    """Generate sequentially; freeze expectations and fixtures before scoring."""
    dataset_path, output_path = Path(dataset_path), Path(output_path)
    if dataset_path.resolve() == output_path.resolve():
        raise ValueError("Results must be saved separately from the dataset")
    dataset = load_behavior_dataset(dataset_path, case_ids=case_ids)
    settings = get_settings()
    configuration = {
        "model": settings.openai_chat_model,
        "system_prompt": SYSTEM_PROMPT,
        "response_format": "text",
        "tool_execution": "synthetic-fixtures",
        "tool_schemas": [
            tool.tool_call_schema.model_json_schema()
            for tool in (list_available_books, answer_book_question)
        ],
    }
    dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    rows = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("[]\n", encoding="utf-8")
    for index, case in enumerate(dataset.cases, start=1):
        fixture = dataset.fixtures[case.fixture]
        row = {
            **case.model_dump(),
            "suite": SUITE,
            "suite_version": dataset.version,
            "dataset_sha256": dataset_hash,
            "response_instructions": list(dataset.response_instructions),
            "fixture_data": fixture.model_dump(),
            "configuration": deepcopy(configuration),
            "actual_answer": None,
            "assistant_messages": [],
            "tool_calls": [],
            "retrieval_context": [],
            "error": None,
        }
        print(f"[{index}/{len(dataset.cases)}] {case.id}", flush=True)
        try:
            agent = get_agent(
                structured_output=False, middleware=[fixture.middleware()]
            )
            context = AgentContext(attached_book_ids=tuple(case.book_ids))
            state = agent.invoke(
                {"messages": [{"role": "user", "content": case.question}]},
                context=context,
            )
            response, prose = _plain_result(state)
            row["actual_answer"] = response.answer
            row["assistant_messages"] = prose
            row["tool_calls"] = [asdict(call) for call in response.tool_calls]
            row["retrieval_context"] = get_retrieval_context(response)
        except Exception as error:
            row["error"] = f"{type(error).__name__}: {error}"
        rows.append(row)
        output_path.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return rows
