"use client";

import { useState } from "react";
import { XIcon, PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { STORAGE_KEYS } from "@/lib/storage-keys";

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
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === "undefined") return true;
    return localStorage.getItem(STORAGE_KEYS.ONBOARDING_DISMISSED) === "true";
  });

  if (dismissed) return null;

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem(STORAGE_KEYS.ONBOARDING_DISMISSED, "true");
  };

  return (
    <div className="relative rounded-lg border border-[var(--color-accent)]/30 bg-[var(--color-accent)]/5 p-4 mb-6">
      <button
        onClick={handleDismiss}
        className="absolute right-3 top-3 text-[var(--color-muted-foreground)] hover:text-[var(--color-foreground)] transition-colors"
        aria-label="Dismiss"
      >
        <XIcon className="size-4" />
      </button>
      <h3 className="text-sm font-semibold text-[var(--color-foreground)] mb-1">
        Welcome to Stock Signal Platform
      </h3>
      <p className="text-sm text-[var(--color-muted-foreground)] mb-3">
        Get started by adding stocks to your watchlist. We&apos;ll fetch prices,
        compute signals, and generate recommendations.
      </p>
      <div className="flex flex-wrap gap-2">
        {SUGGESTED_TICKERS.map(({ ticker, name }) => (
          <Button
            key={ticker}
            variant="outline"
            size="sm"
            onClick={() => onAddTicker(ticker)}
            disabled={addingTickers.has(ticker)}
            className="gap-1.5"
          >
            <PlusIcon className="size-3" />
            {ticker}
            <span className="text-[var(--color-muted-foreground)] font-normal">
              {name}
            </span>
          </Button>
        ))}
      </div>
    </div>
  );
}
