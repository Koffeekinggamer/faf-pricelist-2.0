"""Amish Aspen — 3-column flyer: name | price | dims blocks across the sheet."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from wide_import import (
    WorkbookImportResult,
    _clean_long_rows,
    _norm,
    _to_float,
    list_excel_sheets,
)


def looks_like_amish_aspen(filename: str = "") -> bool:
    fn = (filename or "").lower().replace("_", " ")
    return "amish aspen" in fn or "aspen and rustic" in fn


def import_amish_aspen_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """3-column flyer: name | price | dims blocks across the sheet."""
    names = list_excel_sheets(data)
    vendor_name = vendor or "Amish Aspen and Rustic"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []
    targets = sheet_filter if sheet_filter is not None else names

    # name-col, price-col pairs observed in sheet (0-indexed)
    pairs = [(0, 3), (5, 7), (9, 10), (1, 2), (1, 4), (6, 9), (7, 9)]

    for name in names:
        if name not in targets:
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").reset_index(drop=True)
        if raw.empty:
            tried.append({"sheet": name, "layout": "empty", "rows": 0, "note": ""})
            continue
        rows = []
        current_collection: Optional[str] = default_collection or None
        seen: set[tuple] = set()
        for i in range(len(raw)):
            for name_c, price_c in pairs:
                if name_c >= raw.shape[1] or price_c >= raw.shape[1]:
                    continue
                nm = _norm(raw.iat[i, name_c])
                price = _to_float(raw.iat[i, price_c])
                if not nm or price is None or price < 20:
                    # section banners
                    if nm and price is None and 3 <= len(nm) <= 50:
                        if re.search(
                            r"(?i)bedroom|table|bed|dining|book|living|white cedar",
                            nm,
                        ):
                            current_collection = nm
                    continue
                if re.search(
                    r"(?i)phone|fax|email|@|subject to|price list|joel martin|"
                    r"hillsboro|walnut tops|d\s*w\s*h|table only|add a sceen",
                    nm,
                ):
                    continue
                if re.fullmatch(r"\d+(\.\d+)?\s*[x×]\s*\d+", nm, re.I):
                    continue
                if len(nm) > 70:
                    continue
                key = (nm.lower(), round(price, 2))
                if key in seen:
                    continue
                seen.add(key)
                # optional dims: col after price
                dims = None
                for dc in (price_c + 1, name_c + 1, 4, 8, 11):
                    if dc < raw.shape[1] and dc != price_c and dc != name_c:
                        d = _norm(raw.iat[i, dc])
                        if d and re.search(r"\d", d) and re.search(r"[x×]", d, re.I):
                            dims = d
                            break
                wood = (
                    "White Cedar"
                    if re.search(r"(?i)white cedar", str(current_collection or ""))
                    else "Hickory / Aspen"
                )
                rows.append(
                    {
                        "vendor": vendor_name,
                        "collection": current_collection,
                        "part_number": nm,
                        "description": nm,
                        "dimensions": dims,
                        "option_key": None,
                        "species": wood,
                        "species_tier": None,
                        "finish_state": "finished",
                        "base_price": price,
                        "price_basis": "wholesale",
                        "unit": None,
                        "notes": None,
                    }
                )
        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        tried.append(
            {
                "sheet": name,
                "layout": "amish_aspen_flyer",
                "rows": len(long),
                "note": f"pairs={len(pairs)}",
            }
        )
        if not long.empty:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out
        if not out.empty
        else pd.DataFrame(
            columns=[
                "vendor",
                "collection",
                "part_number",
                "description",
                "dimensions",
                "option_key",
                "species",
                "species_tier",
                "finish_state",
                "base_price",
                "price_basis",
                "unit",
                "notes",
            ]
        ),
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Amish Aspen flyer · {len(out) if not out.empty else 0} rows",
    )
