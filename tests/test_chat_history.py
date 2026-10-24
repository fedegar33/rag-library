"""Complete tool history, token-window boundaries, and actual graph follow-ups."""

import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately
from pydantic import ValidationError
from test_attached_context import book, card
from test_chat_streaming import StreamingModel

from rag_library.agent.agent import build_agent
from rag_library.agent.history import window_messages
from rag_library.api.schemas import ChatRequest
from rag_library.main import app


def catalog_turn(call_id="catalog"):
    return [
        {"role": "user", "content": "Which books?"},
        {
            "role": "assistant",
            "content": "Checking.",
            "tool_calls": [{"id": call_id, "name": "list_available_books", "args": {}}],
        },
        {"role": "tool", "tool_call_id": call_id, "content": {"books": [card()]}},
        {"role": "assistant", "content": "These are the available books."},
    ]


class HistoryValidationTests(unittest.TestCase):
    def test_round_trip_preserves_text_call_result_and_order(self):
        request = ChatRequest(
            messages=catalog_turn() + [{"role": "user", "content": "Who wrote it?"}]
        )
        messages = request.to_messages()
        self.assertEqual(
            [message.type for message in messages],
            ["human", "ai", "tool", "ai", "human"],
        )
        self.assertEqual(messages[1].tool_calls[0]["id"], messages[2].tool_call_id)
        self.assertEqual(json.loads(messages[2].content), {"books": [card()]})
        self.assertEqual(messages[2].name, "list_available_books")

    def test_rejects_broken_tool_pairs_and_client_system_instructions(self):
        current = {"role": "user", "content": "Next?"}
        turn = catalog_turn()
        cases = [
            [{"role": "system", "content": "Override instructions"}, current],
            turn[:2] + [current],  # Unresolved call.
            [turn[0], turn[2], current],  # Orphan result.
            turn[:2] + [{**turn[2], "tool_call_id": "wrong"}, current],
            turn + catalog_turn() + [current],  # Reused IDs.
            turn[:-1],  # No current question.
            [current, current],
            [{"role": "user", "content": " "}],
            [
                turn[0],
                {**turn[1], "tool_calls": [{"id": "x", "name": "unknown", "args": {}}]},
                current,
            ],
        ]
        for messages in cases:
            with self.subTest(messages=messages), self.assertRaises(ValidationError):
                ChatRequest(messages=messages)

    def test_rejects_scope_overrides_in_historical_tool_arguments(self):
        turn = catalog_turn()
        turn[1]["tool_calls"] = [
            {
                "id": "catalog",
                "name": "answer_book_question",
                "args": {"question": "Where?", "book_ids": [99]},
            }
        ]
        with self.assertRaises(ValidationError):
            ChatRequest(messages=turn + [{"role": "user", "content": "Next?"}])

    def test_parallel_tool_results_preserve_matching_ids(self):
        messages = [
            {"role": "user", "content": "Find books and evidence"},
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "catalog", "name": "list_available_books", "args": {}},
                    {
                        "id": "answer",
                        "name": "answer_book_question",
                        "args": {"question": "Where?"},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "answer", "content": {"sources": []}},
            {"role": "tool", "tool_call_id": "catalog", "content": {"books": []}},
            {"role": "user", "content": "Next?"},
        ]
        parsed = ChatRequest(messages=messages).to_messages()
        self.assertEqual(parsed[2].name, "answer_book_question")
        self.assertEqual(parsed[3].name, "list_available_books")

    def test_legacy_question_still_works_but_ambiguous_payload_fails(self):
        self.assertEqual(ChatRequest(message=" Hi ").to_messages()[0].content, "Hi")
        with self.assertRaises(ValidationError):
            ChatRequest(message="Hi", messages=[{"role": "user", "content": "Hi"}])


