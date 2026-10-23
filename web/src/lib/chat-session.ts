import { Chat } from "@ai-sdk/react";
import type { LibraryMessage } from "./chat.ts";
import { LibraryChatTransport } from "./chat-transport.ts";

export function createLibraryChat(
  id: string,
  fetcher?: typeof globalThis.fetch,
): Chat<LibraryMessage> {
  const chat = new Chat<LibraryMessage>({
    id,
    transport: new LibraryChatTransport(fetcher),
    // Do not enable automatic tool follow-ups or stream resumption: Python owns
    // the whole agent run and only explicit user actions may make another call.
    onFinish: ({ message, isAbort, isDisconnect, isError }) => {
      if (!isAbort && !isDisconnect && !isError) return;
      const interrupted: LibraryMessage = {
        ...message,
        metadata: {
          ...message.metadata,
          interruption: isAbort
            ? "Response stopped when you switched conversations."
            : chat.error?.message ||
              "The connection was interrupted. Please try again.",
        },
      };
      chat.messages = chat.messages.some((item) => item.id === message.id)
        ? chat.messages.map((item) =>
            item.id === message.id ? interrupted : item,
          )
        : [...chat.messages, interrupted];
    },
  });
  return chat;
}
