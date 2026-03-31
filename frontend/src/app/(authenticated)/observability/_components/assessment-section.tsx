"use client";

import { Shield } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { StatTile } from "@/components/stat-tile";
import { Skeleton } from "@/components/ui/skeleton";
import { useAssessmentLatest, useAssessmentHistory } from "@/hooks/use-observability";
import { formatPercent, formatMicroCurrency, formatRelativeTime, formatDate } from "@/lib/format";

function passRateAccent(rate: number): "gain" | "warn" | "loss" {
  if (rate >= 0.8) return "gain";
  if (rate >= 0.5) return "warn";
  return "loss";
}

export function AssessmentSection({ isAdmin }: { isAdmin: boolean }) {
  const { data: latest, isLoading } = useAssessmentLatest();
  const { data: history } = useAssessmentHistory(isAdmin);

  return (
    <section aria-label="AI Quality">
      <SectionHeading>AI Quality</SectionHeading>

      {isLoading ? (
        <Skeleton className="h-[72px] w-full rounded-lg bg-card2" />
      ) : !latest ? (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
          <Shield className="h-8 w-8 text-subtle" />
          <p className="text-sm text-muted-foreground">
            Quality benchmarks coming soon — we regularly test AI accuracy against curated datasets.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile
              label="Pass Rate"
              value={formatPercent(latest.pass_rate)}
              accentColor={passRateAccent(latest.pass_rate)}
            />
            <StatTile
              label="Queries Tested"
              value={String(latest.total_queries)}
              sub={<span className="text-[10px] text-muted-foreground">{latest.passed_queries} passed</span>}
              accentColor="cyan"
            />
            <StatTile
              label="Test Cost"
              value={formatMicroCurrency(latest.total_cost_usd)}
              accentColor="cyan"
            />
            <StatTile
              label="Last Tested"
              value={formatRelativeTime(latest.completed_at)}
              sub={<span className="text-[10px] text-muted-foreground">{latest.trigger}</span>}
              accentColor="cyan"
            />
          </div>

          <p className="text-[11px] text-subtle">
            We regularly test AI quality against {latest.total_queries} benchmark queries to ensure accurate recommendations.
          </p>

          {/* Admin-only: assessment history */}
          {isAdmin && history?.items && history.items.length > 0 && (
            <div>
              <h3 className="mb-2 text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">
                Assessment History
              </h3>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-card2">
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Date</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Trigger</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Pass Rate</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Queries</th>
                      <th className="px-3 py-2 text-left text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.items.map((run) => (
                      <tr key={run.id} className="border-t border-border/40">
                        <td className="px-3 py-2 text-xs text-muted-foreground">{formatDate(run.completed_at)}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">{run.trigger}</td>
                        <td className="px-3 py-2 font-mono text-xs text-foreground">{formatPercent(run.pass_rate)}</td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{run.total_queries}</td>
                        <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{formatMicroCurrency(run.total_cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
