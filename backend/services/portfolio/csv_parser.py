"""Fidelity CSV parser with fuzzy column matching and silent fixes.

Accepts Fidelity-format position CSVs with messy formatting
(dollar signs, percentages, varied column names, summary rows)
and returns clean parsed rows with warnings for ambiguous cases.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from decimal import Decimal, InvalidOperation

from backend.schemas.attribution import CsvValidationError, ImportWarning, SnapshotRowSchema

logger = logging.getLogger(__name__)

# Column aliases — fuzzy matching against these after normalizing
_COLUMN_ALIASES: dict[str, list[str]] = {
    "symbol": ["symbol", "ticker"],
    "qty": ["qty", "quantity", "shares"],
    "price": ["price", "last price", "current price"],
    "cost_basis": ["cost basis", "cost", "total cost"],
    "asset_type": ["asset type", "type"],
    "description": ["description", "name"],
    "market_value": ["mkt val", "market value"],
}

_REQUIRED_COLUMNS = {"symbol", "qty", "price", "cost_basis"}

_SKIP_SYMBOLS = frozenset(
    {
        "",
        "cash & cash investments",
        "positions total",
        "pending activity",
    }
)

_SKIP_ASSET_TYPES = frozenset({"cash and money market", ""})


def _normalize_header(raw: str) -> str:
    """Strip parentheticals, whitespace, and lowercase."""
    cleaned = re.sub(r"\([^)]*\)", "", raw)
    return cleaned.strip().lower()


def _resolve_columns(headers: list[str]) -> dict[str, int] | None:
    """Map our canonical names to column indexes via fuzzy alias matching.

    Returns None if any required column is missing.
    """
    normalized = [_normalize_header(h) for h in headers]
    mapping: dict[str, int] = {}

    for canonical, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            for idx, norm in enumerate(normalized):
                if norm == alias:
                    mapping[canonical] = idx
                    break
            if canonical in mapping:
                break

    return mapping if _REQUIRED_COLUMNS.issubset(mapping) else None


def _parse_decimal(val: str) -> Decimal | None:
    """Parse a decimal value, stripping $, commas, %, whitespace."""
    if not val or val.strip() in ("--", "N/A", "Incomplete", ""):
        return None
    cleaned = val.replace("$", "").replace(",", "").replace("%", "").strip()
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _find_header_row(lines: list[str]) -> int | None:
    """Scan first 10 lines for one containing 'Symbol'."""
    for i, line in enumerate(lines[:10]):
        if "symbol" in line.lower():
            return i
    return None


def parse_fidelity_csv(
    content: str,
) -> tuple[list[SnapshotRowSchema], list[ImportWarning], list[CsvValidationError]]:
    """Parse a Fidelity positions CSV into validated snapshot rows.

    Args:
        content: UTF-8 CSV text (raw file content).

    Returns:
        Tuple of (valid_rows, warnings, errors).
        If errors is non-empty, the import should be rejected.
    """
    warnings: list[ImportWarning] = []
    errors: list[CsvValidationError] = []
    rows: list[SnapshotRowSchema] = []

    if not content or not content.strip():
        errors.append(CsvValidationError(message="File is empty."))
        return rows, warnings, errors

    # Strip BOM
    content = content.lstrip("\ufeff")

    lines = content.splitlines()
    header_idx = _find_header_row(lines)

    if header_idx is None:
        errors.append(
            CsvValidationError(
                message="Could not find header row. Expected columns: Symbol, Qty, Price, Cost Basis",
            )
        )
        return rows, warnings, errors

    # Parse from header row onward
    csv_content = "\n".join(lines[header_idx:])
    reader = csv.reader(io.StringIO(csv_content))

    try:
        raw_headers = next(reader)
    except StopIteration:
        errors.append(CsvValidationError(message="File has header but no data rows."))
        return rows, warnings, errors

    col_map = _resolve_columns(raw_headers)
    if col_map is None:
        missing = _REQUIRED_COLUMNS - set(
            k
            for k, aliases in _COLUMN_ALIASES.items()
            if any(_normalize_header(h) == a for h in raw_headers for a in aliases)
        )
        errors.append(
            CsvValidationError(
                message=f"Missing column(s): {', '.join(sorted(missing))}. "
                "Required: Symbol, Qty, Price, Cost Basis",
            )
        )
        return rows, warnings, errors

    seen_tickers: set[str] = set()

    for row_num, fields in enumerate(reader, start=header_idx + 2):
        if len(fields) <= max(col_map.values()):
            continue  # Short row — skip silently

        symbol = fields[col_map["symbol"]].strip().upper()

        # Skip cash, summary, and blank rows
        if symbol.lower() in _SKIP_SYMBOLS:
            continue

        asset_type = ""
        if "asset_type" in col_map:
            asset_type = fields[col_map["asset_type"]].strip()
        if asset_type.lower() in _SKIP_ASSET_TYPES:
            continue

        # Duplicate check
        if symbol in seen_tickers:
            warnings.append(
                ImportWarning(
                    row=row_num,
                    message=f"{symbol} appears twice — first row used",
                )
            )
            continue
        seen_tickers.add(symbol)

        # Parse numeric fields
        shares = _parse_decimal(fields[col_map["qty"]])
        if shares is None or shares < 0:
            warnings.append(
                ImportWarning(
                    row=row_num,
                    message=f"Qty '{fields[col_map['qty']].strip()}' is not a valid number",
                )
            )
            continue

        price = _parse_decimal(fields[col_map["price"]])
        if price is None:
            price = Decimal("0")
            warnings.append(
                ImportWarning(
                    row=row_num,
                    message=f"{symbol} has no price — P&L metrics will be incomplete",
                )
            )

        cost_basis = _parse_decimal(fields[col_map["cost_basis"]])
        if cost_basis is None or cost_basis <= 0:
            if price > 0 and shares > 0:
                cost_basis = price * shares
                warnings.append(
                    ImportWarning(
                        row=row_num,
                        message=f"{symbol} has no cost basis — estimated from Price × Qty",
                    )
                )
            else:
                cost_basis = Decimal("0")

        market_value = Decimal("0")
        if "market_value" in col_map:
            market_value = _parse_decimal(fields[col_map["market_value"]]) or Decimal("0")
        if market_value == 0 and price > 0 and shares > 0:
            market_value = price * shares

        description = ""
        if "description" in col_map:
            description = fields[col_map["description"]].strip()

        avg_cost = cost_basis / shares if shares > 0 else Decimal("0")

        rows.append(
            SnapshotRowSchema(
                ticker=symbol,
                description=description,
                shares=shares,
                price=price,
                cost_basis=cost_basis,
                market_value=market_value,
                asset_type=asset_type or "Equity",
                avg_cost_basis=avg_cost,
            )
        )

    if not rows and not errors:
        errors.append(CsvValidationError(message="No valid positions found in CSV."))

    return rows, warnings, errors
