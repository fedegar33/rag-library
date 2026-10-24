"use client";

import { BookOpen, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { bookCoverSource, readAvailableBooks, type BookCardData } from "@/lib/available-books";
import type { Book } from "@/lib/chat";

type Catalog = { state: "loading" } | { state: "error" } | { state: "ready"; books: BookCardData[] };

export function BookContext({ books, busy, onChange }: {
  books: Book[];
  busy: boolean;
  onChange: (books: Book[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<Book[]>([]);
  const [catalog, setCatalog] = useState<Catalog>({ state: "loading" });

  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => pending.current?.abort(), []);

  async function load() {
    pending.current?.abort();
    const controller = new AbortController();
    pending.current = controller;
    setCatalog({ state: "loading" });
    try {
      const response = await fetch("/api/books", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Catalog unavailable");
      const items = readAvailableBooks(await response.json());
      if (!items) throw new Error("Invalid catalog");
      if (controller.signal.aborted) return;
      setCatalog({ state: "ready", books: [...items].sort((a, b) => a.title.localeCompare(b.title) || a.id - b.id) });
    } catch {
      if (!controller.signal.aborted) setCatalog({ state: "error" });
    }
  }

  function changeOpen(value: boolean) {
    if (value && busy) return;
    setOpen(value);
    if (!value) pending.current?.abort();
    if (value) {
      setDraft(books.map((book) => ({ ...book })));
      void load();
    }
  }

  function toggle(book: Book) {
    setDraft((current) => current.some((item) => item.id === book.id)
      ? current.filter((item) => item.id !== book.id)
      : [...current, { id: book.id, title: book.title }]);
  }

  const missing = catalog.state === "ready"
    ? draft.filter((book) => !catalog.books.some((item) => item.id === book.id))
    : [];

  return (
    <Dialog.Root open={open} onOpenChange={changeOpen}>
      <div className="book-context">
        <Dialog.Trigger asChild>
          <button type="button" className="books-trigger" disabled={busy}>
            <BookOpen size={16} aria-hidden="true" /> Books
          </button>
        </Dialog.Trigger>
        {!books.length ? <span className="whole-library">Whole library</span> : books.slice(0, 2).map((book) => (
          <span className="book-chip" key={book.id}>
            <span title={book.title}>{book.title}</span>
            <button type="button" disabled={busy} aria-label={`Remove ${book.title} from context`}
              onClick={() => onChange(books.filter((item) => item.id !== book.id))}>
              <X size={13} aria-hidden="true" />
            </button>
          </span>
        ))}
        {books.length > 2 && <button type="button" className="books-trigger" disabled={busy}
          aria-label={`View all ${books.length} selected books`} onClick={() => changeOpen(true)}>+{books.length - 2}</button>}
      </div>
      <Dialog.Portal>
        <Dialog.Overlay className="book-picker-overlay" />
        <Dialog.Content className="book-picker">
          <header className="book-picker-header">
            <div>
              <Dialog.Title>Books</Dialog.Title>
              <Dialog.Description>Choose the books to search. No selection searches the whole library.</Dialog.Description>
            </div>
            <Dialog.Close asChild><button type="button" className="icon-button" aria-label="Close book selector"><X size={20} /></button></Dialog.Close>
          </header>
          <div className="book-picker-list" aria-busy={catalog.state === "loading"}>
            {catalog.state === "loading" && <p role="status" className="book-picker-notice">Loading books…</p>}
            {catalog.state === "error" && <div role="alert" className="book-picker-notice">
              <p>Could not load the books.</p><Button variant="outline" onClick={() => void load()}>Retry</Button>
            </div>}
            {catalog.state === "ready" && <>
              {!catalog.books.length && <p className="book-picker-notice">There are no books in the library yet.</p>}
              {missing.length > 0 && <div className="book-picker-notice" role="alert">
                <p>Some selected books are no longer available. Remove them to apply changes.</p>
                {missing.map((book) => <Button key={book.id} variant="outline" onClick={() => toggle(book)}>Remove {book.title}</Button>)}
              </div>}
              {catalog.books.map((book) => {
                const cover = bookCoverSource(book);
                return <label className="book-picker-row" key={book.id}>
                  <span className="book-picker-cover">
                    <BookOpen size={20} aria-hidden="true" />
                    {cover && (
                      // Stored raster covers; the icon remains if a cover cannot load.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={cover} alt="" width={36} height={54} loading="lazy" onError={(event) => { event.currentTarget.hidden = true; }} />
                    )}
                  </span>
                  <span className="book-picker-details"><span className="book-picker-title">{book.title}</span>
                    {book.authors?.trim() && <span className="book-picker-author">By {book.authors}</span>}
                  </span>
                  <input type="checkbox" checked={draft.some((item) => item.id === book.id)} onChange={() => toggle(book)} aria-label={`Search ${book.title}`} />
                </label>;
              })}
            </>}
          </div>
          <footer className="book-picker-footer">
            <div className="book-picker-count">
              <span role="status">{draft.length ? `${draft.length} ${draft.length === 1 ? "book" : "books"} selected` : "Whole library"}</span>
              {draft.length > 0 && <button type="button" className="books-trigger" onClick={() => setDraft([])}>Clear selection</button>}
            </div>
            <Button disabled={busy || catalog.state !== "ready" || missing.length > 0} onClick={() => {
              // Resolve displayed titles from the latest catalog without changing scope.
              if (catalog.state !== "ready" || busy || missing.length) return;
              onChange(draft.map((book) => ({ id: book.id, title: catalog.books.find((item) => item.id === book.id)!.title })));
              setOpen(false);
            }}>{draft.length ? "Apply" : "Use whole library"}</Button>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
