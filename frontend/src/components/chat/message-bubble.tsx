"use client";

import { MarkdownContent } from "./markdown-content";
import { ToolCard } from "./tool-card";
import { MessageActions } from "./message-actions";
import { PlanDisplay } from "./plan-display";
import { EvidenceSection } from "./evidence-section";
import { DeclineMessage } from "./decline-message";
import type { ToolCall, EvidenceItem } from "@/hooks/chat-reducer";

interface MessageBubbleProps {
  role: "user" | "assistant";
  content: string;
  toolCalls: ToolCall[];
  isStreaming: boolean;
  plan?: { steps: string[]; reasoning: string };
  evidence?: EvidenceItem[];
  isDecline?: boolean;
  sessionId?: string;
  messageId?: string;
}

export function MessageBubble({
  role,
  content,
  toolCalls,
  isStreaming,
  plan,
  evidence,
  isDecline,
}: MessageBubbleProps) {
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
        {plan && plan.steps.length > 0 && (
          <div className="mb-2">
            <PlanDisplay
              steps={plan.steps}
              reasoning={plan.reasoning}
              toolCalls={toolCalls}
            />
          </div>
        )}
        {toolCalls.map((tc) => (
          <ToolCard
            key={tc.id}
            tool={tc.tool}
            params={tc.params}
            status={tc.status}
            result={tc.result}
          />
        ))}
        {isDecline && content ? (
          <DeclineMessage content={content} />
        ) : (
          content && (
            <MarkdownContent content={content} isStreaming={isStreaming} />
          )
        )}
        {evidence && evidence.length > 0 && (
          <EvidenceSection evidence={evidence} />
        )}
        {!isStreaming && content && !isDecline && (
          <div className="mt-1">
            <MessageActions content={content} />
          </div>
        )}
      </div>
    </div>
  );
}
