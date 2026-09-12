"""Accuracy fixes for the seven builders that failed inspection."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from backend.amish_aspen_import import import_amish_aspen_workbook
from backend.book_options import extract_book_options
from backend.five_star_import import apply_five_star_oak_tables
from backend.hogback_import import GROUP_1 as HOG_1
from backend.hogback_import import GROUP_2 as HOG_2
from backend.hogback_import import import_hogback_workbook
from backend.superior_import import import_superior_workbook
from wide_import import import_workbook

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
    table = items[items["part_number"] == "42x66"]
    side = items[items["part_number"] == "Side"]
    assert "Oak" in set(table["species"].astype(str))
    assert "Cherry" in set(side["species"].astype(str))
    assert "Walnut" not in set(out["option_key"].dropna())
    walnuts = table[table["species"].astype(str) == "Walnut"]
    assert not walnuts.empty
    assert float(walnuts["base_price"].iloc[0]) == 1620


def test_walnut_percent_becomes_wood_not_option():
    data = _xlsx([["For Walnut, ADD 50% to Oak pricing."]])
    rows = extract_book_options(data, vendor="LAMB")
    assert "Walnut" not in {r["option_key"] for r in rows}


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


def test_lamb_quick_ship_ashton_is_oak():
    live = Path(
        "/Volumes/ExternalSSD/FAF-pricebook/viztech-downloads/all-20260717/"
        "Lamb_Woodworking/Download_2026_Pricelist_23191.xlsx"
    )
    path = live if live.is_file() else LAMB
    if not path.is_file():
        return
    df = import_workbook(path.read_bytes(), vendor="LAMB", filename=path.name).long_df
    items = df[df["line_kind"].fillna("item") != "addon"]
    ash = items[items["part_number"].astype(str) == "LA-ASH-3067-EX"]
    assert not ash.empty
    woods = set(ash["species"].fillna("").astype(str))
    assert "Oak" in woods
    assert all(w.strip() for w in woods)


def test_lamb_live_file_puts_walnut_in_wood():
    live = Path(
        "/Volumes/ExternalSSD/FAF-pricebook/viztech-downloads/all-20260717/"
        "Lamb_Woodworking/Download_2026_Pricelist_23191.xlsx"
    )
    path = live if live.is_file() else LAMB
    if not path.is_file():
        return
    df = import_workbook(path.read_bytes(), vendor="LAMB", filename=path.name).long_df
    items = df[df["line_kind"].fillna("item") != "addon"]
    keys = set(df.get("option_key", pd.Series()).dropna().astype(str))
    woods = set(items["species"].dropna().astype(str))
    assert any("walnut" in w.lower() for w in woods)
    assert not any(k.strip().lower() == "walnut" for k in keys)
    assert any("LED Lights" in k for k in keys)
    assert any("lock" in k.lower() for k in keys)


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
