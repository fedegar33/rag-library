"""HTTP request and response schemas for the catalog agent."""

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator

from rag_library.agent.models import ToolCallRecord


class AgentRequest(BaseModel):
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class AgentResponse(BaseModel):
    answer: str
    tool_calls: list[ToolCallRecord]
