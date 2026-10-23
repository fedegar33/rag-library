"use client";

import { ArrowUp } from "lucide-react";
import type { FormEvent, Ref } from "react";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupTextarea } from "@/components/ui/input-group";

export function ChatComposer({
  draft,
  bookCount,
  busy,
  configurationError,
  inputRef,
  onDraftChange,
  onSubmit,
}: {
  draft: string;
  bookCount: number;
  busy: boolean;
  configurationError?: string;
  inputRef: Ref<HTMLTextAreaElement>;
  onDraftChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="composer-area">
      {configurationError && <p className="configuration-error" role="alert">{configurationError}</p>}
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
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <InputGroupAddon align="block-end" className="composer-toolbar">
            <span className="book-status">
              {bookCount ? `${bookCount} ${bookCount === 1 ? "book" : "books"} attached` : "No books attached"}
            </span>
            <div className="composer-actions">
              <span className="send-hint">Enter to send</span>
              <InputGroupButton
                type="submit"
                variant="default"
                size="icon-sm"
                className="send-button"
                aria-label="Send message"
                disabled={!draft.trim() || busy || !!configurationError || !bookCount}
              >
                <ArrowUp size={19} aria-hidden="true" />
              </InputGroupButton>
            </div>
          </InputGroupAddon>
        </InputGroup>
      </form>
      <p className="demo-note" id="chat-limits">Each question is independent. Chats reset on refresh.</p>
    </div>
  );
}
