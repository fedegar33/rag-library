import { readChatConfig } from "./chat-server.ts";
import { readAvailableBooks } from "./available-books.ts";

export async function proxyCatalog(request: Request, backendUrl = readChatConfig().backendUrl) {
  try {
    const upstream = await fetch(`${backendUrl.replace(/\/$/, "")}/books`, {
      signal: request.signal, cache: "no-store", redirect: "error",
    });
    if (!upstream.ok) throw new Error("Catalog unavailable");
    const books = readAvailableBooks(await upstream.json());
    if (!books) throw new Error("Invalid catalog");
    return Response.json({ books }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "Could not load the books. Please try again." }, {
      status: 503, headers: { "Cache-Control": "no-store" },
    });
  }
}
