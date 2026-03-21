"use client";

import { useState } from "react";
import { patch } from "@/lib/api";

interface FeedbackButtonsProps {
  sessionId: string;
  messageId: string;
}

export function FeedbackButtons({ sessionId, messageId }: FeedbackButtonsProps) {
  const [selected, setSelected] = useState<"up" | "down" | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleFeedback = async (feedback: "up" | "down") => {
    if (isSubmitting || selected === feedback) return;
    setIsSubmitting(true);
    try {
      await patch(
        `/chat/sessions/${sessionId}/messages/${messageId}/feedback`,
        { feedback }
      );
      setSelected(feedback);
    } catch {
      // Silently fail — feedback is non-critical
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex gap-1 mt-1">
      <button
        onClick={() => handleFeedback("up")}
        disabled={isSubmitting}
        className={`rounded p-1 text-xs transition-colors ${
          selected === "up"
            ? "text-[var(--color-gain)] bg-[var(--color-gain)]/10"
            : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
        }`}
        aria-label="Thumbs up"
      >
        👍
      </button>
      <button
        onClick={() => handleFeedback("down")}
        disabled={isSubmitting}
        className={`rounded p-1 text-xs transition-colors ${
          selected === "down"
            ? "text-[var(--color-loss)] bg-[var(--color-loss)]/10"
            : "text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)]"
        }`}
        aria-label="Thumbs down"
      >
        👎
      </button>
    </div>
  );
}
