"""LuxHome Seating — AJ's upholstery book, priced by fabric grade.

The book ships inside AJ's Viztech folder and prints the same template as AJ's
own pricelist: SKU, description, four fabric-grade price columns, an OPTIONS
band on the right, and two reference charts (fabric yardage, leather square
footage) that read like numbers but are not money.

The old generic reader put the fabric grade in the wood column, captured none
of the OPTIONS band, and only named a section when the banner happened to
contain the word "Collection".
"""

import io
import json

import pandas as pd
import pytest

from backend.add_builder import AddBuilderError, plan_builder
from backend.builder_identity import WATCHED_SHORT_TOKENS, is_short_token, matching_readers
from backend.builder_parsers import GENERIC_PARSER_IDS, identify_reader, preferred_parser_for
from backend.builder_profiles import PROFILES_DIR, vendor_slug
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.luxhome_import import import_luxhome_workbook, looks_like_luxhome
from wide_import import import_workbook


def _book(rows: list[list], sheet: str = "Wholesale MARKUP") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False, header=False)
    return buffer.getvalue()


TIERS = [
    None,
    None,
    None,
    "Standard",
    "Premium",
    "Ultra Leather",
    "Genuine Leather",
]
OPTIONS_HEADER = [
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    "MOTORIZED MECHANISM ADD",
    "RECHARGABLE BATTERY PACK ADD",
    "FABRIC YARDAGE CHART",
    "LEATHER SQ FOOTAGE CHART",
]


def _harmony_book() -> bytes:
    return _book(
        [
            ["Harmony Collection", None, None, None, None, None, None],
            OPTIONS_HEADER,
            TIERS,
            ["21 HRR", "Harmony Rocker Recliner", None, 764.4, 795.9, 953.4, 1197.0, None, 80, 100, "7 yd", "124 sq.ft."],
        ]
    )


LUXHOME_NEXT_FILE = "Download_2026_LuxHome_Pricelist_648810.xls"
LUXHOME_SHEETS = ["Wholesale MARKUP"]


def test_detects_the_luxhome_book_by_name():
    assert looks_like_luxhome(
        filename=LUXHOME_NEXT_FILE,
        sheet_names=LUXHOME_SHEETS,
    )
    assert not looks_like_luxhome(
        filename="Download_2026_Pricelist_Finished_301390.xls",
        sheet_names=["Finished Wholesale MARKUP"],
    )


def test_registry_points_detector_and_reader_at_luxhome_import():
    entry = DEFAULT_READER_REGISTRY.get("luxhome")
    assert entry is not None
    assert entry.vendor == "LuxHome"
    assert entry.specific is True
    assert entry.detector == "backend.luxhome_import:looks_like_luxhome"
    assert entry.reader == "backend.luxhome_import:import_luxhome_workbook"
    assert entry.detector.startswith("backend.luxhome_import:")
    assert entry.reader.startswith("backend.luxhome_import:")
    assert not entry.detector.startswith("wide_import:")
    assert not entry.reader.startswith("wide_import:")


def test_locked_profile_names_luxhome_importer():
    path = PROFILES_DIR / f"{vendor_slug('LuxHome')}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    parser = raw.get("parser") or {}
    locked = str(parser.get("importer") or "")
    assert raw.get("vendor") == "LuxHome"
    assert locked == "luxhome"
    assert locked not in GENERIC_PARSER_IDS
    assert parser.get("locked") is True
    hints = [str(hint).strip().lower() for hint in (parser.get("filename_hints") or [])]
    assert "luxhome" in hints
    assert not any(is_short_token(hint) for hint in hints)
    assert not any(hint in WATCHED_SHORT_TOKENS for hint in hints)
    assert preferred_parser_for("LuxHome") == "luxhome"


