"use client";

import { useState, useMemo } from "react";
import { Bell, ChevronDown, ChevronRight } from "lucide-react";
import { AlertTile } from "@/components/alert-tile";
import { Skeleton } from "@/components/ui/skeleton";
import { useAlerts } from "@/hooks/use-alerts";
import { useWatchlist, usePositions } from "@/hooks/use-stocks";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

type Severity = "critical" | "high" | "medium" | "low";

interface DerivedAlert {
  id: string;
  title: string;
  message: string;
  ticker?: string;
  severity: Severity;
  timestamp?: string;
}

/** Map backend severity to AlertTile severity. */
function mapSeverity(sev: string): Severity {
  if (sev === "critical") return "critical";
  if (sev === "warning") return "high";
  if (sev === "info") return "medium";
  return "low";
}

/** Generate alerts from watchlist + portfolio data — no Celery required. */
function useDerivedAlerts(): DerivedAlert[] {
  const { data: watchlist } = useWatchlist();
  const { data: positions } = usePositions();

  return useMemo(() => {
    const alerts: DerivedAlert[] = [];
    const heldTickers = new Set(positions?.map((p) => p.ticker) ?? []);

    if (!watchlist) return alerts;

    for (const stock of watchlist) {
      // 1. Big daily movers (>5% either direction)
      if (stock.change_pct != null && Math.abs(stock.change_pct) >= 5) {
        const direction = stock.change_pct > 0 ? "surged" : "dropped";
        const isHeld = heldTickers.has(stock.ticker);
        alerts.push({
          id: `move-${stock.ticker}`,
          title: `${stock.ticker} ${direction} ${Math.abs(stock.change_pct).toFixed(1)}%`,
          message: isHeld
            ? `Your holding moved significantly today — review position`
            : `Large move detected on watchlist stock`,
          ticker: stock.ticker,
          severity: isHeld ? "high" : "medium",
        });
      }

      // 2. Score crossed into AVOID territory (< 4) for held stocks
      if (
        heldTickers.has(stock.ticker) &&
        stock.composite_score != null &&
        stock.composite_score < 4
      ) {
        alerts.push({
          id: `score-low-${stock.ticker}`,
          title: `${stock.ticker} score below 4.0`,
          message: `Composite score ${stock.composite_score.toFixed(1)}/10 — consider reviewing position`,
          ticker: stock.ticker,
          severity: "high",
        });
      }

      // 3. Score crossed into BUY territory (>= 8) — opportunity
      if (
        stock.composite_score != null &&
        stock.composite_score >= 8 &&
        !heldTickers.has(stock.ticker)
      ) {
        alerts.push({
          id: `buy-signal-${stock.ticker}`,
          title: `BUY signal: ${stock.ticker}`,
          message: `Score ${stock.composite_score.toFixed(1)}/10 — strong across indicators`,
          ticker: stock.ticker,
          severity: "medium",
        });
      }

      // 4. Stocks with no signal data yet (pending ingest)
      if (stock.composite_score == null) {
        alerts.push({
          id: `pending-${stock.ticker}`,
          title: `${stock.ticker} awaiting data`,
          message: `Recently added — signals will appear after pipeline completes`,
          ticker: stock.ticker,
          severity: "low",
        });
      }
    }

    // Sort: critical > high > medium > low
    const rank: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    alerts.sort((a, b) => rank[a.severity] - rank[b.severity]);

    return alerts;
  }, [watchlist, positions]);
}

/** Collapsible alerts bar — merges backend alerts + real-time derived alerts. */
export function AlertsZone() {
  const [expanded, setExpanded] = useState(false);
  const { data, isLoading, isError } = useAlerts();
  const derivedAlerts = useDerivedAlerts();

  // Merge backend alerts (if any) with derived alerts
  const backendAlerts: DerivedAlert[] = useMemo(() => {
    if (!data?.alerts?.length) return [];
    return data.alerts.slice(0, 6).map((a) => ({
      id: a.id,
      title: a.title,
      message: a.message,
      ticker: a.ticker ?? undefined,
      severity: mapSeverity(a.severity),
      timestamp: formatRelativeTime(a.created_at),
    }));
  }, [data]);

  const allAlerts = useMemo(() => {
    // Deduplicate by ticker+type — derived alerts fill gaps when backend is empty
    const seen = new Set(backendAlerts.map((a) => `${a.ticker}-${a.title}`));
    const merged = [...backendAlerts];
    for (const d of derivedAlerts) {
      if (!seen.has(`${d.ticker}-${d.title}`)) {
        merged.push(d);
      }
    }
    return merged.slice(0, 10);
  }, [backendAlerts, derivedAlerts]);

  const unreadCount = data?.unreadCount ?? 0;
  const totalCount = allAlerts.length;
  const hasUrgent = allAlerts.some((a) => a.severity === "critical" || a.severity === "high");

  if (isError && derivedAlerts.length === 0) return null;

  return (
    <section aria-label="Alerts">
      <button
        onClick={() => setExpanded((v) => !v)}
        className={cn(
          "flex w-full items-center gap-2 rounded-lg border bg-card px-4 py-2.5 text-left transition-colors hover:bg-hov",
          hasUrgent ? "border-loss/30" : "border-border",
        )}
      >
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
        <Bell className={cn("h-3.5 w-3.5", hasUrgent ? "text-loss" : "text-muted-foreground")} />
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Alerts
        </span>
        {(unreadCount > 0 || totalCount > 0) && (
          <span className={cn(
            "rounded-full px-1.5 py-0.5 text-[9px] font-bold",
            hasUrgent ? "bg-loss/10 text-loss" : "bg-primary/10 text-primary",
          )}>
            {totalCount}
          </span>
        )}
        {totalCount === 0 && !isLoading && (
          <span className="text-[10px] text-muted-foreground">— all clear</span>
        )}
      </button>

      {expanded && (
        <div className="mt-2">
          {isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-14 w-full rounded-lg bg-card2" />
              ))}
            </div>
          ) : totalCount === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">No alerts at this time</p>
          ) : (
            <div className="space-y-2">
              {allAlerts.map((alert) => (
                <AlertTile
                  key={alert.id}
                  title={alert.title}
                  ticker={alert.ticker}
                  severity={alert.severity}
                  message={alert.message}
                  timestamp={alert.timestamp}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
