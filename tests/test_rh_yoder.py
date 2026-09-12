"""RH Yoder tables print as style × size × leaf × wood, not a Size collection."""

from __future__ import annotations

import io

import openpyxl

from backend.rh_yoder_import import import_rh_yoder_workbook


def _xlsx(rows: list[list], sheet: str = "UNFINISHED From RH Yoder") -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_beckett_table_keeps_style_size_leaf_and_wood():
    data = _xlsx(
        [
            ["Acadia", "Oak", "B. Maple"],
            ["Side Chair", 204.56, 220.93],
            ["Table Pricing"],
            [
                "Beckett Table",
                "Oak",
                "",
                "",
                "",
                "B. Maple, Wormy Maple,Sap Cherry",
            ],
            ["Size", "Solid", "1 Leaf", "2 Leaf", "", "Solid", "1 Leaf"],
            ["42x72", 1024.95, 1145.95, 1206.95, None, 1158.19, 1294.92],
        ]
    )

    result = import_rh_yoder_workbook(data, vendor="RH Yoder", filename="RH_Yoder.xlsx")
    tables = result.long_df
    tables = tables[tables["part_number"].astype(str).eq("42x72")]

    assert set(tables["collection"].astype(str)) == {"Beckett Table"}
    oak_solid = tables[
        (tables["species"].astype(str).str.contains("Oak", case=False))
        & (tables["description"].astype(str).str.contains("Solid", case=False))
        & ~tables["species"].astype(str).str.contains("Maple", case=False)
    ]
    assert not oak_solid.empty
    assert float(oak_solid.iloc[0]["base_price"]) == 1024.95
    oak_leaf = tables[
        (tables["species"].astype(str).str.contains("Oak", case=False))
        & (tables["description"].astype(str).str.contains("1 Leaf", case=False))
        & ~tables["species"].astype(str).str.contains("Maple", case=False)
    ]
    assert not oak_leaf.empty
    assert float(oak_leaf.iloc[0]["base_price"]) == 1145.95
    assert not tables["collection"].astype(str).str.fullmatch("Size").any()
