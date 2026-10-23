import { LIST_AVAILABLE_BOOKS_TOOL } from "./tools-constants.ts";
import { DefaultChatTransport, type UIMessageChunk } from "ai";
import type { LibraryMessage } from "./chat.ts";
import { readAvailableBooks } from "./available-books.ts";

export function messageText(message: LibraryMessage) {
  return message.parts
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("\n\n");
}

// Parsing and accumulation belong to the SDK. This guard enforces /chat's
// completion contract, which the SDK otherwise treats as an ordinary EOF.
export class LibraryChatTransport extends DefaultChatTransport<LibraryMessage> {
  constructor(fetcher?: typeof globalThis.fetch) {
    super({
      api: "/api/chat",
      fetch: fetcher,
      prepareSendMessagesRequest: ({ messages }) => {
        const latestQuestion = messages.findLast(
          (message) => message.role === "user",
        );
        return {
          body: { message: latestQuestion ? messageText(latestQuestion) : "" },
        };
      },
    });
  }

  protected processResponseStream(
    stream: ReadableStream<Uint8Array<ArrayBufferLike>>,
  ) {
    let finished = false;
    let hasText = false;
    let hasBookList = false;
    const catalogCalls = new Set<string>();
    return super.processResponseStream(stream).pipeThrough(
      new TransformStream<UIMessageChunk, UIMessageChunk>({
        transform(chunk, controller) {
          if (chunk.type === "finish") finished = true;
          if (chunk.type === "text-delta" && chunk.delta.trim()) hasText = true;
          if (chunk.type === "tool-input-available" && chunk.toolName === LIST_AVAILABLE_BOOKS_TOOL) {
            catalogCalls.add(chunk.toolCallId);
          }
          if (
            chunk.type === "tool-output-available" &&
            catalogCalls.has(chunk.toolCallId) &&
            readAvailableBooks(chunk.output) !== null
          ) hasBookList = true;
          controller.enqueue(chunk);
        },
        flush() {
          if (!finished)
            throw new Error(
              "The connection ended before the answer was complete.",
            );
          if (!hasText && !hasBookList)
            throw new Error(
              "The agent finished without an answer. Please try again.",
            );
        },
      }),
    );
  }
}
