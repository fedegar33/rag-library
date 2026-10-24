import process from "node:process";

export type ChatConfig = { backendUrl: string };

export function readChatConfig(
  env: Record<string, string | undefined> = process.env,
): ChatConfig {
  return { backendUrl: env.BACKEND_API_URL || "http://127.0.0.1:8000" };
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

// Validate scope at the proxy; Python validates IDs against the current catalog.
// Forward conversation data only; Python validates tool pairs and windows history.
export async function proxyChat(request: Request, config = readChatConfig()) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return failure("Send a valid JSON message.", 400);
  }
  const record = body && typeof body === "object" ? body as Record<string, unknown> : {};
  const { message, messages } = record;
  const validQuestion = (value: unknown) => typeof value === "string" &&
    Boolean(value.trim()) && Array.from(value.trim()).length <= 4000;
  let conversation: Record<string, unknown>;
  if (messages !== undefined) {
    if (message !== undefined || !Array.isArray(messages) || !messages.length || messages.length > 1000 ||
      messages.some((item) => !item || typeof item !== "object" || !["user", "assistant", "tool"].includes(item.role)) ||
      messages[0].role !== "user" || messages.at(-1).role !== "user" ||
      !validQuestion(messages.at(-1).content)) {
      return failure("Send a valid conversation ending with your question.", 422);
    }
    conversation = { messages };
  } else if (validQuestion(message)) {
    conversation = { message: (message as string).trim() };
  } else {
    return failure("Enter a question between 1 and 4,000 characters.", 422);
  }
  const ids = body && typeof body === "object" && "book_ids" in body ? body.book_ids : [];
  if (!Array.isArray(ids) || ids.some((id) => !Number.isSafeInteger(id) || id <= 0)) {
    return failure("Choose valid books before sending your question.", 422);
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
          ...conversation,
          book_ids: [...new Set(ids)],
        }),
        signal: request.signal,
        cache: "no-store",
      },
    );
    if (!upstream.ok) {
      await upstream.body?.cancel();
      if (upstream.status === 422)
        return failure(
          "The conversation or selected books are invalid. Review your selection or start a new chat.",
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
