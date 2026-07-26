"""
Retail pricing rules for FAF Price Book.

Wholesale × multiplier is rolled **up** to the next even whole dollar
(never down). Examples:
  337.50 → 338
  3010.50 → 3012
  100.00 → 100
  101.00 → 102
"""

from __future__ import annotations

import math
from typing import Optional, Union

Number = Union[int, float]


def round_up_even_dollar(amount: Optional[Number]) -> Optional[float]:
    """Ceiling to the next even whole dollar. Exact even dollars stay put."""
    if amount is None:
        return None
    try:
        x = float(amount)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    if x <= 0:
        return 0.0
    # Tiny epsilon so float dust just under an even dollar does not jump a step
    return float(2 * math.ceil(x / 2.0 - 1e-12))


def retail_from_wholesale(
    base_price: Optional[Number],
    multiplier: Optional[Number],
) -> Optional[float]:
    """base × mult, then roll up to next even dollar."""
    if base_price is None or multiplier is None:
        return None
    try:
        raw = float(base_price) * float(multiplier)
    except (TypeError, ValueError):
        return None
    return round_up_even_dollar(raw)


# SQLite expression: even-dollar ceil of (base_price * mult)
# Used in bulk UPDATE paths (SQLite 3.35+ has ceil).
SQL_EVEN_DOLLAR_RETAIL = "2 * CEIL((base_price * {mult}) / 2.0 - 1e-12)"
