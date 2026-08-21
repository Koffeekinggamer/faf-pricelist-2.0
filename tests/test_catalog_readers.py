"""Each catalog builder has a named reader so next year's Drop reuses it."""

from __future__ import annotations

import io

import openpyxl
import pandas as pd

from backend.builder_parsers import guess_named_parser, identify_reader
from backend.builder_profiles import filename_hints_for, match_profile_vendor
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.catalog_readers import CATALOG_SPECS, apply_catalog_description_fixes
from wide_import import import_workbook


def _book(vendor_on_cover: str) -> bytes:
    wb = openpyxl.Workbook()
    cover = wb.active
    cover.title = "Cover"
    cover.append([vendor_on_cover])
    ws = wb.create_sheet("Catalog")
    ws.append(["Part #", "Description", "Species", "Wholesale"])
    ws.append(["T1", "Side Table", "Oak", 100])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_filename_hints_drop_viztech_download_stems():
    hints = filename_hints_for(
        "Black Horse Furniture", "Download_2026_Pricelist_286628.xlsx"
    )
    assert "black horse furniture" in hints
    assert "download" not in hints
    assert not any(h.startswith("download") for h in hints)


def test_filename_hints_include_catalog_spec_tokens():
    hints = filename_hints_for("Brookside Home Furnishings")
    assert "brookside" in hints
    assert "brookside home furnishings" in hints


def test_catalog_readers_do_not_bind_looks_like_globals():
    import backend.catalog_readers as catalog_readers

    assert not hasattr(catalog_readers, "looks_like_black_horse_furniture")
    entry = DEFAULT_READER_REGISTRY.get("black_horse_furniture")
    assert entry.detect_fn is not None
    assert entry.reader_fn is not None
    assert entry.detector == ""


def test_every_catalog_builder_has_a_specific_reader():
    ids = set(DEFAULT_READER_REGISTRY.specific_ids)
    for spec in CATALOG_SPECS:
        assert spec.parser_id in ids
        assert DEFAULT_READER_REGISTRY.get(spec.parser_id).vendor == spec.vendor


def test_next_year_named_file_resolves_to_the_catalog_reader():
    vendor, parser_id = guess_named_parser(
        "Black Horse Furniture/Download_2027_Pricelist.xlsx"
    )
    assert parser_id == "black_horse_furniture"
    assert vendor == "Black Horse Furniture"


def test_xlsx_cover_name_resolves_when_filename_is_viztech_download():
    data = _book("Black Horse Furniture Wholesale")
    vendor, parser_id = guess_named_parser(
        "Download_2027_Pricelist_99999.xlsx",
        data=data,
    )
    assert parser_id == "black_horse_furniture"
    assert vendor == "Black Horse Furniture"


def test_catalog_reader_tags_and_parses_through_generic_unpivot():
    data = _book("Elite Designs")
    result = import_workbook(
        data,
        filename="Elite Designs 2028 Pricelist.xlsx",
        vendor="Elite Designs",
    )
    assert result.detected_importer == "elite_designs"
    assert not result.long_df.empty


def test_ajs_folder_name_with_html_apostrophe_still_matches():
    vendor, parser_id = guess_named_parser(
        "AJ_039_s_Furniture/Download_2027_Pricelist_Finished.xls"
    )
    assert parser_id == "ajs_furniture"
    assert vendor == "AJ's Furniture"


def test_identify_reader_agrees_with_import_workbook():
    data = _book("Black Horse Furniture Wholesale")
    name = "Download_2027_Pricelist_99999.xlsx"
    vendor, parser_id, source = identify_reader(name, data=data)
    result = import_workbook(data, filename=name)
    assert vendor == "Black Horse Furniture"
    assert parser_id == "black_horse_furniture"
    assert source == "guessed"
    assert result.detected_importer == parser_id
    assert result.parser_source == source


def test_bare_download_filename_does_not_match_a_locked_builder():
    assert match_profile_vendor("Download_2027_Pricelist_111.xlsx") is None


def test_ajs_fabric_tier_is_option_not_part_number():
    parsed = pd.DataFrame(
        [
            {
                "part_number": "Leather",
                "description": "101 CSC",
                "option_key": None,
                "species": "RED OAK & BROWN MAPLE",
                "base_price": 1132.10,
            }
        ]
    )

    fixed = apply_catalog_description_fixes(parsed, "AJ's Furniture")

    assert fixed.loc[0, "part_number"] == "101 CSC"
    assert fixed.loc[0, "description"] == "101 CSC"
    assert fixed.loc[0, "option_key"] == "Leather"


def test_integ_upgrades_are_addons_not_fake_catalog_items():
    parsed = pd.DataFrame(
        [
            {
                "collection": "Upgrades / Options",
                "part_number": "#PS2",
                "description": "#PS2",
                "dimensions": "Power Strip, Two 110v, 3 USB",
                "option_key": None,
                "line_kind": None,
                "base_price": 85.0,
            },
            {
                "collection": "#5200 Wall Unit",
                "part_number": "5200",
                "description": "5200",
                "dimensions": '45” TV Opening',
                "option_key": None,
                "line_kind": "item",
                "base_price": 2466.0,
            },
            {
                "collection": "Upgrades",
                "part_number": "Custom Hardware (Not in stock)",
                "description": "Custom Hardware (Not in stock)",
                "dimensions": "Non-stock hardware is $3 per pull/knob",
                "option_key": None,
                "line_kind": None,
                "base_price": 3.0,
            },
        ]
    )

    fixed = apply_catalog_description_fixes(parsed, "INTEG Wood Products")
    upgrade = fixed.iloc[0]

    assert upgrade["line_kind"] == "addon"
    assert upgrade["option_key"] == "Power Strip, Two 110v, 3 USB"
    assert upgrade["part_number"] == "Power Strip, Two 110v, 3 USB"
    assert fixed.iloc[1]["line_kind"] == "item"
    assert fixed.iloc[2]["option_key"].endswith("Per Pull/Knob")


def test_mirror_lake_unfinished_book_keeps_its_finish_twin():
    parsed = pd.DataFrame(
        [
            {
                "part_number": "ML-10-DMB",
                "description": "10 Drawer Mule Box",
                "finish_state": "finished",
                "base_price": 900.0,
            }
        ]
    )

    fixed = apply_catalog_description_fixes(
        parsed,
        "Mirror Lake Woodworks",
        filename="Download_2026_Unfinished_Pricelist_695524.xls",
    )

    assert fixed.loc[0, "finish_state"] == "unfinished"


def test_integ_section_name_replaces_sheet_name_collection():
    parsed = pd.DataFrame(
        [
            {
                "part_number": "5200",
                "description": "5200",
                "collection": "Wall Units 1",
                "dimensions": '45" TV Opening',
            }
        ]
    )

    fixed = apply_catalog_description_fixes(
        parsed,
        "INTEG Wood Products",
        product_context={("Wall Units 1", "5200"): "#5200 Wall Unit"},
    )

    assert fixed.loc[0, "collection"] == "#5200 Wall Unit"


def test_hermies_style_header_replaces_instruction_collection():
    parsed = pd.DataFrame(
        [
            {
                "part_number": "HTS1100-4260",
                "description": "42 x 60",
                "collection": "Additional shapes available at no extra charge",
            }
        ]
    )

    fixed = apply_catalog_description_fixes(
        parsed,
        "Hermies Table Shop",
        product_context={
            ("", "HTS1100-4260"): "652 Mission Double Pedestal Table"
        },
    )

    assert (
        fixed.loc[0, "collection"]
        == "652 Mission Double Pedestal Table"
    )
