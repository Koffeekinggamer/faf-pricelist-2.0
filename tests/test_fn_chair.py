"""FN Chair Level One matrix → searchable style names (not Cat. N as Part #)."""

from __future__ import annotations

from pathlib import Path

from backend.standardize import standardize_row, standardize_rows
from scripts.viztech_sync import rank_file, vendor_from_folder


def test_fn_chair_cat_row_remaps_to_style_part():
    cleaned = standardize_row(
        {
            "vendor": "FN Chair",
            "collection": "Abe",
            "part_number": "Cat. 1",
            "description": "Cat. 1",
            "species": "Red Oak / Sap Cherry / Wormy Maple / Rustic Red Oak",
            "finish_state": "finished",
            "base_price": 147.0,
            "multiplier": 2.7,
            "source_file": "FN_Chairs_Level_One.xlsx",
        }
    )
    assert cleaned is not None
    assert cleaned["vendor"] == "FN Chair"
    assert cleaned["part_number"] == "Abe"
    assert cleaned["description"] == "Abe — Cat. 1"
    assert cleaned["option_key"] == "Cat. 1"
    assert cleaned["collection"] == "Seating"
    assert "Oak" in (cleaned["species"] or "")


def test_fn_chair_level_two_source_dropped():
    assert (
        standardize_row(
            {
                "vendor": "FN Chair",
                "collection": "Abe",
                "part_number": "Cat. 1",
                "description": "Cat. 1",
                "species": "Oak",
                "base_price": 100,
                "multiplier": 2.7,
                "source_file": "FN_Chairs_Level_Two_Orange.xlsx",
            }
        )
        is None
    )


def test_fn_chair_remap_idempotent():
    once = standardize_row(
        {
            "vendor": "FN Chair",
            "collection": "Abe",
            "part_number": "Cat. 2",
            "description": "Cat. 2",
            "species": "Walnut / Rustic Walnut",
            "base_price": 200,
            "multiplier": 2.7,
            "source_file": "level-one.xlsx",
        }
    )
    twice = standardize_row(once)
    assert twice is not None
    assert twice["part_number"] == "Abe"
    assert twice["option_key"] == "Cat. 2"
    assert twice["collection"] == "Seating"


def test_viztech_prefers_fn_level_one_filename(tmp_path: Path):
    assert vendor_from_folder("FN Chairs LLC") == "FN Chair"
    one = tmp_path / "FN_Level_One_Blue.xlsx"
    two = tmp_path / "FN_Level_Two_Orange.xlsx"
    one.write_bytes(b"x" * 5000)
    two.write_bytes(b"x" * 9000)
    assert rank_file(one, "FN Chair") < rank_file(two, "FN Chair")


def test_fn_chair_batch_styles_and_cats():
    rows = [
        {
            "vendor": "FN Chair",
            "collection": "Abe",
            "part_number": "Cat. 1",
            "description": "Cat. 1",
            "species": "Red Oak / Sap Cherry",
            "finish_state": "finished",
            "base_price": 150,
            "multiplier": 2.7,
            "source_file": "FN_Level_One.xlsx",
        },
        {
            "vendor": "FN Chair",
            "collection": "Abe",
            "part_number": "Cat. 2",
            "description": "Cat. 2",
            "species": "Walnut / Rustic Walnut",
            "finish_state": "finished",
            "base_price": 220,
            "multiplier": 2.7,
            "source_file": "FN_Level_One.xlsx",
        },
        {
            "vendor": "FN Chair",
            "collection": "Alana",
            "part_number": "Cat. 1",
            "description": "Cat. 1",
            "species": "Red Oak / Sap Cherry",
            "finish_state": "finished",
            "base_price": 160,
            "multiplier": 2.7,
            "source_file": "FN_Level_One.xlsx",
        },
    ]
    cleaned = standardize_rows(rows)
    parts = sorted({r["part_number"] for r in cleaned})
    assert parts == ["Abe", "Alana"]
    abe = [r for r in cleaned if r["part_number"] == "Abe"]
    assert {r["option_key"] for r in abe} == {"Cat. 1", "Cat. 2"}
    assert all(r["collection"] == "Seating" for r in cleaned)
