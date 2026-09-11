"""Brookside: Unit # × title-row wood groups. Left table only.

Heritage Hutches (and the same Unit # layout on other visible tabs) print
Oak / Sap Cherry-Brown Maple-Rustic Hickory / Cherry-Elm-Hickory / QSWO
over finished prices, with unfinished as the end-column %. The right-hand
copy of the page is the same table — do not load it twice.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, list_excel_sheets, tag_import_result

VENDOR = "Brookside Home Furnishings"
_UNIT_HDR = re.compile(r"(?i)^unit\s*#$")
_SKU = re.compile(r"^#\d+[A-Za-z0-9\-]*$|^[A-Z]{1,6}\d+[A-Za-z0-9\-]*$")
_UNF_NOTE = re.compile(r"(?i)unfinish|deduct")
_SKIP_SHEET = re.compile(r"(?i)^(mark\s*-?\s*up|index|cover|title|instructions?)$")


def _cell(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    return re.sub(r"\s+", " ", str(v).replace("\n", " ")).strip()


def _price(v) -> Optional[float]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        n = float(v)
    else:
        try:
            n = float(str(v).replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
    if n <= 1.05 or n > 200_000:
        return None
    return round(n, 2)


def _wood_label(text: str) -> str:
    from backend.standardize import (
        _expand_wood_abbrevs,
        is_wood_column_label,
        standardize_species,
    )

    raw = _expand_wood_abbrevs(_cell(text))
    if not raw:
        return ""
    if not is_wood_column_label(raw) and not re.search(
        r"(?i)\b(oak|maple|cherry|hickory|elm|qswo|walnut)\b", raw
    ):
        return ""
    return standardize_species(raw) or raw


def _unfinished_price(finished: float, cell, *, fallback_rate: float = 0.0) -> Optional[float]:
    """Unf column is 0.08 (8%) on tables, or $30 / $15 off on chairs."""
    n: Optional[float] = None
    if cell is not None and not (isinstance(cell, float) and pd.isna(cell)):
        try:
            n = float(str(cell).replace("$", "").replace(",", "").strip())
        except ValueError:
            n = None
    if n is not None:
        if 0 < n < 1:
            return round(finished * (1.0 - n), 2)
        if n >= 1:
            out = finished - n
            if out > 1.05:
                return round(out, 2)
            return None
    if fallback_rate:
        return round(finished * (1.0 - fallback_rate), 2)
    return None


def parse_brookside_unit_wood_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = VENDOR,
    collection: str = "",
) -> pd.DataFrame:
    """Left-hand Unit # × wood-group prices. Skip the mirrored right copy."""
    if raw is None or raw.empty:
        return pd.DataFrame()
    header_i = None
    unit_col = 0
    desc_col = 1
    woods: list[tuple[int, str]] = []
    unf_col: Optional[int] = None
    right_edge = raw.shape[1]
    for i in range(min(20, len(raw))):
        cells = [_cell(raw.iat[i, j]) for j in range(raw.shape[1])]
        unit_hits = [j for j, c in enumerate(cells) if _UNIT_HDR.match(c)]
        if not unit_hits:
            continue
        unit_col = unit_hits[0]
        right_edge = unit_hits[1] if len(unit_hits) > 1 else raw.shape[1]
        for j, c in enumerate(cells):
            if j <= unit_col:
                continue
            if j >= right_edge:
                break
            if re.search(r"(?i)^desc", c):
                desc_col = j
                continue
            lab = _wood_label(c)
            if lab:
                woods.append((j, lab))
        if woods:
            header_i = i
            break
    if header_i is None or not woods:
        return pd.DataFrame()

    unf_rate = 0.0
    last_wood = woods[-1][0]
    for j in range(last_wood + 1, right_edge):
        if _UNF_NOTE.search(_cell(raw.iat[header_i, j] if j < raw.shape[1] else "")):
            unf_col = j
            break
    for i in range(header_i, min(header_i + 3, len(raw))):
        joined = " ".join(_cell(raw.iat[i, j]) for j in range(min(raw.shape[1], last_wood + 3)))
        if _UNF_NOTE.search(joined):
            pct = re.search(r"(\d+(?:\.\d+)?)\s*%", joined)
            if pct:
                unf_rate = float(pct.group(1)) / 100.0
            last = last_wood + 1
            if last < raw.shape[1] and _UNF_NOTE.search(_cell(raw.iat[i, last])):
                unf_col = last
            break

    rows: list[dict] = []
    seen: set[tuple] = set()
    for i in range(header_i + 1, len(raw)):
        part = _cell(raw.iat[i, unit_col] if unit_col < raw.shape[1] else "")
        if not part or not _SKU.match(part):
            if re.search(r"(?i)standard features|here are the standard", part):
                break
            continue
        desc = _cell(raw.iat[i, desc_col] if desc_col < raw.shape[1] else "") or part
        unf_cell = None
        if unf_col is not None and unf_col < raw.shape[1]:
            unf_cell = raw.iat[i, unf_col]
        elif last_wood + 1 < raw.shape[1]:
            unf_cell = raw.iat[i, last_wood + 1]
        for j, species in woods:
            price = _price(raw.iat[i, j] if j < raw.shape[1] else None)
            if price is None:
                continue
            key = (part, species, "finished", price)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "vendor": vendor,
                    "collection": collection or None,
                    "part_number": part,
                    "description": desc,
                    "option_key": None,
                    "species": species,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
            unf = _unfinished_price(price, unf_cell, fallback_rate=unf_rate)
            if unf is None:
                continue
            rows.append(
                {
                    "vendor": vendor,
                    "collection": collection or None,
                    "part_number": part,
                    "description": desc,
                    "option_key": None,
                    "species": species,
                    "finish_state": "unfinished",
                    "base_price": unf,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                }
            )
    return pd.DataFrame(rows)


