"""A sliding window of complete conversational turns, without summaries."""

from collections.abc import Sequence

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately

HISTORY_TOKEN_BUDGET = 6000


def window_messages(
    messages: Sequence[BaseMessage], *, token_budget: int = HISTORY_TOKEN_BUDGET
) -> list[BaseMessage]:
    """Keep a contiguous suffix of whole turns plus the current user question.

    The budget applies to history only, leaving the current question, system
    instructions, new tool results, and output outside this history allowance.
    Counting is approximate and offline; no model or tokenizer download is used.
    """
    if token_budget < 0:
        raise ValueError("History token budget cannot be negative")
    if not messages or not isinstance(messages[-1], HumanMessage):
        raise ValueError("Conversation must end with the current user question")
    turns: list[list[BaseMessage]] = []
    for message in messages[:-1]:
        if isinstance(message, HumanMessage):
            turns.append([])
        if not turns:
            raise ValueError("Conversation must start with a user question")
        turns[-1].append(message)

    kept: list[list[BaseMessage]] = []
    remaining = token_budget
    for turn in reversed(turns):
        cost = count_tokens_approximately(turn, chars_per_token=3)
        if cost > remaining:
            break
        kept.append(turn)
        remaining -= cost
    return [message for turn in reversed(kept) for message in turn] + [messages[-1]]


class ConversationWindow(AgentMiddleware):
    """Bound model input without deleting persisted messages or current tool work."""

    async def awrap_model_call(self, request, handler):
        messages = request.messages
        current = next(
            (
                i
                for i in range(len(messages) - 1, -1, -1)
                if isinstance(messages[i], HumanMessage)
            ),
            None,
        )
        if current is None:
            return await handler(request)
        visible = window_messages(messages[: current + 1]) + messages[current + 1 :]
        return await handler(request.override(messages=visible))
