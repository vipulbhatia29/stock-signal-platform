"use client";

import { useState, useCallback } from "react";
import { SidebarNav } from "@/components/sidebar-nav";
import { Topbar } from "@/components/topbar";
import { ChatPanel } from "@/components/chat-panel";
import { ArtifactBar } from "@/components/chat/artifact-bar";
import { ChatProvider, useChat } from "@/contexts/chat-context";
import { useAddToWatchlist, useIngestTicker, useWatchlist } from "@/hooks/use-stocks";
import { toast } from "sonner";

function AuthenticatedShell({ children }: { children: React.ReactNode }) {
  const { chatOpen, setChatOpen } = useChat();
  const [artifact, setArtifact] = useState<{
    tool: string;
    params: Record<string, unknown>;
    data: unknown;
  } | null>(null);
  const { data: watchlist } = useWatchlist();
  const addToWatchlist = useAddToWatchlist();
  const ingestTicker = useIngestTicker();

  const handleAddTicker = useCallback(
    async (ticker: string) => {
      const isInWatchlist = watchlist?.some((w) => w.ticker === ticker);
      if (isInWatchlist) {
        toast.info(`${ticker} is already in your watchlist`);
        return;
      }
      toast.loading(`Fetching data for ${ticker}...`, { id: `ingest-${ticker}` });
      try {
        await ingestTicker.mutateAsync(ticker);
        toast.success(`${ticker} data loaded`, { id: `ingest-${ticker}` });
        addToWatchlist.mutate(ticker);
      } catch {
        toast.error(`Failed to fetch data for ${ticker}`, { id: `ingest-${ticker}` });
      }
    },
    [watchlist, ingestTicker, addToWatchlist]
  );

  return (
    <div className="flex overflow-hidden" style={{ height: "100vh" }}>
      <SidebarNav />

      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar onAddTicker={handleAddTicker} />
        {artifact && (
          <ArtifactBar artifact={artifact} onDismiss={() => setArtifact(null)} />
        )}
        <main className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="px-4 py-6 animate-fade-in">{children}</div>
        </main>
      </div>

      <ChatPanel
        isOpen={chatOpen}
        onClose={() => setChatOpen(false)}
        onArtifact={setArtifact}
      />
    </div>
  );
}

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ChatProvider>
      <AuthenticatedShell>{children}</AuthenticatedShell>
    </ChatProvider>
  );
}
