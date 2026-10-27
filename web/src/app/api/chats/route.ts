import { proxyConversations } from "@/lib/conversations-server";

export const runtime = "nodejs";
export const GET = (request: Request) => proxyConversations(request);
export const POST = (request: Request) => proxyConversations(request);
