"""Wide Excel import fidelity (species matrix → long rows)."""

from __future__ import annotations

import io

import openpyxl

from backend.import_service import ImportService
from backend.pricing import retail_from_wholesale
from backend.standardize import resolve_builder_vendor


def _xlsx_bytes(rows: list[list], sheet: str = "Price List") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_wide_species_matrix_unpivot():
    data = _xlsx_bytes(
        [
            ["Item #", "Description", "Oak", "Cherry", "Walnut"],
            ["T-100", "Trestle Table", 500, 550, 600],
            ["C-10", "Side Chair", 120, 130, 140],
        ]
    )
    preview = ImportService().preview_excel(
        data,
        filename="Hopewood_Price_List.xlsx",
        vendor="Hope Wood",
        multiplier=2.7,
    )
    assert len(preview.rows) >= 6  # 2 parts × 3 woods
    species = {(r.get("species") or "").lower() for r in preview.rows}
    assert any("oak" in s for s in species)
    prices = {r.get("base_price") for r in preview.rows}
    assert 500.0 in prices
    assert 140.0 in prices
    # Retail even-dollar applied
    sample = next(r for r in preview.rows if r.get("base_price") == 500.0)
    assert sample.get("adjusted_price") == retail_from_wholesale(500, 2.7)


def test_resolve_builder_from_filename():
    name = resolve_builder_vendor("", filename="MWS 2023 Wholesale Price List.xlsx")
    assert name == "Millers Woodshop"


def test_flat_table_import():
    data = _xlsx_bytes(
        [
            ["Part #", "Description", "Wood", "Wholesale"],
            ["P1", "Bench", "Maple", 220],
            ["P2", "Stool", "Oak", 90],
        ],
        sheet="Catalog",
    )
    preview = ImportService().preview_excel(
        data,
        filename="FlatBuilder.xlsx",
        vendor="Flat Builder",
        multiplier=2.7,
    )
    assert len(preview.rows) >= 2
    parts = {r.get("part_number") for r in preview.rows}
    assert "P1" in parts or any(
        "Bench" in (r.get("description") or "") for r in preview.rows
    )
