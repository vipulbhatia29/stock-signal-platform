const SECTOR_NORMALIZE: Record<string, string> = {
  Technology: "Technology",
  "Information Technology": "Technology",
  Healthcare: "Healthcare",
  "Health Care": "Healthcare",
  "Financial Services": "Financial Services",
  Financials: "Financial Services",
  "Consumer Cyclical": "Consumer Cyclical",
  "Consumer Discretionary": "Consumer Cyclical",
  "Consumer Defensive": "Consumer Defensive",
  "Consumer Staples": "Consumer Defensive",
  Energy: "Energy",
  Industrials: "Industrials",
  "Basic Materials": "Basic Materials",
  Materials: "Basic Materials",
  Utilities: "Utilities",
  "Real Estate": "Real Estate",
  "Communication Services": "Communication Services",
  Communications: "Communication Services",
  Telecom: "Communication Services",
};

export function normalizeSector(name: string): string {
  return SECTOR_NORMALIZE[name] ?? name;
}
