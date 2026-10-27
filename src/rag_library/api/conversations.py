"""Single-user conversation resources and checkpoint-backed streaming turns."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated, Any
from uuid import UUID, uuid4

import anyio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import Field

from rag_library.agent.agent import get_agent
from rag_library.agent.context import create_agent_context
from rag_library.agent.history import ConversationWindow
from rag_library.api.schemas import UserMessage, WireModel
from rag_library.api.streaming import encode_event, stream_chat
from rag_library.catalog import list_books
from rag_library.conversations import (
    ChatConflict,
    ChatNotFound,
    ConversationStore,
    DisplayMessage,
    get_conversation_store,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats", tags=["chats"])


class BookSelection(WireModel):
    book_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(
        default_factory=list
    )


class PersistentQuestion(BookSelection):
    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
    message: str = Field(min_length=1, max_length=4000)


def store_dependency() -> ConversationStore:
    try:
        return get_conversation_store()
    except Exception as error:
        logger.exception("Chat storage unavailable")
        raise HTTPException(503, "Chat storage unavailable") from error


Store = Annotated[ConversationStore, Depends(store_dependency)]


async def execution(chat_id: UUID, store: Store):
    try:
        # A dedicated connection holds a PostgreSQL advisory lock until the stream
        # closes. It also supplies the checkpointer and works across API workers.
        async with store.execution(str(chat_id)) as saver:
            yield saver
    except ChatConflict as error:
        raise HTTPException(409, str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Chat execution unavailable")
        raise HTTPException(503, "Chat service unavailable") from error


def selected_books(ids: list[int]) -> list[dict]:
    catalog = {book["id"]: book for book in list_books()}
    if any(book_id not in catalog for book_id in ids):
        raise ValueError("Selected book is unavailable")
    return [
        {"id": book_id, "title": catalog[book_id]["title"]}
        for book_id in dict.fromkeys(ids)
    ]


@router.post("", status_code=201)
def create_chat(store: Store):
    return store.create()


@router.get("")
def list_chats(store: Store):
    return {"chats": store.list_chats()}


@router.get("/{chat_id}")
def get_chat(chat_id: UUID, store: Store):
    try:
        return store.get(str(chat_id))
    except ChatNotFound as error:
        raise HTTPException(404, "Chat not found") from error


@router.patch("/{chat_id}")
async def update_chat(
    chat_id: UUID,
    request: BookSelection,
    store: Store,
    saver: Annotated[Any, Depends(execution)],
):
    try:
        books = await asyncio.to_thread(selected_books, request.book_ids)
        return await asyncio.to_thread(store.set_books, str(chat_id), books)
    except ChatNotFound as error:
        raise HTTPException(404, "Chat not found") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/{chat_id}/messages", response_class=StreamingResponse)
async def send_question(
    chat_id: UUID,
    request: PersistentQuestion,
    store: Store,
    saver: Annotated[Any, Depends(execution)],
):
    chat_id = str(chat_id)
    try:
        text = UserMessage(role="user", content=request.message).content
        # Current selection is authoritative, including on explicit retries.
        context = await asyncio.to_thread(create_agent_context, request.book_ids)
        books = await asyncio.to_thread(selected_books, request.book_ids)
        checkpoint_id = await asyncio.to_thread(store.checkpoint, chat_id)
        agent = get_agent(
            structured_output=False,
            checkpointer=saver,
            middleware=[ConversationWindow()],
        )
        message_id = await asyncio.to_thread(
            store.begin_turn, chat_id, request.request_id, text, books
        )
    except ChatNotFound as error:
        raise HTTPException(404, "Chat not found") from error
    except ChatConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Chat initialization failed")
        raise HTTPException(503, "Chat service unavailable") from error

    # An exact committed checkpoint excludes unfinished tool calls from a failed
    # attempt. A nonexistent initial ID deliberately starts an empty state, even
    # if a first attempt previously wrote intermediate checkpoints then crashed.
    config = {
        "configurable": {
            "thread_id": chat_id,
            "checkpoint_id": checkpoint_id or str(uuid4()),
        }
    }

    async def persist_stream() -> AsyncIterator[str]:
        display = DisplayMessage(message_id)
        completed = False
        last_save = 0.0
        try:
            async with aclosing(
                stream_chat(
                    agent,
                    [HumanMessage(content=text, id=request.request_id)],
                    context,
                    config=config,
                    message_id=message_id,
                )
            ) as stream:
                async for frame in stream:
                    if frame == "data: [DONE]\n\n":
                        yield frame
                        continue
                    event = json.loads(frame.removeprefix("data: "))
                    display.apply(event)
                    if event["type"] == "finish":
                        parts = display.message["parts"]
                        if not any(
                            part["type"] == "text"
                            and part["text"].strip()
                            or part["type"] == "dynamic-tool"
                            and part["toolName"] == "list_available_books"
                            and part["state"] == "output-available"
                            for part in parts
                        ):
                            raise ValueError("Agent completed without an answer")
                        state = await agent.aget_state(
                            {"configurable": {"thread_id": chat_id}}
                        )
                        if state.next:
                            raise ValueError("Agent has unfinished work")
                        await display.save(
                            store,
                            request.request_id,
                            status="completed",
                            checkpoint_id=state.config["configurable"]["checkpoint_id"],
                        )
                        completed = True
                    elif time.monotonic() - last_save >= 0.5 or event["type"] in {
                        "tool-output-available",
                        "data-source",
                        "error",
                    }:
                        await display.save(store, request.request_id)
                        last_save = time.monotonic()
                    yield frame
        except Exception:
            logger.exception("Persistent chat stream failed")
            yield encode_event(
                {"type": "error", "errorText": "Chat service unavailable"}
            )
            yield "data: [DONE]\n\n"
        finally:
            if not completed:
                # Starlette cancels its task group on disconnect. Shield the last
                # snapshot so stop/switch/refresh still preserves received output.
                with anyio.CancelScope(shield=True):
                    try:
                        await display.save(
                            store, request.request_id, status="interrupted"
                        )
                    except Exception:
                        logger.exception("Could not save interrupted chat")

    return StreamingResponse(
        persist_stream(),
        media_type="text/event-stream",
        headers={
            "x-vercel-ai-ui-message-stream": "v1",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
