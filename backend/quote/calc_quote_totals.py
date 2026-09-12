"""Client totals: tax retail line totals after existing markup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from backend.quote.cart import CartLine, line_total


@dataclass(frozen=True)
class QuoteTotals:
    subtotal: float
    tax_amount: float
    total: float


def _money(value: float) -> float:
    return round(float(value) + 0.0, 2)


def calc_quote_totals(lines: Iterable[CartLine], rate: float) -> QuoteTotals:
    """subtotal = sum(lineTotals); tax = round(subtotal * rate, 2); total = subtotal + tax."""
    subtotal = _money(sum(line_total(line) for line in lines))
    tax_rate = float(rate or 0.0)
    if tax_rate < 0:
        tax_rate = 0.0
    tax_amount = _money(subtotal * tax_rate)
    return QuoteTotals(
        subtotal=subtotal, tax_amount=tax_amount, total=_money(subtotal + tax_amount)
    )
