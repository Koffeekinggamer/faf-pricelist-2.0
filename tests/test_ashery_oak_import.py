"""Ashery Oak: expand Master wood tiers onto each SKU; Options as addons."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.ashery_oak_import import (
    import_ashery_oak_workbook,
    looks_like_ashery_oak,
    parse_bookcase_door_addons,
    parse_extra_wood_percentages,
    parse_master_sheet,
    parse_option_addons,
)
from backend.workbook_sheets import read_all_sheets
from backend.builder_parsers import (
    filename_hints_for,
    infer_importer,
    match_vendor_from_saved_parsers,
    preferred_parser_for,
)
from backend.builder_profiles import clear_profile_cache
from backend.db import init_db
from backend.drop_parse_session import DropUpload
from backend.normalize import long_df_to_rows
from backend.repository import PriceBookRepository
from backend.service import PriceBookService
from backend.standardize import resolve_builder_vendor
from wide_import import import_workbook

UPLOAD = Path("/Users/lordjudsonmiller/Downloads/AO_Pricelist_070625.xlsx")


def test_looks_like_ashery_oak():
    assert looks_like_ashery_oak(
        "AO_Pricelist_070625.xlsx",
        ["Markup", "Master", "Options&Portal", "Products"],
    )
    assert looks_like_ashery_oak("AsheryOak_2026.xlsx", ["Sheet1"])
    assert not looks_like_ashery_oak("other.xlsx", ["Sheet1", "Prices"])


def test_filename_and_vendor_resolve_ao_prefix():
    hints = filename_hints_for("Ashery Oak", "AO_Pricelist_070625.xlsx")
    assert "ao_pricelist" in hints
    assert resolve_builder_vendor("", filename="AO_Pricelist_070625.xlsx") == "Ashery Oak"
    assert resolve_builder_vendor("AO") == "Ashery Oak"
    assert infer_importer("", ["ashery_oak_master_wood_expand"]) == "ashery_oak"


def test_locked_profile_is_ashery_oak():
    clear_profile_cache()
    assert preferred_parser_for("Ashery Oak") == "ashery_oak"
    assert match_vendor_from_saved_parsers("AO_Pricelist_070625.xlsx") == "Ashery Oak"


def test_parse_master_expands_woods():
    df = pd.DataFrame(
        [
            ["note", None, None, "Oak / Rustic Cherry", "Hickory", "QSWO / Cherry"],
            ["Model #", "Description", "Overall Size", "Regular", "10% More", "35% More"],
            ["BARN FLOOR OCCASIONAL TABLES", None, None, None, None, None],
            ["BF-1648-DS", "Sofa Table", '48"W x 16"D x 30"H', 350, 366, 450],
        ]
    )
    rows = parse_master_sheet(
        df,
        vendor="Ashery Oak",
        extra_woods={"Hickory": 0.10, "QSWO": 0.30, "Rustic Walnut": 0.10},
    )
    items = [r for r in rows if r["line_kind"] == "item"]
    woods = {r["species"] for r in items}
    assert "Oak" in woods
    assert "Brown Maple" in woods
    assert "Hickory" in woods
    assert "QSWO" in woods
    assert "Rustic Walnut" in woods
    oak = next(r for r in items if r["species"] == "Oak")
    hick = next(r for r in items if r["species"] == "Hickory")
    qswo = next(r for r in items if r["species"] == "QSWO")
    walnut = next(r for r in items if r["species"] == "Rustic Walnut")
    assert oak["base_price"] == 350
    assert hick["base_price"] == 385.0
    assert qswo["base_price"] == 455.0
    assert walnut["base_price"] == 385.0
    assert oak["part_number"] == "BF-1648-DS"
    assert oak["collection"] == "BARN FLOOR OCCASIONAL TABLES"


def test_parse_options_addons_and_extra_woods():
    df = pd.DataFrame(
        [
            ["Wood Species Pricing", None, None, "ADD"],
            ["Regular prices listed are in Oak, Rustic Cherry, Sap Cherry, and Brown Maple"],
            ["Hickory …", None, None, 0.10],
            ["Rustic Walnut …", None, None, 0.10],
            ["Prime Walnut …", None, None, 0.55],
            ["Options"],
            ["For painting , Add:", None, None, 0.35],
            ["For Locks on Drawers , Add:", None, None, 13],
        ]
    )
    extra = parse_extra_wood_percentages(df)
    assert extra["Hickory"] == 0.10
    assert extra["Rustic Walnut"] == 0.10
    assert extra["Prime Walnut"] == 0.55
    addons = parse_option_addons(df, vendor="Ashery Oak")
    keys = {r["option_key"] for r in addons}
    assert "Paint" in keys
    assert "Drawer lock" in keys
    paint = next(r for r in addons if r["option_key"] == "Paint")
    assert paint["line_kind"] == "addon"
    assert paint["addon_pct"] == 35.0
    assert paint["base_price"] is None


def test_bookcase_doors_parse_from_visible_options_tab():
    df = pd.DataFrame(
        [
            ["Bookcase Options"],
            ['1-48" High Doors on 24" Wide', 85],
            ["Options"],
            ["For painting , Add:", 0.35],
        ]
    )
    doors = parse_bookcase_door_addons(df, vendor="Ashery Oak")
    assert doors
    assert any("24" in str(d["option_key"]) for d in doors)


def test_uploaded_ao_links_woods_to_items():
    if not UPLOAD.is_file():
        return
    data = UPLOAD.read_bytes()
    result = import_workbook(data, vendor="Ashery Oak", filename=UPLOAD.name)
    assert result.detected_importer == "ashery_oak"
    df = result.long_df
    assert not df.empty
    items = df[df["line_kind"].astype(str).str.lower() != "addon"]
    woods = set(items["species"].dropna().astype(str))
    assert "Oak" in woods
    assert "QSWO" in woods
    assert "Brown Maple" in woods
    assert "Rustic Walnut" in woods
    assert "Wormy Maple" in woods
    assert len(woods) >= 14
    sofa = items[items["part_number"].astype(str) == "BF-1648-DS"]
    assert not sofa.empty
    assert set(sofa["species"].dropna().astype(str)) == woods
    oak = float(sofa[sofa["species"] == "Oak"].iloc[0]["base_price"])
    hick = float(sofa[sofa["species"] == "Hickory"].iloc[0]["base_price"])
    qswo = float(sofa[sofa["species"] == "QSWO"].iloc[0]["base_price"])
    walnut = float(sofa[sofa["species"] == "Rustic Walnut"].iloc[0]["base_price"])
    assert oak == 350
    assert hick == 385.0
    assert qswo == 455.0
    assert walnut == 385.0
    addons = df[df["line_kind"].astype(str).str.lower() == "addon"]
    assert not addons.empty
    assert "Paint" in set(addons["option_key"].astype(str))

    rows = long_df_to_rows(df, source_file=UPLOAD.name, multiplier=2.7, vendor="Ashery Oak")
    norm_woods = {r["species"] for r in rows if r.get("line_kind") != "addon" and r.get("species")}
    norm_opts = {r["option_key"] for r in rows if r.get("line_kind") == "addon"}
    assert "Rustic Walnut" in norm_woods
    assert "Wormy Maple" in norm_woods
    assert "Paint" in norm_opts
    paint = next(r for r in rows if r.get("option_key") == "Paint")
    assert paint["addon_pct"] == 35.0


def test_ao_dropdowns_after_insert(tmp_path):
    if not UPLOAD.is_file():
        return
    data = UPLOAD.read_bytes()
    result = import_ashery_oak_workbook(data, vendor="Ashery Oak", filename=UPLOAD.name)
    db = tmp_path / "ao.db"
    init_db(db)
    repo = PriceBookRepository(db)
    rows = result.long_df.to_dict(orient="records")
    for r in rows:
        r.setdefault("line_kind", "item")
        r.setdefault("source_file", UPLOAD.name)
        r.setdefault("multiplier", 2.7)
        if r.get("base_price") is not None and r.get("adjusted_price") is None:
            r["adjusted_price"] = round(float(r["base_price"]) * 2.7, 2)
    repo.insert_rows(rows)
    woods = repo.list_species("Ashery Oak")
    opts = repo.list_option_keys("Ashery Oak")
    assert "Oak" in woods
    assert "QSWO" in woods
    assert "Paint" in opts


def test_ao_views_every_tab():
    if not UPLOAD.is_file():
        return
    data = UPLOAD.read_bytes()
    views = read_all_sheets(data)
    names = {v.name for v in views}
    assert "Products" in names
    assert "Cover" in names
    assert "Markup" in names
    assert any("Options&Portal" == n for n in names)
    assert "Master" not in names
    assert not any("bk" in n.lower() for n in names)
    assert all(v.role != "error" for v in views)

    result = import_ashery_oak_workbook(data, vendor="Ashery Oak", filename=UPLOAD.name)
    tried = {s["sheet"]: s for s in result.sheets_tried}
    assert set(tried) == names
    assert all("viewed" in str(s.get("note") or s.get("layout") or "") or s.get("rows", 0) > 0
               for s in result.sheets_tried)
    assert tried["Products"]["layout"] == "ashery_oak_products_fill"


def test_drop_session_uses_ashery_oak_parser(tmp_path):
    if not UPLOAD.is_file():
        return
    data = UPLOAD.read_bytes()
    svc = PriceBookService(db_path=tmp_path / "t.db")
    svc.init()
    svc._drop_parse_root = tmp_path / "drop_sessions"
    view = svc.ensure_drop_parse_session(
        [DropUpload(UPLOAD.name, data, size=len(data))],
    )
    f = view.files[0]
    assert f.error == ""
    assert f.suggested_builder == "Ashery Oak"
    assert f.detected_importer == "ashery_oak"
    assert f.row_count > 1000
    assert "Hickory" in (f.variants or {}).get("woods", [])
    wholesale = svc.wholesale_from_drop_parse_session(view.session_id)
    sofa = [
        r
        for wf in wholesale
        for r in wf.rows
        if r.get("part_number") == "BF-1648-DS" and r.get("species") == "Hickory"
    ]
    assert sofa
    assert float(sofa[0]["base_price"]) == 385.0
