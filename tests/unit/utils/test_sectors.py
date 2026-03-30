from backend.utils.sectors import SECTOR_ALIASES, normalize_sector


def test_normalize_exact_match():
    assert normalize_sector("Technology") == "Technology"
    assert normalize_sector("Energy") == "Energy"


def test_normalize_etf_alias():
    assert normalize_sector("Financials") == "Financial Services"
    assert normalize_sector("Consumer Discretionary") == "Consumer Cyclical"
    assert normalize_sector("Consumer Staples") == "Consumer Defensive"
    assert normalize_sector("Materials") == "Basic Materials"


def test_normalize_unknown_passthrough():
    assert normalize_sector("Unknown Sector") == "Unknown Sector"


def test_normalize_communication_services():
    assert normalize_sector("Communications") == "Communication Services"
    assert normalize_sector("Telecom") == "Communication Services"


def test_aliases_cover_all_sectors():
    assert len(SECTOR_ALIASES) == 11
