import assert from "node:assert/strict";
import { test } from "node:test";
import type { DynamicToolUIPart } from "ai";
import { toolStatus } from "../src/lib/tool-status.ts";
import { LIST_AVAILABLE_BOOKS_TOOL, ANSWER_BOOK_QUESTION_TOOL } from "../src/lib/tools-constants.ts";

const pending = (toolName: string) => ({
  type: "dynamic-tool", toolCallId: "call", toolName, state: "input-available", input: {},
} as const satisfies DynamicToolUIPart);

test("pending tools become failures when a run stops, rather than appearing to keep running", () => {
  assert.deepEqual(toolStatus(pending(LIST_AVAILABLE_BOOKS_TOOL), true), { title: "Checking library…", failed: false });
  assert.deepEqual(toolStatus(pending(LIST_AVAILABLE_BOOKS_TOOL), false), { title: "Library check failed", failed: true });
  assert.deepEqual(toolStatus(pending(ANSWER_BOOK_QUESTION_TOOL), true), { title: "Searching books…", failed: false });
  assert.equal(toolStatus(pending("future-tool"), false).failed, true);
});

test("a finished catalog line validates its data, including an empty library", () => {
  const base = pending(LIST_AVAILABLE_BOOKS_TOOL);
  const result: DynamicToolUIPart = { ...base, state: "output-available", input: {}, output: { books: [] } };
  assert.deepEqual(toolStatus(result, false), { title: "Library checked · 0 books found", failed: false });
  assert.deepEqual(toolStatus({ ...result, output: { books: [{}] } }, false), { title: "Library check failed", failed: true });
});

test("completed searches survive a later stream failure and execution errors remain errors", () => {
  const base = pending(ANSWER_BOOK_QUESTION_TOOL);
  assert.deepEqual(toolStatus({ ...base, state: "output-available", input: {}, output: { sources: [] } }, false), { title: "Books searched", failed: false });
  assert.equal(toolStatus({ ...base, state: "output-error", input: {}, errorText: "Internal details" }, true).failed, true);
  assert.equal(toolStatus({ ...base, state: "output-denied", input: {}, approval: { id: "approval", approved: false } }, false).failed, true);
});
