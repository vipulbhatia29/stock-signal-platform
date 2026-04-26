"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useSentiment, useTickerArticles } from "@/hooks/use-sentiment";
import { CollapsibleSection } from "@/components/collapsible-section";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { ChartTooltip } from "@/components/chart-tooltip";
import { useChartColors } from "@/lib/chart-theme";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { NewsSentiment } from "@/types/api";

interface SentimentCardProps {
  ticker: string;
  enabled?: boolean;
}

function formatSentiment(value: number): string {
  if (value >= 0) return `+${value.toFixed(2)}`;
  return `\u2212${Math.abs(value).toFixed(2)}`;
}

function sentimentColor(value: number): string {
  if (value > 0.1) return "text-green-400";
  if (value < -0.1) return "text-red-400";
  return "text-muted-foreground";
}

export function SentimentCard({ ticker, enabled = true }: SentimentCardProps) {
  const {
    data: sentiment,
    isLoading,
    isError,
    refetch,
  } = useSentiment(enabled ? ticker : null);
  const { data: articles } = useTickerArticles(enabled ? ticker : null);
  const colors = useChartColors();

  if (isLoading) {
    return (
      <div className="space-y-3">
        <SectionHeading>Sentiment</SectionHeading>
        <Skeleton className="h-[80px] rounded-lg" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-14 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        <SectionHeading>Sentiment</SectionHeading>
        <ErrorState error="Failed to load sentiment data" onRetry={refetch} />
      </div>
    );
  }

  if (!sentiment || sentiment.data.length === 0) return null;

  const latest = sentiment.data[sentiment.data.length - 1];
  const chartData = [...sentiment.data].sort(
    (a, b) => new Date(a.date).getTime() - new Date(b.date).getTime(),
  );

  return (
    <div className="space-y-3">
      <SectionHeading>Sentiment</SectionHeading>

      {/* Trend chart */}
      <ResponsiveContainer width="100%" height={80}>
        <AreaChart data={chartData}>
          <XAxis dataKey="date" hide />
          <YAxis domain={[-1, 1]} hide />
          <Tooltip
            content={({ active, payload }) => {
              if (!payload?.[0]) return null;
              const d = payload[0].payload as NewsSentiment;
              return (
                <ChartTooltip
                  active={active}
                  label={d.date}
                  items={[
                    { name: "Stock", value: formatSentiment(d.stock_sentiment), color: colors.gain },
                    { name: "Sector", value: formatSentiment(d.sector_sentiment), color: colors.chart1 },
                    { name: "Macro", value: formatSentiment(d.macro_sentiment), color: "#6b7280" },
                    { name: "Articles", value: String(d.article_count), color: colors.price },
                  ]}
                />
              );
            }}
          />
          <Area
            type="monotone"
            dataKey="stock_sentiment"
            stroke={colors.gain}
            fill={colors.gain}
            fillOpacity={0.1}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="sector_sentiment"
            stroke={colors.chart1}
            fill="none"
            strokeWidth={1}
            strokeDasharray="4 2"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="macro_sentiment"
            stroke="#6b7280"
            fill="none"
            strokeWidth={1}
            strokeDasharray="2 2"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Current sentiment tiles */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Stock</p>
          <p className={cn("text-sm font-semibold tabular-nums", sentimentColor(latest.stock_sentiment))}>
            {formatSentiment(latest.stock_sentiment)}
          </p>
          {latest.dominant_event_type && (
            <span className="mt-1 inline-block rounded bg-muted/50 px-1.5 py-0.5 text-[9px] text-muted-foreground">
              {latest.dominant_event_type}
            </span>
          )}
        </div>
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Sector</p>
          <p className={cn("text-sm font-semibold tabular-nums", sentimentColor(latest.sector_sentiment))}>
            {formatSentiment(latest.sector_sentiment)}
          </p>
        </div>
        <div className="rounded-lg border border-border bg-card px-3 py-2 text-center">
          <p className="text-[9px] uppercase tracking-wider text-muted-foreground">Macro</p>
          <p className={cn("text-sm font-semibold tabular-nums", sentimentColor(latest.macro_sentiment))}>
            {formatSentiment(latest.macro_sentiment)}
          </p>
        </div>
      </div>

      {/* Collapsible article list */}
      {articles && articles.articles.length > 0 && (
        <CollapsibleSection title="Recent Articles" count={articles.total}>
          <div className="space-y-2">
            {articles.articles.slice(0, 20).map((article, i) => (
              <div key={`${article.published_at}-${i}`} className="flex items-start justify-between gap-2 text-sm">
                <div className="min-w-0 flex-1">
                  {article.source_url ? (
                    <a
                      href={article.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-foreground hover:underline line-clamp-1"
                    >
                      {article.headline}
                    </a>
                  ) : (
                    <span className="font-medium text-foreground line-clamp-1">{article.headline}</span>
                  )}
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{article.source}</span>
                    <span>·</span>
                    <span>{formatRelativeTime(article.published_at)}</span>
                    {article.event_type && (
                      <>
                        <span>·</span>
                        <span className="rounded bg-muted/50 px-1 py-0.5 text-[10px]">
                          {article.event_type}
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}
    </div>
  );
}
