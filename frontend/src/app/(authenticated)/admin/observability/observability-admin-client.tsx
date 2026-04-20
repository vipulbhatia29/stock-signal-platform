"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageTransition } from "@/components/motion-primitives";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useAdminKpis } from "@/hooks/use-admin-observability";
import { HealthStrip } from "./_components/health-strip";

type TabKey = "overview" | "apis-cost" | "infrastructure" | "trace-explorer";

export default function ObservabilityAdminClient() {
  const router = useRouter();
  const { isAdmin, isLoading: userLoading } = useCurrentUser();
  const { data: kpisEnvelope, isLoading: kpisLoading, error: kpisError } = useAdminKpis();

  const [activeTab, setActiveTab] = useState<TabKey>("overview");
  const [pendingTraceId, setPendingTraceId] = useState<string | null>(null);

  useEffect(() => {
    if (!userLoading && !isAdmin) {
      router.replace("/dashboard");
    }
  }, [userLoading, isAdmin, router]);

  if (userLoading || (!isAdmin && !userLoading)) {
    return null;
  }

  // Used by Zone 2/Zone 3 components to navigate to the Trace Explorer tab.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const openTrace = (traceId: string) => {
    setPendingTraceId(traceId);
    setActiveTab("trace-explorer");
  };

  return (
    <PageTransition className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Observability
          </h1>
          <p className="text-sm text-subtle mt-1">
            Platform health and diagnostics
          </p>
        </div>
      </div>

      {/* Zone 1: Health Strip — always visible */}
      <HealthStrip
        data={kpisEnvelope?.result}
        isLoading={kpisLoading}
        error={kpisError}
      />

      {/* Tab navigation */}
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as TabKey)}
      >
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="apis-cost">APIs & Cost</TabsTrigger>
          <TabsTrigger value="infrastructure">Infrastructure</TabsTrigger>
          <TabsTrigger value="trace-explorer">Trace Explorer</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Zone 2 (Error Stream) and Zone 3 (Anomaly Findings) — coming soon.
          </div>
        </TabsContent>

        <TabsContent value="apis-cost" className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Zone 5 (External API) and Zone 6 (Cost Breakdown) — coming soon.
          </div>
        </TabsContent>

        <TabsContent value="infrastructure" className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Zone 7 (Pipeline Health) and Zone 8 (DQ Scanner) — coming soon.
          </div>
        </TabsContent>

        <TabsContent value="trace-explorer" className="mt-4 space-y-4">
          <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
            Zone 4 (Trace Explorer) — coming soon.
            {pendingTraceId && (
              <p className="mt-2">
                Pending trace: <code className="text-foreground">{pendingTraceId}</code>
              </p>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </PageTransition>
  );
}

export { type TabKey };
export type OpenTraceFn = (traceId: string) => void;
