"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { useChat } from "@ai-sdk/react";
import {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from "@/components/ui/message-scroller";
import { ChatMessage } from "@/components/chat-message";
import { ChatComposer } from "@/components/chat-composer";
import { restoreChat, type Chat, type SavedChat } from "@/lib/chat";
import { messageText } from "@/lib/chat-transport";
import { chatResource } from "@/lib/conversations";

function ChatSidebar({
  chats,
  activeId,
  onSelect,
  onNew,
  onClose,
  disabled,
}: {
  chats: Chat[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
  disabled: boolean;
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
      <button className="new-chat" onClick={onNew} disabled={disabled}>
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
            disabled={disabled}
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

export function ChatShell({ initialChats, initialActiveId }: {
  initialChats: SavedChat[]; initialActiveId: string;
}) {
  const [chats, setChats] = useState<Chat[]>(() => initialChats.map(restoreChat));
  const [activeId, setActiveId] = useState(initialActiveId);
  const [pending, setPending] = useState(false);
  const [storageError, setStorageError] = useState("");
  const operation = useRef(0);
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
  // Each SDK Chat owns its message store. Switching hooks unsubscribes the old
  // conversation; stop() cancels its request and retains the partial message.
  useEffect(
    () => () => {
      void stop();
    },
    [stop],
  );

  const selectChat = useCallback(async (id: string, push = true) => {
    const currentOperation = ++operation.current;
    setPending(true);
    try {
      await stop();
      if (currentOperation !== operation.current) return;
      if (!chats.some((item) => item.id === id && item.loaded)) {
        const saved = await chatResource<SavedChat>(`/${encodeURIComponent(id)}`);
        if (currentOperation !== operation.current) return;
        setChats((current) => [restoreChat(saved), ...current.filter((item) => item.id !== id)]);
      }
      setActiveId(id);
      if (push) window.history.pushState(null, "", `/chats/${id}`);
      setStorageError("");
      mobileSidebar.current?.close();
    } catch (failure) {
      if (currentOperation !== operation.current) return;
      setStorageError(failure instanceof Error ? failure.message : "Could not open the chat.");
      window.history.replaceState(null, "", `/chats/${activeId}`);
    } finally { if (currentOperation === operation.current) setPending(false); }
  }, [chats, stop, activeId]);

  useEffect(() => {
    const onBack = () => {
      const id = window.location.pathname.match(/^\/chats\/([^/]+)$/)?.[1];
      if (id) void selectChat(id, false);
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, [selectChat]);

  async function newChat() {
    if (pending) return;
    const empty = chats.find((item) => item.loaded && item.client.messages.length === 0);
    if (empty) {
      await selectChat(empty.id);
    }
    else {
      const currentOperation = ++operation.current;
      setPending(true);
      try {
        await stop();
        const saved = await chatResource<SavedChat>("", "POST");
        if (currentOperation !== operation.current) return;
        setChats((current) => [restoreChat({ ...saved, messages: [] }), ...current]);
        setActiveId(saved.id);
        window.history.pushState(null, "", `/chats/${saved.id}`);
        setStorageError("");
        mobileSidebar.current?.close();
      } catch (failure) {
        if (currentOperation !== operation.current) return;
        setStorageError(failure instanceof Error ? failure.message : "Could not create the chat.");
      } finally { if (currentOperation === operation.current) setPending(false); }
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
      busy || pending
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
    void sendMessage({ text, metadata: { books: chat.books.map((book) => ({ ...book })) } });
  }

  function retry() {
    if (busy || pending || !latestQuestion) return;
    // An explicit resend keeps the original interrupted answer in the SDK
    // history. regenerate() would replace it and lose the partial output.
    void sendMessage({ text: messageText(latestQuestion), metadata: latestQuestion.metadata });
  }

  const sidebarProps = {
    chats,
    activeId,
    onSelect: selectChat,
    onNew: newChat,
    disabled: pending,
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
        {storageError && <p className="demo-note" role="alert">{storageError}</p>}
        {messages.length === 0 ? (
          <section className="welcome" aria-label="Start a conversation">
            <div className="welcome-content">
              <h2>What’s on your mind?</h2>
              <p>A question, a passage, a new perspective.</p>
            </div>
          </section>
        ) : (
          <MessageScrollerProvider key={chat.id} autoScroll defaultScrollPosition="last-anchor">
            <MessageScroller className="messages">
              <MessageScrollerViewport aria-label="Chat messages">
                <MessageScrollerContent className="message-list">
                  {messages.map((message) => (
                    <MessageScrollerItem
                      key={message.id}
                      messageId={message.id}
                      scrollAnchor={message.role === "user"}
                    >
                      <ChatMessage
                        message={message}
                        active={busy && message.id === lastMessage?.id}
                        retryDisabled={busy || pending}
                        onRetry={message.id === lastMessage?.id && latestQuestion ? retry : undefined}
                      />
                    </MessageScrollerItem>
                  ))}
                  {busy && lastMessage?.role !== "assistant" && (
                    <MessageScrollerItem messageId={`pending-${chat.id}`}>
                      <div className="assistant-label" role="status">
                        <span className="response-status">Thinking…</span>
                      </div>
                    </MessageScrollerItem>
                  )}
                </MessageScrollerContent>
              </MessageScrollerViewport>
              <MessageScrollerButton
                aria-label="Jump to latest message"
                behavior="instant"
                className="scroll-latest size-10 transition-none"
              />
            </MessageScroller>
          </MessageScrollerProvider>
        )}
        <ChatComposer
          key={`composer-${chat.id}`}
          draft={chat.draft}
          books={chat.books}
          busy={busy}
          disabled={pending}
          onBooksChange={async (books) => {
            if (busy || pending) return;
            const currentOperation = ++operation.current;
            setPending(true);
            try {
              const saved = await chatResource<SavedChat>(`/${activeId}`, "PATCH", { book_ids: books.map((book) => book.id) });
              setChats((current) => current.map((item) => item.id === activeId ? { ...item, books: saved.books } : item));
              if (currentOperation === operation.current) setStorageError("");
            } catch (failure) {
              if (currentOperation === operation.current)
                setStorageError(failure instanceof Error ? failure.message : "Could not save the books.");
            } finally { if (currentOperation === operation.current) setPending(false); }
          }}
          onStop={() => void stop()}
          inputRef={composer}
          onDraftChange={setDraft}
          onSubmit={send}
        />
      </main>
    </div>
  );
}
