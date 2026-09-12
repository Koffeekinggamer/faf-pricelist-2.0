"""RH Yoder: chairs stay on style banners; tables keep style × size × leaf × wood.

The book prints Table Pricing as Beckett Table / Size / Solid / 1 Leaf over woods.
Generic unpivot treats Size as the collection and leaf prices as woods, so Search
for table or Beckett misses every table.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import (
    WorkbookImportResult,
    import_workbook,
    list_excel_sheets,
    looks_like_species_header,
    tag_import_result,
)

VENDOR = "RH Yoder"

_SKIP_SHEET = re.compile(r"(?i)instruction|retail")
_TABLE_SECTION = re.compile(r"(?i)^(table pricing|buffet/?server pricing)\b")
_STYLE = re.compile(r"(?i)\b(?:tables?|pub\s+tables?|servers?|buffets?)\b")
_LEAF = re.compile(r"(?i)^(solid(?:\s+top)?|(?:\d+\s+)?\d+\s*leaf(?:ves)?)$")
_SIZE = re.compile(
    r"""(?ix)
    ^\d+(?:\s*\d+/\d+)?\s*[x×]\s*\d+
    |^\d+\s*["”]
    |^\d+(?:\s*\d+/\d+)?["”]?\s*[wdh]\b
    |^\d{2,3}$
    """
)
_SKIP_STYLE = re.compile(
    r"(?i)upcharge|base price|add on for|species|deduct |available only|"
    r"price includes|self store|levelers|standard|optional|for mixed"
)


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _price(value) -> Optional[float]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        try:
            number = float(str(value).replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
    if number <= 2 or number > 200_000:
        return None
    return round(number, 2)


def _wood(text: str) -> str:
    label = _cell(text)
    if not label or not looks_like_species_header(label):
        return ""
    if re.search(r"(?i)base price|upcharge", label):
        return ""
    return re.sub(r"\s*,\s*", " / ", label)


def _sheet_finish(name: str) -> str:
    return "unfinished" if re.search(r"(?i)unfinish", name or "") else "finished"


def parse_table_section(
    raw: pd.DataFrame,
    *,
    vendor: str = VENDOR,
    finish_state: str = "finished",
) -> pd.DataFrame:
    """Walk the Table Pricing / server bands on one visible sheet."""
    if raw is None or getattr(raw, "empty", True):
        return pd.DataFrame()

    rows: list[dict] = []
    in_tables = False
    style = ""
    style_cells: list[str] = []
    leaf_by_col: dict[int, str] = {}

    def wood_for(col: int) -> str:
        for index in range(col, -1, -1):
            label = _wood(style_cells[index]) if index < len(style_cells) else ""
            if label:
                return label
        return ""

    for values in raw.values.tolist():
        cells = [_cell(value) for value in values]
        first = next((cell for cell in cells if cell), "")
        if _TABLE_SECTION.match(first):
            in_tables = True
            style = ""
            style_cells = []
            leaf_by_col = {}
            continue
        if not in_tables:
            continue
        if _SKIP_STYLE.search(first) and not _STYLE.search(first):
            continue

        woods = [_wood(cell) for cell in cells[1:] if _wood(cell)]
        if first and woods and not any(_price(value) for value in values[1:6]):
            style = first
            if not _STYLE.search(style):
                style = f"{style} Table"
            style_cells = cells
            leaf_by_col = {}
            continue

        if first.lower() == "size":
            leaf_by_col = {
                index: cell for index, cell in enumerate(cells) if index and _LEAF.match(cell)
            }
            continue

        if not style or not _SIZE.match(first):
            continue
        if not any(_price(value) for value in values[1:]):
            continue

        for index, value in enumerate(values):
            if index == 0:
                continue
            price = _price(value)
            if price is None:
                continue
            species = wood_for(index)
            if not species:
                continue
            leaf = leaf_by_col.get(index, "")
            detail = f"{first} {leaf}".strip() if leaf else first
            rows.append(
                {
                    "vendor": vendor,
                    "collection": style,
                    "part_number": first,
                    "description": detail,
                    "dimensions": first,
                    "option_key": None,
                    "species": species,
                    "species_tier": None,
                    "finish_state": finish_state,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                    "line_kind": "item",
                }
            )
    return pd.DataFrame(rows)


def import_rh_yoder_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    vendor_name = (vendor or "").strip() or VENDOR
    names = list_excel_sheets(data)
    keep = [
        name
        for name in names
        if not _SKIP_SHEET.search(str(name)) and (sheet_filter is None or name in sheet_filter)
    ]
    chairs = import_workbook(
        data,
        vendor=vendor_name,
        default_collection=default_collection,
        sheet_filter=keep,
        filename=filename,
        force_layout_guess=True,
    )
    long = chairs.long_df
    if long is not None and not long.empty:
        collection = long.get("collection", pd.Series(dtype=str)).fillna("").astype(str)
        long = long.loc[~collection.str.fullmatch(r"(?i)size")].reset_index(drop=True)

    frames = [long] if long is not None and not long.empty else []
    tried = list(chairs.sheets_tried or [])
    for view in read_all_sheets(data):
        if view.name not in keep or view.raw is None:
            continue
        tables = parse_table_section(
            view.raw,
            vendor=vendor_name,
            finish_state=_sheet_finish(view.name),
        )
        n = 0 if tables is None or tables.empty else len(tables)
        tried.append(
            {
                "sheet": view.name,
                "layout": "rh_yoder_tables",
                "rows": n,
                "note": "style × size × leaf",
            }
        )
        if n:
            frames.append(tables)

    frames = [
        frame.dropna(axis=1, how="all") for frame in frames if frame is not None and not frame.empty
    ]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    tagged = tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=chairs.detected_markup,
            sheet_names=names,
            notes=f"{filename + ': ' if filename else ''}RH Yoder chairs + tables · {len(out)} rows",
            expected_option_lines=chairs.expected_option_lines,
        ),
        "rh_yoder",
        source="saved",
    )
    from backend.book_options import merge_book_options

    return merge_book_options(tagged, data, vendor=vendor_name)
