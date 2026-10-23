"use client";

import { BookOpen } from "lucide-react";
import { useState } from "react";
import { bookCoverSource, type BookCardData } from "@/lib/available-books";

export function BookCard({ book }: { book: BookCardData }) {
  const source = bookCoverSource(book);
  const [failedSource, setFailedSource] = useState<string | null>(null);

  return (
    <article className="catalog-book">
      <div className="catalog-cover">
        {source && source !== failedSource ? (
          // Stored covers are served as-is through the same-origin proxy.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={source}
            alt=""
            width={64}
            height={96}
            loading="lazy"
            onError={() => setFailedSource(source)}
          />
        ) : (
          <span className="catalog-cover-placeholder" role="img" aria-label="No cover available">
            <BookOpen size={24} strokeWidth={1.3} aria-hidden="true" />
          </span>
        )}
      </div>
      <div className="catalog-book-details">
        <h3 style={{ fontFamily: "var(--font-heading)", fontSize: 16 }}>{book.title}</h3>
        {book.authors?.trim() && <p className="catalog-author">By {book.authors}</p>}
        {book.categories.some((category) => category.trim()) && (
          <ul className="catalog-categories" aria-label="Categories">
            {book.categories.filter((category) => category.trim()).map((category, index) => (
              <li key={`${category}-${index}`}>{category}</li>
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}
