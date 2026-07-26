"""Wide + flat Excel import (no v1 sys.path dependency)."""

import io

import openpyxl

from backend.config import password_matches
from backend.import_excel import parse_excel
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
    result = parse_excel(
        data, filename="Hopewood_Price_List.xlsx", vendor="", multiplier=2.7
    )
    assert result["engine"] == "wide"
    assert result["row_count"] >= 6  # 2 parts × 3 woods
    species = {r.get("species") for r in result["rows"]}
    assert any("oak" in (s or "").lower() for s in species)
    prices = {r["base_price"] for r in result["rows"]}
    assert 500.0 in prices
    assert 140.0 in prices


def test_flat_table_fallback():
    data = _xlsx_bytes(
        [
            ["Part #", "Description", "Wood", "Wholesale"],
            ["P1", "Bench", "Maple", 220],
            ["P2", "Stool", "Oak", 90],
        ],
        sheet="Catalog",
    )
    result = parse_excel(
        data, filename="FlatBuilder.xlsx", vendor="Flat Builder", multiplier=2.7
    )
    assert result["row_count"] >= 2
    assert result["engine"] in ("wide", "simple")
    parts = {r.get("part_number") for r in result["rows"]}
    assert "P1" in parts or any("Bench" in (r.get("description") or "") for r in result["rows"])


def test_resolve_builder_from_filename():
    name = resolve_builder_vendor("", filename="MWS 2023 Wholesale Price List.xlsx")
    assert name == "Millers Woodshop"


def test_password_hash_auth():
    import hashlib

    digest = hashlib.sha256(b"Amish").hexdigest()
    assert password_matches("Amish", expected_hash=f"sha256:{digest}")
    assert not password_matches("wrong", expected_hash=f"sha256:{digest}")
    assert password_matches("Amish", expected_plain="Amish")
    assert not password_matches("Amish", expected_plain="Nope")
