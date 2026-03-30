"use client";

import { cn } from "@/lib/utils";

export const SECTION_IDS = [
  { id: "sec-price", label: "Price" },
  { id: "sec-signals", label: "Signals" },
  { id: "sec-history", label: "History" },
  { id: "sec-benchmark", label: "Benchmark" },
  { id: "sec-risk", label: "Risk" },
  { id: "sec-fundamentals", label: "Fundamentals" },
  { id: "sec-forecast", label: "Forecast" },
  { id: "sec-intelligence", label: "Intelligence" },
  { id: "sec-news", label: "News" },
  { id: "sec-dividends", label: "Dividends" },
] as const;

export function SectionNav() {
  function handleClick(id: string) {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  return (
    <nav className="sticky top-0 z-20 -mx-4 overflow-x-auto bg-navy-900/95 backdrop-blur-sm px-4 py-2 border-b border-border">
      <div className="flex gap-1">
        {SECTION_IDS.map((section) => (
          <button
            key={section.id}
            type="button"
            onClick={() => handleClick(section.id)}
            className={cn(
              "shrink-0 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
              "text-muted-foreground hover:text-foreground hover:bg-muted/30"
            )}
          >
            {section.label}
          </button>
        ))}
      </div>
    </nav>
  );
}
