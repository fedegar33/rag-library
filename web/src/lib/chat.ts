import type { Chat as SDKChat } from "@ai-sdk/react";
import type { UIMessage } from "ai";
import { createLibraryChat } from "./chat-session.ts";

export type LibraryMessage = UIMessage<{ interruption?: string }>;
export type Book = { id: number; title: string };
export type Chat = {
  id: string;
  title: string;
  group: "Today" | "Yesterday";
  books: Book[];
  client: SDKChat<LibraryMessage>;
  draft: string;
};

export function emptyChat(id: string, bookIds: number[]): Chat {
  return {
    id,
    title: "New conversation",
    group: "Today",
    books: bookIds.map((id) => ({ id, title: `Book #${id}` })),
    client: createLibraryChat(id),
    draft: "",
  };
}

export const starters = [
  {
    label: "Follow an idea",
    text: "What are the main themes in the attached books?",
    detail: "Find the threads that connect a story.",
  },
  {
    label: "Look a little closer",
    text: "Describe an important character in the attached books and what motivates them.",
    detail: "Make room for a different perspective.",
  },
  {
    label: "Find a starting point",
    text: "Tell me about the books attached to this conversation.",
    detail: "Get to know the books in this conversation.",
  },
];
