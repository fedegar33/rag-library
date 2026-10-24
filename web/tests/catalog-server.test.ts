import assert from "node:assert/strict";
import { test } from "node:test";
import { proxyCatalog } from "../src/lib/catalog-server.ts";
import { proxyChat } from "../src/lib/chat-server.ts";

test("catalog proxy validates data, uses fixed URL and never caches", async (t) => {
  const request = new Request("http://web/api/books");
  t.mock.method(globalThis, "fetch", async (url: string, options: RequestInit) => {
    assert.equal(url, "http://backend/books");
    assert.equal(options.signal, request.signal);
    assert.equal(options.cache, "no-store");
    return Response.json({ books: [] });
  });
  const response = await proxyCatalog(request, "http://backend/");
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { books: [] });
});

test("catalog failure is recoverable and never returned as an empty library", async (t) => {
  for (const invalid of [{ books: [{ id: 1 }] }, { message: "private detail" }]) {
    const mocked = t.mock.method(globalThis, "fetch", async () => Response.json(invalid));
    const response = await proxyCatalog(new Request("http://web/api/books"), "http://backend");
    assert.equal(response.status, 503);
    assert.doesNotMatch(await response.text(), /private detail/);
    mocked.mock.restore();
  }
});

test("no selection explicitly forwards whole-library scope", async (t) => {
  const calls: unknown[] = [];
  t.mock.method(globalThis, "fetch", async (_url: string, options: RequestInit) => {
    calls.push(JSON.parse(options.body as string));
    return new Response("data: [DONE]\n\n", { headers: { "Content-Type": "text/event-stream" } });
  });
  for (const body of [{ message: "Hi" }, { message: "Hi", book_ids: [] }]) {
    await proxyChat(new Request("http://web/api/chat", { method: "POST", body: JSON.stringify(body) }), { backendUrl: "http://backend" });
  }
  assert.deepEqual(calls, [{ message: "Hi", book_ids: [] }, { message: "Hi", book_ids: [] }]);
});
