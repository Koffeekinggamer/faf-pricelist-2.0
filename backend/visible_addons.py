"""Shared addon-row constructor for factory readers that print priced notes.

Hope Wood and Maple Lane both turn visible workbook prose into addon rows
with the same catalog shape. Keep the constructor here so those readers
stay thin and do not import each other.
"""

from __future__ import annotations

from typing import Optional


def visible_addon(
    vendor: str,
    label: str,
    *,
    amount: Optional[float] = None,
    notes: str,
) -> dict:
    return {
        "vendor": vendor,
        "collection": "Addons",
        "part_number": label,
        "description": label,
        "dimensions": None,
        "option_key": label,
        "species": None,
        "species_tier": None,
        "finish_state": "finished",
        "base_price": amount,
        "price_basis": "wholesale",
        "unit": None,
        "notes": notes,
        "line_kind": "addon",
        "addon_pct": None,
    }
