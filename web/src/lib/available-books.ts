import type { DynamicToolUIPart } from "ai";

// Public contract of Python's list_available_books. Runtime validation stays at
// the UI boundary because dynamic tool outputs arrive as unknown JSON.
export type BookCardData = {
  id: number;
  title: string;
  authors: string | null;
  categories: string[];
  cover_url: string | null;
};

function isBook(value: unknown): value is BookCardData {
  if (!value || typeof value !== "object") return false;
  const book = value as Record<string, unknown>;
  return (
    typeof book.id === "number" &&
    Number.isSafeInteger(book.id) &&
    book.id > 0 &&
    typeof book.title === "string" &&
    !!book.title.trim() &&
    (book.authors === null || typeof book.authors === "string") &&
    Array.isArray(book.categories) &&
    book.categories.every((category) => typeof category === "string") &&
    (book.cover_url === null || typeof book.cover_url === "string")
  );
}

export function readAvailableBooks(output: unknown): BookCardData[] | null {
  if (!output || typeof output !== "object" || !("books" in output)) return null;
  const books = output.books;
  if (!Array.isArray(books) || !books.every(isBook)) return null;
  if (new Set(books.map((book) => book.id)).size !== books.length) return null;
  return books;
}

export function bookCoverSource(book: BookCardData): string | null {
  // Resolve the backend's relative URL through our same-origin image proxy.
  if (book.cover_url !== `/books/${book.id}/cover`) return null;
  return `/api/books/${book.id}/cover`;
}

export type AvailableBooksView =
  | { state: "loading" }
  | { state: "waiting-for-response" }
  | { state: "error"; message: string }
  | { state: "ready"; books: BookCardData[] };

export function availableBooksView(
  part: DynamicToolUIPart,
  active: boolean,
): AvailableBooksView {
  if (part.state === "output-available") {
    const books = readAvailableBooks(part.output);
    return books
      ? active
        ? { state: "waiting-for-response" }
        : { state: "ready", books }
      : {
          state: "error",
          message: "The book list could not be displayed. Please try again.",
        };
  }
  if (part.state === "output-error" || part.state === "output-denied") {
    return {
      state: "error",
      message: "The book list could not be loaded. Please try again.",
    };
  }
  return active
    ? { state: "loading" }
    : {
        state: "error",
        message: "The book list was interrupted before it finished loading.",
      };
}
