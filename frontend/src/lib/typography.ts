// Semantic typography class constants.
// Single source of truth for type scale — prevents drift across components.

export const TYPOGRAPHY = {
  PAGE_TITLE: "text-2xl font-semibold tracking-tight",
  SECTION_HEADING:
    "text-sm font-medium uppercase tracking-wider text-muted-foreground",
  METRIC_PRIMARY: "text-2xl font-semibold tabular-nums",
  METRIC_SECONDARY: "text-xl font-semibold tabular-nums",
  TICKER: "font-mono text-base font-semibold",
  TABLE_NUM: "text-sm tabular-nums",
  LABEL: "text-xs text-muted-foreground",
} as const;

export type TypographyToken = keyof typeof TYPOGRAPHY;
