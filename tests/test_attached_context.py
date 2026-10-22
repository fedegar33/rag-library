"""Attachment validation and real graph runtime injection, without provider calls."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from rag_library.agent.agent import build_agent, run_agent
from rag_library.agent.context import AgentContext, create_agent_context
from rag_library.agent.tools import answer_book_question, list_books
from rag_library.catalog import get_books_by_refs
from rag_library.rag.search import SearchResult


def book(book_id=7):
    return dict(
        id=book_id, title="Book", authors=None, language="en", content_sha256="a" * 64
    )


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
    def test_catalog_tool_only_exposes_current_attachments(self):
        attached = (book(7), book(8))
        result = list_books.func(
            runtime=SimpleNamespace(context=AgentContext(attached))
        )
        self.assertEqual(result, {"books": list(attached)})
        with self.assertRaises(ValueError):
            AgentContext(())

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
            result = run_agent(agent, "Where?", context=AgentContext((book(book_id),)))
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
            agent, "Where?", context=AgentContext((book(),), candidate_limit=30)
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

    @patch("rag_library.agent.tools.BookRetriever")
    def test_agent_can_explicitly_use_vector_for_comparison(self, ask):
        ask.return_value.invoke.return_value = []
        answer_book_question.func(
            question="Where?",
            runtime=SimpleNamespace(
                context=AgentContext((book(),), retrieval_method="vector")
            ),
        )
        ask.assert_called_once_with(
            k=5, book_ids=[7], method="vector", candidate_limit=None, rerank=True
        )
        ask.return_value.invoke.assert_called_once_with("Where?")

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
                AgentContext((book(),), retrieval_method=method, candidate_limit=depth)

    @patch("rag_library.rag.retriever.hybrid_search", return_value=[])
    def test_agent_can_disable_reranking_through_answering(self, search):
        answer_book_question.func(
            question="Where?",
            runtime=SimpleNamespace(
                context=AgentContext((book(),), candidate_limit=100, rerank=False)
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
        with self.assertRaises(ValueError):
            create_agent_context([])
        with self.assertRaisesRegex(ValueError, "Unknown book IDs"):
            create_agent_context([99, 123])
