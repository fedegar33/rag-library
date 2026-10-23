import { readChatConfig } from "./chat-server.ts";

export async function proxyBookCover(
  request: Request,
  id: string,
  backendUrl = readChatConfig().backendUrl,
) {
  if (!/^[1-9]\d*$/.test(id) || !Number.isSafeInteger(Number(id))) {
    return new Response(null, { status: 400 });
  }
  try {
    const upstream = await fetch(`${backendUrl.replace(/\/$/, "")}/books/${id}/cover`, {
      signal: request.signal,
      cache: "no-store",
      redirect: "error",
    });
    const contentType = upstream.headers.get("content-type")?.split(";")[0].trim();
    // The image endpoint serves stored raster covers, never HTML or SVG.
    if (!upstream.ok || !upstream.body || !contentType || ![
      "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif",
    ].includes(contentType)) {
      await upstream.body?.cancel();
      return new Response(null, { status: upstream.status === 404 ? 404 : 502 });
    }
    return new Response(upstream.body, {
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return new Response(null, { status: 502 });
  }
}
