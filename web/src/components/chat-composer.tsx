"use client";

import { ArrowUp, Square } from "lucide-react";
import { BookContext } from "@/components/book-context";
import type { Book } from "@/lib/chat";
import type { FormEvent, Ref } from "react";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group";

export function ChatComposer({
  draft,
  books,
  onBooksChange,
  onStop,
  busy,
  disabled = false,
  inputRef,
  onDraftChange,
  onSubmit,
}: {
  draft: string;
  books: Book[];
  onBooksChange: (books: Book[]) => void;
  onStop: () => void;
  busy: boolean;
  disabled?: boolean;
  inputRef: Ref<HTMLTextAreaElement>;
  onDraftChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="composer-area">
      <form onSubmit={onSubmit} aria-busy={busy}>
        <label className="sr-only" htmlFor="message-input">Message RAG Library</label>
        <InputGroup className="composer">
          <InputGroupTextarea
            ref={inputRef}
            id="message-input"
            placeholder="Ask about your books…"
            rows={1}
            maxLength={4000}
            aria-describedby="chat-limits"
            value={draft}
            disabled={disabled}
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <InputGroupAddon align="block-end" className="composer-toolbar">
            <BookContext books={books} busy={busy || disabled} onChange={onBooksChange} />
            <div className="composer-actions">
              <span className="send-hint">Enter to send</span>
              <InputGroupButton
                type={busy ? "button" : "submit"}
                onClick={busy ? onStop : undefined}
                variant="default"
                size="icon-sm"
                className="send-button"
                aria-label={busy ? "Stop response" : "Send message"}
                disabled={disabled || (!busy && !draft.trim())}
              >
                {busy ? <Square size={16} aria-hidden="true" /> : <ArrowUp size={19} aria-hidden="true" />}
              </InputGroupButton>
            </div>
          </InputGroupAddon>
        </InputGroup>
      </form>
      <p className="demo-note" id="chat-limits">Chats are saved automatically. Recent conversation is kept in context.</p>
    </div>
  );
}
