import { readChatConfig } from "./chat-server.ts";

export const validChatId = (id: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);

export async function proxyConversations(request: Request, id?: string, backendUrl = readChatConfig().backendUrl) {
  if (id !== undefined && !validChatId(id))
    return Response.json({ error: "Chat not found." }, { status: 404 });
  if (!(id ? ["GET", "PATCH"] : ["GET", "POST"]).includes(request.method))
    return new Response(null, { status: 405 });
  let body: string | undefined;
  if (request.method === "PATCH") {
    try {
      const data = await request.json();
      if (!Array.isArray(data.book_ids) || data.book_ids.some((value: unknown) => !Number.isSafeInteger(value) || (value as number) <= 0))
        throw new Error("Invalid books");
      body = JSON.stringify({ book_ids: [...new Set(data.book_ids)] });
    } catch {
      return Response.json({ error: "Choose valid books." }, { status: 422 });
    }
  }
  try {
    const response = await fetch(`${backendUrl.replace(/\/$/, "")}/chats${id ? `/${id}` : ""}`, {
      method: request.method, body, signal: request.signal, cache: "no-store", redirect: "error",
      headers: { "Content-Type": "application/json" },
    });
    if (!response.ok) {
      await response.body?.cancel();
      return Response.json({ error: response.status === 404 ? "Chat not found." :
        response.status === 409 ? "This chat is busy. Try again when it finishes." :
        "Could not save or load the chat. Please try again." }, {
        status: [404, 409, 422].includes(response.status) ? response.status : 503,
        headers: { "Cache-Control": "no-store" },
      });
    }
    return Response.json(await response.json(), {
      status: response.status, headers: { "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ error: "Chat storage is unavailable. Please try again." }, {
      status: 503, headers: { "Cache-Control": "no-store" },
    });
  }
}
