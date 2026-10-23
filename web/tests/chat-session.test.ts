import assert from "node:assert/strict";
import { setImmediate as tick } from "node:timers/promises";
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
const start = { type: "text-start", id: "text-1" };
const delta = (text: string) => ({
  type: "text-delta",
  id: "text-1",
  delta: text,
});
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

test("SDK owns fragmented text, dynamic tool state, and source parts", async () => {
  const chat = createLibraryChat(
    "chat-1",
    eventFetch([
      { type: "start", messageId: "reply" },
      {
        type: "tool-input-available",
        toolCallId: "a",
        toolName: "answer_book_question",
        input: {},
        dynamic: true,
      },
      { type: "tool-output-available", toolCallId: "a", output: {} },
      {
        type: "data-source",
        id: "a-0",
        data: { book_id: 17, chapter: "One", chunk_index: 4 },
      },
      start,
      delta("Café 📚"),
      { type: "text-end", id: "text-1" },
      { type: "text-start", id: "text-2" },
      { type: "text-delta", id: "text-2", delta: "Second paragraph" },
      { type: "text-end", id: "text-2" },
      finish,
      "[DONE]",
    ]),
  );
  await chat.sendMessage({ text: "Latest question" });
  assert.equal(chat.status, "ready");
  assert.equal(chat.messages.length, 2);
  assert.equal(messageText(chat.lastMessage!), "Café 📚\n\nSecond paragraph");
  assert.deepEqual(
    chat.lastMessage!.parts.find((part) => part.type === "data-source"),
    {
      type: "data-source",
      id: "a-0",
      data: { book_id: 17, chapter: "One", chunk_index: 4 },
    },
  );
  assert.ok(
    chat.lastMessage!.parts.some(
      (part) =>
        part.type === "dynamic-tool" && part.state === "output-available",
    ),
  );
});

test("SDK publishes tokens before completion and transport sends only the latest question", async () => {
  let body: unknown;
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const chat = createLibraryChat("not-sent", async (_url, options) => {
    body = JSON.parse(options!.body as string);
    return new Response(
      new ReadableStream({
        start(value) {
          controller = value;
          controller.enqueue(encode([start, delta("First token")]));
        },
      }),
    );
  });
  chat.messages = [
    {
      id: "older",
      role: "user",
      parts: [{ type: "text", text: "Earlier question" }],
    },
  ];
  const operation = chat.sendMessage({ text: "Only this question" });
  await tick();
  assert.equal(chat.status, "streaming");
  assert.equal(messageText(chat.lastMessage!), "First token");
  assert.deepEqual(body, { message: "Only this question" });
  controller.enqueue(
    encode([{ type: "text-end", id: "text-1" }, finish, "[DONE]"]),
  );
  controller.close();
  await operation;
  assert.equal(chat.status, "ready");
});

test("SDK tool states retain parallel retrieval activity until all tools finish", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const chat = createLibraryChat(
    "tools",
    async () =>
      new Response(
        new ReadableStream({
          start(value) {
            controller = value;
            controller.enqueue(
              encode([
                {
                  type: "tool-input-available",
                  toolCallId: "a",
                  toolName: "search",
                  input: {},
                  dynamic: true,
                },
                {
                  type: "tool-input-available",
                  toolCallId: "b",
                  toolName: "search",
                  input: {},
                  dynamic: true,
                },
                { type: "tool-output-available", toolCallId: "a", output: {} },
              ]),
            );
          },
        }),
      ),
  );
  const operation = chat.sendMessage({ text: "Question" });
  await tick();
  assert.ok(
    chat.lastMessage!.parts.some(
      (part) =>
        part.type === "dynamic-tool" &&
        part.toolCallId === "b" &&
        part.state === "input-available",
    ),
  );
  controller.enqueue(
    encode([
      { type: "tool-output-available", toolCallId: "b", output: {} },
      start,
      delta("Answer"),
      { type: "text-end", id: "text-1" },
      finish,
    ]),
  );
  controller.close();
  await operation;
  assert.equal(chat.status, "ready");
});

