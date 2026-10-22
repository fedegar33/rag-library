"""Build and run the stateless book agent, recording actual tool executions."""

import json

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langchain.agents.structured_output import ProviderStrategy
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from rag_library.agent.context import AgentContext
from rag_library.agent.models import AgentAnswer, AgentResult, ToolCallRecord
from rag_library.agent.prompts import SYSTEM_PROMPT
from rag_library.agent.tools import answer_book_question, list_books
from rag_library.config import get_settings


def build_agent(model: str | BaseChatModel, *, structured_output: bool = True):
    """Build an agent with independent state and bounded execution per invocation."""
    return create_agent(
        model=model,
        tools=[list_books, answer_book_question],
        system_prompt=SYSTEM_PROMPT,
        context_schema=AgentContext,
        response_format=(
            ProviderStrategy(AgentAnswer, strict=True) if structured_output else None
        ),
        middleware=[
            ModelCallLimitMiddleware[AgentContext, AgentAnswer](
                run_limit=3, exit_behavior="error"
            ),
            ToolCallLimitMiddleware[AgentContext, AgentAnswer](
                run_limit=2, exit_behavior="error"
            ),
        ],
    )


def get_agent(*, structured_output: bool = True):
    """Create a fresh configured agent for the API or notebook experiments."""
    settings = get_settings()
    return build_agent(
        ChatOpenAI(
            model=settings.openai_chat_model,
            api_key=settings.openai_api_key,
            timeout=30,
            max_retries=0,
        ),
        structured_output=structured_output,
    )


def run_agent(agent, message: str, *, context: AgentContext) -> AgentResult:
    state = agent.invoke(
        {"messages": [{"role": "user", "content": message}]}, context=context
    )
    messages = state["messages"]
    answer = AgentAnswer.model_validate(state["structured_response"])

    calls = {}
    records = []
    for item in messages:
        if isinstance(item, AIMessage):
            for call in item.tool_calls:
                calls[call["id"]] = call
        elif isinstance(item, ToolMessage):
            if item.status == "error":
                raise ValueError("Agent tool execution failed")
            call = calls.pop(item.tool_call_id)
            records.append(
                ToolCallRecord(
                    name=call["name"],
                    arguments=call["args"],
                    result=json.loads(item.content),
                )
            )
    if calls:
        raise ValueError("Agent returned unresolved tool calls")
    return AgentResult(answer=answer.answer, tool_calls=records)
