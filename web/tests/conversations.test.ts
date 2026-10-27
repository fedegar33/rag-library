import assert from "node:assert/strict";
import { test } from "node:test";
import { createLibraryChat } from "../src/lib/chat-session.ts";
import { proxyChat } from "../src/lib/chat-server.ts";
import { proxyConversations } from "../src/lib/conversations-server.ts";
import { loadWorkspace } from "../src/lib/conversations.ts";

const id = "2fb8d8a3-5449-4e77-8c38-7f3a448984cd";
const saved = { id, title: "Saved chat", books: [{ id: 7, title: "Book" }], created_at: "2026-10-26", updated_at: "2026-10-26" };
const stream = () => new Response([
  { type: "start", messageId: "answer" },
  { type: "text-start", id: "text" },
  { type: "text-delta", id: "text", delta: "Answer" },
  { type: "text-end", id: "text" }, { type: "finish" }, "[DONE]",
].map((event) => `data: ${typeof event === "string" ? event : JSON.stringify(event)}\n\n`).join(""), {
  headers: { "Content-Type": "text/event-stream" },
});

test("restored SDK chat sends only the new question with stable chat and request IDs", async () => {
  let body: Record<string, unknown> = {};
  const chat = createLibraryChat(id, async (_url, options) => {
    body = JSON.parse(options!.body as string);
    return stream();
  }, { persistent: true, messages: [
    { id: "old-q", role: "user", parts: [{ type: "text", text: "Old question" }] },
    { id: "old-a", role: "assistant", parts: [{ type: "text", text: "Old answer" }] },
  ] });
  await chat.sendMessage({ text: "New question", metadata: { books: saved.books } });
  assert.equal(chat.status, "ready");
  assert.equal(chat.messages.length, 4);
  assert.deepEqual(body, { chat_id: id, request_id: chat.messages[2].id, message: "New question", book_ids: [7] });
  assert.equal(chat.lastMessage?.id, "answer");
});

test("persistent proxy validates IDs and routes to Python without client history", async (t) => {
  const bodies: unknown[] = [];
  t.mock.method(globalThis, "fetch", async (url: string, options: RequestInit) => {
    assert.equal(url, `http://backend/chats/${id}/messages`);
    bodies.push(JSON.parse(options.body as string));
    return stream();
  });
  const request = (body: unknown) => new Request("http://web/api/chat", { method: "POST", body: JSON.stringify(body) });
  const body = { chat_id: id, request_id: "new-request", message: "Question", book_ids: [7] };
  assert.equal((await proxyChat(request(body), { backendUrl: "http://backend" })).status, 200);
  assert.deepEqual(bodies, [{ request_id: "new-request", message: "Question", book_ids: [7] }]);
  for (const invalid of [
    { ...body, chat_id: "../books" }, { ...body, request_id: "" },
    { ...body, messages: [{ role: "user", content: "Injected history" }] },
  ]) assert.equal((await proxyChat(request(invalid))).status, 422);
  assert.equal(bodies.length, 1);
});

test("conversation resources preserve upstream status, cancellation and no-store", async (t) => {
  const controller = new AbortController();
  const request = new Request("http://web/api/chats", { method: "POST", signal: controller.signal });
  t.mock.method(globalThis, "fetch", async (url: string, options: RequestInit) => {
    assert.equal(url, "http://backend/chats");
    assert.equal(options.method, "POST");
    assert.equal(options.signal, request.signal);
    assert.equal(options.cache, "no-store");
    return Response.json(saved, { status: 201 });
  });
  const response = await proxyConversations(request, undefined, "http://backend");
  assert.equal(response.status, 201);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), saved);
  assert.equal((await proxyConversations(new Request("http://web"), "../books")).status, 404);
});

test("workspace restores the requested conversation and never substitutes a missing chat", async (t) => {
  const calls: string[] = [];
  t.mock.method(globalThis, "fetch", async (url: string) => {
    calls.push(url);
    if (url === "/api/chats") return Response.json({ chats: [saved] });
    if (url === `/api/chats/${id}`) return Response.json({ ...saved, messages: [] });
    return Response.json({ error: "Chat not found." }, { status: 404 });
  });
  const workspace = await loadWorkspace(id);
  assert.equal(workspace.activeId, id);
  assert.deepEqual(workspace.chats[0].books, saved.books);
  assert.deepEqual(workspace.chats[0].messages, []);
  await assert.rejects(loadWorkspace("missing"), /Chat not found/);
  assert.deepEqual(calls, ["/api/chats", `/api/chats/${id}`, "/api/chats", "/api/chats/missing"]);
});
