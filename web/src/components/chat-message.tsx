"use client";

import { Streamdown } from "streamdown";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Message, MessageContent, MessageHeader } from "@/components/ui/message";
import { Button } from "@/components/ui/button";
import { ToolActivity, ToolResult } from "@/components/tool-result";
import { messageText } from "@/lib/chat-transport";
import type { LibraryMessage } from "@/lib/chat";

export function ChatMessage({
  message,
  active,
  retryDisabled,
  onRetry,
}: {
  message: LibraryMessage;
  active: boolean;
  retryDisabled: boolean;
  onRetry?: () => void;
}) {
  if (message.role === "user") {
    return (
      <Message align="end" className="message user" role="article" aria-label="Your message">
        <MessageContent>
          <Bubble align="end" variant="muted" className="user-bubble">
            <BubbleContent className="user-bubble-content">
              <div className="message-text">{messageText(message)}</div>
            </BubbleContent>
          </Bubble>
        </MessageContent>
      </Message>
    );
  }

  const toolParts = message.parts.filter((part) => part.type === "dynamic-tool");
  const hasVisibleContent = message.parts.some(
    (part) => (part.type === "text" && !!part.text.trim()) || part.type === "dynamic-tool",
  );
  const thinking = active && !hasVisibleContent;

  return (
    <Message className="message assistant" role="article" aria-label="Assistant reply">
      <MessageContent className="chat-message-content">
        {(message.metadata?.interruption || thinking) && (
          <MessageHeader className="assistant-label">
            {message.metadata?.interruption && <span className="sample-label">Interrupted</span>}
            {thinking && (
              <span className="response-status" role="status">Thinking…</span>
            )}
          </MessageHeader>
        )}
        <div className="message-parts">
          {message.parts.map((part, index) => {
            if (part.type === "text" && part.text.trim()) {
              return (
                <Streamdown
                  key={`text-${index}`}
                  className="message-markdown"
                  isAnimating={active && part.state === "streaming"}
                  controls={false}
                  skipHtml
                  disallowedElements={["img"]}
                  linkSafety={{ enabled: false }}
                >
                  {part.text}
                </Streamdown>
              );
            }
            if (part.type === "dynamic-tool") {
              return <ToolActivity key={part.toolCallId} part={part} active={active} />;
            }
            return null;
          })}
          {toolParts.map((part) => (
            <ToolResult key={`result-${part.toolCallId}`} part={part} active={active} />
          ))}
        </div>
        {message.metadata?.interruption && (
          <div className="response-error" role="alert">
            <p>{message.metadata.interruption}</p>
            {onRetry && (
              <Button variant="outline" className="retry-button" disabled={retryDisabled} onClick={onRetry}>
                Retry question
              </Button>
            )}
          </div>
        )}
      </MessageContent>
    </Message>
  );
}
