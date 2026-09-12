"""Criswell Bedroom — four factory books, one vendor catalog."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest

from backend.builder_parsers import guess_named_parser
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.criswell_import import looks_like_criswell
from backend.drop_parse_session import evaluate_readiness
from backend.import_service import ImportService
from backend.standardize import resolve_builder_vendor

DOWNLOADS = Path.home() / "Downloads" / "CWF_Pricelists_2025_1224"
WHOLESALE = DOWNLOADS / "Wholesale Price List.xlsx"
BEDS_AF = DOWNLOADS / "Beds A-F.xlsx"
BEDS_HW = DOWNLOADS / "Beds H-W.xlsx"
LIVING = DOWNLOADS / "Living Rooms Price List.xlsx"


def test_ole_xls_does_not_claim_criswell_from_binary_noise():
    ole = b"\xd0\xcf\x11\xe0" + b"CWF8111" + b"\x00" * 40
    assert not looks_like_criswell("Download_2026_Pricelist.xls", [], ole)
    vendor, parser_id = guess_named_parser("Download_2026_Pricelist.xls", data=ole)
    assert parser_id != "criswell"
    assert vendor != "Criswell Bedroom"


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_cwf_filenames_resolve_to_criswell_bedroom():
    assert resolve_builder_vendor("CWF") == "Criswell Bedroom"
    assert resolve_builder_vendor("Criswell Furniture") == "Criswell Bedroom"
    assert resolve_builder_vendor("", filename="Beds A-F.xlsx") == "Criswell Bedroom"
    assert resolve_builder_vendor("", filename="Beds H-W.xlsx") == "Criswell Bedroom"
    assert (
        resolve_builder_vendor("", filename="Living Rooms Price List.xlsx")
        == "Criswell Bedroom"
    )
    assert resolve_builder_vendor("", filename="Wholesale Price List.xlsx") is None
    assert looks_like_criswell("Living Rooms Price List.xlsx", ["Markup", "Cover", "Sheet2"])
    assert looks_like_criswell("Beds A-F.xlsx", ["Markup", "Beds For Every Taste"])
    assert looks_like_criswell("Beds H-W.xlsx", ["Markup", "Beds For Every Taste (2)"])
    assert looks_like_criswell(
        "Wholesale Price List.xlsx",
        ["Markup", "Cover", "Bloomfield Collection", "Options "],
    )
    vendor, parser_id = DEFAULT_READER_REGISTRY.detect(
        "CWF_Pricelists_2025_1224/Wholesale Price List.xlsx",
        sheet_names=["Markup", "Cover", "Bloomfield Collection"],
    )
    assert vendor == "Criswell Bedroom"
    assert parser_id == "criswell"


def test_criswell_reader_keeps_left_wholesale_copy_and_options():
    data = _xlsx(
        {
            "Markup": [["Enter Markup"], [1]],
            "Cover": [["CRISWELL FURNITURE"]],
            "Options ": [
                ["Options", None, "Oak", None, "Cherry"],
                ["Phone Charger", 55, None, 55, None],
            ],
            "Bloomfield Collection": [
                [
                    "CWF8100 Series Bloomfield Set",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "CWF8100 Series Bloomfield Set",
                ],
                [None, None, "Oak", None, "Cherry", None, "QSWO", None, None, None, "Oak"],
                [
                    "CWF8111",
                    "Tall Dresser",
                    1099,
                    None,
                    1170,
                    None,
                    1359,
                    None,
                    "CWF8111",
                    "Tall Dresser",
                    1099,
                    None,
                    1170,
                    None,
                    1359,
                ],
            ],
        }
    )
    result = DEFAULT_READER_REGISTRY.run(
        "criswell", data, vendor="Criswell Bedroom", filename="Wholesale Price List.xlsx"
    )
    assert result is not None
    items = result.long_df[result.long_df["line_kind"].fillna("item") != "addon"]
    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    assert len(items) == 3
    oak = items[items["species"].fillna("").astype(str).str.contains("Oak", case=False)]
    assert not oak.empty
    assert float(oak.iloc[0]["base_price"]) == 1099.0
    assert oak.iloc[0]["collection"] == "Bloomfield"
    assert "Phone Charger" in set(addons["option_key"].astype(str))
    assert result.expected_option_lines == 1


def test_criswell_deduct_option_is_emitted_as_a_negative_charge():
    data = _xlsx(
        {
            "Markup": [["Enter Markup"], [1]],
            "Cover": [["CRISWELL FURNITURE"]],
            "Options ": [
                ["Options", None, "Oak"],
                ['20" high low footboard (DEDUCT)', 203],
            ],
            "Bloomfield Collection": [
                [None, None, "Oak"],
                ["CWF8111", "Tall Dresser", 1099],
            ],
        }
    )

    result = DEFAULT_READER_REGISTRY.run(
        "criswell", data, vendor="Criswell Bedroom", filename="Wholesale Price List.xlsx"
    )
    deduct = result.long_df[
        result.long_df["option_key"] == '20" high low footboard (DEDUCT)'
    ]

    assert len(deduct) == 1
    assert float(deduct.iloc[0]["base_price"]) == -203.0


def test_criswell_option_gate_counts_source_lines_not_emitted_rows(monkeypatch):
    """Options tab can go silent and Load must still block (ADR-0011)."""
    data = _xlsx(
        {
            "Markup": [["Enter Markup"], [1]],
            "Cover": [["CRISWELL FURNITURE"]],
            "Options ": [
                ["Options", None, "Oak", None, "Cherry"],
                ["Phone Charger", 55, None, 55, None],
            ],
            "Bloomfield Collection": [
                [None, None, "Oak", None, "Cherry"],
                ["CWF8111", "Tall Dresser", 1099, None, 1170],
            ],
        }
    )
    import backend.book_options as book_options
    import backend.criswell_import as criswell_import

    monkeypatch.setattr(criswell_import, "_parse_options", lambda *a, **k: [])
    monkeypatch.setattr(book_options, "extract_book_options", lambda *a, **k: [])
    preview = ImportService().preview_excel(
        data,
        filename="Wholesale Price List.xlsx",
        vendor="Criswell Bedroom",
        multiplier=2.7,
    )
    assert preview.detected_importer == "criswell"
    assert preview.priced_option_count == 1
    assert not any(str(r.get("line_kind") or "") == "addon" for r in preview.rows)
    readiness = evaluate_readiness(
        {
            "rows": preview.rows,
            "priced_option_count": preview.priced_option_count,
        }
    )
    assert readiness.load_ready is False
    assert readiness.block_code == "options_missing"


def test_live_cwf_wholesale_parses_bloomfield_and_options():
    if not WHOLESALE.is_file():
        pytest.skip(f"{WHOLESALE.name} not on this machine")
    preview = ImportService().preview_excel(
        WHOLESALE.read_bytes(),
        filename=WHOLESALE.name,
        vendor="Criswell Bedroom",
        multiplier=2.7,
    )
    items = [r for r in preview.rows if str(r.get("line_kind") or "item") != "addon"]
    addons = [r for r in preview.rows if str(r.get("line_kind") or "") == "addon"]
    assert any(str(r.get("part_number") or "").startswith("CWF8111") for r in items)
    oak = [
        r
        for r in items
        if str(r.get("part_number") or "").startswith("CWF8111")
        and "oak" in str(r.get("species") or "").lower()
        and "white" not in str(r.get("species") or "").lower()
    ]
    assert oak and float(oak[0]["base_price"]) == 1099.0
    assert any("Phone Charger" in str(r.get("option_key") or "") for r in addons)
    assert preview.priced_option_count >= 1


def test_living_rooms_banner_sets_collection():
    data = _xlsx(
        {
            "Markup": [["Enter Markup"], [1]],
            "Sheet2": [
                ["Art & Craft Collection"],
                [None, None, "Oak / Brown Maple", None, "Cherry / QSWO"],
                ["CWF #3044", "T.V. Stand", 285, None, 329],
            ],
        }
    )
    result = DEFAULT_READER_REGISTRY.run(
        "criswell",
        data,
        vendor="Criswell Bedroom",
        filename="Living Rooms Price List.xlsx",
    )
    assert result is not None
    items = result.long_df[result.long_df["line_kind"].fillna("item") != "addon"]
    assert set(items["collection"].astype(str)) == {"Art & Craft"}
    oak = items[items["species"].fillna("").astype(str).str.contains("Oak", case=False)]
    assert not oak.empty
    assert float(oak.iloc[0]["base_price"]) == 285.0
    assert str(oak.iloc[0]["part_number"]) == "CWF3044"
    assert result.expected_option_lines == 0
