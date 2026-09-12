"""Five Star Tables — Oak-priced size SKUs and wood % as Wood-column species."""

from __future__ import annotations

import io
import json

import pandas as pd
from openpyxl import Workbook

from backend.add_builder import plan_builder
from backend.builder_parsers import GENERIC_PARSER_IDS, identify_reader, preferred_parser_for
from backend.builder_profiles import PROFILES_DIR, vendor_slug
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.five_star_import import (
    apply_five_star_oak_tables,
    looks_like_five_star,
    parse_five_star_oak_price_sheet,
)
from backend.standardize import resolve_builder_vendor
from wide_import import extract_multi_name_price_catalog, import_workbook

NEXT_FILE = "Five Star Tables 2028 Pricelist.xlsx"
SHEETS = ["Cover", "Tables", "Options"]


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    book = Workbook()
    first = True
    for name, rows in sheets.items():
        sheet = book.active if first else book.create_sheet(name)
        if first:
            sheet.title = name
            first = False
        for row in rows:
            sheet.append(row)
        assert sheet.sheet_state == "visible"
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def _dining_book() -> bytes:
    return _xlsx(
        {
            "Cover": [["Five Star Tables dining"]],
            "Tables": [
                ["Dining Tables"],
                ["42x66", 900],
                ["48x72", 1100],
                ["Side Chair", 200],
            ],
            "Options": [
                ["Options"],
                ["Regular prices listed are in Oak"],
                ["For Walnut, ADD 80%"],
                ["Two Toning", "", "ADD 20%"],
                ["Lock: $25"],
                ["Terms"],
                ["Net 30"],
            ],
        }
    )


def _items(df: pd.DataFrame) -> pd.DataFrame:
    kind = df["line_kind"].fillna("item").astype(str).str.lower()
    return df[kind != "addon"]


def test_generic_multi_name_price_drops_size_skus():
    raw = pd.DataFrame(
        [
            ["Dining Tables", None],
            ["42x66", 900],
            ["48x72", 1100],
            ["Side Chair", 200],
        ]
    )
    dropped = extract_multi_name_price_catalog(raw, vendor="Five Star Tables")
    parts = (
        set(dropped["part_number"].astype(str))
        if dropped is not None and not dropped.empty
        else set()
    )
    assert "42x66" not in parts
    assert "48x72" not in parts


def test_shape_reader_keeps_size_skus_as_oak():
    raw = pd.DataFrame([["Dining Tables", None], ["42x66", 900], ["Side Chair", 200]])
    parsed = parse_five_star_oak_price_sheet(raw, vendor="Five Star Tables")
    parts = set(parsed["part_number"].astype(str))
    assert "42x66" in parts
    assert "Side Chair" in parts
    stamped = apply_five_star_oak_tables(parsed)
    table = stamped[stamped["part_number"].astype(str) == "42x66"]
    assert "Oak" in set(table["species"].astype(str))
    walnuts = table[table["species"].astype(str) == "Walnut"]
    assert not walnuts.empty
    assert float(walnuts["base_price"].iloc[0]) == 1620


def test_detects_five_star_by_name_and_not_a_generic_dining_book():
    assert looks_like_five_star(filename=NEXT_FILE, sheet_names=SHEETS)
    assert not looks_like_five_star(
        filename="Dining Furniture 2028 Pricelist.xlsx",
        sheet_names=["Cover", "Tables"],
    )


def test_registry_and_profile_lock_five_star():
    entry = DEFAULT_READER_REGISTRY.get("five_star_tables")
    assert entry is not None
    assert entry.specific is True
    assert entry.vendor == "Five Star Tables"
    raw = json.loads((PROFILES_DIR / f"{vendor_slug('Five Star Tables')}.json").read_text())
    assert (raw.get("parser") or {}).get("importer") == "five_star_tables"
    assert preferred_parser_for("Five Star Tables") == "five_star_tables"
    assert preferred_parser_for("Five Star Tables") not in GENERIC_PARSER_IDS


def test_add_builder_reuses_five_star_and_refuses_generic():
    plan = plan_builder("Five Star Tables")
    assert plan.parser_id == "five_star_tables"


def test_next_year_file_resolves_to_five_star():
    assert resolve_builder_vendor(NEXT_FILE, filename=NEXT_FILE) == "Five Star Tables"
    vendor, parser_id, source = identify_reader(NEXT_FILE, sheet_names=SHEETS)
    assert vendor == "Five Star Tables"
    assert parser_id == "five_star_tables"
    assert source == "saved"


def test_workbook_keeps_oak_woods_and_real_options():
    data = _dining_book()
    result = import_workbook(
        data,
        filename=NEXT_FILE,
        vendor="Five Star Tables",
        preferred_parser="five_star_tables",
    )
    assert result.detected_importer == "five_star_tables"
    items = _items(result.long_df)
    table = items[items["part_number"].astype(str) == "42x66"]
    assert "Oak" in set(table["species"].astype(str))
    walnuts = table[table["species"].astype(str) == "Walnut"]
    assert not walnuts.empty
    assert float(walnuts["base_price"].iloc[0]) == 1620
    keys = {
        str(key).strip()
        for key in result.long_df["option_key"].dropna()
        if str(key).strip()
    }
    assert "Two-tone" in keys
    assert "Lock" in keys
    assert "Walnut" not in keys
    assert "Terms" not in keys
    assert "Net 30" not in keys
    addons = result.long_df[result.long_df["line_kind"].fillna("item") == "addon"]
    assert not addons.empty


def test_existing_cherry_row_is_not_overwritten():
    df = pd.DataFrame(
        [
            {
                "vendor": "Five Star Tables",
                "part_number": "SC-1",
                "species": "Cherry",
                "line_kind": "item",
                "base_price": 200,
            }
        ]
    )
    out = apply_five_star_oak_tables(df)
    chair = out[out["part_number"].astype(str) == "SC-1"]
    assert "Cherry" in set(chair["species"].astype(str))
    oak = chair[chair["species"].astype(str) == "Oak"]
    assert oak.empty
