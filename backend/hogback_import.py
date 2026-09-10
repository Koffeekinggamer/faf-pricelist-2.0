"""Hogback: two wood-group price columns on the Pricing tab."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_sheet
from wide_import import WorkbookImportResult, list_excel_sheets, tag_import_result

GROUP_1 = "Oak / Brown Maple / Rustic Cherry / Sap Cherry"
GROUP_2 = "QSWO / Cherry / Hard Maple / Elm / Walnut"
_SKIP_ROW = re.compile(r"(?i)^(standard features|options?:|item\s*#|description|pricing|add:)")
_SKU = re.compile(r"^[A-Za-z]{2,}\d{1,}|^[A-Z]{2,}\d+[A-Z0-9]*$")


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()


def _price(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = float(v)
        return n if n > 0 else None
    try:
        n = float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None
    return n if n > 0 else None


def import_hogback_workbook(
    data: bytes,
    *,
    vendor: str = "Hogback Design And Finishing",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    names = list_excel_sheets(data)
    rows: list[dict] = []
    tried: list[dict] = []
    collection = default_collection or None
    for name in names:
        if sheet_filter and name not in sheet_filter:
            continue
        if str(name).strip().lower() in {"markup", "title page"}:
            tried.append({"sheet": name, "layout": "skip", "rows": 0})
            continue
        raw = read_sheet(data, name, header=None)
        if raw is None or raw.empty:
            continue
        before = len(rows)
        for i in range(len(raw)):
            a = _cell(raw.iat[i, 0]) if raw.shape[1] else ""
            b = _cell(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
            dims = _cell(raw.iat[i, 2]) if raw.shape[1] > 2 else ""
            p1 = _price(raw.iat[i, 3]) if raw.shape[1] > 3 else None
            p2 = _price(raw.iat[i, 4]) if raw.shape[1] > 4 else None
            if a and not p1 and not p2 and _SKIP_ROW.search(a):
                continue
            if a and not p1 and not p2 and 3 <= len(a) <= 60:
                if re.search(r"(?i)collection|pieces?$", a) or a.isupper():
                    collection = a.title() if a.isupper() else a
                continue
            if not a or _SKIP_ROW.search(a) or (p1 is None and p2 is None):
                continue
            if not (_SKU.match(a) or re.search(r"\d", a)):
                continue
            for price, species in ((p1, GROUP_1), (p2, GROUP_2)):
                if price is None:
                    continue
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": collection,
                        "part_number": a,
                        "description": b or a,
                        "dimensions": dims or None,
                        "species": species,
                        "finish_state": "finished",
                        "base_price": price,
                        "price_basis": "wholesale",
                        "line_kind": "item",
                    }
                )
        tried.append({"sheet": name, "rows": len(rows) - before})
    out = pd.DataFrame(rows)
    return tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=None,
            sheet_names=names,
            notes=f"{filename}: Hogback two wood groups · {len(out)} rows",
        ),
        "hogback_design_and_finishing",
    )
