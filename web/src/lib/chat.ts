import type { Chat as SDKChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { createLibraryChat } from "./chat-session.ts";

export type LibraryMessage = UIMessage<{ interruption?: string; books?: Book[] }>;
export type Book = { id: number; title: string };
export type Chat = {
  id: string;
  title: string;
  group: "Today" | "Yesterday";
  books: Book[];
  client: SDKChat<LibraryMessage>;
  draft: string;
  loaded?: boolean;
};

export function emptyChat(id: string): Chat {
  return {
    id,
    title: "New chat",
    group: "Today",
    books: [],
    client: createLibraryChat(id),
    draft: "",
  };
}

export type SavedChat = {
  id: string;
  title: string;
  books: Book[];
  created_at: string;
  updated_at: string;
  messages?: LibraryMessage[];
};

export function restoreChat(saved: SavedChat): Chat {
  return {
    id: saved.id,
    group: "Today",
    draft: "",
    title: saved.title,
    books: saved.books,
    loaded: saved.messages !== undefined,
    client: createLibraryChat(saved.id, undefined, {
      persistent: true, messages: saved.messages ?? [],
    }),
  };
}
