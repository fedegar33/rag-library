import { ChatWorkspace } from "@/components/chat-workspace";

export default async function ChatPage({ params }: { params: Promise<{ id: string }> }) {
  return <ChatWorkspace initialId={(await params).id} />;
}
