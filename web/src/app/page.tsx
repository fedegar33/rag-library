import { ChatShell } from "@/components/chat-shell";
import { readChatConfig } from "@/lib/chat-server";

export const dynamic = "force-dynamic";

export default function Home() {
  const { bookIds, error } = readChatConfig();
  return <ChatShell bookIds={bookIds} configurationError={error} />;
}
