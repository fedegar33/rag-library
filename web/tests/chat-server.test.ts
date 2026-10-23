import assert from "node:assert/strict";
import { test } from "node:test";
import { proxyChat, readChatConfig } from "../src/lib/chat-server.ts";

const config = { bookIds: [17, 18], backendUrl: "http://backend:8000/" };
const request = (body: unknown) =>
  new Request("http://web/api/chat", {
    method: "POST",
    body: JSON.stringify(body),
  });

test("test IDs are required, strict positive safe integers, and deduplicated", () => {
  for (const value of [
    undefined,
    "",
    "1,",
    "0",
    "-1",
    "1.2",
    "1e2",
    "NaN",
    "9007199254740992",
  ]) {
    assert.ok(readChatConfig({ CHAT_BOOK_IDS: value }).error, String(value));
  }
  assert.deepEqual(
    readChatConfig({ CHAT_BOOK_IDS: "17, 18,17" }).bookIds,
    [17, 18],
  );
});

test("invalid configuration and messages never call the backend", async (t) => {
  let calls = 0;
  t.mock.method(globalThis, "fetch", async () => {
    calls++;
    throw new Error();
  });
  assert.equal(
    (await proxyChat(request({ message: "Hi" }), readChatConfig({}))).status,
    503,
  );
  for (const message of ["", "  ", 42, null, "x".repeat(4001)]) {
    assert.equal((await proxyChat(request({ message }), config)).status, 422);
  }
  const invalid = new Request("http://web/api/chat", {
    method: "POST",
    body: "{",
  });
  assert.equal((await proxyChat(invalid, config)).status, 400);
  assert.equal(calls, 0);
});

test("proxy streams immediately, forwards cancellation, and overrides client IDs/history", async (t) => {
  const original = request({
    message: "  Latest question  ",
    book_ids: [999],
    messages: ["history"],
  });
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  let cancelled = false;
  t.mock.method(
    globalThis,
    "fetch",
    async (url: string, options: RequestInit) => {
      assert.equal(url, "http://backend:8000/chat");
      assert.deepEqual(JSON.parse(options.body as string), {
        message: "Latest question",
        book_ids: [17, 18],
      });
      assert.equal(options.signal, original.signal);
      assert.equal(options.cache, "no-store");
      return new Response(
        new ReadableStream({
          start(value) {
            controller = value;
          },
          cancel() {
            cancelled = true;
          },
        }),
        { headers: { "Content-Type": "text/event-stream" } },
      );
    },
  );
  const response = await proxyChat(original, config);
  assert.equal(response.headers.get("x-vercel-ai-ui-message-stream"), "v1");
  assert.match(response.headers.get("cache-control")!, /no-transform/);
  const reader = response.body!.getReader();
  controller.enqueue(new TextEncoder().encode("data: first\n\n"));
  assert.equal(
    new TextDecoder().decode((await reader.read()).value),
    "data: first\n\n",
  );
  await reader.cancel();
  assert.equal(cancelled, true);
});

test("upstream errors and unexpected responses do not leak response bodies", async (t) => {
  for (const [upstreamStatus, expected] of [
    [422, 422],
    [503, 503],
    [500, 502],
  ]) {
    const mocked = t.mock.method(
      globalThis,
      "fetch",
      async () =>
        new Response("private backend detail", { status: upstreamStatus }),
    );
    const response = await proxyChat(request({ message: "Hi" }), config);
    assert.equal(response.status, expected);
    assert.doesNotMatch(await response.text(), /private backend detail/);
    mocked.mock.restore();
  }
  t.mock.method(globalThis, "fetch", async () => new Response("not SSE"));
  assert.equal(
    (await proxyChat(request({ message: "Hi" }), config)).status,
    502,
  );
});

test("network failures and cancelled requests return controlled errors", async (t) => {
  t.mock.method(globalThis, "fetch", async () => {
    throw new Error("connection refused");
  });
  assert.equal(
    (await proxyChat(request({ message: "Hi" }), config)).status,
    502,
  );
  const abort = new AbortController();
  abort.abort();
  const cancelled = new Request("http://web/api/chat", {
    method: "POST",
    body: JSON.stringify({ message: "Hi" }),
    signal: abort.signal,
  });
  assert.equal((await proxyChat(cancelled, config)).status, 499);
});
