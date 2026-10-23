import assert from "node:assert/strict";
import { test } from "node:test";
import { setImmediate as tick } from "node:timers/promises";
import { createLibraryChat } from "../src/lib/chat-session.ts";
import { availableBooksView } from "../src/lib/available-books.ts";
import { toolStatus } from "../src/lib/tool-status.ts";
import { LIST_AVAILABLE_BOOKS_TOOL } from "../src/lib/tools-constants.ts";

const books = [{ id: 1, title: "A book", authors: null, categories: [], cover_url: null }];
const encode = (events: unknown[]) => new TextEncoder().encode(
  events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""),
);
const input = {
  type: "tool-input-available", toolCallId: "catalog", toolName: LIST_AVAILABLE_BOOKS_TOOL,
  input: {}, dynamic: true,
};
const output = { type: "tool-output-available", toolCallId: "catalog", output: { books } };

test("catalog activity is ready before prose, but cards wait even past text-end until the turn finishes", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const chat = createLibraryChat("sequence", async () => new Response(new ReadableStream({
    start(value) { controller = value; },
  })));
  const operation = chat.sendMessage({ text: "Which books are available?" });
  await tick();
  controller.enqueue(encode([
    { type: "start", messageId: "reply" },
    { type: "text-start", id: "preamble" },
    { type: "text-delta", id: "preamble", delta: "Let me check the library." },
    { type: "text-end", id: "preamble" }, input, output,
  ]));
  await tick();
  const tool = () => chat.lastMessage!.parts.find((part) => part.type === "dynamic-tool")!;
  assert.equal(chat.status, "streaming");
  assert.deepEqual(chat.lastMessage!.parts.map((part) => part.type), ["text", "dynamic-tool"]);
  assert.equal(toolStatus(tool(), true).title, "Library checked · 1 book found");
  assert.equal(availableBooksView(tool(), true).state, "waiting-for-response");

  controller.enqueue(encode([
    { type: "text-start", id: "intro" },
    { type: "text-delta", id: "intro", delta: "Here are the books." },
    { type: "text-end", id: "intro" },
  ]));
  await tick();
  assert.deepEqual(chat.lastMessage!.parts.map((part) => part.type), ["text", "dynamic-tool", "text"]);
  assert.equal(availableBooksView(tool(), true).state, "waiting-for-response");

  controller.enqueue(encode([{ type: "finish" }]));
  controller.close();
  await operation;
  assert.equal(chat.status, "ready");
  assert.deepEqual(availableBooksView(tool(), false), { state: "ready", books });
});

test("catalog cards survive failure or cancellation after discovery; an unfinished tool has no cards", async () => {
  for (const outcome of ["error", "cancel", "tool-error"] as const) {
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const chat = createLibraryChat(outcome, async (_url, options) => {
      options!.signal!.addEventListener("abort", () => controller.error(new DOMException("Aborted", "AbortError")));
      return new Response(new ReadableStream({ start(value) { controller = value; } }));
    });
    const operation = chat.sendMessage({ text: "Books?" });
    await tick();
    controller.enqueue(encode([input, ...(outcome === "tool-error" ? [] : [output])]));
    await tick();
    const tool = () => chat.lastMessage!.parts.find((part) => part.type === "dynamic-tool")!;
    assert.notEqual(availableBooksView(tool(), true).state, "ready");
    if (outcome === "cancel") await chat.stop();
    else {
      controller.enqueue(encode([{ type: "error", errorText: "Agent service unavailable" }]));
      controller.close();
    }
    await operation;
    assert.ok(chat.lastMessage!.metadata?.interruption);
    assert.equal(availableBooksView(tool(), false).state, outcome === "tool-error" ? "error" : "ready");
  }
});
