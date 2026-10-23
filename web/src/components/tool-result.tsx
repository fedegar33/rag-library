"use client";

import type { DynamicToolUIPart } from "ai";
import { AvailableBooks } from "@/components/available-books";
import { Trace, TraceLine, TraceTitle } from "@/components/ui/trace";
import { availableBooksView } from "@/lib/available-books";
import { LIST_AVAILABLE_BOOKS_TOOL } from "@/lib/tools-constants";
import { toolStatus } from "@/lib/tool-status";

// Activity stays at its original place in the stream, independently of when
// the result view is released. Both parts retain the server's toolCallId.
export function ToolActivity({ part, active }: { part: DynamicToolUIPart; active: boolean }) {
  const status = toolStatus(part, active);
  return (
    <Trace className="tool-status" role="status" aria-live="polite">
      <TraceLine status={status.failed ? "error" : undefined}>
        <TraceTitle>{status.title}</TraceTitle>
      </TraceLine>
    </Trace>
  );
}

export function ToolResult({ part, active }: { part: DynamicToolUIPart; active: boolean }) {
  switch (part.toolName) {
    case LIST_AVAILABLE_BOOKS_TOOL: {
      const view = availableBooksView(part, active);
      if (view.state === "loading" || view.state === "waiting-for-response") return null;
      return <AvailableBooks view={view} />;
    }
    default:
      return null;
  }
}
