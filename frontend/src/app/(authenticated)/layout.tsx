"use client";

import { useState, useCallback } from "react";
import { SidebarNav } from "@/components/sidebar-nav";
import { Topbar } from "@/components/topbar";
import { ChatPanel } from "@/components/chat-panel";
import { useAddToWatchlist, useIngestTicker, useWatchlist } from "@/hooks/use-stocks";
import { toast } from "sonner";

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [chatIsOpen, setChatIsOpen] = useState(true); // open by default
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
        <Topbar
          chatIsOpen={chatIsOpen}
          onToggleChat={() => setChatIsOpen((v) => !v)}
          onAddTicker={handleAddTicker}
        />
        <main className="flex-1 overflow-y-auto">
          <div className="px-4 py-6 animate-fade-in">{children}</div>
        </main>
      </div>

      <ChatPanel
        isOpen={chatIsOpen}
        onClose={() => setChatIsOpen(false)}
      />
    </div>
  );
}
