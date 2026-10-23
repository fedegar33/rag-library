"use client";

import { ArrowUp, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useChat } from "@ai-sdk/react";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { emptyChat, type Chat } from "@/lib/chat";
import { messageText } from "@/lib/chat-transport";

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
        <span>RAG Library</span>
        <button
          className="icon-button sidebar-close"
          aria-label="Close sidebar"
          onClick={onClose}
        >
          <PanelLeftClose size={18} />
        </button>
      </div>
      <button className="new-chat" onClick={onNew}>
        New chat
      </button>
      <nav aria-label="Conversations" className="chat-navigation">
        <h2>Recents</h2>
        {chats.map((chat) => (
          <button
            key={chat.id}
            className={`chat-link${chat.id === activeId ? " selected" : ""}`}
            aria-current={chat.id === activeId ? "page" : undefined}
            onClick={() => onSelect(chat.id)}
            title={chat.title}
          >
            <span>{chat.title}</span>
          </button>
        ))}
      </nav>
      <p className="sidebar-footer">Your reading space</p>
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
          <h1>{chat.title}</h1>
        </header>
        {messages.length === 0 ? (
          <section className="welcome" aria-label="Start a conversation">
            <div className="welcome-content">
              <h2>What’s on your mind?</h2>
              <p>A question, a passage, a new perspective.</p>
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
              placeholder="Ask about your books…"
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
            Each question is independent. Chats reset on refresh.
          </p>
        </div>
      </main>
    </div>
  );
}
