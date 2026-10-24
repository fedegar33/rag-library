"""Exercise live event translation and the real graph without paid providers."""

import asyncio
import json
import unittest
from contextlib import aclosing
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from test_attached_context import ScriptedModel, book

from rag_library.agent.agent import build_agent
from rag_library.agent.context import AgentContext, create_agent_context
from rag_library.api.streaming import stream_chat
from rag_library.main import app
from rag_library.rag.search import SearchResult


def decode(frame):
    return json.loads(frame.removeprefix("data: ").strip())


class StreamingModel(ScriptedModel):
    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        response = self.responses.pop(0)
        if response.tool_calls:
            if response.content:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(content=response.content)
                )
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_calls=response.tool_calls,
                )
            )
        else:
            for text in [response.content[:5], response.content[5:]]:
                yield ChatGenerationChunk(message=AIMessageChunk(content=text))


class ChatStreamTests(unittest.IsolatedAsyncioTestCase):
    @patch("rag_library.rag.retriever.hybrid_search")
    async def test_real_graph_streams_tools_sources_and_text_with_two_model_calls(
        self, search
    ):
        search.return_value = [
            SearchResult(
                "Pet Sematary",
                4,
                "Church was short for Winston Churchill.",
                None,
                1,
                7,
                bm25_score=2.0,
                rerank_score=0.9,
            )
        ]
        model = StreamingModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "answer_book_question",
                            "args": {"question": "Church's name?"},
                            "id": "call-church",
                        }
                    ],
                ),
                AIMessage(content="Winston Churchill."),
            ]
        )
        graph = build_agent(model, structured_output=False)
        frames = [
            frame
            async for frame in stream_chat(
                graph,
                "Church's name?",
                AgentContext((7,)),
            )
        ]
        self.assertEqual(frames[-1], "data: [DONE]\n\n")
        events = [decode(frame) for frame in frames[:-1]]
        kinds = [event["type"] for event in events]
        self.assertEqual(
            kinds,
            [
                "start",
                "tool-input-available",
                "tool-output-available",
                "data-source",
                "text-start",
                "text-delta",
                "text-delta",
                "text-end",
                "finish",
            ],
        )
        self.assertEqual(events[1]["toolName"], "answer_book_question")
        self.assertEqual(events[1]["input"], {"question": "Church's name?"})
        self.assertEqual(events[1]["toolCallId"], events[2]["toolCallId"])
        self.assertEqual(events[3]["data"]["book_id"], 7)
        self.assertEqual(events[3]["data"]["chunk_index"], 4)
        self.assertEqual(events[3]["data"]["rerank_score"], 0.9)
        self.assertEqual(
            "".join(e["delta"] for e in events if e["type"] == "text-delta"),
            "Winston Churchill.",
        )
        self.assertEqual(model.responses, [])
        search.assert_called_once()

    @patch("rag_library.catalog.list_books")
    async def test_catalog_preamble_precedes_tool_and_final_intro_follows_result(
        self, catalog
    ):
        catalog.return_value = [book()]
        model = StreamingModel(
            responses=[
                AIMessage(
                    content="Let me check the library.",
                    tool_calls=[
                        {"name": "list_available_books", "args": {}, "id": "catalog"}
                    ],
                ),
                AIMessage(content="Here are the available books."),
            ]
        )
        frames = [
            frame
            async for frame in stream_chat(
                build_agent(model, structured_output=False),
                "Which books are available?",
                AgentContext((7,)),
            )
        ]
        events = [decode(frame) for frame in frames[:-1]]
        kinds = [event["type"] for event in events]
        tool_start = kinds.index("tool-input-available")
        tool_end = kinds.index("tool-output-available")
        self.assertLess(kinds.index("text-end"), tool_start)
        self.assertEqual(
            "".join(
                event["delta"]
                for event in events[:tool_start]
                if event["type"] == "text-delta"
            ),
            "Let me check the library.",
        )
        self.assertEqual(
            "".join(
                event["delta"]
                for event in events[tool_end + 1 :]
                if event["type"] == "text-delta"
            ),
            "Here are the available books.",
        )
        self.assertEqual(
            events[tool_start]["toolCallId"], events[tool_end]["toolCallId"]
        )
        self.assertEqual(events[-1]["type"], "finish")

    async def test_first_text_arrives_while_agent_is_still_running_and_closes_on_cancel(
        self,
    ):
        released = asyncio.Event()
        closed = asyncio.Event()

        class GatedAgent:
            async def astream_events(self, *args, **kwargs):
                try:
                    yield {
                        "event": "on_chat_model_stream",
                        "run_id": "text-1",
                        "metadata": {"langgraph_node": "model"},
                        "parent_ids": [],
                        "data": {"chunk": AIMessageChunk(content="First")},
                    }
                    await released.wait()
                    raise AssertionError("The response should not be drained")
                finally:
                    closed.set()

        async with aclosing(
            stream_chat(GatedAgent(), "Hi", AgentContext((7,)))
        ) as stream:
            self.assertEqual(decode(await anext(stream))["type"], "start")
            self.assertEqual(
                decode(await asyncio.wait_for(anext(stream), 1))["type"], "text-start"
            )
            self.assertEqual(
                decode(await asyncio.wait_for(anext(stream), 1))["delta"], "First"
            )
            self.assertFalse(released.is_set())
        self.assertTrue(closed.is_set())

    async def test_midstream_error_is_terminal_and_does_not_expose_exception(self):
        class FailedAgent:
            async def astream_events(self, *args, **kwargs):
                raise RuntimeError("secret provider details")
                yield

        with self.assertLogs("rag_library.api.streaming", level="ERROR"):
            frames = [
                frame
                async for frame in stream_chat(
                    FailedAgent(),
                    "Hi",
                    AgentContext((7,)),
                )
            ]
        self.assertEqual([decode(f)["type"] for f in frames[:-1]], ["start", "error"])
        self.assertNotIn("secret", "".join(frames))
        self.assertEqual(frames[-1], "data: [DONE]\n\n")

    @patch(
        "rag_library.rag.retriever.hybrid_search", side_effect=RuntimeError("secret")
    )
    async def test_real_tool_failure_ends_stream_without_success(self, search):
        model = StreamingModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "answer_book_question",
                            "args": {"question": "Where?"},
                            "id": "failed-call",
                        }
                    ],
                )
            ]
        )
        with self.assertLogs("rag_library.api.streaming", level="ERROR"):
            frames = [
                f
                async for f in stream_chat(
                    build_agent(model, structured_output=False),
                    "Where?",
                    AgentContext((7,)),
                )
            ]
        kinds = [decode(f)["type"] for f in frames[:-1]]
        self.assertEqual(kinds, ["start", "tool-input-available", "error"])
        self.assertNotIn("secret", "".join(frames))

    async def test_cancelling_wait_for_event_closes_upstream(self):
        waiting, closed = asyncio.Event(), asyncio.Event()

        class WaitingAgent:
            async def astream_events(self, *args, **kwargs):
                try:
                    waiting.set()
                    await asyncio.Event().wait()
                    yield
                finally:
                    closed.set()

        stream = stream_chat(WaitingAgent(), "Hi", AgentContext((7,)))
        await anext(stream)
        task = asyncio.create_task(anext(stream))
        await asyncio.wait_for(waiting.wait(), 1)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(closed.is_set())

    async def test_nested_model_text_is_filtered_and_partial_text_closed_on_error(self):
        class NestedAgent:
            async def astream_events(self, *args, **kwargs):
                yield {
                    "event": "on_tool_start",
                    "run_id": "tool-1",
                    "name": "answer_book_question",
                    "data": {"input": {"question": "Where?"}},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "run_id": "nested",
                    "metadata": {"langgraph_node": "model"},
                    "parent_ids": ["tool-1"],
                    "data": {"chunk": AIMessageChunk(content="Hidden")},
                }
                yield {
                    "event": "on_chat_model_stream",
                    "run_id": "outer",
                    "metadata": {"langgraph_node": "model"},
                    "parent_ids": [],
                    "data": {"chunk": AIMessageChunk(content="Visible")},
                }
                raise RuntimeError("provider failure")

        with self.assertLogs("rag_library.api.streaming", level="ERROR"):
            frames = [
                f
                async for f in stream_chat(NestedAgent(), "Where?", AgentContext((7,)))
            ]
        events = [decode(f) for f in frames[:-1]]
        self.assertEqual(
            [e["type"] for e in events][-3:], ["text-delta", "text-end", "error"]
        )
        self.assertEqual(
            [e["delta"] for e in events if e["type"] == "text-delta"], ["Visible"]
        )

    async def test_empty_retrieval_leaves_abstention_to_agent(self):
        with patch("rag_library.rag.retriever.hybrid_search", return_value=[]):
            model = StreamingModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "answer_book_question",
                                "args": {"question": "Unknown?"},
                                "id": "call-empty",
                            }
                        ],
                    ),
                    AIMessage(content="I couldn't find that in the ingested books."),
                ]
            )
            frames = [
                f
                async for f in stream_chat(
                    build_agent(model, structured_output=False),
                    "Unknown?",
                    AgentContext((7,)),
                )
            ]
        events = [decode(f) for f in frames[:-1]]
        self.assertNotIn("error", [e["type"] for e in events])
        self.assertNotIn("data-source", [e["type"] for e in events])
        self.assertEqual(
            next(e["output"] for e in events if e["type"] == "tool-output-available"),
            {"sources": []},
        )


