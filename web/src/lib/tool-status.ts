import type { DynamicToolUIPart } from "ai";
import { LIST_AVAILABLE_BOOKS_TOOL, ANSWER_BOOK_QUESTION_TOOL } from "./tools-constants.ts";
import { readAvailableBooks } from "./available-books.ts";

export function toolStatus(part: DynamicToolUIPart, active: boolean) {
  const labels = part.toolName === LIST_AVAILABLE_BOOKS_TOOL
    ? { pending: "Checking library…", done: "Library checked", error: "Library check failed" }
    : part.toolName === ANSWER_BOOK_QUESTION_TOOL
      ? { pending: "Searching books…", done: "Books searched", error: "Book search failed" }
      : { pending: "Running tool…", done: "Tool completed", error: "Tool failed" };

  if (part.state === "output-available") {
    if (part.toolName === LIST_AVAILABLE_BOOKS_TOOL) {
      const books = readAvailableBooks(part.output);
      return books === null
        ? { title: labels.error, failed: true }
        : { title: `Library checked · ${books.length} ${books.length === 1 ? "book" : "books"} found`, failed: false };
    }
    return { title: labels.done, failed: false };
  }
  if (part.state === "output-error" || part.state === "output-denied") {
    return { title: labels.error, failed: true };
  }
  return { title: active ? labels.pending : labels.error, failed: !active };
}