def import_brookside_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    from wide_import import detect_markup_from_workbook, import_workbook

    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or VENDOR
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []
    unit_sheets: list[str] = []
    for view in read_all_sheets(data):
        name = view.name
        if sheet_filter is not None and name not in sheet_filter:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "filtered"})
            continue
        if view.role in {"cover", "markup", "empty", "error"} or _SKIP_SHEET.match(
            str(name).strip()
        ):
            tried.append(
                {
                    "sheet": name,
                    "layout": view.role if view.role != "catalog" else "skip",
                    "rows": 0,
                    "note": view.note or "non-product",
                }
            )
            continue
        if view.role == "options":
            tried.append({"sheet": name, "layout": "options", "rows": 0, "note": "book Options"})
            continue
        collection = default_collection or str(name).strip()
        long = parse_brookside_unit_wood_sheet(view.raw, vendor=vendor_name, collection=collection)
        n = 0 if long is None or long.empty else len(long)
        if n:
            unit_sheets.append(name)
            frames.append(long)
            tried.append(
                {"sheet": name, "layout": "brookside_unit_woods", "rows": n, "note": "Unit # woods"}
            )
        else:
            tried.append({"sheet": name, "layout": "other", "rows": 0, "note": "generic later"})

    others = [n for n in names if n not in unit_sheets]
    if sheet_filter is not None:
        others = [n for n in others if n in sheet_filter]
    if others:
        generic = import_workbook(
            data,
            vendor=vendor_name,
            default_collection=default_collection,
            sheet_filter=others,
            filename=filename,
            force_layout_guess=True,
        )
        if generic.long_df is not None and not generic.long_df.empty:
            frames.append(generic.long_df)
        tried.extend(generic.sheets_tried or [])

    frames = [frame for frame in frames if frame is not None and not frame.empty]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=detect_markup_from_workbook(data, names),
            sheet_names=names,
            notes=f"{filename + ': ' if filename else ''}Brookside Unit # woods · {len(out)} rows",
        ),
        "brookside_home_furnishings",
        source="saved",
    )
