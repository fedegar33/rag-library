import type { SavedChat } from "./chat.ts";

export async function chatResource<T>(path = "", method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`/api/chats${path}`, {
    method, cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Chat storage is unavailable.");
  return data as T;
}

export async function loadWorkspace(id?: string) {
  const { chats } = await chatResource<{ chats: SavedChat[] }>();
  const activeId = id ?? chats[0]?.id;
  const active = activeId
    ? await chatResource<SavedChat>(`/${encodeURIComponent(activeId)}`)
    : { ...await chatResource<SavedChat>("", "POST"), messages: [] };
  return { chats: [active, ...chats.filter((chat) => chat.id !== active.id)], activeId: active.id };
}
