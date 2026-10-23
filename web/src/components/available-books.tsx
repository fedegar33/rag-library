"use client";

import { useId, useState } from "react";
import { BookOpen } from "lucide-react";
import { BookCard } from "@/components/book-card";
import type { AvailableBooksView } from "@/lib/available-books";

const INITIAL_BOOK_COUNT = 6;

export function AvailableBooks({ view }: { view: AvailableBooksView }) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();

  if (view.state === "waiting-for-response") return null;
  if (view.state === "loading") {
    return (
      <p className="catalog-status" role="status">Loading available books…</p>
    );
  }
  if (view.state === "error") {
    return (
      <p className="response-error" role="alert">{view.message}</p>
    );
  }
  const books = view.books;
  if (!books.length) {
    return (
      <div className="catalog-empty" role="status">
        <BookOpen size={22} strokeWidth={1.4} aria-hidden="true" />
        <p>No books are available in the library yet.</p>
      </div>
    );
  }
  const visible = expanded ? books : books.slice(0, INITIAL_BOOK_COUNT);

  return (
    <section className="available-books" aria-label="Available books">
      <ul className="catalog-grid" id={listId}>
        {visible.map((book) => (
          <li key={book.id}><BookCard book={book} /></li>
        ))}
      </ul>
      {books.length > INITIAL_BOOK_COUNT && (
        <button
          type="button"
          className="catalog-expand"
          aria-expanded={expanded}
          aria-controls={listId}
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? "Show fewer" : `View all ${books.length} books`}
        </button>
      )}
    </section>
  );
}
