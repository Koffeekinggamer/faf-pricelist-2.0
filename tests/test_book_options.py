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
