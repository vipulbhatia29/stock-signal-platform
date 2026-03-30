"""Sector name normalization between yfinance GICS names and ETF sector names."""

SECTOR_ALIASES: dict[str, list[str]] = {
    "Technology": ["Technology", "Information Technology"],
    "Healthcare": ["Healthcare", "Health Care"],
    "Financial Services": ["Financial Services", "Financials"],
    "Consumer Cyclical": ["Consumer Cyclical", "Consumer Discretionary"],
    "Consumer Defensive": ["Consumer Defensive", "Consumer Staples"],
    "Energy": ["Energy"],
    "Industrials": ["Industrials"],
    "Basic Materials": ["Basic Materials", "Materials"],
    "Utilities": ["Utilities"],
    "Real Estate": ["Real Estate"],
    "Communication Services": ["Communication Services", "Communications", "Telecom"],
}

SECTOR_NORMALIZE: dict[str, str] = {
    alias: canonical for canonical, aliases in SECTOR_ALIASES.items() for alias in aliases
}


def normalize_sector(name: str) -> str:
    """Normalize a sector name to yfinance canonical form."""
    return SECTOR_NORMALIZE.get(name, name)
