"""Tier B SETTLED fixtures must keep their dedicated shape, not a generic unpivot.

Each case is the factory's own reader proof: woods, finish twins, or Options
that the generic guesser historically dropped. Downloads stay extra.
"""

from __future__ import annotations

from tests.fixture_corpus import SETTLED_FIXTURES
from wide_import import import_workbook


def _row(builder: str):
    return next(row for row in SETTLED_FIXTURES if row[0] == builder)


def _parse(builder: str):
    vendor, importer, filename, path, _opts = _row(builder)
    result = import_workbook(
        path.read_bytes(),
        filename=filename,
        vendor=vendor,
        preferred_parser=importer,
    )
    assert result.detected_importer == importer
    df = result.long_df
    kind = df["line_kind"].fillna("item").astype(str).str.lower()
    items = df[kind != "addon"]
    addons = df[kind == "addon"]
    return result, items, addons


def test_ajs_fixture_keeps_fabric_tier_and_options_band():
    _result, items, addons = _parse("AJ's Furniture")
    assert {"Standard", "Premium"} <= set(items["option_key"].astype(str))
    chair = items[items["part_number"].astype(str) == "101 CSC"]
    oak = chair[chair["species"].astype(str) == "Red Oak / Brown Maple"]
    prices = dict(zip(oak["option_key"].astype(str), oak["base_price"]))
    assert prices["Standard"] == 887.45
    assert {"Optional Springs", "Motorized Mechanism"} <= set(addons["option_key"].astype(str))


def test_amish_aspen_fixture_stamps_hickory_aspen():
    _result, items, _addons = _parse("Amish Aspen")
    assert {"Coffee Table", "Night Stand"} <= set(items["part_number"].astype(str))
    assert items["species"].fillna("").astype(str).str.contains("Hickory").any()


def test_brookside_fixture_binds_title_row_woods():
    _result, items, _addons = _parse("Brookside Home Furnishings")
    sixteen = items[items["part_number"].astype(str) == "#16"]
    woods = set(sixteen["species"].astype(str))
    assert "Oak" in woods
    oak_fin = sixteen[
        (sixteen["species"].astype(str) == "Oak") & (sixteen["finish_state"] == "finished")
    ]
    assert float(oak_fin.iloc[0]["base_price"]) == 658.75


def test_fredericksburg_fixture_keeps_left_wholesale_woods():
    _result, items, _addons = _parse("Fredericksburg Furniture")
    sixteen = items[items["part_number"].astype(str) == "#16"]
    assert not sixteen.empty
    woods = set(sixteen["species"].astype(str))
    assert any("Oak" in w for w in woods)
    assert 658.0 in set(float(p) for p in sixteen["base_price"])


def test_frog_pond_fixture_binds_title_row_wood_groups():
    _result, items, addons = _parse("Frog Pond Furniture")
    assert {"100K", "105"} <= set(items["part_number"].astype(str))
    woods = set(items["species"].astype(str))
    assert any("Sap Cherry" in w and "Oak" in w for w in woods)
    keys = {str(k).lower() for k in addons["option_key"].astype(str)}
    assert any("paint" in k for k in keys)


def test_hillside_fixture_expands_unf_fin_under_woods():
    _result, items, _addons = _parse("Hillside Chair")
    assert set(items["finish_state"]) == {"finished", "unfinished"}
    woods = set(items["species"].astype(str))
    assert any("Oak" in w for w in woods)
    assert len(items) >= 4


def test_hogback_fixture_emits_two_wood_groups():
    from backend.hogback_import import GROUP_1, GROUP_2

    _result, items, _addons = _parse("Hogback Design And Finishing")
    woods = set(items["species"].astype(str))
    assert GROUP_1 in woods
    assert GROUP_2 in woods
    assert "HB10" in set(items["part_number"].astype(str))


def test_hope_wood_fixture_expands_markup_calculator_woods():
    _result, items, _addons = _parse("Hope Wood")
    woods = set(items["species"].astype(str))
    assert any("Oak" in w for w in woods)
    assert any("Cherry" in w for w in woods)
    assert "Side Chair" in set(items["part_number"].astype(str)) | set(
        items["description"].astype(str)
    )


