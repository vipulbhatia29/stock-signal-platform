"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { SignalBadge } from "@/components/signal-badge";
import { formatNumber } from "@/lib/format";
import {
  signalToSentiment,
  SENTIMENT_BORDER_CLASSES,
} from "@/lib/signals";
import { cn } from "@/lib/utils";
import { StalenessBadge } from "@/components/staleness-badge";
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

  const rsiDesc = signals.rsi.value !== null
    ? signals.rsi.value < 30 ? "Below 30 — potential oversold bounce"
    : signals.rsi.value > 70 ? "Above 70 — overbought, watch for pullback"
    : "Between 30-70 — balanced momentum"
    : null;

  const macdDesc = signals.macd.signal === "BULLISH"
    ? "Histogram positive — upward pressure"
    : signals.macd.signal === "BEARISH"
    ? "Histogram negative — downward pressure"
    : null;

  const smaDesc = signals.sma.signal === "GOLDEN_CROSS" ? "50-day crossed above 200-day SMA"
    : signals.sma.signal === "DEATH_CROSS" ? "50-day crossed below 200-day SMA"
    : signals.sma.signal === "ABOVE_200" ? "Price above 200-day SMA"
    : signals.sma.signal === "BELOW_200" ? "Price below 200-day SMA"
    : null;

  const bbDesc = signals.bollinger.position === "UPPER" ? "Near upper band — potential resistance"
    : signals.bollinger.position === "LOWER" ? "Near lower band — potential support"
    : "Within normal range";

  const cards = [
    {
      title: "RSI (14)",
      value: formatNumber(signals.rsi.value, 1),
      signal: signals.rsi.signal,
      type: "rsi" as const,
      subtitle: signals.rsi.value !== null ? `${formatNumber(signals.rsi.value, 0)} / 100` : null,
      description: rsiDesc,
    },
    {
      title: "MACD",
      value: formatNumber(signals.macd.histogram, 4),
      signal: signals.macd.signal,
      type: "macd" as const,
      subtitle: signals.macd.value !== null ? `Line: ${formatNumber(signals.macd.value, 4)}` : null,
      description: macdDesc,
    },
    {
      title: "SMA Crossover",
      value:
        signals.sma.sma_50 !== null
          ? `50: ${formatNumber(signals.sma.sma_50, 0)}`
          : "—",
      signal: signals.sma.signal,
      type: "sma" as const,
      subtitle: signals.sma.sma_200 !== null ? `200: ${formatNumber(signals.sma.sma_200, 0)}` : null,
      description: smaDesc,
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
      description: bbDesc,
    },
  ];

  return (
    <div className="space-y-3">
      <StalenessBadge
        lastUpdated={signals.computed_at ?? null}
        slaHours={4}
        refreshing={signals.is_refreshing}
      />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card, i) => {
        const sentiment = signalToSentiment(card.signal, card.type);
        return (
          <Card
            key={card.title}
            className={cn(
              "border-l-4 animate-fade-slide-up",
              SENTIMENT_BORDER_CLASSES[sentiment]
            )}
            style={{ '--stagger-delay': `${i * 80}ms` } as React.CSSProperties}
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
              {card.description && (
                <p className="mt-1.5 text-[10px] text-muted-foreground">{card.description}</p>
              )}
            </CardContent>
          </Card>
        );
      })}
    </div>
    </div>
  );
}
