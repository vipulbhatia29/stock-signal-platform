"use client";

import { useState } from "react";
import { Trash2, AlertTriangle } from "lucide-react";
import { useClearCache, useClearAllCaches } from "@/hooks/use-admin-pipelines";

const CACHE_PATTERNS = [
  { label: "Convergence", value: "convergence:*" },
  { label: "Forecasts", value: "forecast:*" },
  { label: "Sentiment", value: "sentiment:*" },
  { label: "BL Forecasts", value: "bl-forecast:*" },
  { label: "Monte Carlo", value: "monte-carlo:*" },
  { label: "CVaR", value: "cvar:*" },
  { label: "Sector Forecasts", value: "sector-forecast:*" },
  { label: "Screener", value: "app:screener:*" },
  { label: "Sectors", value: "app:sectors:*" },
  { label: "Signals", value: "app:signals:*" },
];

export function CacheControls() {
  const [selectedPattern, setSelectedPattern] = useState("");
  const [showConfirmAll, setShowConfirmAll] = useState(false);
  const [lastResult, setLastResult] = useState<string | null>(null);

  const clearCache = useClearCache();
  const clearAll = useClearAllCaches();

  const handleClear = () => {
    if (!selectedPattern) return;
    clearCache.mutate(
      { pattern: selectedPattern },
      {
        onSuccess: (data) => {
          setLastResult(`Cleared ${data.keys_deleted} keys for ${selectedPattern}`);
          setSelectedPattern("");
        },
      }
    );
  };

  const handleClearAll = () => {
    clearAll.mutate(undefined, {
      onSuccess: (data) => {
        setLastResult(`Cleared ${data.keys_deleted} keys across all patterns`);
        setShowConfirmAll(false);
      },
    });
  };

  return (
    <div className="rounded-lg border border-border bg-card2 px-4 py-3 space-y-3">
      <h4 className="text-[9px] uppercase tracking-wider text-subtle">Cache Controls</h4>

      {/* Pattern clear */}
      <div className="flex items-center gap-2">
        <select
          value={selectedPattern}
          onChange={(e) => setSelectedPattern(e.target.value)}
          className="flex-1 bg-background border border-border rounded-md px-3 py-1.5 text-sm text-foreground"
        >
          <option value="">Select pattern...</option>
          {CACHE_PATTERNS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label} ({p.value})
            </option>
          ))}
        </select>
        <button
          onClick={handleClear}
          disabled={!selectedPattern || clearCache.isPending}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-loss/10 text-loss hover:bg-loss/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Trash2 className="h-3 w-3" />
          Clear
        </button>
      </div>

      {/* Clear all with confirmation */}
      {!showConfirmAll ? (
        <button
          onClick={() => setShowConfirmAll(true)}
          className="flex items-center gap-1.5 text-xs text-subtle hover:text-loss transition-colors"
        >
          <AlertTriangle className="h-3 w-3" />
          Clear all caches
        </button>
      ) : (
        <div className="flex items-center gap-2 p-2 rounded-md bg-loss/5 border border-loss/20">
          <AlertTriangle className="h-4 w-4 text-loss flex-shrink-0" />
          <span className="text-xs text-loss">Clear ALL cached data?</span>
          <div className="ml-auto flex gap-2">
            <button
              onClick={() => setShowConfirmAll(false)}
              className="px-2 py-1 text-xs text-subtle hover:text-foreground transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleClearAll}
              disabled={clearAll.isPending}
              className="px-2 py-1 text-xs font-medium text-loss bg-loss/10 rounded hover:bg-loss/20 transition-colors"
            >
              Confirm
            </button>
          </div>
        </div>
      )}

      {/* Result message */}
      {lastResult && <div className="text-[11px] text-chart2">{lastResult}</div>}
    </div>
  );
}
