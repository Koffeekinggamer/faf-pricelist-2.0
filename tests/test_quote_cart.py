"""Cart merge rules: increment same product+options, unique line ids."""

from __future__ import annotations

from backend.quote.cart import QuoteCart, priced_catalog_row


def _row(sku: str, name: str, wood: str = "Oak") -> dict[str, object]:
    return priced_catalog_row(
        sku=sku,
        name=name,
        wholesale=100,
        multiplier=2.7,
        options={"wood": wood, "finish": "finished"},
    )


def test_add_two_different_items() -> None:
    cart = QuoteCart()
    cart.add_from_row(_row("CH-1", "Chair"))
    cart.add_from_row(_row("TB-1", "Table"))
    assert len(cart.lines) == 2
    assert cart.lines[0].unit_price == 270.0
    assert cart.badge_count == 2


def test_same_product_options_increments_qty() -> None:
    cart = QuoteCart()
    cart.add_from_row(_row("CH-1", "Chair"))
    cart.add_from_row(_row("CH-1", "Chair"))
    assert len(cart.lines) == 1
    assert cart.lines[0].qty == 2


def test_add_as_separate_line_keeps_two_rows() -> None:
    cart = QuoteCart()
    cart.add_from_row(_row("CH-1", "Chair"))
    cart.add_from_row(_row("CH-1", "Chair"), add_as_separate_line=True)
    assert len(cart.lines) == 2
    assert cart.lines[0].id != cart.lines[1].id


def test_qty_reset_remove_and_clear() -> None:
    cart = QuoteCart()
    a = cart.add_from_row(_row("CH-1", "Chair", wood="Oak"))
    cart.set_line_options(a.id, {"wood": "Cherry", "finish": "finished"})
    cart.set_qty(a.id, 4)
    assert cart.lines[0].qty == 4
    cart.reset_line_options(a.id)
    assert cart.lines[0].options_snapshot["wood"] == "Oak"
    assert cart.lines[0].qty == 4
    cart.remove_line(a.id)
    assert cart.lines == []
    cart.add_from_row(_row("CH-1", "Chair"))
    cart.select_county("Spartanburg", "SC")
    cart.clear_quote()
    assert cart.lines == []
    assert cart.tax_rate == 0.0
    assert cart.tax_label == "Select delivery county"
    assert cart.county is None
