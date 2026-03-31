"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageTransition } from "@/components/motion-primitives";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useCommandCenter } from "@/hooks/use-command-center";
import { LastRefreshed } from "@/components/command-center/last-refreshed";
import { DegradedBadge } from "@/components/command-center/degraded-badge";
import { SystemHealthPanel } from "@/components/command-center/system-health-panel";
import { ApiTrafficPanel } from "@/components/command-center/api-traffic-panel";
import { LlmOperationsPanel } from "@/components/command-center/llm-operations-panel";
import { PipelinePanel } from "@/components/command-center/pipeline-panel";

function LoadingSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-[280px] w-full rounded-xl bg-card2" />
      ))}
    </div>
  );
}

export default function CommandCenterPage() {
  const router = useRouter();
  const { isAdmin, isLoading: userLoading } = useCurrentUser();
  const { data, isLoading, error } = useCommandCenter();

  useEffect(() => {
    if (!userLoading && !isAdmin) {
      router.replace("/dashboard");
    }
  }, [userLoading, isAdmin, router]);

  if (userLoading || (!isAdmin && !userLoading)) {
    return null;
  }

  return (
    <PageTransition className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Command Center
          </h1>
          <p className="text-sm text-subtle mt-1">
            Platform operations overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data?.meta.degraded_zones && (
            <DegradedBadge zones={data.meta.degraded_zones} />
          )}
          <LastRefreshed timestamp={data?.timestamp} />
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-400">
          Failed to load command center data. Retrying...
        </div>
      )}

      {/* Zone grid */}
      {isLoading ? (
        <LoadingSkeleton />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <SystemHealthPanel data={data?.system_health ?? null} />
          <ApiTrafficPanel data={data?.api_traffic ?? null} />
          <LlmOperationsPanel data={data?.llm_operations ?? null} />
          <PipelinePanel data={data?.pipeline ?? null} />
        </div>
      )}
    </PageTransition>
  );
}
