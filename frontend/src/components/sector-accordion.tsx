"use client";

import { ChevronDownIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ScoreBar } from "@/components/score-bar";
import { ChangeIndicator } from "@/components/change-indicator";
import type { SectorSummary } from "@/types/api";

interface SectorAccordionProps {
  sector: SectorSummary;
  isOpen: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  badge?: React.ReactNode;
}

export function SectorAccordion({
  sector,
  isOpen,
  onToggle,
  children,
  badge,
}: SectorAccordionProps) {
  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-4 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span className="text-sm font-medium text-foreground truncate">
            {sector.sector}
          </span>
          <span className="text-xs text-subtle tabular-nums">
            {sector.stock_count} stocks
          </span>
          {badge}
        </div>

        <div className="flex items-center gap-4 shrink-0">
          {sector.avg_composite_score !== null && (
            <div className="flex items-center gap-2">
              <ScoreBar
                score={sector.avg_composite_score}
                className="w-16"
              />
              <span className="text-xs font-mono tabular-nums text-subtle w-8 text-right">
                {sector.avg_composite_score.toFixed(1)}
              </span>
            </div>
          )}

          <ChangeIndicator
            value={sector.avg_return_pct}
            size="sm"
            showIcon={false}
          />

          {sector.your_stock_count > 0 && (
            <span className="text-xs text-primary tabular-nums">
              {sector.your_stock_count} yours
            </span>
          )}

          {sector.allocation_pct !== null && (
            <span className="text-xs font-mono tabular-nums text-subtle w-12 text-right">
              {sector.allocation_pct.toFixed(1)}%
            </span>
          )}

          <ChevronDownIcon
            className={cn(
              "size-4 text-subtle transition-transform duration-200",
              isOpen && "rotate-180"
            )}
          />
        </div>
      </button>

      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
            className="overflow-hidden"
          >
            <div className="border-t border-border px-4 py-4 space-y-4">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
