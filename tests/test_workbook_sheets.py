"""Drop must open every Excel tab before importing or ignoring it."""

from __future__ import annotations

import io

import openpyxl

from backend.workbook_sheets import classify_sheet_role, read_all_sheets
from wide_import import import_workbook


def _book(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    first = True
    for name, rows in sheets.items():
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_read_all_sheets_classifies_every_tab():
    data = _book(
        {
            "Cover": [["ASHERY OAK WHOLESALE"], ["Fredericksburg OH"]],
            "Markup": [[None, "Markup"], [None, 1]],
            "Options": [["Wood Species Pricing"], ["Hickory", 0.1], ["Options"], ["For painting , Add:", 0.35]],
            "Items": [["Part #", "Description", "Wholesale"], ["P1", "Bench", 220]],
        }
    )
    views = read_all_sheets(data)
    by = {v.name: v.role for v in views}
    assert by["Cover"] == "cover"
    assert by["Markup"] == "markup"
    assert by["Options"] == "options"
    assert by["Items"] == "catalog"
    assert classify_sheet_role("Options&Portal bk", views[2].raw) == "options"


def test_generic_drop_views_options_instead_of_skipping():
    data = _book(
        {
            "Cover": [["Title"]],
            "Options&Portal": [
                ["Options"],
                ["For painting , Add:", 0.35],
                ["For Locks on Drawers , Add:", 13],
            ],
            "Catalog": [["Part #", "Description", "Oak"], ["T-1", "Table", 100]],
        }
    )
    result = import_workbook(data, vendor="Test Builder", filename="Test_Pricelist.xlsx")
    tried = {s["sheet"]: s for s in result.sheets_tried}
    assert "Cover" in tried
    assert "viewed" in str(tried["Cover"].get("layout") or tried["Cover"].get("note"))
    assert "Options&Portal" in tried
    assert tried["Options&Portal"]["layout"] == "viewed_options"
    assert tried["Options&Portal"]["rows"] >= 1
    addons = result.long_df[result.long_df.get("line_kind", "") == "addon"] if not result.long_df.empty else result.long_df
    if not result.long_df.empty and "line_kind" in result.long_df.columns:
        keys = set(addons["option_key"].astype(str))
        assert "Paint" in keys or "Drawer lock" in keys
