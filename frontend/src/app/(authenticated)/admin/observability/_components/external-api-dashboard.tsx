"use client";

import { useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminExternals } from "@/hooks/use-admin-observability";
import { ProviderRow } from "./provider-row";

/** Known providers from the external_api subsystem. */
const KNOWN_PROVIDERS = ["yfinance", "openai", "anthropic", "groq", "alphavantage"];

const WINDOW_OPTIONS = [
  { label: "1h", value: 60 },
  { label: "4h", value: 240 },
  { label: "24h", value: 1440 },
] as const;

type WindowMin = (typeof WINDOW_OPTIONS)[number]["value"];

function ProviderLoader({
  provider,
  windowMin,
}: {
  provider: string;
  windowMin: WindowMin;
}) {
  const { data, isLoading, error } = useAdminExternals(provider, windowMin);

  if (isLoading) {
    return <Skeleton className="h-14 w-full rounded-lg bg-card2" />;
  }

  if (error || !data?.result) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-400">
        Failed to load {provider} stats. Retrying...
      </div>
    );
  }

  return <ProviderRow data={data.result} />;
}

export function ExternalApiDashboard() {
  const [windowMin, setWindowMin] = useState<WindowMin>(60);

  return (
    <section aria-label="External API Dashboard" className="space-y-3">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">External APIs</h2>
        <div className="flex gap-1.5">
          {WINDOW_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setWindowMin(opt.value)}
              className={
                windowMin === opt.value
                  ? "rounded-md bg-card2 px-2.5 py-1 text-[10px] font-medium text-foreground"
                  : "rounded-md px-2.5 py-1 text-[10px] font-medium text-subtle hover:text-muted-foreground"
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Column headers */}
      <div className="flex items-center gap-4 px-4 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        <span className="w-5" />
        <span className="w-32">Provider</span>
        <span className="w-24">Calls</span>
        <span className="w-24">Success</span>
        <span className="w-28">p95 Latency</span>
        <span className="w-24">Cost</span>
        <span className="w-20">Rate Limit</span>
      </div>

      {/* Provider rows */}
      <div className="space-y-2">
        {KNOWN_PROVIDERS.map((provider) => (
          <ProviderLoader key={provider} provider={provider} windowMin={windowMin} />
        ))}
      </div>
    </section>
  );
}
