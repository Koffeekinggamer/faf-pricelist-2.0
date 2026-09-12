"""Millers Woodshop — section titles + SKU-only rows → floor descriptions.

The book prints a banner (Bookcases, Gun Cabinets) then SKU-only lines
(``36 x 72``, ``M-140``). Generic unpivot keeps the SKU as the description;
this reader fills a floor-friendly label from the section. Not in the
48-builder SSD catalog — locked so the next selling Drop reuses it.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

import pandas as pd

from wide_import import WorkbookImportResult, tag_import_result

VENDOR = "Millers Woodshop"
PARSER_ID = "millers_woodshop"


def looks_like_millers(
    filename: str = "",
    sheet_names: Optional[Sequence[str]] = None,
    data: Optional[bytes] = None,
) -> bool:
    """MWS / Millers filename, tab, or xlsx XML. Does not claim Millcraft."""
    from backend.catalog_readers import _haystack, _xlsx_mentions

    fn = (filename or "").lower().replace("_", " ")
    if "miller" in fn or re.search(r"\bmws\b", fn):
        return True
    hay = _haystack(filename, sheet_names)
    if re.search(r"\bmillers?\s*woodshop\b", hay) or re.search(r"\bmws\b", hay):
        return True
    return _xlsx_mentions(data, (b"Millers Woodshop", b"Miller's Woodshop"))


def enhance_millers_long_df(df: pd.DataFrame) -> pd.DataFrame:
    """Fill descriptions from collection/section when the builder only ships SKUs."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for index, row in out.iterrows():
        part = _cell(row.get("part_number"))
        desc = _cell(row.get("description"))
        coll = _cell(row.get("collection"))
        if not part:
            continue
        if desc and desc != part:
            continue
        if re.match(r"^\d+(\.\d+)?\s*x\s*\d+", part, re.I):
            label = coll or "Bookcase"
            label = re.sub(r"(?i)^mult-?", "", label).strip() or "Bookcase"
            out.at[index, "description"] = f"{label} {part}"
        elif coll:
            coll_clean = re.sub(r"(?i)^mult-?", "", coll).strip()
            out.at[index, "description"] = f"{coll_clean} {part}".strip()
        else:
            out.at[index, "description"] = part
    return out


def _cell(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def import_millers_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    from wide_import import import_workbook

    result = import_workbook(
        data,
        vendor=vendor or VENDOR,
        default_collection=default_collection,
        sheet_filter=sheet_filter,
        filename=filename,
        force_layout_guess=True,
    )
    result.long_df = enhance_millers_long_df(result.long_df)
    if vendor and result.long_df is not None and not result.long_df.empty:
        result.long_df["vendor"] = vendor or VENDOR
    return tag_import_result(result, PARSER_ID, source="saved")