def test_j_troyer_fixture_keeps_item_number_not_stain():
    _result, items, _addons = _parse("J. Troyer & Company")
    parts = set(items["part_number"].astype(str))
    assert "7430-64" in parts
    assert "Stain" not in parts
    woods = set(items["species"].astype(str))
    assert any("Maple" in w or "Oak" in w for w in woods)


def test_kidron_fixture_uses_wholesale_twins_not_left_retail():
    _result, items, _addons = _parse("Kidron Woodcraft")
    assert 2180.0 not in set(float(p) for p in items["base_price"])
    brown = items[items["species"].astype(str).str.contains("Brown Maple")]
    assert 716.0 in set(float(p) for p in brown["base_price"])
    assert set(items["finish_state"]) >= {"finished", "unfinished"}


def test_lamb_fixture_keeps_wood_matrix_and_furniture_options():
    _result, items, addons = _parse("LAMB")
    parts = set(items["part_number"].astype(str))
    assert "LA-ASH-3067-EX" in parts
    woods = set(items["species"].fillna("").astype(str))
    assert any("Oak" in w or "Maple" in w for w in woods)
    keys = set(addons["option_key"].astype(str))
    assert "LED Lights" in keys
    assert "Lock" in keys


def test_maple_lane_fixture_reads_code_then_next_row_prices():
    _result, items, addons = _parse("Maple Lane")
    assert "ML10" in set(items["part_number"].astype(str))
    oak = items[items["species"].astype(str).str.contains("Oak", case=False)]
    assert 220.0 in set(float(p) for p in oak["base_price"])
    keys = set(addons["option_key"].astype(str))
    assert "Corian top — Maui Quartz" in keys
    assert "Crypton fabric pad — Breeze" in keys


def test_patio_kraft_fixture_explodes_color_tiers():
    _result, items, _addons = _parse("Patio Kraft")
    parts = set(items["part_number"].astype(str))
    assert {"VECG", "VELC"} <= parts
    glider = items[items["part_number"].astype(str) == "VECG"]
    assert len(glider) >= 2
    assert 210.0 in set(float(p) for p in glider["base_price"])


def test_superior_fixture_skips_retail_twins():
    _result, items, _addons = _parse("Superior Woodcrafts")
    woods = set(items["species"].astype(str))
    assert woods == {"Oak", "Cherry"}
    prices = set(float(p) for p in items["base_price"])
    assert 270 not in prices
    assert 351 not in prices
    assert 100.0 in prices


def test_townline_fixture_keeps_finished_and_unfinished_twins():
    _result, items, _addons = _parse("Townline Furniture")
    assert set(items["finish_state"]) == {"finished", "unfinished"}
    hutch = items[items["part_number"].astype(str) == "TL-25"]
    assert not hutch.empty
    assert 400.0 in set(float(p) for p in hutch["base_price"])


def test_troyer_ridge_fixture_emits_stacked_wood_groups():
    from backend.troyer_ridge_import import GROUP_1, GROUP_2

    _result, items, _addons = _parse("Troyer Ridge Furniture")
    woods = set(items["species"].astype(str))
    assert GROUP_1 in woods
    assert GROUP_2 in woods
    assert items["part_number"].astype(str).str.contains("TR100|Queen|King").any()


def test_windy_acres_fixture_reads_item_hash_and_in_sheet_options():
    _result, items, addons = _parse("Windy Acres Furniture")
    parts = set(items["part_number"].astype(str))
    assert {"1702", "1715-CK"} <= parts
    night = items[items["part_number"].astype(str) == "1702"]
    assert set(night["finish_state"]) == {"finished", "unfinished"}
    keys = {str(k).lower() for k in addons["option_key"].astype(str)}
    assert any("two" in k and "tone" in k for k in keys)
    assert any("paint" in k for k in keys)
    assert any("jewelry" in k for k in keys)
