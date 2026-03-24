"use client";

import { useState } from "react";
import { XIcon, PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { useMounted } from "@/hooks/use-mounted";

const SUGGESTED_TICKERS = [
  { ticker: "AAPL", name: "Apple" },
  { ticker: "MSFT", name: "Microsoft" },
  { ticker: "GOOGL", name: "Alphabet" },
  { ticker: "TSLA", name: "Tesla" },
  { ticker: "NVDA", name: "NVIDIA" },
];

interface WelcomeBannerProps {
  onAddTicker: (ticker: string) => void;
  addingTickers: Set<string>;
}

export function WelcomeBanner({ onAddTicker, addingTickers }: WelcomeBannerProps) {
  const mounted = useMounted();
  const [dismissed, setDismissed] = useState(false);

  // Don't render on server or before mount (avoids hydration mismatch).
  // After mount, check localStorage to decide visibility.
  if (!mounted) return null;
  if (dismissed) return null;
  if (localStorage.getItem(STORAGE_KEYS.ONBOARDING_DISMISSED) === "true") return null;

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem(STORAGE_KEYS.ONBOARDING_DISMISSED, "true");
  };

  return (
    <div className="relative rounded-lg border border-[var(--bhi)] bg-gradient-to-r from-[var(--cdim)] to-transparent p-5 mb-2">
      <button
        onClick={handleDismiss}
        className="absolute right-3 top-3 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-[var(--hov)] transition-colors"
        aria-label="Dismiss"
      >
        <XIcon className="size-4" />
      </button>
      <div className="flex items-start gap-3">
        <div className="mt-0.5 h-8 w-8 rounded-lg bg-[var(--cdim)] flex items-center justify-center flex-shrink-0">
          <PlusIcon className="size-4 text-cyan" />
        </div>
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-foreground">
            Build your watchlist
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5 mb-3">
            Add stocks to track signals, compute scores, and get AI-powered recommendations.
          </p>
          <div className="flex flex-wrap gap-2">
            {SUGGESTED_TICKERS.map(({ ticker, name }) => (
              <Button
                key={ticker}
                variant="outline"
                size="sm"
                onClick={() => onAddTicker(ticker)}
                disabled={addingTickers.has(ticker)}
                className="gap-1.5 h-7 text-xs"
              >
                <PlusIcon className="size-3" />
                <span className="font-mono font-semibold">{ticker}</span>
                <span className="text-muted-foreground font-normal">
                  {name}
                </span>
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