class ChatRouteTests(unittest.TestCase):
    @patch("rag_library.api.routes.get_agent")
    @patch("rag_library.catalog.list_books", return_value=[book()])
    def test_validation_precedes_initialization_and_success_sets_sse_headers(
        self, catalog, get
    ):
        client = TestClient(app)
        for payload in [
            {"message": "Hi", "book_ids": None},
            {"message": "Hi", "book_ids": [0]},
            {"message": "Hi", "book_ids": [True]},
            {"message": "Hi", "book_ids": ["7"]},
            {"message": "Hi", "book_ids": [7, 99]},
            {"message": "Hi", "book_ids": [99]},
            {"message": " ", "book_ids": [7]},
        ]:
            self.assertEqual(client.post("/chat", json=payload).status_code, 422)
        get.assert_not_called()
        get.return_value = build_agent(
            StreamingModel(responses=[AIMessage(content="Hello!")]),
            structured_output=False,
        )
        with patch(
            "rag_library.api.routes.create_agent_context", wraps=create_agent_context
        ) as create_context:
            response = client.post("/chat", json={"message": "Hi", "book_ids": [7, 7]})
        create_context.assert_called_once_with([7, 7])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertEqual(response.headers["x-vercel-ai-ui-message-stream"], "v1")
        self.assertEqual(response.headers["x-accel-buffering"], "no")
        get.assert_called_once_with(structured_output=False)
        self.assertTrue(response.text.endswith("data: [DONE]\n\n"))

    @patch("rag_library.api.routes.get_agent")
    @patch("rag_library.catalog.list_books", return_value=[book(7), book(8)])
    @patch("rag_library.agent.tools.BookRetriever")
    def test_without_attachments_streams_global_retrieval(
        self, retriever, catalog, get
    ):
        retriever.return_value.invoke.return_value = []
        for payload in [{"message": "Where?"}, {"message": "Where?", "book_ids": []}]:
            with self.subTest(payload=payload):
                get.return_value = build_agent(
                    StreamingModel(
                        responses=[
                            AIMessage(
                                content="",
                                tool_calls=[
                                    dict(
                                        name="answer_book_question",
                                        args={"question": "Where?"},
                                        id="global",
                                    )
                                ],
                            ),
                            AIMessage(content="No matching evidence."),
                        ]
                    ),
                    structured_output=False,
                )
                response = TestClient(app).post("/chat", json=payload)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn('"type": "finish"', response.text)
                self.assertEqual(retriever.call_args.kwargs["book_ids"], [7, 8])

    @patch("rag_library.api.routes.get_agent")
    @patch("rag_library.catalog.list_books", return_value=[])
    @patch("rag_library.agent.tools.BookRetriever")
    def test_empty_library_streams_tool_message_without_retrieval(
        self, retriever, catalog, get
    ):
        get.return_value = build_agent(
            StreamingModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                name="answer_book_question",
                                args={"question": "Where?"},
                                id="empty-library",
                            )
                        ],
                    ),
                    AIMessage(content="No books are available."),
                ]
            ),
            structured_output=False,
        )
        response = TestClient(app).post("/chat", json={"message": "Where?"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn(
            '"message": "No books are available in the library."', response.text
        )
        self.assertIn('"type": "finish"', response.text)
        self.assertNotIn('"type": "data-source"', response.text)
        retriever.assert_not_called()

    @patch("rag_library.catalog.list_books", return_value=[book()])
    @patch("rag_library.api.routes.get_agent", side_effect=RuntimeError("secret"))
    def test_initialization_error_is_http_503(self, get, catalog):
        with self.assertLogs("rag_library.api.routes", level="ERROR"):
            response = TestClient(app).post(
                "/chat", json={"message": "Hi", "book_ids": [7]}
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "Agent service unavailable"})
