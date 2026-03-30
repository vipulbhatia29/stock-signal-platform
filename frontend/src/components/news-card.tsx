"use client";

import { ExternalLinkIcon } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/error-state";
import { formatRelativeTime } from "@/lib/format";
import type { StockNewsResponse } from "@/types/api";

const MAX_ARTICLES = 8;

interface NewsCardProps {
  news: StockNewsResponse | undefined;
  isLoading: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

export function NewsCard({ news, isLoading, isError, onRetry }: NewsCardProps) {
  if (isLoading) {
    return (
      <div className="space-y-4">
        <SectionHeading>News</SectionHeading>
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-12 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-4">
        <SectionHeading>News</SectionHeading>
        <ErrorState error="Failed to load news" onRetry={onRetry} />
      </div>
    );
  }

  if (!news || news.articles.length === 0) {
    return (
      <div className="space-y-4">
        <SectionHeading>News</SectionHeading>
        <p className="text-sm text-muted-foreground">
          No news available for this ticker.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionHeading>News</SectionHeading>
      <ul className="space-y-2">
        {news.articles.slice(0, MAX_ARTICLES).map((article, i) => (
          <li
            key={`${article.link}-${i}`}
            className="flex items-start gap-3 rounded-lg border border-border bg-card px-3 py-2.5"
          >
            <div className="min-w-0 flex-1">
              <a
                href={article.link}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-foreground hover:text-primary transition-colors line-clamp-2"
              >
                {article.title}
              </a>
              <div className="mt-1 flex items-center gap-2 text-xs text-subtle">
                {article.publisher && (
                  <span className="font-medium text-muted-foreground">
                    {article.publisher}
                  </span>
                )}
                {article.published && (
                  <span>{formatRelativeTime(article.published)}</span>
                )}
              </div>
            </div>
            <ExternalLinkIcon className="mt-0.5 size-3.5 shrink-0 text-subtle" />
          </li>
        ))}
      </ul>
    </div>
  );
}
