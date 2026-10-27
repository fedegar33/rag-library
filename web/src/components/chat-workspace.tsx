"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChatShell } from "@/components/chat-shell";
import { loadWorkspace } from "@/lib/conversations";

export function ChatWorkspace({ initialId }: { initialId?: string }) {
  const [workspace, setWorkspace] = useState<Awaited<ReturnType<typeof loadWorkspace>>>();
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const loading = useRef<{ id?: string; attempt: number; promise: ReturnType<typeof loadWorkspace> } | null>(null);
  useEffect(() => {
    let cancelled = false;
    if (!loading.current || loading.current.id !== initialId || loading.current.attempt !== attempt)
      loading.current = { id: initialId, attempt, promise: loadWorkspace(initialId) };
    loading.current.promise.then((data) => {
      if (cancelled) return;
      window.history.replaceState(null, "", `/chats/${data.activeId}`);
      setWorkspace(data);
      setError("");
    }).catch((failure: unknown) => {
      if (!cancelled) setError(failure instanceof Error ? failure.message : "Could not load chats.");
    });
    return () => { cancelled = true; };
  }, [initialId, attempt]);
  if (workspace) return <ChatShell key={workspace.activeId} initialChats={workspace.chats} initialActiveId={workspace.activeId} />;
  return <main className="welcome" aria-live="polite"><div className="welcome-content">
    <h2>{error ? "Could not open the chat" : "Loading conversations…"}</h2>
    {error && <><p role="alert">{error}</p><button className="new-chat" onClick={() => setAttempt((value) => value + 1)}>Try again</button><Link href="/">Open conversations</Link></>}
  </div></main>;
}
