"""Structured model output and server-owned agent execution records."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass(frozen=True)
class AgentResult:
    answer: str
    tool_calls: list[ToolCallRecord]


class BookCard(BaseModel):
    """Public catalog data for a book card; no internal hashes or image bytes."""

    id: int = Field(gt=0, strict=True)
    title: str
    authors: str | None
    categories: list[str]
    cover_url: str | None


class AvailableBooksResult(BaseModel):
    """Validated output of the server-owned catalog tool."""

    books: list[BookCard]


class AgentAnswer(BaseModel):
    """The model-generated final answer, excluding server-owned execution records."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(description="Final answer in English")

    @field_validator("answer")
    @classmethod
    def require_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Agent answer cannot be empty")
        return value
