import { LIST_AVAILABLE_BOOKS_TOOL, ANSWER_BOOK_QUESTION_TOOL } from "../src/lib/tools-constants.ts";
import assert from "node:assert/strict";
import { test } from "node:test";
import { createLibraryChat } from "../src/lib/chat-session.ts";
import { messageText } from "../src/lib/chat-transport.ts";

const encode = (events: unknown[]) =>
  new TextEncoder().encode(
    events
      .map(
        (event) =>
          `data: ${typeof event === "string" ? event : JSON.stringify(event)}\r\n\r\n`,
      )
      .join(""),
  );
const finish = { type: "finish" };

function eventFetch(events: unknown[]): typeof fetch {
  return async () => {
    const bytes = encode(events);
    return new Response(
      new ReadableStream({
        start(controller) {
          // Exercise the actual SDK parser with split UTF-8 and SSE delimiters.
          for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
          controller.close();
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  };
}

test("catalog-only replies complete without text and retain each execution separately", async () => {
  const chat = createLibraryChat("catalog", eventFetch([
    { type: "start", messageId: "catalog-reply" },
    { type: "tool-input-available", toolCallId: "first", toolName: LIST_AVAILABLE_BOOKS_TOOL, input: {}, dynamic: true },
    { type: "tool-input-available", toolCallId: "second", toolName: LIST_AVAILABLE_BOOKS_TOOL, input: {}, dynamic: true },
    { type: "tool-output-available", toolCallId: "second", output: { books: [] } },
    { type: "tool-output-available", toolCallId: "first", output: { books: [
      { id: 1, title: "A book", authors: null, categories: [], cover_url: null },
    ] } },
    finish, "[DONE]",
  ]));
  await chat.sendMessage({ text: "Which books are available?" });
  assert.equal(chat.status, "ready");
  assert.equal(messageText(chat.lastMessage!), "");
  assert.deepEqual(chat.lastMessage!.parts.filter((part) => part.type === "dynamic-tool").map((part) => [part.toolCallId, part.state]), [
    ["first", "output-available"], ["second", "output-available"],
  ]);
});

test("unrelated or malformed tool output cannot satisfy an otherwise empty response", async () => {
  for (const [toolName, output] of [
    [ANSWER_BOOK_QUESTION_TOOL, { books: [] }],
    [LIST_AVAILABLE_BOOKS_TOOL, { books: [{ title: "Missing metadata" }] }],
  ] as const) {
    const chat = createLibraryChat("invalid-tool", eventFetch([
      { type: "tool-input-available", toolCallId: "a", toolName, input: {}, dynamic: true },
      { type: "tool-output-available", toolCallId: "a", output },
      finish,
    ]));
    await chat.sendMessage({ text: "Books?" });
    assert.equal(chat.status, "error");
  }
});