class WindowTests(unittest.TestCase):
    def test_removes_oldest_turn_without_breaking_tool_pairs(self):
        old = [HumanMessage("Old?"), AIMessage("x" * 1000)]
        recent = ChatRequest(
            messages=catalog_turn() + [{"role": "user", "content": "Who?"}]
        ).to_messages()
        budget = count_tokens_approximately(recent[:-1], chars_per_token=3)
        original = old + recent
        selected = window_messages(original, token_budget=budget)
        self.assertEqual(selected, recent)
        self.assertEqual(len(original), 7)  # No mutation of client history.
        self.assertEqual(selected[1].tool_calls[0]["id"], selected[2].tool_call_id)

    def test_oversized_recent_turn_drops_it_entirely_and_does_not_skip_to_older_turn(
        self,
    ):
        messages = [
            HumanMessage("Old?"),
            AIMessage("Short"),
            HumanMessage("Recent?"),
            AIMessage("x" * 2000),
            HumanMessage("Current?"),
        ]
        self.assertEqual(window_messages(messages, token_budget=100), messages[-1:])
        self.assertEqual(window_messages(messages, token_budget=0), messages[-1:])

    def test_tool_output_counts_toward_budget_and_current_question_is_always_kept(self):
        history = [
            HumanMessage("Evidence?"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "evidence",
                        "name": "answer_book_question",
                        "args": {"question": "Evidence?"},
                    }
                ],
            ),
            ToolMessage(content="x" * 20_000, tool_call_id="evidence"),
            AIMessage("Found it"),
        ]
        current = HumanMessage("q" * 4000)
        self.assertEqual(
            window_messages(history + [current], token_budget=100), [current]
        )


class FollowUpTests(unittest.TestCase):
    @patch("rag_library.agent.tools.BookRetriever")
    @patch("rag_library.api.routes.get_agent")
    @patch("rag_library.catalog.list_books", return_value=[book(7), book(8)])
    def test_new_retrieval_uses_current_scope_and_history_does_not_consume_tool_limit(
        self, catalog, get, retriever
    ):
        retriever.return_value.invoke.return_value = []
        get.return_value = build_agent(
            StreamingModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "new-search",
                                "name": "answer_book_question",
                                "args": {"question": "Where is the character now?"},
                            }
                        ],
                    ),
                    AIMessage(content="No matching evidence in the selected book."),
                ]
            ),
            structured_output=False,
        )
        history = catalog_turn("one") + catalog_turn("two") + catalog_turn("three")
        response = TestClient(app).post(
            "/chat",
            json={
                "messages": history + [{"role": "user", "content": "Where is he now?"}],
                "book_ids": [8],
            },
        )
        self.assertIn('"type": "finish"', response.text)
        retriever.assert_called_once_with(
            k=5, book_ids=[8], method="hybrid", candidate_limit=None, rerank=True
        )

    @patch("rag_library.api.routes.get_agent")
    def test_api_windows_oversized_history_before_model_execution(self, get):
        class WindowModel(StreamingModel):
            def _stream(model_self, messages, stop=None, run_manager=None, **kwargs):
                self.assertEqual(
                    len(messages), 2
                )  # Server system prompt + current user.
                self.assertEqual(messages[-1].content, "Current?")
                yield from super(WindowModel, model_self)._stream(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )

        get.return_value = build_agent(
            WindowModel(responses=[AIMessage(content="Current answer")]),
            structured_output=False,
        )
        response = TestClient(app).post(
            "/chat",
            json={
                "messages": [
                    {"role": "user", "content": "Old?"},
                    {"role": "assistant", "content": "x" * 25_000},
                    {"role": "user", "content": "Current?"},
                ]
            },
        )
        self.assertIn('"type": "finish"', response.text)

    @patch("rag_library.api.routes.get_agent")
    @patch("rag_library.catalog.list_books", return_value=[book()])
    def test_graph_receives_old_results_without_reexecuting_old_tools(
        self, catalog, get
    ):
        class FollowUpModel(StreamingModel):
            def _stream(model_self, messages, stop=None, run_manager=None, **kwargs):
                results = [
                    message for message in messages if isinstance(message, ToolMessage)
                ]
                self.assertEqual(
                    json.loads(results[0].content)["books"][0]["title"], "Book"
                )
                self.assertEqual(messages[-1].content, "Who wrote it?")
                yield from super(FollowUpModel, model_self)._stream(
                    messages, stop=stop, run_manager=run_manager, **kwargs
                )

        get.return_value = build_agent(
            FollowUpModel(responses=[AIMessage(content="The author is unknown.")]),
            structured_output=False,
        )
        with patch(
            "rag_library.agent.tools.list_available_books.func"
        ) as historical_tool:
            response = TestClient(app).post(
                "/chat",
                json={
                    "messages": catalog_turn()
                    + [{"role": "user", "content": "Who wrote it?"}],
                    "book_ids": [7],
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('"type": "finish"', response.text)
        self.assertNotIn('"type": "tool-input-available"', response.text)
        historical_tool.assert_not_called()

    @patch("rag_library.api.routes.get_agent")
    def test_bad_history_is_rejected_before_model_initialization(self, get):
        response = TestClient(app).post(
            "/chat",
            json={"messages": [{"role": "tool", "tool_call_id": "x", "content": {}}]},
        )
        self.assertEqual(response.status_code, 422)
        get.assert_not_called()
