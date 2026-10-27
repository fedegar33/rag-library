"""Opt-in real PostgreSQL tests in an isolated, automatically removed schema.

Set RAG_TEST_POSTGRES=1 and run unittest discovery for this file.
Uses DATABASE_URL from the project environment; no providers are called.
"""

import asyncio
import os
import unittest
from contextlib import aclosing
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from test_chat_streaming import StreamingModel

from rag_library.agent.agent import build_agent
from rag_library.agent.context import AgentContext
from rag_library.api.conversations import (
    PersistentQuestion,
    send_question,
    store_dependency,
)
from rag_library.config import get_database_settings
from rag_library.conversations import (
    ChatConflict,
    ChatTurn,
    Conversation,
    ConversationStore,
)
from rag_library.main import app


@unittest.skipUnless(
    os.environ.get("RAG_TEST_POSTGRES") == "1", "Opt-in PostgreSQL test"
)
class PostgresChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_chat_" + uuid4().hex
        cls.root = create_engine(get_database_settings().database_url)
        with cls.root.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        url = make_url(get_database_settings().database_url).update_query_dict(
            {"options": f"-csearch_path={cls.schema}"}
        )
        cls.engine = create_engine(url)
        Conversation.__table__.create(cls.engine)
        ChatTurn.__table__.create(cls.engine)
        cls.store = ConversationStore(cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.root.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))
        cls.root.dispose()

    def setUp(self):
        app.dependency_overrides[store_dependency] = lambda: self.store
        self.addCleanup(app.dependency_overrides.clear)

    def factory(self, **kwargs):
        return build_agent(
            StreamingModel(responses=[AIMessage(content="Saved answer")]), **kwargs
        )

    def test_api_restores_checkpoint_and_ui_across_requests_and_rejects_duplicates(
        self,
    ):
        with (
            patch("rag_library.api.conversations.get_agent", side_effect=self.factory),
            patch("rag_library.api.conversations.selected_books", return_value=[]),
            patch(
                "rag_library.api.conversations.create_agent_context",
                return_value=AgentContext(()),
            ),
        ):
            client = TestClient(app)
            created = client.post("/chats")
            self.assertEqual(created.status_code, 201, created.text)
            chat_id = created.json()["id"]
            endpoint = f"/chats/{chat_id}/messages"
            for question, request_id in [
                ("First question", "first"),
                ("Second question", "second"),
            ]:
                response = client.post(
                    endpoint, json={"message": question, "request_id": request_id}
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn('"type": "finish"', response.text)
                self.assertNotIn('"type": "error"', response.text)
            restored = TestClient(app).get(f"/chats/{chat_id}").json()
            self.assertEqual(
                [m["parts"][0]["text"] for m in restored["messages"]],
                [
                    "First question",
                    "Saved answer",
                    "Second question",
                    "Saved answer",
                ],
            )
            self.assertEqual(
                client.post(
                    endpoint, json={"message": "First question", "request_id": "first"}
                ).status_code,
                409,
            )
            self.assertEqual(client.get(f"/chats/{uuid4()}").status_code, 404)

            async def checkpoint_messages():
                async with self.store.execution(chat_id) as saver:
                    checkpoint = await saver.aget_tuple(
                        {
                            "configurable": {
                                "thread_id": chat_id,
                                "checkpoint_id": self.store.checkpoint(chat_id),
                            }
                        }
                    )
                    return checkpoint.checkpoint["channel_values"]["messages"]

            self.assertEqual(len(asyncio.run(checkpoint_messages())), 4)

    def test_database_lock_excludes_second_worker_and_releases_after_disconnect(self):
        chat_id = self.store.create()["id"]

        async def run():
            async with self.store.execution(chat_id):
                with self.assertRaises(ChatConflict):
                    async with self.store.execution(chat_id):
                        self.fail("Second worker acquired an active chat")
            async with self.store.execution(chat_id):
                pass

        asyncio.run(run())

    def test_failed_first_attempt_keeps_partial_and_next_turn_starts_clean(self):
        class FailedModel(StreamingModel):
            def _stream(self, *args, **kwargs):
                yield ChatGenerationChunk(message=AIMessageChunk(content="Partial"))
                raise RuntimeError("Offline simulated failure")

        models = [
            FailedModel(responses=[]),
            StreamingModel(responses=[AIMessage(content="Recovered")]),
        ]

        def factory(**kwargs):
            return build_agent(models.pop(0), **kwargs)

        with (
            patch("rag_library.api.conversations.get_agent", side_effect=factory),
            patch("rag_library.api.conversations.selected_books", return_value=[]),
            patch(
                "rag_library.api.conversations.create_agent_context",
                return_value=AgentContext(()),
            ),
        ):
            client = TestClient(app)
            chat_id = client.post("/chats").json()["id"]
            endpoint = f"/chats/{chat_id}/messages"
            with self.assertLogs("rag_library.api.streaming", level="ERROR"):
                response = client.post(
                    endpoint,
                    json={
                        "message": "First",
                        "request_id": "failed-" + uuid4().hex,
                    },
                )
            self.assertIn('"type": "error"', response.text)
            self.assertIsNone(self.store.checkpoint(chat_id))
            restored = client.get(f"/chats/{chat_id}").json()
            self.assertEqual(restored["messages"][-1]["parts"][0]["text"], "Partial")
            self.assertIn("interruption", restored["messages"][-1]["metadata"])
            response = client.post(
                endpoint,
                json={
                    "message": "Retry",
                    "request_id": "retry-" + uuid4().hex,
                },
            )
            self.assertIn('"type": "finish"', response.text)

            async def read_checkpoint():
                async with self.store.execution(chat_id) as saver:
                    checkpoint = await saver.aget_tuple(
                        {
                            "configurable": {
                                "thread_id": chat_id,
                                "checkpoint_id": self.store.checkpoint(chat_id),
                            }
                        }
                    )
                    return checkpoint.checkpoint["channel_values"]["messages"]

            self.assertEqual(
                [m.content for m in asyncio.run(read_checkpoint())],
                ["Retry", "Recovered"],
            )

    def test_disconnect_flushes_partial_and_releases_connection_lock(self):
        chat_id = self.store.create()["id"]

        async def run():
            closed = asyncio.Event()

            class WaitingAgent:
                async def astream_events(self, *args, **kwargs):
                    try:
                        yield {
                            "event": "on_chat_model_stream",
                            "run_id": "model",
                            "parent_ids": [],
                            "metadata": {"langgraph_node": "model"},
                            "data": {"chunk": AIMessageChunk(content="Saved partial")},
                        }
                        await asyncio.Event().wait()
                    finally:
                        closed.set()

            with (
                patch(
                    "rag_library.api.conversations.get_agent",
                    return_value=WaitingAgent(),
                ),
                patch("rag_library.api.conversations.selected_books", return_value=[]),
                patch(
                    "rag_library.api.conversations.create_agent_context",
                    return_value=AgentContext(()),
                ),
            ):
                async with self.store.execution(chat_id) as saver:
                    response = await send_question(
                        UUID(chat_id),
                        PersistentQuestion(
                            request_id="disconnect-" + uuid4().hex,
                            message="Question",
                        ),
                        self.store,
                        saver,
                    )
                    async with aclosing(response.body_iterator) as stream:
                        await anext(stream)
                        await anext(stream)
                        self.assertIn("Saved partial", await anext(stream))
                    self.assertTrue(closed.is_set())
                async with self.store.execution(chat_id):
                    pass

        asyncio.run(run())
        restored = self.store.get(chat_id)["messages"][-1]
        self.assertEqual(restored["parts"][0]["text"], "Saved partial")
        self.assertIn("interruption", restored["metadata"])
        self.assertIsNone(self.store.checkpoint(chat_id))
