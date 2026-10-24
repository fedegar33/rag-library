import type { LibraryMessage } from "./chat.ts";
import {
  ANSWER_BOOK_QUESTION_TOOL,
  LIST_AVAILABLE_BOOKS_TOOL,
} from "./tools-constants.ts";

type ToolName = typeof ANSWER_BOOK_QUESTION_TOOL | typeof LIST_AVAILABLE_BOOKS_TOOL;
export type ConversationMessage =
  | { role: "user"; content: string }
  | {
      role: "assistant";
      content: string;
      tool_calls?: {
        id: string;
        name: ToolName;
        args: Record<string, unknown>;
      }[];
    }
  | { role: "tool"; tool_call_id: string; content: Record<string, unknown> };

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function assistantHistory(message: LibraryMessage): ConversationMessage[] {
  const result: ConversationMessage[] = [];
  let text: string[] = [];
  function flushText() {
    const content = text.join("\n\n");
    if (content.trim()) result.push({ role: "assistant", content });
    text = [];
  }
  for (const part of message.parts) {
    if (part.type === "text") {
      text.push(part.text);
    } else if (
      part.type === "dynamic-tool" &&
      part.state === "output-available" &&
      !part.preliminary &&
      (part.toolName === LIST_AVAILABLE_BOOKS_TOOL ||
        part.toolName === ANSWER_BOOK_QUESTION_TOOL) &&
      isObject(part.input) &&
      isObject(part.output)
    ) {
      flushText();
      result.push({
        role: "assistant",
        content: "",
        tool_calls: [{
          id: part.toolCallId,
          name: part.toolName,
          args: part.input,
        }],
      });
      result.push({
        role: "tool", tool_call_id: part.toolCallId, content: part.output,
      });
    }
    // Sources duplicate retrieval output. Pending/failed calls and UI metadata
    // are not complete model history and must not become orphan tool calls.
  }
  flushText();
  return result;
}

export function conversationHistory(
  messages: LibraryMessage[],
): ConversationMessage[] {
  const result: ConversationMessage[] = [];
  const lastQuestion = messages.findLastIndex((message) => message.role === "user");
  for (const message of messages.slice(0, lastQuestion + 1)) {
    if (message.role === "user") {
      // A cancelled attempt with no assistant output remains visible in the UI,
      // but is not a completed historical turn.
      if (result.at(-1)?.role === "user") result.pop();
      const content = message.parts
        .filter((part) => part.type === "text")
        .map((part) => part.text).join("\n\n").trim();
      result.push({ role: "user", content });
    } else if (message.role === "assistant" && result.length) {
      result.push(...assistantHistory(message));
    }
  }
  return result;
}
