"""Attachment validation and real graph runtime injection, without provider calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from rag_library.agent.agent import build_agent, run_agent
from rag_library.agent.context import AgentContext, create_agent_context
from rag_library.agent.tools import answer_book_question, list_available_books
from rag_library.catalog import get_books_by_refs
from rag_library.rag.search import SearchResult


def book(book_id=7):
    return dict(
        id=book_id,
        title="Book",
        authors=None,
        language="en",
        content_sha256="a" * 64,
        categories=[],
        cover_url=None,
    )


def card(book_id=7):
    return {
        key: value
        for key, value in book(book_id).items()
        if key not in ("language", "content_sha256")
    }


class ScriptedModel(BaseChatModel):
    responses: list[AIMessage]

    @property
    def _llm_type(self):
        return "offline-script"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self.responses.pop(0))])


class AttachedContextTests(unittest.TestCase):
    @patch("rag_library.catalog.list_books", return_value=[book(7), book(8)])
    def test_catalog_tool_lists_all_books_without_model_arguments(self, catalog):
        self.assertEqual(list_available_books.func(), {"books": [card(7), card(8)]})
        catalog.assert_called_once_with()
        schema = list_available_books.tool_call_schema.model_json_schema()
        self.assertEqual(schema["properties"], {})

    @patch("rag_library.catalog.list_books", return_value=[book(7), book(8)])
    @patch("rag_library.agent.tools.BookRetriever")
    def test_no_attachments_resolve_all_books_and_reach_retriever(
        self, retriever, catalog
    ):
        retriever.return_value.invoke.return_value = []
        for ids in [(), []]:
            catalog.reset_mock()
            context = create_agent_context(ids)
            self.assertEqual(context.attached_book_ids, ())
            catalog.assert_not_called()
            answer_book_question.func(
                question="Where?", runtime=SimpleNamespace(context=context)
            )
        self.assertEqual(create_agent_context().attached_book_ids, ())
        self.assertEqual(
            [call.kwargs["book_ids"] for call in retriever.call_args_list],
            [[7, 8], [7, 8]],
        )

    @patch("rag_library.catalog.list_books")
    @patch("rag_library.agent.tools.BookRetriever")
    def test_global_scope_resolves_current_catalog_at_retrieval_time(
        self, retriever, catalog
    ):
        context = create_agent_context()
        catalog.assert_not_called()
        catalog.side_effect = [[book(7)], [book(8), book(9)]]
        retriever.return_value.invoke.return_value = []
        for _ in range(2):
            answer_book_question.func(
                question="Where?", runtime=SimpleNamespace(context=context)
            )
        self.assertEqual(context.attached_book_ids, ())
        self.assertEqual(
            [call.kwargs["book_ids"] for call in retriever.call_args_list],
            [[7], [8, 9]],
        )

    def test_context_keeps_only_normalized_ids_and_rejects_invalid_ids(self):
        ids = [8, 7, 8]
        context = AgentContext(attached_book_ids=ids)
        ids.append(9)
        self.assertEqual(context.attached_book_ids, (8, 7))
        for invalid in [(0,), (-1,), (True,), ("7",)]:
            with self.subTest(ids=invalid), self.assertRaises(ValueError):
                AgentContext(attached_book_ids=invalid)

    @patch("rag_library.catalog.list_books", return_value=[])
    @patch("rag_library.agent.tools.BookRetriever")
    def test_empty_library_returns_explicit_message_without_retrieval(
        self, retriever, catalog
    ):
        context = create_agent_context()
        result = answer_book_question.func(
            question="Where?", runtime=SimpleNamespace(context=context)
        )
        self.assertEqual(result["sources"], [])
        self.assertIn("No books", result["message"])
        self.assertEqual(list_available_books.func(), {"books": []})
        retriever.assert_not_called()

    @patch("rag_library.catalog.list_books", return_value=[book(7), book(8)])
    def test_graph_catalog_listing_does_not_expand_attached_retrieval_scope(
        self, catalog
    ):
        agent = build_agent(
            ScriptedModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            dict(name="list_available_books", args={}, id="list")
                        ],
                    ),
                    AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                name="answer_book_question",
                                args={"question": "Where?"},
                                id="answer",
                            )
                        ],
                    ),
                    AIMessage(content='{"answer":"Evidence"}'),
                ]
            )
        )
        with patch("rag_library.agent.tools.BookRetriever") as retriever:
            retriever.return_value.invoke.return_value = []
            result = run_agent(agent, "Where?", context=create_agent_context([7]))
        self.assertEqual(result.tool_calls[0].name, "list_available_books")
        self.assertEqual(result.tool_calls[0].result, {"books": [card(7), card(8)]})
        self.assertEqual(retriever.call_args.kwargs["book_ids"], [7])

    @patch("rag_library.agent.tools.BookRetriever")
    def test_graph_injects_hidden_scope_and_does_not_keep_previous_attachments(
        self, ask
    ):
        ask.return_value.invoke.return_value = []
        responses = []
        for index in range(2):
            responses.extend(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                name="answer_book_question",
                                args={"question": "Where?"},
                                id=str(index),
                            )
                        ],
                    ),
                    AIMessage(content='{"answer":"Evidence"}'),
                ]
            )
        agent = build_agent(ScriptedModel(responses=responses))
        for book_id in [7, 8]:
            result = run_agent(agent, "Where?", context=AgentContext((book_id,)))
            self.assertEqual(result.answer, "Evidence")
            self.assertEqual(result.tool_calls[0].arguments, {"question": "Where?"})
        self.assertEqual(
            [call.kwargs["book_ids"] for call in ask.call_args_list], [[7], [8]]
        )
        schema = answer_book_question.tool_call_schema.model_json_schema()
        self.assertEqual(set(schema["properties"]), {"question"})

    @patch("rag_library.rag.answering.ChatOpenAI")
    @patch("rag_library.rag.retriever.hybrid_search")
    def test_agent_uses_hybrid_and_preserves_lexical_only_source(self, search, chat):
        search.return_value = [
            SearchResult(
                "Book",
                4,
                "Ludlow is the destination.",
                None,
                1,
                7,
                bm25_score=2.0,
                rrf_score=1 / 61,
                bm25_rank=1,
                rerank_score=0.9,
                rrf_rank=41,
            )
        ]
        agent = build_agent(
            ScriptedModel(
                responses=[
                    AIMessage(
                        content="",
                        tool_calls=[
                            dict(
                                name="answer_book_question",
                                args={"question": "Where?"},
                                id="one",
                            )
                        ],
                    ),
                    AIMessage(content='{"answer":"Ludlow"}'),
                ]
            )
        )
        result = run_agent(
            agent, "Where?", context=AgentContext((7,), candidate_limit=30)
        )
        search.assert_called_once_with(
            "Where?", limit=5, book_ids=[7], candidate_limit=30, rerank=True
        )
        self.assertEqual(result.answer, "Ludlow")
        source = result.tool_calls[0].result["sources"][0]
        self.assertEqual(source["book_id"], 7)
        self.assertEqual(source["bm25_rank"], 1)
        self.assertEqual(source["bm25_score"], 2.0)
        self.assertAlmostEqual(source["rrf_score"], 1 / 61)
        self.assertEqual(source["rerank_score"], 0.9)
        self.assertEqual(source["rrf_rank"], 41)
        self.assertIsNone(source["similarity"])
        chat.assert_not_called()

    @patch("rag_library.catalog.list_books")
    @patch("rag_library.agent.tools.BookRetriever")
    def test_agent_can_explicitly_use_vector_for_comparison(self, ask, catalog):
        ask.return_value.invoke.return_value = []
        answer_book_question.func(
            question="Where?",
            runtime=SimpleNamespace(
                context=AgentContext((7,), retrieval_method="vector")
            ),
        )
        ask.assert_called_once_with(
            k=5, book_ids=[7], method="vector", candidate_limit=None, rerank=True
        )
        ask.return_value.invoke.assert_called_once_with("Where?")
        catalog.assert_not_called()

    def test_invalid_retrieval_configuration_rejected_before_agent_execution(self):
        for method, depth in [
            ("invalid", None),
            ("vector", 20),
            ("hybrid", 4),
            ("hybrid", True),
        ]:
            with (
                self.subTest(method=method, depth=depth),
                self.assertRaises(ValueError),
            ):
                AgentContext((7,), retrieval_method=method, candidate_limit=depth)

    @patch("rag_library.rag.retriever.hybrid_search", return_value=[])
    def test_agent_can_disable_reranking_through_answering(self, search):
        answer_book_question.func(
            question="Where?",
            runtime=SimpleNamespace(
                context=AgentContext((7,), candidate_limit=100, rerank=False)
            ),
        )
        search.assert_called_once_with(
            "Where?", limit=5, book_ids=[7], candidate_limit=100, rerank=False
        )

    @patch("rag_library.catalog.list_books")
    def test_refs_resolve_after_numeric_ids_change_and_missing_refs_fail(self, catalog):
        for book_id in [7, 99]:
            catalog.return_value = [book(book_id)]
            self.assertEqual(get_books_by_refs(["a" * 64])[0]["id"], book_id)
        with self.assertRaisesRegex(ValueError, "No ingested book"):
            get_books_by_refs(["b" * 64])
        with self.assertRaisesRegex(ValueError, "Unknown book IDs"):
            create_agent_context([99, 123])
