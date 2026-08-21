"""Drop / folder import typo + light grammar pass (standardize)."""

from __future__ import annotations

from backend.standardize import (
    clean_catalog_label,
    standardize_collection,
    standardize_row,
    standardize_text,
)


def test_occasonial_collection_on_standardize():
    assert (
        standardize_collection("Classic Shaker Occasonial Tables")
        == "Classic Shaker Occasional Tables"
    )
    assert standardize_collection("OCCASONIAL TABLES") == "Occasional Tables"


def test_typo_pass_does_not_touch_skus():
    row = standardize_row(
        {
            "vendor": "J & M Woodworking",
            "collection": "Classic Shaker Occasonial Tables",
            "part_number": "1024",
            "description": "King Occasonial night stand",
            "species": "Oak",
            "finish_state": "finished",
            "base_price": 100,
            "multiplier": 2.7,
        }
    )
    assert row["collection"] == "Classic Shaker Occasional Tables"
    assert (
        row["description"]
        == "King Occasional night stand — Classic Shaker Occasional Tables"
    )
    assert row["part_number"] == "1024"


def test_repeated_function_word_grammar():
    assert clean_catalog_label("Beds and and Tables") == "Beds and Tables"
    assert standardize_text("The the Hampton Bed") == "The Hampton Bed"


def test_unknown_words_left_alone():
    assert standardize_collection("Wyndham Hills Beds") == "Wyndham Hills Beds"
    assert clean_catalog_label("QSWO") == "QSWO"
