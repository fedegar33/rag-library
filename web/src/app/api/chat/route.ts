import { proxyChat } from "@/lib/chat-server";

export const runtime = "nodejs";

export async function POST(request: Request) {
  return proxyChat(request);
}
