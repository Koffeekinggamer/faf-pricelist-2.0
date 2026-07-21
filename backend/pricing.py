"""Retail = wholesale × mult, rolled up to next even dollar."""

from __future__ import annotations

import math
from typing import Optional, Union

Number = Union[int, float]


def round_up_even_dollar(amount: Optional[Number]) -> Optional[float]:
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
    return float(2 * math.ceil(x / 2.0 - 1e-12))


def retail_from_wholesale(
    base_price: Optional[Number],
    multiplier: Optional[Number],
) -> Optional[float]:
    if base_price is None or multiplier is None:
        return None
    try:
        raw = float(base_price) * float(multiplier)
    except (TypeError, ValueError):
        return None
    return round_up_even_dollar(raw)
