"""Fredericksburg: left-hand wholesale wood columns only (retail half stays out)."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result

_SKIP_SHEET = re.compile(r"(?i)^(read first|instructions?)$")
_WOODISH = re.compile(r"(?i)\b(oak|maple|cherry|hickory|qs\s*w|qswo|elm|walnut|inlay)\b")
_FINISHED = re.compile(r"(?i)^finished$")


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


def _wood_labels(raw: pd.DataFrame) -> list[tuple[int, str]]:
    if raw is None or raw.empty:
        return []
    labels: list[tuple[int, str]] = []
    for i in range(min(3, len(raw))):
        carry = ""
        for j in range(raw.shape[1]):
            text = _cell(raw.iat[i, j])
            if not text:
                continue
            if _FINISHED.match(text):
                continue
            if _WOODISH.search(text) and "collection" not in text.lower():
                name = re.sub(r"\s+", " / ", text)
                labels.append((j, name))
                carry = name
            elif carry and _price(raw.iat[i, j]) is None:
                continue
    # Unique columns, first wood label wins.
    by_col: dict[int, str] = {}
    for col, name in labels:
        by_col.setdefault(col, name)
    return sorted(by_col.items())


def import_fredericksburg_workbook(
    data: bytes,
    *,
    vendor: str = "Fredericksburg Furniture",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    views = read_all_sheets(data)
    rows: list[dict] = []
    tried: list[dict] = []
    names = [v.name for v in views]
    for view in views:
        name = str(view.name)
        if sheet_filter and name not in sheet_filter:
            continue
        if _SKIP_SHEET.match(name) or view.role in {"cover", "markup", "empty"}:
            tried.append({"sheet": name, "layout": "skip", "rows": 0})
            continue
        raw = view.raw
        woods = _wood_labels(raw)
        if not woods:
            tried.append({"sheet": name, "rows": 0, "note": "no wood header"})
            continue
        # Left block only: stop when the first wood column's header repeats.
        first_wood_col = woods[0][0]
        split_at = raw.shape[1]
        header_cell = _cell(raw.iat[0, 0]) if len(raw) else ""
        for j in range(first_wood_col + 1, raw.shape[1]):
            if header_cell and _cell(raw.iat[0, j]) == header_cell:
                split_at = j
                break
        woods = [(c, n) for c, n in woods if c < split_at]
        before = len(rows)
        collection = default_collection or name
        sku = ""
        desc = ""
        for i in range(len(raw)):
            left = _cell(raw.iat[i, 0])
            mid = _cell(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
            prices = [(_price(raw.iat[i, c]), n) for c, n in woods]
            if left and not any(p for p, _ in prices):
                if 3 <= len(left) <= 60 and not re.match(r"^#", left):
                    collection = left
                continue
            if left.startswith("#") or re.match(r"^[A-Z]{1,3}-?\d", left):
                sku = left
                desc = mid or left
            elif mid and any(p for p, _ in prices):
                desc = left or mid
                if not sku:
                    sku = left or mid
            if not any(p for p, _ in prices):
                continue
            part = sku or left or desc
            if not part:
                continue
            for price, species in prices:
                if price is None:
                    continue
                # Skip marked-up retail leftovers (wholesale is whole dollars).
                if abs(price - round(price)) > 0.02:
                    continue
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": collection,
                        "part_number": part,
                        "description": desc or part,
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
            notes=f"{filename}: Fredericksburg wholesale woods · {len(out)} rows",
        ),
        "fredericksburg_furniture",
    )
