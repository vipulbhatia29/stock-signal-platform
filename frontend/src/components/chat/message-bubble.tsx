"use client";

import { memo } from "react";
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

/**
 * Extract tabular data from completed tool calls for CSV export.
 * Only tools that return arrays of records produce meaningful CSV data.
 */
function extractCsvData(toolCalls: ToolCall[]): Record<string, unknown>[] | undefined {
  for (const tc of toolCalls) {
    if (tc.status !== "completed" || !tc.result) continue;
    const r = tc.result as Record<string, unknown>;
    // screen_stocks returns { results: [...] }
    if (Array.isArray(r.results) && r.results.length > 0) return r.results as Record<string, unknown>[];
    // recommendations returns { recommendations: [...] }
    if (Array.isArray(r.recommendations) && r.recommendations.length > 0) return r.recommendations as Record<string, unknown>[];
    // Direct array result
    if (Array.isArray(tc.result) && tc.result.length > 0) return tc.result as Record<string, unknown>[];
  }
  return undefined;
}

export const MessageBubble = memo(function MessageBubble({
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
            <MessageActions content={content} csvData={extractCsvData(toolCalls)} />
          </div>
        )}
      </div>
    </div>
  );
});
