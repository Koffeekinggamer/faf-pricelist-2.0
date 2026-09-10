"""Superior Woodcrafts: ITEM # × wood name × unfinished/finished wholesale."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_sheet
from wide_import import WorkbookImportResult, list_excel_sheets, tag_import_result

_ITEM = re.compile(r"(?i)^item\s*#")
_ZERO = re.compile(r"^0+(\.0+)?$")


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
    s = str(v).strip().replace("$", "").replace(",", "")
    if not s or _ZERO.match(s):
        return None
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n > 0 else None


def import_superior_workbook(
    data: bytes,
    *,
    vendor: str = "Superior Woodcrafts",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    names = list_excel_sheets(data)
    targets = [n for n in names if not sheet_filter or n in sheet_filter]
    rows: list[dict] = []
    tried: list[dict] = []
    collection = default_collection or None
    for name in targets:
        raw = read_sheet(data, name, header=None)
        if raw is None or raw.empty:
            tried.append({"sheet": name, "rows": 0})
            continue
        header_i = None
        cols = {}
        for i in range(min(40, len(raw))):
            labels = [_cell(raw.iat[i, j]).lower() for j in range(raw.shape[1])]
            if any(_ITEM.match(x) for x in labels) and any("wood" in x for x in labels):
                header_i = i
                for j, lab in enumerate(labels):
                    if _ITEM.match(lab) or lab == "item #":
                        cols["part"] = j
                    elif "desc" in lab:
                        cols["desc"] = j
                    elif "wood" in lab:
                        cols["wood"] = j
                    elif lab == "unfinished":
                        cols["unf"] = j
                    elif lab == "finished":
                        cols["fin"] = j
                break
        if header_i is None or "part" not in cols:
            tried.append({"sheet": name, "rows": 0, "note": "no superior header"})
            continue
        before = len(rows)
        for i in range(header_i + 1, len(raw)):
            part = _cell(raw.iat[i, cols["part"]])
            desc = _cell(raw.iat[i, cols["desc"]]) if "desc" in cols else ""
            if not part:
                banner = desc or _cell(raw.iat[i, 1])
                if banner and not _price(raw.iat[i, cols.get("fin", 0)]):
                    if 3 <= len(banner) <= 48 and not re.search(r"\d", banner[:2]):
                        collection = banner
                continue
            if re.search(r"(?i)item\s*#|description|wholesale|retail", part):
                continue
            wood = _cell(raw.iat[i, cols["wood"]]) if "wood" in cols else ""
            wood = wood or None
            for key, finish in (("unf", "unfinished"), ("fin", "finished")):
                if key not in cols:
                    continue
                price = _price(raw.iat[i, cols[key]])
                if price is None:
                    continue
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": collection,
                        "part_number": part,
                        "description": desc or part,
                        "species": wood,
                        "finish_state": finish,
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
            notes=f"{filename}: Superior wood × finish wholesale · {len(out)} rows",
        ),
        "superior_woodcrafts",
    )
