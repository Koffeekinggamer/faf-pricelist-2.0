"""Criswell rows read like a catalog page, not like parser internals."""

import io

import pandas as pd

from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
from backend.criswell_import import _wood_labels


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False, header=False)
    return buffer.getvalue()


def test_wood_labels_ignore_footnote_cells_in_the_header_band():
    header_rows = [
        [None, None, "Oak", None, "Cherry"],
        [None, None, "Standard Footboard", None, "Drawer Unit #002"],
        [None, None, 'Height: 8 1/2" from floor to bottom of sideboard.', None, None],
    ]

    assert _wood_labels(header_rows) == {2: "Oak", 4: "Cherry"}


def test_criswell_rows_do_not_carry_parser_provenance_as_human_text():
    data = _xlsx(
        {
            "Markup": [["Enter Markup"], [1]],
            "Cover": [["CRISWELL FURNITURE"]],
            "Options ": [
                ["Options", None, "Oak", None, "Cherry"],
                ["Phone Charger", 55, None, 55, None],
            ],
            "Bloomfield Collection": [
                [None, None, "Oak", None, "Cherry"],
                ["CWF8111", "Tall Dresser", 1099, None, 1170],
            ],
        }
    )

    result = DEFAULT_READER_REGISTRY.run(
        "criswell", data, vendor="Criswell Bedroom", filename="Wholesale Price List.xlsx"
    )

    assert result is not None
    blob = " ".join(
        str(value)
        for column in ("description", "notes")
        if column in result.long_df.columns
        for value in result.long_df[column].fillna("").tolist()
    ).lower()
    assert "left pane" not in blob


def test_criswell_item_rows_keep_the_factory_item_code():
    data = _xlsx(
        {
            "Markup": [["Enter Markup"], [1]],
            "Cover": [["CRISWELL FURNITURE"]],
            "Options ": [
                ["Options", None, "Oak"],
                ["Phone Charger", 55, None],
            ],
            "Bloomfield Collection": [
                [None, None, "Oak"],
                ["CWF8111", "Tall Dresser", 1099],
            ],
        }
    )

    result = DEFAULT_READER_REGISTRY.run(
        "criswell", data, vendor="Criswell Bedroom", filename="Wholesale Price List.xlsx"
    )

    assert result is not None
    items = result.long_df[result.long_df["line_kind"].fillna("item") != "addon"]
    assert items["part_number"].astype(str).str.startswith("CWF8111").all()
