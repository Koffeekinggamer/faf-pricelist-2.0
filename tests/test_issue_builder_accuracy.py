"""Accuracy fixes for the seven builders that failed inspection."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from backend.book_options import extract_book_options
from backend.catalog_readers import apply_five_star_oak_tables
from backend.hogback_import import GROUP_1 as HOG_1
from backend.hogback_import import GROUP_2 as HOG_2
from backend.hogback_import import import_hogback_workbook
from backend.superior_import import import_superior_workbook
from wide_import import import_amish_aspen_workbook, import_workbook

ASPEN = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717/"
    "Amish_Aspen_and_Rustic/Download_2026_Pricelist_1501888.xlsx"
)
SUPERIOR = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717/"
    "Superior_Woodcrafts/Download_2026_Pricelist_687470.xlsx"
)
HOGBACK = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717/"
    "Hogback_Design_And_Finishing/Download_2026_Pricelist_2196.xlsx"
)
LAMB = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717/"
    "Lamb_Woodworking/Download_2026_Pricelist_23191.xlsx"
)
FIVE_STAR = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717/"
    "Five_Star_Tables/Download_2026_Dining_Furniture_Pricelist_296087.xlsx"
)


def _xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


def test_superior_uses_wood_column_and_skips_retail():
    data = _xlsx(
        [
            [
                "ITEM #",
                "DESCRIPTION",
                "WOOD SPECIES",
                "UNFINISHED",
                "FINISHED",
                "UNFIN.RETAIL",
                "FIN.RETAIL",
            ],
            ["A1", "Desk", "Oak", 100, 130, 270, 351],
            ["A1C", "Desk", "Cherry", 120, 150, 324, 405],
        ]
    )
    df = import_superior_workbook(data, filename="superior.xlsx").long_df
    items = df[df["line_kind"].fillna("item") != "addon"]
    woods = set(items["species"])
    assert woods == {"Oak", "Cherry"}
    assert set(items["finish_state"]) == {"unfinished", "finished"}
    assert 270 not in set(items["base_price"])
    assert 351 not in set(items["base_price"])
    assert len(items) == 4


def test_five_star_blank_tables_are_oak():
    df = pd.DataFrame(
        [
            {
                "vendor": "Five Star Tables",
                "part_number": "42x66",
                "species": None,
                "line_kind": "item",
                "base_price": 900,
            },
            {
                "vendor": "Five Star Tables",
                "part_number": "Side",
                "species": "Cherry",
                "line_kind": "item",
                "base_price": 200,
            },
        ]
    )
    out = apply_five_star_oak_tables(df)
    items = out[out["line_kind"] != "addon"]
    by = {r["part_number"]: r["species"] for _, r in items.iterrows()}
    assert by["42x66"] == "Oak"
    assert by["Side"] == "Cherry"
    assert "Walnut" in set(out["option_key"].dropna())


def test_walnut_percent_is_a_search_option():
    data = _xlsx([["For Walnut, ADD 50% to Oak pricing."]])
    rows = extract_book_options(data, vendor="LAMB")
    by = {r["option_key"]: r for r in rows}
    assert "Walnut" in by
    assert by["Walnut"]["addon_pct"] == 50.0


def test_amish_aspen_live_file_stamps_hickory_aspen():
    if not ASPEN.exists():
        return
    df = import_amish_aspen_workbook(ASPEN.read_bytes(), filename=ASPEN.name).long_df
    assert len(df) >= 30
    assert df["species"].fillna("").ne("").all()
    assert "Hickory / Aspen" in set(df["species"])


def test_superior_live_file_has_named_woods_no_retail_twins():
    if not SUPERIOR.exists():
        return
    df = import_workbook(
        SUPERIOR.read_bytes(), vendor="Superior Woodcrafts", filename=SUPERIOR.name
    ).long_df
    items = df[df["line_kind"].fillna("item") != "addon"]
    woods = set(items["species"].dropna())
    assert "Oak" in woods
    assert "Wood Tier 1" not in woods
    assert "FINISHED" not in woods
    blank = int(items["species"].fillna("").astype(str).str.strip().eq("").sum())
    assert blank / max(len(items), 1) < 0.2


def test_hogback_live_file_has_two_wood_groups():
    if not HOGBACK.exists():
        return
    df = import_hogback_workbook(HOGBACK.read_bytes(), filename=HOGBACK.name).long_df
    woods = set(df["species"].dropna())
    assert HOG_1 in woods
    assert HOG_2 in woods
    assert df["species"].fillna("").ne("").all()


def test_lamb_live_file_exposes_walnut_option():
    if not LAMB.exists():
        return
    df = import_workbook(LAMB.read_bytes(), vendor="LAMB", filename=LAMB.name).long_df
    keys = set(df.get("option_key", pd.Series()).dropna().astype(str))
    assert any("walnut" in k.lower() for k in keys)


def test_five_star_live_file_tables_are_oak():
    if not FIVE_STAR.exists():
        return
    df = import_workbook(
        FIVE_STAR.read_bytes(), vendor="Five Star Tables", filename=FIVE_STAR.name
    ).long_df
    items = df[df["line_kind"].fillna("item") != "addon"]
    blank = int(items["species"].fillna("").astype(str).str.strip().eq("").sum())
    assert blank == 0
    assert "Oak" in set(items["species"])
