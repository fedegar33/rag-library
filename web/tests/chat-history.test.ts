import assert from "node:assert/strict";
import { test } from "node:test";
import { conversationHistory } from "../src/lib/chat-history.ts";
import { createLibraryChat } from "../src/lib/chat-session.ts";
import type { LibraryMessage } from "../src/lib/chat.ts";

test("SDK follow-ups send chronological text, tool calls and results without source duplication", async () => {
  const requests: { messages: unknown[]; book_ids: number[] }[] = [];
  const output = { books: [{ id: 7, title: "Book", authors: null, categories: [], cover_url: null }] };
  const evidence = { sources: [{ book_id: 7, text: "A passage" }] };
  const chat = createLibraryChat("history", async (_url, options) => {
    requests.push(JSON.parse(options!.body as string));
    const events = requests.length === 1 ? [
      { type: "start", messageId: "first-reply" },
      { type: "text-start", id: "announce" },
      { type: "text-delta", id: "announce", delta: "Checking the library." },
      { type: "text-end", id: "announce" },
      { type: "tool-input-available", toolCallId: "catalog", toolName: "list_available_books", input: {}, dynamic: true },
      { type: "tool-output-available", toolCallId: "catalog", output },
      { type: "tool-input-available", toolCallId: "evidence", toolName: "answer_book_question", input: { question: "Where?" }, dynamic: true },
      { type: "tool-output-available", toolCallId: "evidence", output: evidence },
      { type: "data-source", id: "evidence-0", data: evidence.sources[0] },
      { type: "text-start", id: "answer" },
      { type: "text-delta", id: "answer", delta: "Here are the books." },
      { type: "text-end", id: "answer" },
      { type: "finish" },
    ] : [
      { type: "start", messageId: "second-reply" },
      { type: "text-start", id: "answer-2" },
      { type: "text-delta", id: "answer-2", delta: "A follow-up answer." },
      { type: "text-end", id: "answer-2" },
      { type: "finish" },
    ];
    return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("") + "data: [DONE]\n\n", {
      headers: { "Content-Type": "text/event-stream" },
    });
  });
  await chat.sendMessage({ text: "Which books?", metadata: { books: [{ id: 7, title: "Book" }] } });
  await chat.sendMessage({ text: "Who wrote the first?", metadata: { books: [] } });
  assert.equal(chat.status, "ready");
  assert.deepEqual(requests[1], {
    book_ids: [],
    messages: [
      { role: "user", content: "Which books?" },
      { role: "assistant", content: "Checking the library." },
      { role: "assistant", content: "", tool_calls: [{ id: "catalog", name: "list_available_books", args: {} }] },
      { role: "tool", tool_call_id: "catalog", content: output },
      { role: "assistant", content: "", tool_calls: [{ id: "evidence", name: "answer_book_question", args: { question: "Where?" } }] },
      { role: "tool", tool_call_id: "evidence", content: evidence },
      { role: "assistant", content: "Here are the books." },
      { role: "user", content: "Who wrote the first?" },
    ],
  });
});

test("interrupted calls cannot become orphan tool history; UI messages stay untouched", () => {
  const messages: LibraryMessage[] = [
    { id: "q1", role: "user", parts: [{ type: "text", text: "First?" }] },
    { id: "a1", role: "assistant", metadata: { interruption: "Stopped" }, parts: [
      { type: "text", text: "Partial answer" },
      { type: "dynamic-tool", toolName: "answer_book_question", toolCallId: "unfinished", state: "input-available", input: { question: "First?" } },
    ] },
    { id: "q2", role: "user", parts: [{ type: "text", text: "Next?" }] },
  ];
  const snapshot = structuredClone(messages);
  assert.deepEqual(conversationHistory(messages), [
    { role: "user", content: "First?" },
    { role: "assistant", content: "Partial answer" },
    { role: "user", content: "Next?" },
  ]);
  assert.deepEqual(messages, snapshot);
});
