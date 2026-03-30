import { cn } from "@/lib/utils";
import { classifyNewsSentiment, type NewsSentiment } from "@/lib/news-sentiment";

interface NewsCardProps {
  title: string;
  publisher?: string | null;
  published?: string | null;
  link: string;
  ticker?: string | null;
  className?: string;
}

const SENTIMENT_PILL: Record<NewsSentiment, { label: string; style: string }> = {
  bullish: { label: "Bullish", style: "bg-gain/15 text-[var(--gain)]" },
  bearish: { label: "Bearish", style: "bg-loss/15 text-[var(--loss)]" },
  neutral: { label: "", style: "" },
};

export function NewsCard({ title, publisher, published, link, ticker, className }: NewsCardProps) {
  const sentiment = classifyNewsSentiment(title);
  const pill = SENTIMENT_PILL[sentiment];

  return (
    <a
      href={link}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "block rounded-lg border border-border/20 bg-[rgba(15,23,42,0.5)] p-3 transition-colors hover:border-border/40",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="text-sm font-medium text-foreground line-clamp-2">{title}</div>
        {pill.label && (
          <span className={cn("shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-semibold", pill.style)}>
            {pill.label}
          </span>
        )}
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
        {ticker && <span className="font-semibold text-foreground">{ticker}</span>}
        {publisher && <span>{publisher}</span>}
        {published && <span>&bull; {published}</span>}
      </div>
    </a>
  );
}