def test_add_builder_reuses_luxhome_and_refuses_generic():
    plan = plan_builder("LuxHome", kind="shape", source_file=LUXHOME_NEXT_FILE)
    assert plan.vendor == "LuxHome"
    assert plan.parser_id == "luxhome"
    assert plan.parser_id not in GENERIC_PARSER_IDS
    assert plan.kind == "shape"
    assert plan.reader_entry is not None
    assert plan.reader_entry.detector.startswith("backend.luxhome_import:")
    assert plan.reader_entry.reader.startswith("backend.luxhome_import:")
    with pytest.raises(AddBuilderError, match="luxhome"):
        plan_builder("LuxHome", parser_id="generic")


def test_identify_reader_locks_luxhome_on_the_book_name():
    hits = matching_readers(LUXHOME_NEXT_FILE, sheet_names=LUXHOME_SHEETS)
    assert {hit.parser_id for hit in hits} == {"luxhome"}
    vendor, parser_id, source = identify_reader(
        LUXHOME_NEXT_FILE, sheet_names=LUXHOME_SHEETS
    )
    assert vendor == "LuxHome"
    assert parser_id == "luxhome"
    assert source == "saved"


def test_import_workbook_uses_luxhome_import_and_proves_options():
    result = import_workbook(
        _harmony_book(),
        vendor="LuxHome",
        filename=LUXHOME_NEXT_FILE,
    )
    assert result.detected_importer == "luxhome"
    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    assert not addons.empty, "empty Options is a capture miss"
    assert dict(zip(addons["option_key"], addons["base_price"])) == {
        "Motorized Mechanism": 80.0,
        "Rechargable Battery Pack": 100.0,
    }


def test_fabric_grade_is_the_option_and_the_wood_column_stays_empty():
    """Upholstery is priced by fabric, not by species.

    ``Ultra Leather`` in the Wood column is not a wood, and the floor filters
    Wood by species.
    """
    result = import_luxhome_workbook(
        _harmony_book(), vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    )

    items = result.long_df[result.long_df["line_kind"] == "item"]
    assert set(items["species"].fillna("")) == {""}
    assert dict(zip(items["option_key"], items["base_price"])) == {
        "Standard": 764.4,
        "Premium": 795.9,
        "Ultra Leather": 953.4,
        "Genuine Leather": 1197.0,
    }


def test_the_options_band_lands_as_addon_charges_once_per_sku():
    result = import_luxhome_workbook(
        _harmony_book(), vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    )

    addons = result.long_df[result.long_df["line_kind"] == "addon"]
    assert dict(zip(addons["option_key"], addons["base_price"])) == {
        "Motorized Mechanism": 80.0,
        "Rechargable Battery Pack": 100.0,
    }
    assert set(addons["part_number"]) == {"21 HRR"}


def test_the_yardage_and_leather_charts_are_never_prices():
    result = import_luxhome_workbook(
        _harmony_book(), vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    )

    prices = set(result.long_df["base_price"].dropna())
    assert 7.0 not in prices and 124.0 not in prices
    blob = " ".join(str(v) for v in result.long_df["option_key"].fillna("")).lower()
    assert "yardage" not in blob and "sq.ft" not in blob


def test_a_section_banner_names_the_collection_without_the_word_collection():
    """``Oaklee Swivel Chairs`` and ``FOOTSTOOLS`` are sections too."""
    book = _book(
        [
            ["Oaklee Swivel Chairs", None, None, None, None, None, None],
            TIERS,
            ["301 OSC", "Oaklee Swivel Chair", None, 709.8, 741.3, 898.8, 1127.7],
            ["FOOTSTOOLS", None, None, None, None, None, None],
            TIERS,
            ["FRF22", 'Fusion 22" Round Footstool', None, 302.4, 315.0, 378.0, 472.5],
        ]
    )

    rows = import_luxhome_workbook(
        book, vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    ).long_df

    assert dict(zip(rows["part_number"], rows["collection"])) == {
        "301 OSC": "Oaklee Swivel Chairs",
        "FRF22": "Footstools",
    }


