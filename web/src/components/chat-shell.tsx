"use client";

import {
  ArrowRight,
  ArrowUp,
  BookOpen,
  ChevronRight,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useChat } from "@ai-sdk/react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { emptyChat, starters, type Chat } from "@/lib/chat";
import { messageText } from "@/lib/chat-transport";

function LibraryMark({ small = false }: { small?: boolean }) {
  return (
    <span
      className={small ? "library-mark small" : "library-mark"}
      aria-hidden="true"
    >
      <BookOpen strokeWidth={1.4} />
    </span>
  );
}

function ChatSidebar({
  chats,
  activeId,
  onSelect,
  onNew,
  onClose,
}: {
  chats: Chat[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
}) {
  return (
    <div className="sidebar-inner">
      <div className="sidebar-brand">
        <LibraryMark small />
        <span>
          RAG Library
          <span className="brand-caption">A space for curious minds</span>
        </span>
        <button
          className="icon-button sidebar-close"
          aria-label="Close sidebar"
          onClick={onClose}
        >
          <PanelLeftClose size={18} />
        </button>
      </div>
      <button className="new-chat" onClick={onNew}>
        <Plus size={17} />
        New conversation
        <span className="new-chat-plus" aria-hidden="true">
          ↗
        </span>
      </button>
      <nav aria-label="Conversations" className="chat-navigation">
        {(["Today", "Yesterday"] as const).map((group) => (
          <div
            className="chat-group"
            key={group}
            hidden={!chats.some((chat) => chat.group === group)}
          >
            <h2>{group}</h2>
            {chats
              .filter((chat) => chat.group === group)
              .map((chat) => (
                <button
                  key={chat.id}
                  className={`chat-link${chat.id === activeId ? " selected" : ""}`}
                  aria-current={chat.id === activeId ? "page" : undefined}
                  onClick={() => onSelect(chat.id)}
                >
                  <MessageCircle size={16} strokeWidth={1.6} />
                  <span className="chat-link-text">
                    <span>{chat.title}</span>
                    <span className="chat-link-detail">
                      {chat.books.length
                        ? `${chat.books.length} ${chat.books.length === 1 ? "book" : "books"}`
                        : "General conversation"}
                    </span>
                  </span>
                  {chat.id === activeId && (
                    <span className="active-dot" aria-hidden="true" />
                  )}
                </button>
              ))}
          </div>
        ))}
      </nav>
      <div className="sidebar-bottom">
        <div className="sidebar-note">
          <BookOpen size={18} strokeWidth={1.5} />
          <p>
            Good questions.
            <br />
            <span>Even better conversations.</span>
          </p>
        </div>
        <div className="profile-row">
          <span className="profile-avatar" aria-hidden="true">
            Y
          </span>
          <div>
            Your reading space<span>This session only</span>
          </div>
          <span className="preview-dot" aria-hidden="true" />
        </div>
      </div>
    </div>
  );
}

export function ChatShell({
  bookIds,
  configurationError,
}: {
  bookIds: number[];
  configurationError?: string;
}) {
  const [chats, setChats] = useState<Chat[]>(() => [emptyChat("new", bookIds)]);
  const [activeId, setActiveId] = useState("new");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const mobileSidebar = useRef<HTMLDialogElement>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const chat = chats.find((item) => item.id === activeId)!;
  const { messages, status, sendMessage, stop } = useChat({
    chat: chat.client,
  });
  const busy = status === "submitted" || status === "streaming";
  const lastMessage = messages.at(-1);
  const latestQuestion = messages.findLast(
    (message) => message.role === "user",
  );
  const searching = lastMessage?.parts.some(
    (part) =>
      part.type === "dynamic-tool" &&
      (part.state === "input-available" || part.state === "input-streaming"),
  );
  const responseStatus = searching
    ? "Searching your books…"
    : lastMessage?.parts.some(
          (part) => part.type === "text" && part.state === "streaming",
        )
      ? "Writing…"
      : "Thinking…";

  // Each SDK Chat owns its message store. Switching hooks unsubscribes the old
  // conversation; stop() cancels its request and retains the partial message.
  useEffect(
    () => () => {
      void stop();
    },
    [stop],
  );

  function selectChat(id: string) {
    setActiveId(id);
    mobileSidebar.current?.close();
  }

  function newChat() {
    const empty = chats.find((item) => item.client.messages.length === 0);
    if (empty) selectChat(empty.id);
    else {
      const id = crypto.randomUUID();
      setChats((current) => [emptyChat(id, bookIds), ...current]);
      selectChat(id);
    }
    composer.current?.focus();
  }

  function setDraft(draft: string) {
    setChats((current) =>
      current.map((item) => (item.id === activeId ? { ...item, draft } : item)),
    );
  }

  function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = chat.draft.trim();
    if (
      !text ||
      text.length > 4000 ||
      busy ||
      configurationError ||
      !bookIds.length
    )
      return;
    setChats((current) =>
      current.map((item) =>
        item.id === activeId
          ? {
              ...item,
              title: messages.length ? item.title : text,
              draft: "",
            }
          : item,
      ),
    );
    void sendMessage({ text });
  }

  function retry() {
    if (busy || configurationError || !latestQuestion) return;
    // An explicit resend keeps the original interrupted answer in the SDK
    // history. regenerate() would replace it and lose the partial output.
    void sendMessage({ text: messageText(latestQuestion) });
  }

  const sidebarProps = {
    chats,
    activeId,
    onSelect: selectChat,
    onNew: newChat,
  };

  return (
    <div className={`chat-shell${sidebarOpen ? "" : " sidebar-hidden"}`}>
      <a className="skip-link" href="#message-input">
        Skip to message
      </a>
      <aside className="desktop-sidebar" aria-label="Chat sidebar">
        <ChatSidebar {...sidebarProps} onClose={() => setSidebarOpen(false)} />
      </aside>
      <dialog
        ref={mobileSidebar}
        className="mobile-sidebar"
        aria-label="Conversations"
        onClick={(event) => {
          if (event.target === event.currentTarget)
            mobileSidebar.current?.close();
        }}
      >
        <ChatSidebar
          {...sidebarProps}
          onClose={() => mobileSidebar.current?.close()}
        />
      </dialog>
      <main className="chat-main">
        <header className="chat-header">
          <button
            className="icon-button desktop-toggle"
            aria-label={sidebarOpen ? "Hide sidebar" : "Show sidebar"}
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen((value) => !value)}
          >
            {sidebarOpen ? (
              <PanelLeftClose size={19} />
            ) : (
              <PanelLeftOpen size={19} />
            )}
          </button>
          <button
            className="icon-button mobile-toggle"
            aria-label="Open conversations"
            onClick={() => mobileSidebar.current?.showModal()}
          >
            <PanelLeftOpen size={19} />
          </button>
          <div className="header-path">
            <span className="header-library">Your library</span>
            <ChevronRight size={13} />
            <h1>{chat.title}</h1>
          </div>
          <span className="demo-badge">
            <span aria-hidden="true" />
            Agent chat
          </span>
        </header>
        {chat.books.length > 0 && (
          <section className="attached-books" aria-label="Attached books">
            <BookOpen size={15} />
            <span className="attached-label">In this conversation</span>
            {chat.books.map((book) => (
              <span
                className="book-chip"
                key={book.id}
                title={`Catalog ID ${book.id}`}
              >
                {book.title}
              </span>
            ))}
          </section>
        )}
        {messages.length === 0 ? (
          <section className="welcome" aria-label="Start a conversation">
            <div className="welcome-content">
              <div className="welcome-eyebrow">
                <span />
                BETWEEN THE LINES
                <span />
              </div>
              <LibraryMark />
              <h2>
                A good book is just
                <br />
                the beginning.
              </h2>
              <p>
                Follow a thought. Ask a question.
                <br className="mobile-break" /> See where the conversation takes
                you.
              </p>
              <div className="starter-grid">
                {starters.map((starter, index) => (
                  <button
                    className="starter-card"
                    key={starter.label}
                    onClick={() => {
                      setDraft(starter.text);
                      composer.current?.focus();
                    }}
                  >
                    <span className="starter-top">
                      <span className="starter-number">0{index + 1}</span>
                      <ArrowRight size={16} />
                    </span>
                    <strong>{starter.label}</strong>
                    <span>{starter.detail}</span>
                  </button>
                ))}
              </div>
            </div>
          </section>
        ) : (
          <Conversation
            key={chat.id}
            initial="instant"
            resize="instant"
            className="messages"
            aria-label="Chat messages"
          >
            <ConversationContent className="message-list">
              {messages.map((message) => (
                <article
                  className={`message ${message.role}`}
                  key={message.id}
                  aria-label={
                    message.role === "user" ? "Your message" : "Assistant reply"
                  }
                >
                  {message.role === "assistant" && (
                    <div className="assistant-label">
                      <LibraryMark small />
                      <span>RAG Library</span>
                      {message.metadata?.interruption && (
                        <span className="sample-label">Interrupted</span>
                      )}
                      {busy && message.id === lastMessage?.id && (
                        <span className="response-status" role="status">
                          {responseStatus}
                        </span>
                      )}
                    </div>
                  )}
                  <div className="message-text">
                    {messageText(message)
                      .split("\n\n")
                      .map((paragraph, index) => (
                        <p key={index}>{paragraph}</p>
                      ))}
                  </div>
                  {message.metadata?.interruption && (
                    <div className="response-error" role="alert">
                      <p>{message.metadata.interruption}</p>
                      {message.id === lastMessage?.id && latestQuestion && (
                        <button
                          className="retry-button"
                          disabled={busy || !!configurationError}
                          onClick={retry}
                        >
                          Retry question
                        </button>
                      )}
                    </div>
                  )}
                </article>
              ))}
              {busy && lastMessage?.role !== "assistant" && (
                <div className="assistant-label" role="status">
                  <LibraryMark small />
                  <span>RAG Library</span>
                  <span className="response-status">Thinking…</span>
                </div>
              )}
            </ConversationContent>
            <ConversationScrollButton aria-label="Scroll to latest message" />
          </Conversation>
        )}
        <div className="composer-area">
          {configurationError && (
            <p className="configuration-error" role="alert">
              {configurationError}
            </p>
          )}
          <form className="composer" onSubmit={send} aria-busy={busy}>
            <label className="sr-only" htmlFor="message-input">
              Message RAG Library
            </label>
            <textarea
              ref={composer}
              id="message-input"
              placeholder="Where would you like to begin?"
              rows={1}
              maxLength={4000}
              aria-describedby="chat-limits"
              value={chat.draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing &&
                  event.keyCode !== 229
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <div className="composer-toolbar">
              <span className="book-status">
                <BookOpen size={15} />
                {chat.books.length === 0
                  ? "No books attached"
                  : `${chat.books.length} ${chat.books.length === 1 ? "book" : "books"} attached`}
              </span>
              <div className="composer-actions">
                <span className="send-hint">Enter to send</span>
                <button
                  className="send-button"
                  type="submit"
                  aria-label="Send message"
                  disabled={
                    !chat.draft.trim() ||
                    busy ||
                    !!configurationError ||
                    !bookIds.length
                  }
                >
                  <ArrowUp size={19} />
                </button>
              </div>
            </div>
          </form>
          <p className="demo-note" id="chat-limits">
            <Sparkles size={12} aria-hidden="true" />
            Each question is independent. Chats reset on refresh.
          </p>
        </div>
      </main>
    </div>
  );
}
