// CSS variable name constants — single source of truth for design tokens.
// Use these when accessing CSS variables programmatically (e.g., in chart themes,
// sparklines, and other components that need resolved color strings).

export const CSS_VARS = {
  // Financial semantic
  gain: "--gain",
  gainForeground: "--gain-foreground",
  loss: "--loss",
  lossForeground: "--loss-foreground",
  neutralSignal: "--neutral-signal",
  // Accent
  cyan: "--cyan",
  cdim: "--cdim",
  // Warning
  warning: "--warning",
  warningForeground: "--warning-foreground",
  // Text hierarchy
  foreground: "--foreground",
  mutedForeground: "--muted-foreground",
  subtle: "--subtle",
  // Surfaces
  card: "--card",
  card2: "--card2",
  hov: "--hov",
  // Borders
  border: "--border",
  bhi: "--bhi",
  // Chart-specific
  chartPrice: "--chart-price",
  chartVolume: "--chart-volume",
  chartSma50: "--chart-sma-50",
  chartSma200: "--chart-sma-200",
  chartRsi: "--chart-rsi",
  // shadcn chart palette
  chart1: "--chart-1",
  chart2: "--chart-2",
  chart3: "--chart-3",
  chart4: "--chart-4",
  chart5: "--chart-5",
  popover: "--popover",
  popoverForeground: "--popover-foreground",
} as const;
