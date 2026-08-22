"""Size-option pricing and finishes are Search Options for every builder."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd

from backend.book_options import extract_book_options, merge_book_options
from wide_import import WorkbookImportResult, import_workbook


def _xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Pricelist"
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _millcraft_front_matter() -> bytes:
    return _xlsx(
        [
            ["", "PREFERRED DEALER Wholesale Price List"],
            ["", "", "Standard Options *No Upcharge*"],
            ["", "Oak", "Brown Maple"],
            ["", "ADD 10%"],
            ["", "Size Changes", "", "", "ADD ON OPTIONS"],
            ["", "Any casegood or bed can be customized up to 10''.", "", "", "Hidden Jewelry Tray: $30"],
            ["", "Two Toning", "", "", "Lock: $25"],
            ["", "ADD 20%"],
            ["", "Size changes on any casegood or bed over 10''."],
            ["", "Premium Finish Choices:"],
            ["", "Distressing"],
            ["", "Hand Rubbed Oil"],
            ["", "Description", "Item Number", "Standard Wood", "Premium Wood"],
            ["", "1 Drw Nightstand", "MAG22NS", 410.5, 492.5],
        ]
    )


def test_extracts_size_pct_finishes_and_flat_add_ons():
    rows = extract_book_options(_millcraft_front_matter(), vendor="Millcraft")
    by = {r["option_key"]: r for r in rows}
    assert by["Size change (up to 10\")"]["addon_pct"] == 10
    assert by["Size change (over 10\")"]["addon_pct"] == 20
    assert by["Two-tone"]["addon_pct"] == 10
    assert by["Distressing"]["addon_pct"] == 20
    assert by["Hand-rubbed oil"]["addon_pct"] == 20
    assert by["Hidden Jewelry Tray"]["base_price"] == 30
    assert by["Lock"]["base_price"] == 25
    assert all(r["line_kind"] == "addon" for r in rows)
    assert "Oak" not in by
    assert "Standard Wood" not in by


def test_import_workbook_puts_size_and_finish_on_search_options():
    data = _millcraft_front_matter()
    result = import_workbook(data, vendor="Millcraft", filename="Millcraft.xlsx")
    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    keys = set(addons["option_key"].astype(str))
    assert "Size change (up to 10\")" in keys
    assert "Two-tone" in keys
    assert "Lock" in keys


def test_skips_cover_sheet_and_catalog_fragments():
    data = _xlsx(
        [
            ["4. Password for Price List"],
            ["Password: $4"],
            ["Prices for the year: $2026"],
            ['36" Deep x 37" High OPTION: Hidden Chair: $120'],
            ["ieces 15% larger like the Premier Series, add 15%"],
            ["ADD 10%"],
            ["Size Changes"],
            ["Two Toning"],
            ["Distressing"],
            ["Premium Finish Choices:"],
            ["Hand Rubbed Oil"],
        ]
    )
    rows = extract_book_options(data, vendor="X")
    keys = {r["option_key"] for r in rows}
    assert "Password" not in keys
    assert not any("password" in k.lower() for k in keys)
    assert "Prices for the year" not in keys
    assert not any("Hidden Chair" in k or "OPTION:" in k for k in keys)
    assert not any(k[:1].islower() for k in keys)
    assert "Size change (up to 10\")" in keys
    assert "Two-tone" in keys


def test_merge_does_not_duplicate_existing_option_keys():
    existing = pd.DataFrame(
        [
            {
                "vendor": "Millcraft",
                "option_key": "Lock",
                "line_kind": "addon",
                "base_price": 25,
            }
        ]
    )
    result = WorkbookImportResult(
        sheets_tried=[],
        long_df=existing,
        detected_markup=None,
        sheet_names=["Pricelist"],
    )
    merged = merge_book_options(result, _millcraft_front_matter(), vendor="Millcraft")
    locks = merged.long_df[merged.long_df["option_key"] == "Lock"]
    assert len(locks) == 1


def test_extracts_visible_options_rows_with_percent_dollar_and_deduct_shapes():
    data = _xlsx(
        [
            ["Options"],
            ["Paint & Glaze", 0.15],
            ["Without Drawers", "$45 Less"],
            ["Plank Rough Sawn Tops", "No Upcharge"],
            ["Option: Slatted or Grooved Doors, ADD", 65, 65, 65, 65],
        ]
    )

    by = {row["option_key"]: row for row in extract_book_options(data, vendor="X")}

    assert by["Paint & Glaze"]["addon_pct"] == 15
    assert by["Without Drawers"]["base_price"] == -45
    assert by["Plank Rough Sawn Tops"]["base_price"] == 0
    assert by["Slatted or Grooved Doors"]["base_price"] == 65


def test_extracts_formatted_finish_percent_rows_after_finish_banner():
    data = _xlsx(
        [
            ["FINISHING OPTIONS FOR ALL PRODUCTS"],
            ["ADD ALL THAT APPLY"],
            [None, None, None, None, None, "Category 2 Colors", None, None, 0.8],
            [None, None, None, None, None, "Two-Tone", None, None, 0.4],
        ]
    )

    by = {row["option_key"]: row for row in extract_book_options(data, vendor="X")}

    assert by["Category 2 Colors"]["addon_pct"] == 80
    assert by["Two-tone"]["addon_pct"] == 40


def test_extracts_per_drawer_hardware_charges_from_visible_note():
    data = _xlsx(
        [
            [
                '*Add $10/drawer for side mount soft close, '
                '$20/drawer for undermount soft close'
            ]
        ]
    )

    by = {row["option_key"]: row for row in extract_book_options(data, vendor="X")}

    assert by["Side Mount Soft Close Slides"]["base_price"] == 10
    assert by["Undermount Soft Close Slides"]["base_price"] == 20


def test_options_banner_does_not_turn_following_product_skus_into_options():
    data = _xlsx(
        [
            ["Options"],
            ["10-16", "Chair", 250, 250, 250],
            ["101 CSC", "Corner Sofa", 1200, 1200],
            ["Option: Slatted Door, ADD", 65, 65],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="X")}

    assert "10-16" not in labels
    assert "101 CSC" not in labels
    assert "Slatted Door" in labels


def test_quote_only_lines_surface_as_non_priced_options():
    """Call-for-quote and TBD choices exist. The floor must see them, not guess."""
    data = _xlsx(
        [
            ["Options"],
            ["Leather", "Call for pricing"],
            ["Marble Top", "TBD"],
            ["Paint", "add 20%"],
        ]
    )

    rows = extract_book_options(data, vendor="X")
    by_label = {row["option_key"]: row for row in rows}

    assert set(by_label) == {"Leather", "Marble Top", "Paint"}
    leather = by_label["Leather"]
    assert leather["base_price"] is None
    assert leather["addon_pct"] is None
    assert "quote" in leather["notes"].lower()
    assert by_label["Paint"]["addon_pct"] == 20.0


def test_builder_names_never_become_option_labels():
    """Ashery Oak is a builder. A builder name in an Options tab is not an Option."""
    data = _xlsx(
        [
            ["Options"],
            ["Ashery Oak", "Add 10%"],
            ["Quality Fabrications Leather", "Add 15%"],
            ["Paint", "Add 20%"],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="X")}

    assert "Ashery Oak" not in labels
    assert "Quality Fabrications Leather" not in labels
    assert "Paint" in labels


def test_per_sku_finish_markup_rows_are_not_global_options():
    data = _xlsx(
        [
            ["110 CSF", '36" Cubic Slat Footstool', 54.6, "Standard Wiping Stains", "List Price", "add 10%"],
            ["10-36", 'AJ #1 36" Square End Table', 110.25, "Standard Wiping Stains", "List Price", "add 10%"],
            ["PD-36", 'Pioneer 36" Coffee Table', 99.75, "Standard Wiping Stains", "List Price", "add 10%"],
            ["Paint", "add 20%"],
        ]
    )

    labels = {row["option_key"] for row in extract_book_options(data, vendor="X")}

    assert labels == {"Paint"}
