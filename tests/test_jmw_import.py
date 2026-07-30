"""J & M Woodworking: expand woods from Percentage; panel + finish options."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.db import init_db
from backend.jmw_import import (
    import_jmw_workbook,
    looks_like_jmw,
    parse_specialty_finish_addons,
    parse_wood_percentages,
)
from backend.repository import PriceBookRepository
from wide_import import import_workbook

UPLOAD = Path("/home/ubuntu/.cursor/projects/workspace/uploads/JMW_2026_Pricelist_0426_8528.xlsx")


def test_looks_like_jmw():
    assert looks_like_jmw(
        "JMW_2026_Pricelist_0426.xlsx",
        ["Markup", " Percentage", "Java", "Specialty Finish Options"],
    )
    assert not looks_like_jmw("other.xlsx", ["Sheet1", "Prices"])


def test_parse_wood_percentages_mini():
    df = pd.DataFrame(
        [
            [None, "Wood Specie", "Percentage"],
            [None, "Br. Maple", 0],
            [None, "Cherry", 0.1],
            [None, "Walnut", 0.6],
        ]
    )
    pct = parse_wood_percentages(df)
    assert pct["Brown Maple"] == 0.0
    assert pct["Cherry"] == 0.1
    assert pct["Walnut"] == 0.6


def test_specialty_finish_addons_mini():
    df = pd.DataFrame(
        [
            ["Specialty Finish Options", None, None],
            ["Item", "2-tone Stain", "Paint"],
            ["King Bed", 75, 135],
            ["Queen Bed", 75, 130],
        ]
    )
    rows = parse_specialty_finish_addons(df, vendor="J & M Woodworking")
    assert rows
    assert all(r["line_kind"] == "addon" for r in rows)
    labels = {r["option_key"] for r in rows}
    assert "2-tone Stain" in labels
    assert "Paint" in labels


def test_uploaded_jmw_expands_woods_and_options():
    if not UPLOAD.is_file():
        return
    data = UPLOAD.read_bytes()
    assert looks_like_jmw(UPLOAD.name, [" Percentage", "Specialty Finish Options", "Java"])
    result = import_workbook(data, vendor="J & M Woodworking", filename=UPLOAD.name)
    assert "J & M" in result.notes or "jmw" in result.notes.lower() or "Woodworking" in result.notes
    assert not result.long_df.empty
    df = result.long_df
    items = df[df.get("line_kind", "item").fillna("item").astype(str).str.lower() != "addon"]
    if "line_kind" not in df.columns:
        items = df
    woods = set(items["species"].dropna().astype(str))
    assert "Brown Maple" in woods
    assert "Cherry" in woods or "Walnut" in woods
    assert len(woods) >= 10, f"expected many woods from Percentage, got {sorted(woods)}"

    # Panel options on Java / Wyndham
    opts = set(df["option_key"].dropna().astype(str))
    assert "Crypton" in opts or "Leather" in opts or "Fabric" in opts, opts

    # Specialty finishes as addons
    if "line_kind" in df.columns:
        addons = df[df["line_kind"].astype(str).str.lower() == "addon"]
        assert not addons.empty
        assert any("Paint" in str(x) or "2-tone" in str(x) for x in addons["option_key"])

    # Crypton banner must not become Collection
    cols = set(df["collection"].dropna().astype(str))
    assert not any("Heartland" in c or "Available in Crypton" in c for c in cols)

    # Cherry priced above Brown Maple for same SKU
    mule = items[
        (items["part_number"].astype(str) == "40")
        & (items["option_key"].isna() | (items["option_key"].astype(str) == ""))
    ]
    if not mule.empty and "Cherry" in woods and "Brown Maple" in woods:
        bm = float(mule[mule["species"] == "Brown Maple"].iloc[0]["base_price"])
        ch = float(mule[mule["species"] == "Cherry"].iloc[0]["base_price"])
        assert ch == round(bm * 1.1, 2)


def test_jmw_dropdowns_after_insert(tmp_path):
    if not UPLOAD.is_file():
        return
    data = UPLOAD.read_bytes()
    result = import_jmw_workbook(data, vendor="J & M Woodworking", filename=UPLOAD.name)
    db = tmp_path / "jmw.db"
    init_db(db)
    repo = PriceBookRepository(db)
    rows = result.long_df.to_dict(orient="records")
    # light normalize
    for r in rows:
        r.setdefault("line_kind", "item")
        r.setdefault("source_file", UPLOAD.name)
        r.setdefault("multiplier", 2.7)
        if r.get("base_price") is not None and r.get("adjusted_price") is None:
            r["adjusted_price"] = round(float(r["base_price"]) * 2.7, 2)
    repo.insert_rows(rows)
    woods = repo.list_species(vendor="J & M Woodworking")
    opts = repo.list_option_keys("J & M Woodworking")
    assert len(woods) >= 10, woods
    assert opts, opts
    assert any(x in opts for x in ("Crypton", "Leather", "Fabric", "Paint", "2-tone Stain")), opts
