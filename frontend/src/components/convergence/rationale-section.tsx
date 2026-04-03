"use client";

import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronUp } from "lucide-react";

interface RationaleSectionProps {
  rationale: string | null;
  className?: string;
  /** Start expanded (default: collapsed). */
  defaultOpen?: boolean;
}

/** Expandable rationale text for convergence explanation. */
export function RationaleSection({
  rationale,
  className,
  defaultOpen = false,
}: RationaleSectionProps) {
  const contentId = `rationale-${useId()}`;
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (!rationale) return null;

  const Icon = isOpen ? ChevronUp : ChevronDown;

  return (
    <div className={cn("rounded-lg border border-border bg-card/50", className)}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between px-3 py-2",
          "text-sm font-medium text-muted-foreground",
          "hover:text-foreground transition-colors",
        )}
        aria-expanded={isOpen}
        aria-controls={contentId}
      >
        <span>Signal rationale</span>
        <Icon className="h-4 w-4" aria-hidden="true" />
      </button>
      {isOpen && (
        <div
          id={contentId}
          className="px-3 pb-3 text-sm leading-relaxed text-muted-foreground"
        >
          {rationale}
        </div>
      )}
    </div>
  );
}
