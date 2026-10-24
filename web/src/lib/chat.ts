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
