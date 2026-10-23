"""Validated request body for streaming chat."""

from typing import Annotated, Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list
    )
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value
