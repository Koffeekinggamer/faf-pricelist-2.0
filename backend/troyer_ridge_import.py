"""Troyer Ridge: stacked wood groups, finished left + unfinished/finished right."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result

GROUP_1 = "Oak / Brown Maple / Rustic Hickory / Rustic Cherry"
GROUP_2 = "Hard Maple / Cherry / QSWO"
_SKIP_SHEET = re.compile(
    r"(?i)(price multiplier|front cover|inside front|inside back|back cover|"
    r"furniture customization)$"
)


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


def _has_wood_banner(raw: pd.DataFrame) -> bool:
    blob = " ".join(
        _cell(raw.iat[i, j]) for i in range(min(4, len(raw))) for j in range(min(12, raw.shape[1]))
    )
    return bool(re.search(r"(?i)oak|maple|cherry|qswo", blob))


def import_troyer_ridge_workbook(
    data: bytes,
    *,
    vendor: str = "Troyer Ridge Furniture",
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
        if _SKIP_SHEET.search(name.strip()) or view.role in {"cover", "markup", "empty"}:
            tried.append({"sheet": name, "layout": "skip", "rows": 0})
            continue
        raw = view.raw
        if raw is None or raw.empty or not _has_wood_banner(raw):
            tried.append({"sheet": name, "rows": 0})
            continue
        before = len(rows)
        collection = default_collection or name.strip()
        piece = ""
        for i in range(len(raw)):
            left = _cell(raw.iat[i, 0]) if raw.shape[1] else ""
            dims = _cell(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
            p_fin_1 = _price(raw.iat[i, 2]) if raw.shape[1] > 2 else None
            p_fin_2 = _price(raw.iat[i, 4]) if raw.shape[1] > 4 else None
            p_unf_1 = _price(raw.iat[i, 8]) if raw.shape[1] > 8 else None
            p_fin_r1 = _price(raw.iat[i, 9]) if raw.shape[1] > 9 else None
            p_unf_2 = _price(raw.iat[i, 10]) if raw.shape[1] > 10 else None
            p_fin_r2 = _price(raw.iat[i, 11]) if raw.shape[1] > 11 else None
            # Bed sheets sometimes shift the right block one column.
            if p_unf_1 is None and raw.shape[1] > 9:
                alt = _price(raw.iat[i, 9])
                if alt and p_fin_r1:
                    p_unf_1 = alt
            if left and not any(
                x for x in (p_fin_1, p_fin_2, p_unf_1, p_fin_r1, p_unf_2, p_fin_r2)
            ):
                if re.match(r"(?i)^tr\d|^#?\d{3,}", left) or re.search(
                    r"(?i)bed|dresser|chest|night", left
                ):
                    piece = left
                    collection = name.strip()
                elif re.search(r'(?i)\d+"?\s*hb|\d+\s*fb', left):
                    collection = f"{piece} {left}".strip() if piece else left
                continue
            if not any(x for x in (p_fin_1, p_fin_2, p_unf_1, p_fin_r1, p_unf_2, p_fin_r2)):
                continue
            size = left or piece
            if re.match(r"(?i)^(king|queen|full|twin|california)", size):
                part = f"{piece} {size}".strip()
                desc = part
            else:
                part = piece or size
                desc = size
            if not part:
                continue
            pairs = [
                (p_unf_1, GROUP_1, "unfinished"),
                (p_fin_r1 or p_fin_1, GROUP_1, "finished"),
                (p_unf_2, GROUP_2, "unfinished"),
                (p_fin_r2 or p_fin_2, GROUP_2, "finished"),
            ]
            seen: set[tuple] = set()
            for price, species, finish in pairs:
                if price is None or abs(price - round(price)) > 0.05:
                    continue
                key = (part, species, finish, round(price, 2))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": collection,
                        "part_number": part,
                        "description": desc,
                        "dimensions": dims or None,
                        "species": species,
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
            notes=f"{filename}: Troyer Ridge wood groups · {len(out)} rows",
        ),
        "troyer_ridge_furniture",
    )
