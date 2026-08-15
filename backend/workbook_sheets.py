"""Read every Excel tab on Drop. Never skip a sheet unread.

Named parsers and the generic Drop router both start here so Options,
Percentage, Cover, and backup tabs are inspected before anything is
imported or ignored.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

_COVER_RE = re.compile(
    r"(?i)^(cover|title(\s*page)?|index|toc|table\s*of\s*contents|"
    r"instructions?|information(\s*sheet)?|customer\s*letter|notes?|"
    r"dealer\s*info.*)$"
)
_MARKUP_RE = re.compile(
    r"(?i)^(mark\s*-?\s*up|multiplier|multipliers|controls?|settings?)$"
)
_OPTIONS_RE = re.compile(
    r"(?i)option|percentage|portal|addon|upcharge|specialty\s*finish"
)


@dataclass
class SheetView:
    name: str
    role: str  # catalog | options | markup | cover | empty | error
    n_rows: int
    n_cols: int
    raw: Optional[pd.DataFrame] = None
    note: str = ""
    preview: list[str] = field(default_factory=list)


def classify_sheet_role(name: str, raw: Optional[pd.DataFrame]) -> str:
    n = str(name or "").strip()
    if raw is None or raw.empty:
        return "empty"
    if _COVER_RE.match(n):
        return "cover"
    if _MARKUP_RE.match(n):
        return "markup"
    if _OPTIONS_RE.search(n):
        return "options"
    return "catalog"


def _preview(raw: pd.DataFrame, *, limit: int = 4) -> list[str]:
    out: list[str] = []
    for i in range(min(limit, len(raw))):
        cells = []
        for j in range(min(4, raw.shape[1])):
            v = raw.iat[i, j]
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            s = re.sub(r"\s+", " ", str(v)).strip()
            if s:
                cells.append(s[:60])
        if cells:
            out.append(" | ".join(cells)[:160])
    return out


def read_all_sheets(data: bytes) -> list[SheetView]:
    """Open every workbook tab. Callers may ignore a tab only after this."""
    from wide_import import list_excel_sheets

    views: list[SheetView] = []
    for name in list_excel_sheets(data):
        try:
            raw = pd.read_excel(
                io.BytesIO(data), sheet_name=name, header=None, engine="openpyxl"
            )
        except Exception as e:
            views.append(
                SheetView(name=str(name), role="error", n_rows=0, n_cols=0, note=str(e)[:200])
            )
            continue
        raw = raw.dropna(how="all")
        if raw.empty:
            views.append(SheetView(name=str(name), role="empty", n_rows=0, n_cols=0))
            continue
        role = classify_sheet_role(str(name), raw)
        views.append(
            SheetView(
                name=str(name),
                role=role,
                n_rows=int(len(raw)),
                n_cols=int(raw.shape[1]),
                raw=raw,
                preview=_preview(raw),
            )
        )
    return views


def sheets_tried_from_views(
    views: list[SheetView],
    *,
    extra: Optional[dict[str, dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """One sheets_tried row per tab so Drop can show that every sheet was viewed."""
    extra = extra or {}
    out: list[dict[str, Any]] = []
    for v in views:
        over = extra.get(v.name) or {}
        out.append(
            {
                "sheet": v.name,
                "layout": over.get("layout") or f"viewed_{v.role}",
                "rows": over.get("rows", 0),
                "note": over.get("note")
                or v.note
                or f"viewed · {v.role} · {v.n_rows}×{v.n_cols}",
            }
        )
    return out
