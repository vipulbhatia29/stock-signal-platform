// CSS variable name constants — single source of truth for design tokens.
// Use these when accessing CSS variables programmatically (e.g., in chart themes).

export const CSS_VARS = {
  // Financial semantic
  gain: "--gain",
  gainForeground: "--gain-foreground",
  loss: "--loss",
  lossForeground: "--loss-foreground",
  neutralSignal: "--neutral-signal",
  // Chart-specific
  chartPrice: "--chart-price",
  chartVolume: "--chart-volume",
  chartSma50: "--chart-sma-50",
  chartSma200: "--chart-sma-200",
  chartRsi: "--chart-rsi",
  // Core
  chart1: "--chart-1",
  chart2: "--chart-2",
  chart3: "--chart-3",
  mutedForeground: "--muted-foreground",
  border: "--border",
  popover: "--popover",
  popoverForeground: "--popover-foreground",
} as const;
