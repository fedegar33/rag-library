"""Persistence boundaries and real checkpoint-backed agents, without providers."""

import json
import unittest
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import create_engine
from test_chat_streaming import StreamingModel

from rag_library.agent.agent import build_agent
from rag_library.agent.context import AgentContext
from rag_library.agent.history import ConversationWindow
from rag_library.api.streaming import stream_chat
from rag_library.conversations import (
    ChatConflict,
    ChatNotFound,
    ChatTurn,
    Conversation,
    ConversationStore,
    DisplayMessage,
)


class ConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Conversation.__table__.create(self.engine)
        ChatTurn.__table__.create(self.engine)
        self.store = ConversationStore(self.engine)
        self.chat = self.store.create()

    def tearDown(self):
        self.engine.dispose()

    def test_recreated_store_restores_complete_ui_and_scope_without_other_chats(self):
        books = [{"id": 7, "title": "Book"}]
        self.store.set_books(self.chat["id"], books)
        reply = self.store.begin_turn(self.chat["id"], "request-1", "Question", books)
        display = DisplayMessage(reply)
        events = [
            {"type": "text-start", "id": "a"},
            {"type": "text-delta", "id": "a", "delta": "Checking."},
            {"type": "text-end", "id": "a"},
            {
                "type": "tool-input-available",
                "toolCallId": "tool",
                "toolName": "list_available_books",
                "input": {},
            },
            {
                "type": "tool-output-available",
                "toolCallId": "tool",
                "output": {"books": []},
            },
            {
                "type": "data-source",
                "id": "source",
                "data": {"book_id": 7, "text": "Passage"},
            },
            {"type": "text-start", "id": "b"},
            {"type": "text-delta", "id": "b", "delta": "Answer."},
            {"type": "text-end", "id": "b"},
        ]
        for event in events:
            display.apply(event)
        self.store.save(
            "request-1",
            display.message,
            status="completed",
            checkpoint_id="checkpoint-1",
        )
        reopened = ConversationStore(self.engine)
        chat = reopened.get(self.chat["id"])
        self.assertEqual(chat["title"], "Question")
        self.assertEqual(chat["books"], books)
        self.assertEqual(chat["messages"][0]["metadata"]["books"], books)
        self.assertEqual(chat["messages"][1], display.message)
        self.assertEqual(reopened.checkpoint(self.chat["id"]), "checkpoint-1")
        other = reopened.create()
        self.assertEqual(reopened.get(other["id"])["messages"], [])
        self.assertEqual(len(reopened.list_chats()), 2)
        with self.assertRaises(ChatNotFound):
            reopened.get(str(uuid4()))

    def test_failed_attempt_keeps_partial_ui_but_never_advances_committed_state(self):
        reply = self.store.begin_turn(self.chat["id"], "one", "First", [])
        self.store.save(
            "one",
            {"id": reply, "role": "assistant", "parts": []},
            status="completed",
            checkpoint_id="good",
        )
        reply = self.store.begin_turn(self.chat["id"], "two", "Second", [])
        partial = {
            "id": reply,
            "role": "assistant",
            "parts": [{"type": "text", "text": "Partial", "state": "streaming"}],
        }
        self.store.save("two", partial)
        restored = self.store.get(self.chat["id"])["messages"][-1]
        self.assertEqual(restored["parts"][0]["text"], "Partial")
        self.assertEqual(restored["parts"][0]["state"], "done")
        self.assertIn("interruption", restored["metadata"])
        self.assertEqual(self.store.checkpoint(self.chat["id"]), "good")
        self.store.begin_turn(self.chat["id"], "three", "Retry", [])
        with self.assertRaises(ChatConflict):
            self.store.begin_turn(self.chat["id"], "two", "Second", [])


class CheckpointChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_window_bounds_model_input_without_deleting_checkpoint_history(self):
        class RecordingModel(StreamingModel):
            seen: list = []

            def _stream(self, messages, *args, **kwargs):
                self.seen.append([message.content for message in messages])
                yield from super()._stream(messages, *args, **kwargs)

        model = RecordingModel(responses=[AIMessage(content="New answer")])
        graph = build_agent(
            model,
            structured_output=False,
            checkpointer=InMemorySaver(),
            middleware=[ConversationWindow()],
        )
        old = "Old history " * 4000
        config = await graph.aupdate_state(
            {"configurable": {"thread_id": "large", "checkpoint_id": str(uuid4())}},
            {"messages": [HumanMessage(content=old), AIMessage(content="Old answer")]},
        )
        async for _ in stream_chat(graph, "Current", AgentContext(()), config=config):
            pass
        self.assertNotIn(old, model.seen[0])
        self.assertIn("Current", model.seen[0])
        state = await graph.aget_state({"configurable": {"thread_id": "large"}})
        self.assertEqual(state.values["messages"][0].content, old)
        self.assertEqual(len(state.values["messages"]), 4)

    async def test_fresh_agent_restores_history_from_committed_checkpoint(
        self,
    ):
        saver = InMemorySaver()
        config = {"configurable": {"thread_id": "chat", "checkpoint_id": str(uuid4())}}
        model = StreamingModel(responses=[AIMessage(content="First answer")])
        graph = build_agent(
            model,
            structured_output=False,
            checkpointer=saver,
            middleware=[ConversationWindow()],
        )
        async for _ in stream_chat(
            graph,
            [HumanMessage(content="My name is Ada", id="q1")],
            AgentContext(()),
            config=config,
        ):
            pass
        committed = (
            await graph.aget_state({"configurable": {"thread_id": "chat"}})
        ).config
        fresh = build_agent(
            StreamingModel(responses=[AIMessage(content="Ada")]),
            structured_output=False,
            checkpointer=saver,
            middleware=[ConversationWindow()],
        )
        async for _ in stream_chat(
            fresh,
            [HumanMessage(content="My name?", id="q2")],
            AgentContext((7,)),
            config=committed,
        ):
            pass
        state = await fresh.aget_state({"configurable": {"thread_id": "chat"}})
        self.assertEqual(
            [m.content for m in state.values["messages"]],
            ["My name is Ada", "First answer", "My name?", "Ada"],
        )
        self.assertFalse(state.next)

    async def test_interrupted_tool_branch_is_not_replayed_on_next_question(self):
        saver = InMemorySaver()
        graph = build_agent(
            StreamingModel(responses=[AIMessage(content="Done")]),
            structured_output=False,
            checkpointer=saver,
        )
        base = {"configurable": {"thread_id": "chat", "checkpoint_id": str(uuid4())}}
        async for _ in stream_chat(graph, "First", AgentContext(()), config=base):
            pass
        committed = (
            await graph.aget_state({"configurable": {"thread_id": "chat"}})
        ).config
        await graph.aupdate_state(
            committed,
            {
                "messages": [
                    HumanMessage(content="Interrupted"),
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "list_available_books",
                                "args": {},
                                "id": "unfinished",
                            }
                        ],
                    ),
                ]
            },
        )
        fresh = build_agent(
            StreamingModel(responses=[AIMessage(content="New answer")]),
            structured_output=False,
            checkpointer=saver,
        )
        events = []
        async for frame in stream_chat(
            fresh, "Next", AgentContext(()), config=committed
        ):
            if "[DONE]" not in frame:
                events.append(json.loads(frame.removeprefix("data: ")))
        self.assertNotIn("error", [e["type"] for e in events])
        self.assertNotIn("tool-input-available", [e["type"] for e in events])
        state = await fresh.aget_state({"configurable": {"thread_id": "chat"}})
        self.assertEqual(
            [m.content for m in state.values["messages"]],
            ["First", "Done", "Next", "New answer"],
        )
