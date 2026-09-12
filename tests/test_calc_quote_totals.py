"""Quote totals: tax the retail line totals, not wholesale."""

from __future__ import annotations

from backend.pricing import retail_from_wholesale
from backend.quote.calc_quote_totals import calc_quote_totals
from backend.quote.cart import CartLine, line_total


def test_calc_quote_totals_spartanburg_7_percent() -> None:
    unit = retail_from_wholesale(100, 2.7)
    assert unit == 270.0
    lines = [
        CartLine(
            id="a",
            product_id="1",
            sku="A",
            name="Chair",
            options_snapshot={"wood": "Oak", "finish": "finished"},
            unit_price=unit,
            qty=2,
        )
    ]
    totals = calc_quote_totals(lines, 0.07)
    assert totals.subtotal == 540.0
    assert totals.tax_amount == 37.80
    assert totals.total == 577.80


def test_calc_quote_totals_mecklenburg_and_exempt() -> None:
    unit = retail_from_wholesale(100, 2.7)
    lines = [
        CartLine(
            id="b",
            product_id="2",
            sku="B",
            name="Table",
            options_snapshot={},
            unit_price=unit,
            qty=1,
        )
    ]
    taxed = calc_quote_totals(lines, 0.0825)
    assert taxed.subtotal == 270.0
    assert taxed.tax_amount == 22.28
    assert taxed.total == 292.28
    exempt = calc_quote_totals(lines, 0.0)
    assert exempt.tax_amount == 0.0
    assert exempt.total == 270.0


def test_line_total_is_unit_times_qty() -> None:
    line = CartLine(
        id="c",
        product_id="3",
        sku="C",
        name="Bench",
        options_snapshot={},
        unit_price=1932.0,
        qty=3,
    )
    assert line_total(line) == 5796.0
