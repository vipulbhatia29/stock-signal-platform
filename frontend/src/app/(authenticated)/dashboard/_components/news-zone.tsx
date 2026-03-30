"use client";

import { Newspaper } from "lucide-react";
import { SectionHeading } from "@/components/section-heading";
import { NewsArticleCard } from "@/components/news-article-card";
import { EmptyState } from "@/components/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { useUserDashboardNews, useMarketBriefing } from "@/hooks/use-stocks";

/** Zone 5 — Personalized news + general market news. */
export function NewsZone() {
  const { data: dashNews, isLoading: dashLoading } = useUserDashboardNews();
  const { data: briefing } = useMarketBriefing();

  const personalArticles = dashNews?.articles ?? [];
  const generalArticles = briefing?.general_news ?? [];
  const allArticles = [...personalArticles, ...generalArticles];
  const isLoading = dashLoading;

  return (
    <section aria-label="News and Intelligence">
      <SectionHeading>
        <span className="inline-flex items-center gap-1.5">
          <Newspaper className="h-3 w-3" />
          News &amp; Intelligence
        </span>
      </SectionHeading>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg bg-card2" />
          ))}
        </div>
      ) : allArticles.length === 0 ? (
        <EmptyState icon={Newspaper} title="No news yet" description="Add stocks to your watchlist to see personalized news" />
      ) : (
        <div className="space-y-2">
          {allArticles.slice(0, 8).map((article, i) => (
            <NewsArticleCard
              key={`${article.link}-${i}`}
              title={article.title}
              publisher={article.publisher}
              published={article.published}
              link={article.link}
              ticker={article.portfolio_ticker}
            />
          ))}
        </div>
      )}
    </section>
  );
}