test("in-stream failure preserves partial output; explicit resend preserves the original attempt", async () => {
  let calls = 0;
  const chat = createLibraryChat("retry", async (url, options) => {
    calls++;
    assert.deepEqual(JSON.parse(options!.body as string), {
      message: "Question",
    });
    return eventFetch(
      calls === 1
        ? [
            start,
            delta("Keep me"),
            { type: "error", errorText: "Agent service unavailable" },
          ]
        : [
            { type: "start", messageId: "retry-reply" },
            start,
            delta("New answer"),
            { type: "text-end", id: "text-1" },
            finish,
          ],
    )(url, options);
  });
  await chat.sendMessage({ text: "Question" });
  assert.equal(chat.status, "error");
  assert.equal(messageText(chat.lastMessage!), "Keep me");
  assert.match(
    chat.lastMessage!.metadata!.interruption!,
    /Agent service unavailable/,
  );
  assert.equal(calls, 1);
  await chat.sendMessage({ text: "Question" });
  assert.equal(calls, 2);
  assert.equal(chat.status, "ready");
  assert.equal(messageText(chat.messages[1]), "Keep me");
  assert.equal(messageText(chat.lastMessage!), "New answer");
});

test("EOF or DONE without finish remains interrupted even when SDK parsing succeeds", async () => {
  for (const end of [[], ["[DONE]"]]) {
    const chat = createLibraryChat(
      "truncated",
      eventFetch([start, delta("Partial"), ...end]),
    );
    await chat.sendMessage({ text: "Q" });
    assert.equal(chat.status, "error");
    assert.equal(messageText(chat.lastMessage!), "Partial");
    assert.match(
      chat.lastMessage!.metadata!.interruption!,
      /before the answer was complete/,
    );
  }
});

test("empty completion and malformed protocol produce retryable interruptions", async () => {
  for (const fetcher of [
    eventFetch([finish, "[DONE]"]),
    async () => new Response("data: {broken}\n\n"),
  ]) {
    const chat = createLibraryChat("invalid", fetcher);
    await chat.sendMessage({ text: "Q" });
    assert.equal(chat.status, "error");
    assert.ok(chat.lastMessage?.metadata?.interruption);
  }
});

test("pre-stream HTTP failure creates an interrupted assistant entry and never retries automatically", async () => {
  let calls = 0;
  const chat = createLibraryChat("http", async () => {
    calls++;
    return new Response("Test books are unavailable", { status: 422 });
  });
  await chat.sendMessage({ text: "Q" });
  assert.equal(calls, 1);
  assert.equal(chat.lastMessage?.role, "assistant");
  assert.match(
    chat.lastMessage!.metadata!.interruption!,
    /Test books are unavailable/,
  );
});

test("SDK stop aborts upstream, preserves partial reply, and isolates another conversation", async () => {
  let aborted = false;
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const chat = createLibraryChat("old", async (_url, options) => {
    options!.signal!.addEventListener("abort", () => {
      aborted = true;
      controller.error(new DOMException("Aborted", "AbortError"));
    });
    return new Response(
      new ReadableStream({
        start(value) {
          controller = value;
          controller.enqueue(encode([start, delta("Partial")]));
        },
      }),
    );
  });
  const operation = chat.sendMessage({ text: "Q" });
  await tick();
  await chat.stop();
  await operation;
  assert.equal(aborted, true);
  assert.equal(messageText(chat.lastMessage!), "Partial");
  assert.match(
    chat.lastMessage!.metadata!.interruption!,
    /switched conversations/,
  );
  const other = createLibraryChat(
    "new",
    eventFetch([
      start,
      delta("Other answer"),
      { type: "text-end", id: "text-1" },
      finish,
    ]),
  );
  await other.sendMessage({ text: "New question" });
  assert.equal(other.status, "ready");
  assert.equal(messageText(chat.lastMessage!), "Partial");
  assert.equal(messageText(other.lastMessage!), "Other answer");
});
