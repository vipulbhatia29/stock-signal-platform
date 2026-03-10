"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SignalBadge } from "@/components/signal-badge";
import { formatNumber } from "@/lib/format";
import {
  signalToSentiment,
  SENTIMENT_BORDER_CLASSES,
} from "@/lib/signals";
import { cn } from "@/lib/utils";
import type { SignalResponse } from "@/types/api";

interface SignalCardsProps {
  signals: SignalResponse | undefined;
  isLoading: boolean;
}

export function SignalCards({ signals, isLoading }: SignalCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-16" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-20" />
              <Skeleton className="mt-2 h-5 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!signals) return null;

  const cards = [
    {
      title: "RSI",
      value: formatNumber(signals.rsi.value, 1),
      signal: signals.rsi.signal,
      type: "rsi" as const,
      subtitle: signals.rsi.value !== null ? `${formatNumber(signals.rsi.value, 0)} / 100` : null,
    },
    {
      title: "MACD",
      value: formatNumber(signals.macd.histogram, 4),
      signal: signals.macd.signal,
      type: "macd" as const,
      subtitle: signals.macd.value !== null ? `Line: ${formatNumber(signals.macd.value, 4)}` : null,
    },
    {
      title: "SMA",
      value:
        signals.sma.sma_50 !== null
          ? `50: ${formatNumber(signals.sma.sma_50, 0)}`
          : "—",
      signal: signals.sma.signal,
      type: "sma" as const,
      subtitle: signals.sma.sma_200 !== null ? `200: ${formatNumber(signals.sma.sma_200, 0)}` : null,
    },
    {
      title: "Bollinger",
      value:
        signals.bollinger.upper !== null
          ? `${formatNumber(signals.bollinger.lower, 0)}–${formatNumber(signals.bollinger.upper, 0)}`
          : "—",
      signal: signals.bollinger.position,
      type: "bollinger" as const,
      subtitle: null,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => {
        const sentiment = signalToSentiment(card.signal, card.type);
        return (
          <Card
            key={card.title}
            className={cn(
              "border-l-4",
              SENTIMENT_BORDER_CLASSES[sentiment]
            )}
          >
            <CardHeader className="pb-1">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                {card.title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xl font-semibold tabular-nums">
                {card.value}
              </p>
              {card.subtitle && (
                <p className="text-xs text-muted-foreground">
                  {card.subtitle}
                </p>
              )}
              <div className="mt-2">
                <SignalBadge signal={card.signal} type={card.type} />
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
