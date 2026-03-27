"""Shared constants for the backend package."""

# Sector-to-ETF mapping for sector forecast lookups
SECTOR_ETF_MAP: dict[str, str] = {
    "technology": "XLK",
    "healthcare": "XLV",
    "financials": "XLF",
    "consumer discretionary": "XLY",
    "consumer staples": "XLP",
    "energy": "XLE",
    "industrials": "XLI",
    "materials": "XLB",
    "utilities": "XLU",
    "real estate": "XLRE",
    "communication services": "XLC",
}