def test_a_product_description_never_becomes_a_collection():
    """Sectional names print alone in the description column and read like banners."""
    book = _book(
        [
            ["Harmony Collection", None, None, None, None, None, None],
            TIERS,
            [None, "5-Piece Sectional w/ Reclining Ends", None, None, None, None, None],
            ["30 H5PS", "Harmony WH 5-Piece Sectional", None, 4300.5, 4483.5, 5397.0, 6772.5],
        ]
    )

    rows = import_luxhome_workbook(
        book, vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    ).long_df

    assert set(rows["collection"]) == {"Harmony Collection"}
    assert set(rows["part_number"]) == {"30 H5PS"}


def test_pillows_price_by_grade_down_the_rows_under_one_price_column():
    book = _book(
        [
            ["Pillows", None, None, None, None, None, None, None],
            [None, "*Price per pillow", None, "PRICE", None, None, None, "LEATHER SQ FOOTAGE CHART"],
            ["213 SP", "13x13 Small Pillow", "Standard", 32.55, None, None, None, "15 sq.ft."],
            ["213 SP", "13x13 Small Pillow", "Genuine Leather", 77.5, None, None, None, "15 sq.ft."],
        ]
    )

    rows = import_luxhome_workbook(
        book, vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    ).long_df

    pillow = rows[rows["part_number"] == "213 SP"]
    assert set(pillow["collection"]) == {"Pillows"}
    assert dict(zip(pillow["option_key"], pillow["base_price"])) == {
        "Standard": 32.55,
        "Genuine Leather": 77.5,
    }
    assert set(pillow["species"].fillna("")) == {""}


def test_an_included_option_is_kept_as_a_no_charge_choice():
    """``0`` in the Nail Heads column means included, not missing."""
    book = _book(
        [
            ["Ellington Collection", None, None, None, None, None, None],
            [None, None, None, None, None, None, None, None, "OPTIONAL FOAM BACKS ADD", "Nail Heads"],
            TIERS,
            ["1114-EL", "Ellington Corner Seat", None, 1000.0, 1050.0, 1200.0, 1400.0, None, 77.7, 0],
        ]
    )

    addons = import_luxhome_workbook(
        book, vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    ).long_df
    addons = addons[addons["line_kind"] == "addon"]

    assert dict(zip(addons["option_key"], addons["base_price"])) == {
        "Optional Foam Backs": 77.7,
        "Nail Heads": 0.0,
    }


def test_an_options_band_does_not_leak_into_the_next_section():
    book = _book(
        [
            ["Harmony Collection", None, None, None, None, None, None],
            OPTIONS_HEADER,
            TIERS,
            ["21 HRR", "Harmony Rocker Recliner", None, 764.4, None, None, None, None, 80, 100],
            ["Serene Collection (Fully Modular)", None, None, None, None, None, None],
            TIERS,
            ["10 SC-FA", "Serene Chair Flat Arm", None, 602.0, None, None, None, None, 999, 999],
        ]
    )

    rows = import_luxhome_workbook(
        book, vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    ).long_df

    serene = rows[rows["part_number"] == "10 SC-FA"]
    assert set(serene["line_kind"]) == {"item"}
    assert 999.0 not in set(rows["base_price"].dropna())


def test_page_furniture_never_becomes_a_product_or_a_section():
    book = _book(
        [
            ["Effective May 11, 2026", None, None, None, None, None, None],
            ["Wholesale", None, None, None, None, None, None],
            ["LuxHome Seating", None, None, None, None, None, None],
            ["5355W 400S, Topeka, IN 46571", None, None, None, None, None, None],
            ["Email: sales@ajsfurniture.net", None, None, None, None, None, None],
            ["LuxHome Seating WARRANTY", None, None, None, None, None, None],
            ["Harmony Collection", None, None, None, None, None, None],
            TIERS,
            ["21 HRR", "Harmony Rocker Recliner", None, 764.4, None, None, None],
        ]
    )

    rows = import_luxhome_workbook(
        book, vendor="LuxHome", filename="LuxHome_Pricelist.xls"
    ).long_df

    assert set(rows["part_number"]) == {"21 HRR"}
    assert set(rows["collection"]) == {"Harmony Collection"}
