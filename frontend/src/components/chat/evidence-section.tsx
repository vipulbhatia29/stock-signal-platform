"use client";

import { useState } from "react";
import type { EvidenceItem } from "@/hooks/chat-reducer";

interface EvidenceSectionProps {
  evidence: EvidenceItem[];
}

export function EvidenceSection({ evidence }: EvidenceSectionProps) {
  const [isOpen, setIsOpen] = useState(false);

  if (!evidence.length) return null;

  return (
    <div className="mt-2">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="text-xs font-medium text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] transition-colors"
      >
        {isOpen ? "▾ Hide Evidence" : "▸ Show Evidence"} ({evidence.length})
      </button>
      {isOpen && (
        <div className="mt-2 space-y-1.5 rounded border border-[var(--color-border)] bg-[var(--color-surface-raised)] p-2">
          {evidence.map((item, i) => (
            <div key={i} className="flex gap-2 text-xs">
              <span className="shrink-0 font-mono text-[var(--color-muted-foreground)]">
                [{item.source_tool}]
              </span>
              <span className="text-[var(--color-foreground)]">
                {item.claim}
                {item.value && (
                  <span className="ml-1 text-[var(--color-muted-foreground)]">
                    = {item.value}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
