import { proxyConversations } from "@/lib/conversations-server";

export const runtime = "nodejs";
type Context = { params: Promise<{ id: string }> };
export async function GET(request: Request, context: Context) {
  return proxyConversations(request, (await context.params).id);
}
export async function PATCH(request: Request, context: Context) {
  return proxyConversations(request, (await context.params).id);
}
