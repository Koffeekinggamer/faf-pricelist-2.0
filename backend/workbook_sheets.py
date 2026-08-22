"""Read every *visible* Excel tab on Drop.

Never unhide a sheet or row. Factories hide Masters, backups, and leftover
tables that often duplicate the visible book. Named parsers and the generic
Drop router start here so Options, Percentage, Cover, and backup tabs that
are visible are inspected; hidden tabs stay hidden and unread.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Union

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
    r"(?i)option|percentage|portal|add[\s_-]*ons?|addon|upcharge|"
    r"specialty\s*finish|customi[sz]ation|personalization|features"
)

# OLE Compound File magic — BIFF .xls, not a zip .xlsx
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"


def excel_engine(data: bytes) -> str:
    """Pick the pandas Excel adapter from file magic, not the filename.

    One seam for Drop, named readers, and Viztech: BIFF .xls uses xlrd,
    Office Open XML uses openpyxl. Callers pass bytes; they do not choose
    an engine.
    """
    head = bytes(data or b"")[:8]
    if head.startswith(_OLE_MAGIC):
        return "xlrd"
    return "openpyxl"


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


def hidden_sheet_names(data: bytes) -> set[str]:
    """Sheet titles marked hidden / veryHidden. Does not unhide them."""
    found: set[str] = set()
    if excel_engine(data) == "xlrd":
        try:
            import xlrd

            book = xlrd.open_workbook(file_contents=data, formatting_info=False)
            for i, name in enumerate(book.sheet_names()):
                if getattr(book.sheet_by_index(i), "visibility", 0):
                    found.add(str(name))
        except Exception:
            return found
        return found
    try:
        from xml.etree import ElementTree as ET
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml = zf.read("xl/workbook.xml")
        root = ET.fromstring(xml)
        ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for sh in root.findall(".//m:sheet", ns):
            state = (sh.attrib.get("state") or "visible").lower()
            if state != "visible":
                name = sh.attrib.get("name") or ""
                if name:
                    found.add(name)
    except Exception:
        pass
    return found


def hidden_product_candidates(data: bytes) -> list[str]:
    """Hidden tabs whose names read like sellable collections.

    Reporting only — the caller still Drops visible content. Master, markup,
    index, and ``bk``/backup/old/copy tabs are known internals, so they never
    become candidates. Judson decides whether a candidate is real product.
    """
    hidden = hidden_sheet_names(data)
    if not hidden:
        return []
    known_internal = re.compile(
        r"^\s*(?:master|markup|mark[\s_-]*up|index|contents?|toc|template|"
        r"calc\w*|pivot|data|notes?|instructions?|summary)\b"
        r"|\b(?:bk|bak|backup|old|copy|orig(?:inal)?|do\s*not\s*use|"
        r"archive|test|temp)\b"
        r"|\(\d+\)\s*$",
        re.IGNORECASE,
    )
    out = [
        name
        for name in sorted(hidden)
        if not known_internal.search(str(name).strip())
        and not _COVER_RE.match(str(name).strip())
        and not _MARKUP_RE.match(str(name).strip())
    ]
    return out


def hidden_row_indexes(data: bytes, sheet_name: Union[str, int]) -> set[int]:
    """0-based pandas indexes of hidden Excel rows (header=None → row 0 is Excel 1)."""
    hidden: set[int] = set()
    if excel_engine(data) == "xlrd":
        try:
            import xlrd

            book = xlrd.open_workbook(file_contents=data, formatting_info=True)
            if isinstance(sheet_name, int):
                ws = book.sheet_by_index(sheet_name)
            else:
                ws = book.sheet_by_name(str(sheet_name))
            info = getattr(ws, "rowinfo_map", {}) or {}
            for r, meta in info.items():
                if getattr(meta, "hidden", 0):
                    hidden.add(int(r))
        except Exception:
            return hidden
        return hidden
    try:
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=False, data_only=False)
        ws = wb[sheet_name] if not isinstance(sheet_name, int) else wb.worksheets[sheet_name]
        for idx, dim in ws.row_dimensions.items():
            if dim.hidden and isinstance(idx, int) and idx >= 1:
                hidden.add(idx - 1)
        wb.close()
    except Exception:
        return hidden
    return hidden


def drop_hidden_rows(df: pd.DataFrame, data: bytes, sheet_name: Union[str, int]) -> pd.DataFrame:
    """Drop hidden Excel rows without unhiding them in the file."""
    skip = hidden_row_indexes(data, sheet_name)
    if not skip or df is None or df.empty:
        return df
    keep = [i for i in df.index if int(i) not in skip]
    return df.loc[keep].reset_index(drop=True)


def hidden_rows_by_sheet(
    data: bytes,
    sheet_names: list[str],
) -> dict[str, set[int]]:
    """Read hidden-row metadata once for a multi-sheet Drop."""
    found = {str(name): set() for name in sheet_names}
    if excel_engine(data) == "xlrd":
        try:
            import xlrd

            book = xlrd.open_workbook(file_contents=data, formatting_info=True)
            for name in sheet_names:
                ws = book.sheet_by_name(str(name))
                for row_index, meta in (getattr(ws, "rowinfo_map", {}) or {}).items():
                    if getattr(meta, "hidden", 0):
                        found[str(name)].add(int(row_index))
        except Exception:
            pass
        return found
    try:
        import posixpath
        import zipfile
        from xml.etree import ElementTree as ET

        main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        doc_rel_ns = (
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        )
        package_rel_ns = (
            "http://schemas.openxmlformats.org/package/2006/relationships"
        )
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(
                archive.read("xl/_rels/workbook.xml.rels")
            )
            targets = {
                rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
                for rel in relationships.findall(
                    f"{{{package_rel_ns}}}Relationship"
                )
            }
            wanted = set(str(name) for name in sheet_names)
            for sheet in workbook.findall(f".//{{{main_ns}}}sheet"):
                name = str(sheet.attrib.get("name") or "")
                if name not in wanted:
                    continue
                rel_id = sheet.attrib.get(f"{{{doc_rel_ns}}}id", "")
                target = targets.get(rel_id, "")
                if not target:
                    continue
                xml_path = (
                    target.lstrip("/")
                    if target.startswith("/xl/")
                    else posixpath.normpath(posixpath.join("xl", target))
                )
                if xml_path.startswith("xl/"):
                    pass
                elif xml_path.startswith("xl"):
                    xml_path = "xl/" + xml_path[2:].lstrip("/")
                root = ET.fromstring(archive.read(xml_path))
                for row in root.findall(f".//{{{main_ns}}}row"):
                    if str(row.attrib.get("hidden") or "").lower() not in {
                        "1",
                        "true",
                    }:
                        continue
                    row_number = int(row.attrib.get("r") or 0)
                    if row_number >= 1:
                        found[name].add(row_number - 1)
    except Exception:
        pass
    return found


def read_sheet(
    data: bytes,
    sheet_name: Union[str, int],
    *,
    header: Optional[int] = None,
) -> pd.DataFrame:
    """Bytes-in sheet adapter. Visible rows only. Callers never pick an engine."""
    raw = pd.read_excel(
        io.BytesIO(data),
        sheet_name=sheet_name,
        header=header,
        engine=excel_engine(data),
    )
    if header is None:
        return drop_hidden_rows(raw, data, sheet_name)
    return raw


def read_all_sheets(data: bytes) -> list[SheetView]:
    """Open every visible workbook tab. Hidden tabs are not read."""
    from wide_import import list_excel_sheets

    views: list[SheetView] = []
    names = list_excel_sheets(data)
    hidden_rows = hidden_rows_by_sheet(data, names)
    engine = excel_engine(data)
    if engine == "openpyxl":
        import openpyxl

        workbook = openpyxl.load_workbook(
            io.BytesIO(data),
            read_only=True,
            data_only=True,
            keep_links=False,
        )

        def parse_sheet(name: str) -> pd.DataFrame:
            return pd.DataFrame(
                workbook[str(name)].iter_rows(values_only=True)
            )

    else:
        try:
            workbook = pd.ExcelFile(io.BytesIO(data), engine=engine)
        except Exception:
            workbook = pd.ExcelFile(io.BytesIO(data))

        def parse_sheet(name: str) -> pd.DataFrame:
            return workbook.parse(sheet_name=name, header=None)

    for name in names:
        try:
            raw = parse_sheet(name)
            skip = hidden_rows.get(str(name)) or set()
            if skip and raw is not None and not raw.empty:
                keep = [index for index in raw.index if int(index) not in skip]
                raw = raw.loc[keep].reset_index(drop=True)
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
    workbook.close()
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
