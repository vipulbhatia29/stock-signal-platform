"use client";

import { XIcon } from "lucide-react";
import { PortfolioValueChart } from "@/components/portfolio-value-chart";
import { usePortfolioSummary, usePortfolioHistory } from "@/hooks/use-stocks";
import { formatCurrency } from "@/lib/format";

interface PortfolioDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  chatIsOpen: boolean;
}

export function PortfolioDrawer({ isOpen, onClose, chatIsOpen }: PortfolioDrawerProps) {
  const { data: summary } = usePortfolioSummary();
  const { data: snapshots = [] } = usePortfolioHistory(365);

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40"
          style={{
            background: "rgba(7,13,24,.7)",
            backdropFilter: "blur(3px)",
          }}
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className="fixed bottom-0 z-50 bg-card overflow-auto"
        style={{
          left: "var(--sw)",
          right: chatIsOpen ? "var(--cp)" : 0,
          height: isOpen ? "62vh" : 0,
          overflow: isOpen ? "auto" : "hidden",
          borderTop: "1px solid var(--bhi)",
          borderRadius: "14px 14px 0 0",
          boxShadow: "0 -20px 60px rgba(56,189,248,.08)",
          transition:
            "height 0.3s cubic-bezier(.22,.68,0,1.1), right 0.25s cubic-bezier(.22,.68,0,1.1)",
        }}
      >
        <div className="px-7 pb-7 pt-5">
          {/* Drag handle */}
          <div
            className="w-9 h-1 rounded-full bg-border mx-auto mb-5 cursor-pointer"
            onClick={onClose}
          />

          {/* Close button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-5 w-7 h-7 rounded-[6px] bg-hov border border-border text-muted-foreground hover:text-foreground flex items-center justify-center"
            aria-label="Close portfolio chart"
          >
            <XIcon size={13} />
          </button>

          {/* Header */}
          <div className="flex items-baseline gap-3 mb-4">
            <div className="font-mono text-[30px] font-bold tracking-tight text-foreground">
              {summary ? formatCurrency(summary.total_value) : "—"}
            </div>
            <div className="text-[11px] text-subtle">Portfolio Value</div>
          </div>

          {/* Full-width chart */}
          <PortfolioValueChart snapshots={snapshots} />

          {/* Stats row */}
          {summary && (
            <div className="grid grid-cols-4 gap-2.5 mt-5">
              {[
                { label: "Unrealized P&L", value: formatCurrency(summary.unrealized_pnl) },
                { label: "P&L %", value: `${summary.unrealized_pnl_pct.toFixed(2)}%` },
                { label: "Positions", value: String(summary.position_count) },
                { label: "Cost Basis", value: formatCurrency(summary.total_cost_basis) },
              ].map((s) => (
                <div key={s.label} className="bg-card2 rounded-lg p-[10px_13px]">
                  <div className="text-[9px] uppercase tracking-[0.08em] text-subtle mb-1">
                    {s.label}
                  </div>
                  <div className="font-mono text-[16px] font-semibold text-foreground">
                    {s.value}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
