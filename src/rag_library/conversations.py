"""Durable chat presentation, separate from LangGraph's agent checkpoints."""

import asyncio
import copy
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import uuid4

import anyio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from rag_library.config import get_database_settings
from rag_library.database import Base, create_database_engine

json_type = JSON().with_variant(JSONB, "postgresql")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="New chat")
    books: Mapped[list] = mapped_column(json_type, default=list)
    checkpoint_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChatTurn(Base):
    __tablename__ = "chat_turns"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    user_message: Mapped[dict] = mapped_column(json_type)
    assistant_message: Mapped[dict] = mapped_column(json_type)
    status: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChatNotFound(Exception):
    pass


class ChatConflict(Exception):
    pass


class ConversationStore:
    def __init__(self, engine):
        self.engine = engine
        # psycopg expects a PostgreSQL URI, without SQLAlchemy's driver suffix.
        self.connection_url = engine.url.set(drivername="postgresql").render_as_string(
            hide_password=False
        )

    def create(self) -> dict:
        now = datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            chat = Conversation(
                id=str(uuid4()),
                title="New chat",
                books=[],
                created_at=now,
                updated_at=now,
            )
            session.add(chat)
            return self.summary(chat)

    @staticmethod
    def summary(chat: Conversation) -> dict:
        return {
            "id": chat.id,
            "title": chat.title,
            "books": chat.books,
            "created_at": chat.created_at.isoformat(),
            "updated_at": chat.updated_at.isoformat(),
        }

    def list_chats(self) -> list[dict]:
        with Session(self.engine) as session:
            return [
                self.summary(chat)
                for chat in session.scalars(
                    select(Conversation).order_by(
                        Conversation.updated_at.desc(), Conversation.id
                    )
                )
            ]

    def get(self, chat_id: str) -> dict:
        with Session(self.engine) as session:
            chat = session.get(Conversation, chat_id)
            if chat is None:
                raise ChatNotFound
            messages = []
            for turn in session.scalars(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == chat_id)
                .order_by(ChatTurn.created_at, ChatTurn.id)
            ):
                assistant = {**turn.assistant_message}
                if turn.status != "completed":
                    assistant["metadata"] = {
                        "interruption": "Response interrupted. You can retry."
                    }
                    assistant["parts"] = [
                        {**part, "state": "done"} if part["type"] == "text" else part
                        for part in assistant["parts"]
                    ]
                messages.extend([turn.user_message, assistant])
            return {**self.summary(chat), "messages": messages}

    def set_books(self, chat_id: str, books: list[dict]) -> dict:
        with Session(self.engine) as session, session.begin():
            chat = session.get(Conversation, chat_id)
            if chat is None:
                raise ChatNotFound
            chat.books = books
            chat.updated_at = datetime.now(UTC)
            return self.summary(chat)

    def begin_turn(self, chat_id: str, request_id: str, text: str, books: list) -> str:
        """Called under a per-chat PostgreSQL advisory lock; never replay a request."""
        with Session(self.engine) as session, session.begin():
            chat = session.get(Conversation, chat_id)
            if chat is None:
                raise ChatNotFound
            if session.get(ChatTurn, request_id) is not None:
                raise ChatConflict(
                    "This question was already accepted. Reload the chat."
                )
            # A stale running turn survived a disconnected process. It stays visible,
            # but only the last completed checkpoint is eligible for model history.
            for stale in session.scalars(
                select(ChatTurn).where(
                    ChatTurn.conversation_id == chat_id, ChatTurn.status == "streaming"
                )
            ):
                stale.status = "interrupted"
            now = datetime.now(UTC)
            if not session.scalar(
                select(ChatTurn.id).where(ChatTurn.conversation_id == chat_id).limit(1)
            ):
                chat.title = text
            chat.updated_at = now
            session.add(
                ChatTurn(
                    id=request_id,
                    conversation_id=chat_id,
                    status="streaming",
                    created_at=now,
                    user_message={
                        "id": request_id,
                        "role": "user",
                        "parts": [{"type": "text", "text": text}],
                        "metadata": {"books": books},
                    },
                    assistant_message={
                        "id": str(uuid4()),
                        "role": "assistant",
                        "parts": [],
                    },
                )
            )
            session.flush()
            return session.get(ChatTurn, request_id).assistant_message["id"]

    def checkpoint(self, chat_id: str) -> str | None:
        with Session(self.engine) as session:
            chat = session.get(Conversation, chat_id)
            if chat is None:
                raise ChatNotFound
            return chat.checkpoint_id

    def save(
        self,
        request_id: str,
        message: dict,
        *,
        status="streaming",
        checkpoint_id: str | None = None,
    ) -> None:
        with Session(self.engine) as session, session.begin():
            turn = session.get(ChatTurn, request_id)
            turn.assistant_message = message
            turn.status = status
            chat = session.get(Conversation, turn.conversation_id)
            chat.updated_at = datetime.now(UTC)
            if checkpoint_id is not None:
                # Commit the UI turn and the pointer to its finished state together.
                chat.checkpoint_id = checkpoint_id

    @asynccontextmanager
    async def execution(self, chat_id: str) -> AsyncIterator[AsyncPostgresSaver]:
        async with await AsyncConnection.connect(
            self.connection_url,
            autocommit=True,
            row_factory=dict_row,
            connect_timeout=10,
        ) as conn:
            cursor = await conn.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired",
                ("rag-library-chat:" + chat_id,),
            )
            if not (await cursor.fetchone())["acquired"]:
                raise ChatConflict("This chat is busy. Try again when it finishes.")
            # Setup is idempotent; serialize migrations across API workers.
            await conn.execute("SELECT pg_advisory_lock(791930174)")
            saver = AsyncPostgresSaver(conn)
            try:
                await saver.setup()
            finally:
                await conn.execute("SELECT pg_advisory_unlock(791930174)")
            try:
                yield saver
            finally:
                await conn.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    ("rag-library-chat:" + chat_id,),
                )


