import process from "node:process";

export type ChatConfig = {
  bookIds: number[];
  backendUrl: string;
  error?: string;
};

export function readChatConfig(
  env: Record<string, string | undefined> = process.env,
): ChatConfig {
  const backendUrl = env.BACKEND_API_URL || "http://127.0.0.1:8000";
  const entries = (env.CHAT_BOOK_IDS ?? "")
    .split(",")
    .map((value) => value.trim());
  if (
    entries.some(
      (value) =>
        !/^[1-9]\d*$/.test(value) || !Number.isSafeInteger(Number(value)),
    )
  ) {
    return {
      bookIds: [],
      backendUrl,
      error:
        "Test books are not configured. Set CHAT_BOOK_IDS in web/.env.local to current catalog IDs, then restart the web server.",
    };
  }
  return { bookIds: [...new Set(entries.map(Number))], backendUrl };
}

function failure(message: string, status: number) {
  return new Response(message, {
    status,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

// Keep configuration and request validation on the server. Never forward client history or IDs.
export async function proxyChat(request: Request, config = readChatConfig()) {
  if (config.error) return failure(config.error, 503);
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return failure("Send a valid JSON message.", 400);
  }
  const message =
    body && typeof body === "object" && "message" in body
      ? body.message
      : undefined;
  if (
    typeof message !== "string" ||
    !message.trim() ||
    Array.from(message.trim()).length > 4000
  ) {
    return failure("Enter a question between 1 and 4,000 characters.", 422);
  }
  try {
    const upstream = await fetch(
      `${config.backendUrl.replace(/\/$/, "")}/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify({
          message: message.trim(),
          book_ids: config.bookIds,
        }),
        signal: request.signal,
        cache: "no-store",
      },
    );
    if (!upstream.ok) {
      await upstream.body?.cancel();
      if (upstream.status === 422)
        return failure(
          "The configured test books are unavailable. Check CHAT_BOOK_IDS against the current catalog.",
          422,
        );
      return failure(
        "The agent is unavailable. Please try again when it is back online.",
        upstream.status === 503 ? 503 : 502,
      );
    }
    if (
      !upstream.body ||
      !upstream.headers.get("content-type")?.includes("text/event-stream")
    ) {
      await upstream.body?.cancel();
      return failure(
        "The agent returned an unexpected response. Please try again.",
        502,
      );
    }
    return new Response(upstream.body, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "x-vercel-ai-ui-message-stream": "v1",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return failure(
      request.signal.aborted
        ? "Request cancelled."
        : "Could not connect to the agent. Please try again when it is back online.",
      request.signal.aborted ? 499 : 502,
    );
  }
}
