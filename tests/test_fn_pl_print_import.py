"""FN Chair Level One PL Print → style + chair type + Cat.N option."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from backend.fn_chair_import import (
    import_fn_chair_workbook,
    looks_like_fn_level_one,
    parse_fn_pl_print_rows,
)
from wide_import import import_workbook


def _mini_pl_print_df() -> pd.DataFrame:
    """Tiny Abe block matching Level One Blue layout."""
    return pd.DataFrame(
        [
            [
                "Abe",
                None,
                "Red Oak / Sap Cherry / Wormy Maple / Rustic Red Oak",
                "Brown Soft Maple / Rustic Brown Maple / Rustic Cherry",
                "Walnut / Rustic Walnut",
                None,
                None,
                None,
                None,
                None,
                "Solid Fabrics / COM",
            ],
            ["Side Chair", "Unf", 105, 113, 216, None, None, None, None, None, 23],
            [None, "Cat. 1", 147, 155, 258, None, None, None, None, None, None],
            [None, "Cat. 2", 181, 189, 292, None, None, None, None, None, None],
            ["Arm Chair", "Unf", 144, 155, 280, None, None, None, None, None, 23],
            [None, "Cat. 1", 199, 210, 335, None, None, None, None, None, None],
        ]
    )


def test_parse_pl_print_style_chair_cat():
    rows = parse_fn_pl_print_rows(_mini_pl_print_df(), vendor="FN Chair")
    assert rows
    parts = {r["part_number"] for r in rows}
    assert parts == {"Abe Side Chair", "Abe Arm Chair"}
    side_cat1 = [
        r
        for r in rows
        if r["part_number"] == "Abe Side Chair" and r["option_key"] == "Cat. 1"
    ]
    assert len(side_cat1) == 3  # three woods
    assert all(r["finish_state"] == "finished" for r in side_cat1)
    assert all(r["collection"] == "Seating" for r in rows)
    unf = [r for r in rows if r["part_number"] == "Abe Side Chair" and not r["option_key"]]
    assert unf
    assert all(r["finish_state"] == "unfinished" for r in unf)
    # Fabric adder column must not become a wood price row
    assert all(r["base_price"] != 23 for r in rows)


def test_looks_like_fn_level_one():
    assert looks_like_fn_level_one(
        "FNC_2026_Pricelist_Level_One_Blue_1225.xlsm",
        ["Cover Page", "PL Print", "PL To Export", "PCL Color List"],
    )
    assert not looks_like_fn_level_one("other.xlsx", ["Sheet1", "Prices"])


def test_import_workbook_routes_fn_level_one(tmp_path: Path):
    # Build a minimal .xlsx with PL Print + PCL Color List sheets
    path = tmp_path / "FNC_Level_One_Blue.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        _mini_pl_print_df().to_excel(writer, sheet_name="PL Print", header=False, index=False)
        pd.DataFrame([["STAIN COLORS"]]).to_excel(
            writer, sheet_name="PCL Color List", header=False, index=False
        )
        pd.DataFrame([["Abe Side Chair", 92]]).to_excel(
            writer, sheet_name="PL To Export", header=False, index=False
        )
    data = path.read_bytes()
    result = import_workbook(data, vendor="FN Chair", filename=path.name)
    assert "PL Print" in " ".join(result.notes) or "fn" in result.notes.lower()
    assert not result.long_df.empty
    assert set(result.long_df["part_number"]) == {"Abe Side Chair", "Abe Arm Chair"}
    assert "Cat. 1" in set(result.long_df["option_key"].dropna())
    # PL To Export must not double-count
    assert len(result.long_df) == len(
        parse_fn_pl_print_rows(_mini_pl_print_df(), vendor="FN Chair")
    )


def test_uploaded_fn_workbook_if_present():
    """Smoke-parse the fresh Level One Blue doc when available in uploads."""
    uploads = Path("/home/ubuntu/.cursor/projects/workspace/uploads")
    matches = list(uploads.glob("FNC_2026_Pricelist_Level_One_Blue*.xlsm"))
    if not matches:
        return
    data = matches[0].read_bytes()
    assert looks_like_fn_level_one(matches[0].name, ["PL Print", "PCL Color List"])
    result = import_fn_chair_workbook(data, vendor="FN Chair", filename=matches[0].name)
    assert not result.long_df.empty
    assert len(result.long_df) > 5000
    abe_side = result.long_df[
        (result.long_df["part_number"] == "Abe Side Chair")
        & (result.long_df["option_key"] == "Cat. 1")
    ]
    assert not abe_side.empty
    red = abe_side[
        abe_side["species"].astype(str).str.contains("Red Oak", case=False, na=False)
    ]
    assert float(red.iloc[0]["base_price"]) == 147.0