@lru_cache
def get_conversation_store() -> ConversationStore:
    engine = create_database_engine(get_database_settings().database_url)
    with engine.begin() as connection:
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(791930175)")
        Base.metadata.create_all(
            connection,
            tables=[
                Conversation.__table__,
                ChatTurn.__table__,
            ],
        )
    return ConversationStore(engine)


class DisplayMessage:
    """Accumulate the same ordered UI parts that the SSE consumer receives."""

    def __init__(self, message_id: str):
        self.message: dict[str, Any] = {
            "id": message_id,
            "role": "assistant",
            "parts": [],
        }
        self.text: dict[str, dict] = {}
        self.tools: dict[str, dict] = {}

    def apply(self, event: dict) -> None:
        kind = event["type"]
        parts = self.message["parts"]
        if kind == "text-start":
            part = {"type": "text", "text": "", "state": "streaming"}
            self.text[event["id"]] = part
            parts.append(part)
        elif kind == "text-delta":
            self.text[event["id"]]["text"] += event["delta"]
        elif kind == "text-end":
            self.text[event["id"]]["state"] = "done"
        elif kind == "tool-input-available":
            part = {
                "type": "dynamic-tool",
                "toolCallId": event["toolCallId"],
                "toolName": event["toolName"],
                "input": event["input"],
                "state": "input-available",
            }
            self.tools[event["toolCallId"]] = part
            parts.append(part)
        elif kind == "tool-output-available":
            self.tools[event["toolCallId"]].update(
                state="output-available", output=event["output"]
            )
        elif kind == "data-source":
            parts.append({key: value for key, value in event.items()})

    async def save(self, store: ConversationStore, request_id: str, **kwargs) -> None:
        # Copy before handing mutable stream state to a worker thread.
        # Finish writes before cancellation cleanup writes a newer snapshot.
        with anyio.CancelScope(shield=True):
            await asyncio.to_thread(
                store.save, request_id, copy.deepcopy(self.message), **kwargs
            )
