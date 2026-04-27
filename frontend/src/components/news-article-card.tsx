import { cn } from "@/lib/utils";

interface NewsCardProps {
  title: string;
  publisher?: string | null;
  published?: string | null;
  link: string;
  ticker?: string | null;
  sentimentLabel?: string | null;
  category?: string | null;
  className?: string;
}

const SENTIMENT_PILL: Record<string, { label: string; style: string }> = {
  bullish: { label: "Bullish", style: "bg-gain/15 text-[var(--gain)]" },
  bearish: { label: "Bearish", style: "bg-loss/15 text-[var(--loss)]" },
  neutral: { label: "", style: "" },
};

const CATEGORY_LABEL: Record<string, { label: string; style: string }> = {
  stock: { label: "Stock", style: "text-primary" },
  sector: { label: "Sector", style: "text-purple-400" },
  macro: { label: "Macro", style: "text-warning" },
  general: { label: "General", style: "text-muted-foreground" },
};

export function NewsArticleCard({
  title,
  publisher,
  published,
  link,
  ticker,
  sentimentLabel,
  category,
  className,
}: NewsCardProps) {
  const pill = sentimentLabel ? (SENTIMENT_PILL[sentimentLabel] ?? SENTIMENT_PILL.neutral) : SENTIMENT_PILL.neutral;
  const cat = category ? (CATEGORY_LABEL[category] ?? CATEGORY_LABEL.general) : null;

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
        <div className="flex shrink-0 items-center gap-1.5">
          {cat && cat.label !== "General" && (
            <span className={cn("rounded-md px-1.5 py-0.5 text-[9px] font-medium bg-muted/30", cat.style)}>
              {cat.label}
            </span>
          )}
          {pill.label && (
            <span className={cn("rounded-md px-1.5 py-0.5 text-[10px] font-semibold", pill.style)}>
              {pill.label}
            </span>
          )}
        </div>
      </div>
      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-muted-foreground">
        {ticker && <span className="font-semibold text-foreground">{ticker}</span>}
        {publisher && <span>{publisher}</span>}
        {published && <span>&bull; {published}</span>}
      </div>
    </a>
  );
}
