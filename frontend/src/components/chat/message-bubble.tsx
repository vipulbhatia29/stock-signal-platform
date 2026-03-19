"use client";

import { MarkdownContent } from "./markdown-content";
import { ToolCard } from "./tool-card";
import { MessageActions } from "./message-actions";
import type { ToolCall } from "@/hooks/chat-reducer";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  toolCalls: ToolCall[];
  isStreaming: boolean;
}

export function MessageBubble({ role, content, toolCalls, isStreaming }: MessageBubbleProps) {
  if (role === "user") {
    return (
      <div className="flex justify-end px-4 py-2">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-accent/15 px-4 py-2.5 text-sm text-foreground">
          {content}
        </div>
      </div>
    );
  }

  return (
    <div className="group px-4 py-2">
      <div className="max-w-full">
        {toolCalls.map((tc) => (
          <ToolCard
            key={tc.id}
            tool={tc.tool}
            params={tc.params}
            status={tc.status}
            result={tc.result}
          />
        ))}
        {content && (
          <MarkdownContent content={content} isStreaming={isStreaming} />
        )}
        {!isStreaming && content && (
          <div className="mt-1">
            <MessageActions content={content} />
          </div>
        )}
      </div>
    </div>
  );
}
