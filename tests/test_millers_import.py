"""Millers Woodshop — locked reader for SKU-only section rows. Out of the 48-book."""

from __future__ import annotations

import io
import json

import pandas as pd
from openpyxl import Workbook

from backend.add_builder import plan_builder
from backend.builder_parsers import GENERIC_PARSER_IDS, identify_reader, preferred_parser_for
from backend.builder_profiles import PROFILES_DIR, vendor_slug
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.millers_import import enhance_millers_long_df, import_millers_workbook, looks_like_millers
from backend.standardize import resolve_builder_vendor
from tests.test_builder_parser_contract import SETTLED
from wide_import import import_workbook


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


def test_looks_like_millers_filename_and_not_millcraft():
    assert looks_like_millers(filename="MWS 2023 Wholesale Price List.xlsx")
    assert looks_like_millers(filename="Millers Woodshop 2028 Pricelist.xlsx")
    assert not looks_like_millers(filename="Millcraft 2028 Pricelist.xlsx")
    assert not looks_like_millers(filename="Millwood Quality Furniture 2028.xlsx")


def test_enhance_fills_description_from_section():
    df = pd.DataFrame(
        [
            {
                "part_number": "36 x 72",
                "description": "36 x 72",
                "collection": "Bookcases",
            },
            {
                "part_number": "M-140",
                "description": "M-140",
                "collection": "Mult-Gun",
            },
        ]
    )
    out = enhance_millers_long_df(df)
    assert out.loc[0, "description"] == "Bookcases 36 x 72"
    assert out.loc[1, "description"] == "Gun M-140"


def test_registry_and_profile_lock_millers():
    entry = DEFAULT_READER_REGISTRY.get("millers_woodshop")
    assert entry is not None
    assert entry.specific is True
    assert entry.vendor == "Millers Woodshop"
    raw = json.loads((PROFILES_DIR / f"{vendor_slug('Millers Woodshop')}.json").read_text())
    locked = (raw.get("parser") or {}).get("importer")
    assert locked == "millers_woodshop"
    assert locked not in GENERIC_PARSER_IDS
    assert preferred_parser_for("Millers Woodshop") == "millers_woodshop"


def test_add_builder_reuses_millers():
    plan = plan_builder("Millers Woodshop")
    assert plan.parser_id == "millers_woodshop"


def test_millers_is_not_settled():
    settled = {row[0] for row in SETTLED}
    assert "Millers Woodshop" not in settled


def test_mws_filename_resolves_and_runs_the_named_reader():
    name = "MWS 2023 Wholesale Price List.xlsx"
    assert resolve_builder_vendor("", filename=name) == "Millers Woodshop"
    vendor, parser_id, source = identify_reader(
        "Millers Woodshop 2028 Pricelist.xlsx",
        sheet_names=["Cover", "Pricelist", "Options"],
    )
    assert vendor == "Millers Woodshop"
    assert parser_id == "millers_woodshop"
    assert source == "saved"


def test_workbook_fills_sku_descriptions_and_keeps_options():
    data = _xlsx(
        {
            "Cover": [["Millers Woodshop"]],
            "Pricelist": [
                ["Item #", "Description", "Oak"],
                ["36 x 72", "36 x 72", 410],
                ["M-140", "M-140", 220],
            ],
            "Options": [
                ["Options"],
                ["Two Toning", "", "ADD 20%"],
                ["Lock: $25"],
            ],
        }
    )
    result = import_workbook(
        data,
        filename="Millers Woodshop 2028 Pricelist.xlsx",
        vendor="Millers Woodshop",
        preferred_parser="millers_woodshop",
    )
    assert result.detected_importer == "millers_woodshop"
    descs = set(result.long_df["description"].astype(str))
    assert any("36 x 72" in desc for desc in descs)
    keys = {
        str(key).strip()
        for key in result.long_df["option_key"].dropna()
        if str(key).strip()
    }
    assert "Two-tone" in keys
    assert "Lock" in keys
    named = import_millers_workbook(
        data, filename="Millers Woodshop 2028 Pricelist.xlsx", vendor="Millers Woodshop"
    )
    assert named.detected_importer == "millers_woodshop"
