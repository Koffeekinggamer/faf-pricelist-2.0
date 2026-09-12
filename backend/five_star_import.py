"""Five Star Tables — Oak-priced dining sizes; other woods are Wood-column species.

Visible dining tabs print table sizes (``42x66``) next to a dollar amount with
no wood header. Those prices are Oak. Generic ``multi_name_price`` drops a
pure size used as a name; this reader keeps it.

Options lists % adders for other woods (Walnut +80%, QSWO +45%, …). Those
become sibling item rows in the Wood column, not Search Options. Terms /
Net 30 / levelers / table-of-contents lines are cover junk, not addons.
Hidden leftovers stay hidden.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional, Sequence

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, list_excel_sheets, tag_import_result

VENDOR = "Five Star Tables"
PARSER_ID = "five_star_tables"

_SIZE_SKU = re.compile(
    r"^\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?(?:\s*[x×]\s*\d+(?:\.\d+)?)?$",
    re.I,
)
_WOOD_HEADER = re.compile(
    r"(?i)\b(oak|maple|cherry|walnut|hickory|elm|qswo|qsw)\b"
)
_JUNK_NAME = re.compile(
    r"(?i)phone|fax|email|@|subject to|price list|wholesale|from:|"
    r"order date|due date|please call|table of contents|locks on all|"
    r"levelers|standard table|2%\s+will be added|^terms$|^net\s*30$"
)
_SKIP_SHEET = re.compile(
    r"(?i)^(mark\s*-?\s*up|index|cover|title|instructions?)$"
)
_WOOD_ADDONS = (
    ("Sap Cherry / Brown Maple / Wormy Maple", 15.0),
    ("Cherry / Maple / Elm", 35.0),
    ("Hickory / Rustic Cherry", 25.0),
    ("QSWO / Rustic QSWO / Flat Sawn White Oak", 45.0),
    ("Rustic Hickory", 25.0),
    ("Walnut", 80.0),
    ("Rustic Walnut", 45.0),
    ("Wormy Maple / Walnut Combo", 35.0),
    ("Rustic Hickory / Walnut Combo", 35.0),
)
_FIVE_STAR_JUNK = re.compile(
    r"(?i)^(terms|net 30|standard table|locks on all|levelers|please call|"
    r"2%\s+will be added|table of contents)$"
)


def looks_like_five_star(
    filename: str = "",
    sheet_names: Optional[Sequence[str]] = None,
    data: Optional[bytes] = None,
) -> bool:
    """Five Star's own book: factory name in the file, tabs, or xlsx XML."""
    from backend.catalog_readers import _haystack, _xlsx_mentions

    hay = _haystack(filename, sheet_names)
    compact = hay.replace(" ", "")
    if "fivestartables" in compact or "five star tables" in hay:
        return True
    return _xlsx_mentions(data, (b"Five Star Tables",))


def _cell(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _price(value: Any) -> Optional[float]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        try:
            number = float(str(value).replace("$", "").replace(",", "").strip())
        except ValueError:
            return None
    if number < 5 or number > 50_000:
        return None
    return round(number, 2)


def _looks_like_wide_woods(raw: pd.DataFrame) -> bool:
    """A printed wood column belongs on the leftover wide unpivot, not size|price."""
    for row_i in range(min(8, len(raw))):
        for col_i in range(raw.shape[1]):
            text = _cell(raw.iat[row_i, col_i])
            if _WOOD_HEADER.search(text) and not _SIZE_SKU.match(text):
                return True
    return False


def parse_five_star_oak_price_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = VENDOR,
    collection: str = "",
) -> pd.DataFrame:
    """Name|price dining sizes, including ``42x66``. Blank species is Oak later."""
    if raw is None or raw.empty or raw.shape[1] < 2:
        return pd.DataFrame()
    if _looks_like_wide_woods(raw):
        return pd.DataFrame()
    rows: list[dict] = []
    current = collection.strip() or None
    for position in range(len(raw)):
        cells = raw.iloc[position].tolist()
        texts: list[str] = []
        prices: list[float] = []
        for cell in cells:
            amount = _price(cell)
            if amount is not None:
                prices.append(amount)
                continue
            text = _cell(cell)
            if text:
                texts.append(text)
        if texts and not prices:
            name = texts[0]
            if (
                3 <= len(name) <= 60
                and not _JUNK_NAME.search(name)
                and not _SIZE_SKU.match(name)
            ):
                current = name
            continue
        if not texts or not prices:
            continue
        name = texts[0]
        if _JUNK_NAME.search(name) or _FIVE_STAR_JUNK.search(name):
            continue
        description = name
        if _SIZE_SKU.match(name) and current:
            description = f"{current} {name}"
        rows.append(
            {
                "vendor": vendor,
                "collection": current,
                "part_number": name,
                "description": description,
                "option_key": None,
                "species": None,
                "finish_state": "finished",
                "base_price": prices[0],
                "price_basis": "wholesale",
                "line_kind": "item",
            }
        )
    return pd.DataFrame(rows)


def apply_five_star_oak_tables(df):
    """Tables are priced in Oak; other woods become Wood-column species."""
    from backend.book_options import convert_option_woods_to_species

    if df is None or getattr(df, "empty", True):
        return df
    out = df.copy()
    if "species" not in out.columns:
        out["species"] = None
    if "line_kind" in out.columns:
        kind = out["line_kind"].fillna("item").astype(str).str.lower()
    else:
        kind = "item"
        out["line_kind"] = "item"
    blank = out["species"].isna() | out["species"].astype(str).str.strip().eq("")
    if not isinstance(kind, str):
        blank = blank & (kind != "addon")
    out.loc[blank, "species"] = "Oak"
    if "option_key" in out.columns and not isinstance(kind, str):
        junk = kind.eq("addon") & out["option_key"].fillna("").astype(str).map(
            lambda s: bool(_FIVE_STAR_JUNK.search(s))
        )
        out = out.loc[~junk].reset_index(drop=True)
    adders = {label: pct / 100.0 for label, pct in _WOOD_ADDONS}
    return convert_option_woods_to_species(out, adders)


def import_five_star_workbook(
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
    sized_sheets: list[str] = []
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
        long = parse_five_star_oak_price_sheet(
            view.raw, vendor=vendor_name, collection=collection
        )
        count = 0 if long is None or long.empty else len(long)
        if count:
            sized_sheets.append(name)
            frames.append(long)
            tried.append(
                {
                    "sheet": name,
                    "layout": "five_star_oak_sizes",
                    "rows": count,
                    "note": "Oak-priced dining sizes",
                }
            )
        else:
            tried.append({"sheet": name, "layout": "other", "rows": 0, "note": "generic later"})

    skip_generic = set(sized_sheets)
    for view in read_all_sheets(data):
        if view.role in {"cover", "markup", "empty", "error", "options"}:
            skip_generic.add(view.name)
        if _SKIP_SHEET.match(str(view.name).strip()):
            skip_generic.add(view.name)
    others = [name for name in names if name not in skip_generic]
    if sheet_filter is not None:
        others = [name for name in others if name in sheet_filter]
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
    out = apply_five_star_oak_tables(out)
    return tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=detect_markup_from_workbook(data, names),
            sheet_names=names,
            notes=f"{filename + ': ' if filename else ''}Five Star Oak sizes · {len(out)} rows",
        ),
        PARSER_ID,
        source="saved",
    )
