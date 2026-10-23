import assert from "node:assert/strict";
import { test } from "node:test";
import { proxyBookCover } from "../src/lib/book-cover-server.ts";

test("cover proxy restricts IDs and streams stored images from the configured backend", async (t) => {
  const request = new Request("http://localhost/api/books/17/cover");
  let calls = 0;
  t.mock.method(globalThis, "fetch", async (url: string, options: RequestInit) => {
    calls++;
    assert.equal(url, "http://backend/books/17/cover");
    assert.equal(options.signal, request.signal);
    assert.equal(options.redirect, "error");
    return new Response(Uint8Array.of(1, 2, 3), { headers: { "Content-Type": "image/jpeg" } });
  });
  for (const id of ["../secrets", "0", "1?x=y", "9007199254740992"]) {
    assert.equal((await proxyBookCover(request, id, "http://backend")).status, 400);
  }
  assert.equal(calls, 0);
  const response = await proxyBookCover(request, "17", "http://backend/");
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("Content-Type"), "image/jpeg");
  assert.deepEqual(new Uint8Array(await response.arrayBuffer()), Uint8Array.of(1, 2, 3));
});

test("missing covers, unsafe content, and upstream failures trigger the image fallback", async (t) => {
  const request = new Request("http://localhost/api/books/1/cover");
  for (const [status, type, expected] of [
    [404, "text/plain", 404], [503, "text/plain", 502],
    [200, "text/html", 502], [200, "image/svg+xml", 502],
  ] as const) {
    const mock = t.mock.method(globalThis, "fetch", async () => new Response("content", { status, headers: { "Content-Type": type } }));
    assert.equal((await proxyBookCover(request, "1", "http://backend")).status, expected);
    mock.mock.restore();
  }
  t.mock.method(globalThis, "fetch", async () => { throw new Error("offline"); });
  assert.equal((await proxyBookCover(request, "1", "http://backend")).status, 502);
});
