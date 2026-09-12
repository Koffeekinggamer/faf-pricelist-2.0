"""Quote cart behavior through the public PriceBookService seam."""

from backend import PriceBookService


def _configured_row(*, option: str = "Premium finish", retail: float = 300.0) -> dict:
    return {
        "id": 42,
        "vendor": "Test Builder",
        "collection": "Tables",
        "part_number": "T-100",
        "description": "Dining Table",
        "dimensions": '42" x 60"',
        "option_key": option,
        "species": "Brown Maple",
        "finish_state": "finished",
        "base_price": 110.0,
        "adjusted_price": retail,
    }


def _default_row() -> dict:
    return {
        **_configured_row(option="", retail=270.0),
        "species": "Oak",
        "base_price": 100.0,
    }


def test_same_product_and_options_merge_unless_separate_line_requested(tmp_path):
    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote()

    first_id = svc.add_quote_cart_line(
        quote_id,
        _configured_row(),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
        qty=1,
    )
    merged_id = svc.add_quote_cart_line(
        quote_id,
        _configured_row(),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
        qty=2,
    )
    separate_id = svc.add_quote_cart_line(
        quote_id,
        _configured_row(),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
        qty=1,
        separate_line=True,
    )

    lines = svc.quote_lines(quote_id)
    assert merged_id == first_id
    assert separate_id != first_id
    assert lines["qty"].tolist() == [3.0, 1.0]
    assert lines["line_total"].tolist() == [900.0, 300.0]


def test_different_option_snapshots_remain_distinct_lines(tmp_path):
    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote()

    svc.add_quote_cart_line(
        quote_id,
        _configured_row(option="Premium finish"),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
    )
    svc.add_quote_cart_line(
        quote_id,
        _configured_row(option="Two tone", retail=320.0),
        default_pricebook_row=_default_row(),
        options={"Two tone": 1},
    )

    assert len(svc.quote_lines(quote_id)) == 2


def test_clear_quote_requires_confirmation_and_resets_tax(tmp_path):
    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote(tax_pct=7.0)
    svc.update_quote(
        quote_id,
        tax_state="SC",
        tax_county="Spartanburg",
        tax_exempt=False,
    )
    svc.add_quote_cart_line(
        quote_id,
        _configured_row(),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
    )

    assert svc.clear_quote(quote_id, confirmed=False) is False
    assert len(svc.quote_lines(quote_id)) == 1

    assert svc.clear_quote(quote_id, confirmed=True) is True
    assert svc.quote_lines(quote_id).empty
    quote = svc.get_quote(quote_id)
    assert quote["tax_pct"] == 0
    assert quote["tax_state"] is None
    assert quote["tax_county"] is None
    assert quote["tax_exempt"] == 0
    assert svc.quote_totals(quote_id)["grand_total"] == 0


def test_tax_exempt_forces_zero_tax_without_losing_selected_rate(tmp_path):
    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote(tax_pct=7.0)
    svc.add_quote_cart_line(
        quote_id,
        _configured_row(retail=300.0),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
        qty=2,
    )

    svc.update_quote(quote_id, tax_exempt=True)
    totals = svc.quote_totals(quote_id)

    assert totals["subtotal"] == 600.0
    assert totals["tax_pct"] == 0
    assert totals["tax_amount"] == 0
    assert totals["grand_total"] == 600.0
    assert totals["tax_label"] == "Exempt"
    assert svc.get_quote(quote_id)["tax_pct"] == 7.0


def test_reset_line_options_restores_catalog_defaults_and_keeps_line(tmp_path):
    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote()
    line_id = svc.add_quote_cart_line(
        quote_id,
        _configured_row(),
        default_pricebook_row=_default_row(),
        options={"Premium finish": 1},
    )

    assert svc.reset_quote_line_options(line_id) is True
    line = svc.quote_lines(quote_id).iloc[0]
    assert int(line["id"]) == line_id
    assert line["options_json"] == "{}"
    assert line["species"] == "Oak"
    assert line["unit_retail"] == 270.0
    assert line["line_total"] == 270.0


def test_reset_options_computes_default_retail_when_adjusted_price_missing(tmp_path):
    """Catalog rows often store wholesale only; Reset must not collapse to $0.00."""
    from backend.pricing import retail_from_wholesale

    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote()
    configured = {
        **_configured_row(retail=0),
        "base_price": 525.0,
        "adjusted_price": None,
        "multiplier": 2.7,
    }
    default = {
        **_default_row(),
        "base_price": 500.0,
        "adjusted_price": None,
        "multiplier": 2.7,
        "option_key": "",
    }
    line_id = svc.add_quote_cart_line(
        quote_id,
        configured,
        default_pricebook_row=default,
        options={"Premium finish": 1},
    )

    line = svc.quote_lines(quote_id).iloc[0]
    assert float(line["unit_retail"]) == float(retail_from_wholesale(525.0, 2.7))
    assert float(line["default_unit_retail"]) == float(
        retail_from_wholesale(500.0, 2.7)
    )

    assert svc.reset_quote_line_options(line_id) is True
    line = svc.quote_lines(quote_id).iloc[0]
    assert float(line["unit_retail"]) == float(retail_from_wholesale(500.0, 2.7))
    assert float(line["line_total"]) == float(retail_from_wholesale(500.0, 2.7))
    assert float(line["unit_retail"]) != 0.0


def test_reset_options_heals_null_default_unit_retail_snapshot(tmp_path):
    """Lines snapshotted before the retail fix still Reset to catalog retail."""
    import sqlite3

    from backend.pricing import retail_from_wholesale

    svc = PriceBookService(tmp_path / "cart.db")
    quote_id = svc.create_quote()
    line_id = svc.add_quote_cart_line(
        quote_id,
        _configured_row(retail=1418.0),
        default_pricebook_row={
            **_default_row(),
            "base_price": 500.0,
            "adjusted_price": 1350.0,
            "multiplier": 2.7,
        },
        options={"Premium finish": 1},
    )
    with sqlite3.connect(tmp_path / "cart.db") as conn:
        conn.execute(
            "UPDATE quote_lines SET default_unit_retail = NULL WHERE id = ?",
            (line_id,),
        )
        conn.commit()

    assert svc.reset_quote_line_options(line_id) is True
    line = svc.quote_lines(quote_id).iloc[0]
    assert float(line["unit_retail"]) == float(retail_from_wholesale(500.0, 2.7))
    assert float(line["line_total"]) == float(retail_from_wholesale(500.0, 2.7))
    assert line["default_unit_retail"] is not None
    assert float(line["default_unit_retail"]) == float(
        retail_from_wholesale(500.0, 2.7)
    )
