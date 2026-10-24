"""Validated conversation wire format and conversion into LangChain messages."""

import json
from typing import Annotated, Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from rag_library.agent.models import AvailableBooksResult


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserMessage(WireModel):
    role: Literal["user"]
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class ToolCall(WireModel):
    id: str = Field(min_length=1, max_length=128)
    name: Literal["list_available_books", "answer_book_question"]
    args: dict[str, Any]

    @model_validator(mode="after")
    def validate_arguments(self):
        if self.name == "list_available_books":
            if self.args:
                raise ValueError("list_available_books takes no arguments")
        elif (
            set(self.args) != {"question"}
            or not isinstance(self.args["question"], str)
            or not self.args["question"].strip()
        ):
            raise ValueError("answer_book_question requires only a question")
        return self


class AssistantMessage(WireModel):
    role: Literal["assistant"]
    content: str = Field(default="", max_length=100_000)
    tool_calls: list[ToolCall] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def require_content(self):
        if not self.content.strip() and not self.tool_calls:
            raise ValueError("Assistant messages need text or tool calls")
        return self


class ToolResult(WireModel):
    role: Literal["tool"]
    tool_call_id: str = Field(min_length=1, max_length=128)
    content: dict[str, Any]


ChatMessage = Annotated[
    UserMessage | AssistantMessage | ToolResult, Field(discriminator="role")
]


class ChatRequest(BaseModel):
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list
    )
    # Retain the single-question body for CLI/curl clients during this transition.
    message: str | None = Field(default=None, min_length=1, max_length=4000)
    messages: list[ChatMessage] | None = Field(
        default=None, min_length=1, max_length=1000
    )

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_conversation(self):
        if (self.message is None) == (self.messages is None):
            raise ValueError("Supply either message or messages")
        if self.messages is None:
            return self
        if not isinstance(self.messages[0], UserMessage) or not isinstance(
            self.messages[-1], UserMessage
        ):
            raise ValueError("Conversation must start and end with a user question")
        if len(json.dumps([item.model_dump() for item in self.messages])) > 1_000_000:
            raise ValueError("Conversation payload is too large")
        seen: set[str] = set()
        pending: dict[str, ToolCall] = {}
        previous = None
        for item in self.messages:
            if pending and not isinstance(item, ToolResult):
                raise ValueError("Every tool call needs its result before continuing")
            if isinstance(item, UserMessage) and isinstance(previous, UserMessage):
                raise ValueError("Historical questions need an assistant response")
            if isinstance(item, AssistantMessage):
                for call in item.tool_calls:
                    if call.id in seen:
                        raise ValueError("Duplicate tool call ID")
                    seen.add(call.id)
                    pending[call.id] = call
            elif isinstance(item, ToolResult):
                call = pending.pop(item.tool_call_id, None)
                if call is None:
                    raise ValueError("Tool result has no matching call")
                if call.name == "list_available_books":
                    AvailableBooksResult.model_validate(item.content)
                else:
                    sources = item.content.get("sources")
                    if not isinstance(sources, list) or any(
                        not isinstance(source, dict)
                        or not isinstance(source.get("text"), str)
                        for source in sources
                    ):
                        raise ValueError("Retrieval results need source passages")
            previous = item
        return self

    def to_messages(self) -> list[BaseMessage]:
        if self.messages is None:
            return [HumanMessage(content=self.message)]
        result: list[BaseMessage] = []
        names: dict[str, str] = {}
        for item in self.messages:
            if isinstance(item, UserMessage):
                result.append(HumanMessage(content=item.content))
            elif isinstance(item, AssistantMessage):
                calls = [call.model_dump() for call in item.tool_calls]
                names.update({call.id: call.name for call in item.tool_calls})
                result.append(AIMessage(content=item.content, tool_calls=calls))
            else:
                result.append(
                    ToolMessage(
                        content=json.dumps(item.content, ensure_ascii=False),
                        tool_call_id=item.tool_call_id,
                        name=names[item.tool_call_id],
                    )
                )
        return result
