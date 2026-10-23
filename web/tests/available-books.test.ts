import { LIST_AVAILABLE_BOOKS_TOOL } from "../src/lib/tools-constants.ts";
import assert from "node:assert/strict";
import { test } from "node:test";
import type { DynamicToolUIPart } from "ai";
import { availableBooksView, bookCoverSource, readAvailableBooks } from "../src/lib/available-books.ts";

const book = {
  id: 17,
  title: "A book with a long title",
  authors: null,
  categories: ["Fiction"],
  cover_url: "/books/17/cover",
};
const result = (output: unknown): DynamicToolUIPart => ({
  type: "dynamic-tool", toolName: LIST_AVAILABLE_BOOKS_TOOL, toolCallId: "catalog-1",
  state: "output-available", input: {}, output,
});

test("catalog boundary accepts nullable presentation fields, order, and empty results", () => {
  const books = [book, { ...book, id: 2, authors: "An author", cover_url: null, categories: [] }];
  assert.deepEqual(readAvailableBooks({ books }), books);
  assert.deepEqual(availableBooksView(result({ books: [] }), false), { state: "ready", books: [] });
});

test("malformed metadata and duplicate identities display an error instead of partial cards", () => {
  for (const output of [
    null, {}, { books: null }, { books: [null] },
    { books: [{ ...book, categories: [42] }] },
    { books: [{ ...book, title: " " }] },
    { books: [{ ...book, id: -1 }] },
    { books: [{ ...book, cover_url: {} }] },
    { books: [book, book] },
  ]) {
    assert.equal(readAvailableBooks(output), null);
    assert.equal(availableBooksView(result(output), false).state, "error");
  }
});

test("pending executions stop loading after interruption; completed results survive later failures", () => {
  const pending: DynamicToolUIPart = {
    type: "dynamic-tool", toolName: LIST_AVAILABLE_BOOKS_TOOL, toolCallId: "pending",
    state: "input-available", input: {},
  };
  assert.equal(availableBooksView(pending, true).state, "loading");
  assert.equal(availableBooksView(pending, false).state, "error");
  assert.deepEqual(availableBooksView(result({ books: [book] }), false), { state: "ready", books: [book] });
  assert.equal(availableBooksView({ ...pending, state: "output-error", errorText: "Internal error" }, true).state, "error");
});

test("covers only resolve the matching backend catalog path through the same origin", () => {
  assert.equal(bookCoverSource(book), "/api/books/17/cover");
  for (const cover_url of [null, "/books/2/cover", "https://example.com/image.jpg", "javascript:alert(1)"]) {
    assert.equal(bookCoverSource({ ...book, cover_url }), null);
  }
});
