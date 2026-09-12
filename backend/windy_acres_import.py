"""Windy Acres — multi-section wood groups above FINISHED/UNFINISHED pairs."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from wide_import import (
    WorkbookImportResult,
    _clean_long_rows,
    _norm,
    _to_float,
    detect_markup_from_workbook,
    list_excel_sheets,
)


def looks_like_windy_acres(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
    data: Optional[bytes] = None,
) -> bool:
    fn = (filename or "").lower().replace("_", " ").replace("-", " ").replace("/", " ")
    if "windy" in fn and "acres" in fn:
        return True
    from backend.catalog_readers import _xlsx_mentions

    return _xlsx_mentions(data, (b"Windy Acres", b"WINDY ACRES"))


_WINDY_WOOD_HINT = re.compile(
    r"(?i)oak|maple|cherry|walnut|hickory|elm|ash|qswo|qsw|wormy|rustic|sap\s*cherry"
)


def _windy_species_label(cell) -> str:
    """Turn multi-line wood group cell into slash-separated species label."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    t = str(cell).replace("\r", "\n")
    # Reject section titles / non-wood cells
    flat = re.sub(r"\s+", " ", t).strip()
    if re.search(r"(?i)collection|dimension|item\s*#|finished|unfinished|two\s*tone", flat):
        if not _WINDY_WOOD_HINT.search(flat):
            return ""
    if not _WINDY_WOOD_HINT.search(t):
        return ""
    parts = []
    for line in t.split("\n"):
        line = re.sub(r"\s+", " ", line).strip(" \t-•")
        if not line or not _WINDY_WOOD_HINT.search(line):
            continue
        line = re.sub(
            r"(?i)\br(?:u)?\.?\s*(?P<wood>qswo|qsw|hickory|walnut|wal|cherry|oak|maple)\b",
            lambda m: (
                "Rustic "
                + {
                    "qswo": "QSWO",
                    "qsw": "QSWO",
                    "wal": "Walnut",
                }.get(m.group("wood").lower(), m.group("wood").title())
            ),
            line,
        )
        line = re.sub(r"(?i)cherry-hickory", "Cherry / Hickory", line)
        parts.append(line)
    seen = set()
    out = []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return " / ".join(out)


_WINDY_TITLE_SKIP = re.compile(
    r"(?i)dimension|markup|instruction|read first|^options?$|password|"
    r"portal|login|please read|^add\s|per (?:piece|drawer|bed)|cost is"
)


def _windy_item_header_col(raw: pd.DataFrame, i: int) -> Optional[int]:
    """ITEM # can sit in column 0 (Master) or column 1 (Bedroom Collection)."""
    for j in range(min(4, raw.shape[1])):
        if re.match(r"(?i)^item\s*#?$", _norm(raw.iat[i, j])):
            return j
    return None


def _windy_first_text(raw: pd.DataFrame, i: int) -> str:
    for j in range(min(3, raw.shape[1])):
        text = _norm(raw.iat[i, j])
        if text:
            return text
    return ""


def parse_windy_acres_sheet(
    raw: pd.DataFrame, *, vendor: str = "Windy Acres Furniture"
) -> pd.DataFrame:
    """
    Walk visible Windy sheets (Master or Bedroom Collection):
      [collection title]
      woodgroup1 | woodgroup2 | …
      ITEM # | Description | D | W | H | FINISHED | UNFINISHED | …
      1702 | Night stand | 16.25 | 22 | 27.75 | 429 | 377 | …
    Hidden Master/backup tabs are never opened — callers pass visible frames only.
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    current_collection: Optional[str] = None
    price_cols: list[tuple[int, str, str]] = []
    dim_cols: dict[str, int] = {}
    item_col = 0
    desc_col: Optional[int] = None
    last_wood_labels: dict[int, str] = {}
    last_pair_species: list[str] = []

    def _is_item_header(s: str) -> bool:
        return bool(re.match(r"(?i)^item\s*#?$", (s or "").strip()))

    def _is_finish(s: str) -> bool:
        k = s.strip().lower()
        return k in {"finished", "finshed", "unfinished", "unf"}

    def _bind_price_cols(i: int, wood_labels_by_col: dict[int, str]) -> list[tuple[int, str, str]]:
        bound: list[tuple[int, str, str]] = []
        carry_species = ""
        pair_i = 0
        for j in range(raw.shape[1]):
            cell = _norm(raw.iat[i, j])
            if not cell:
                continue
            if _is_finish(cell):
                sp = wood_labels_by_col.get(j) or carry_species
                if not sp:
                    for k in range(j, -1, -1):
                        if k in wood_labels_by_col:
                            sp = wood_labels_by_col[k]
                            break
                if (not sp or not _WINDY_WOOD_HINT.search(sp)) and pair_i < len(last_pair_species):
                    sp = last_pair_species[pair_i]
                if not sp or not _WINDY_WOOD_HINT.search(sp):
                    sp = f"Wood Tier {len(bound) // 2 + 1}"
                else:
                    carry_species = sp
                fin = "unfinished" if "unf" in cell.lower() else "finished"
                bound.append((j, sp, fin))
                if fin == "unfinished" or (bound and len(bound) % 2 == 0):
                    pair_i = len(bound) // 2
            elif j in wood_labels_by_col and _WINDY_WOOD_HINT.search(wood_labels_by_col[j]):
                carry_species = wood_labels_by_col[j]
        if not bound:
            for j in range(raw.shape[1]):
                lab = _windy_species_label(raw.iat[i, j])
                if lab:
                    bound.append((j, lab, "finished"))
        return bound

    for i in range(len(raw)):
        header_col = _windy_item_header_col(raw, i)
        title = _windy_first_text(raw, i)

        if header_col is None and title and not _is_item_header(title) and len(title) < 80:
            nums = [_to_float(raw.iat[i, j]) for j in range(raw.shape[1])]
            if not any(n is not None for n in nums):
                if re.search(
                    r"(?i)collection|bedroom|occasionals|with one drawer|without drawers|solid color",
                    title,
                ) or (title[0].isupper() and " " in title and len(title) > 8):
                    if not _WINDY_TITLE_SKIP.search(title):
                        current_collection = title

        if header_col is not None:
            item_col = header_col
            price_cols = []
            dim_cols = {}
            desc_col = None
            wood_row = raw.iloc[i - 1] if i > 0 else None
            wood_row2 = raw.iloc[i - 2] if i > 1 else None

            for j in range(raw.shape[1]):
                lab = _norm(raw.iat[i, j]).lower().replace('"', "")
                if _is_item_header(_norm(raw.iat[i, j])) or _is_finish(_norm(raw.iat[i, j])):
                    continue
                if lab in {"description", "desc"}:
                    desc_col = j
                    continue
                from backend.standardize import dimension_axis

                axis = dimension_axis(raw.iat[i, j])
                if axis:
                    dim_cols[axis] = j

            wood_labels_by_col: dict[int, str] = {}
            for src in (wood_row2, wood_row):
                if src is None:
                    continue
                for j in range(raw.shape[1]):
                    lab = _windy_species_label(src.iloc[j] if j < len(src) else None)
                    if lab and not re.match(r"(?i)^dimension", lab):
                        wood_labels_by_col[j] = lab
            if not wood_labels_by_col and last_wood_labels:
                wood_labels_by_col = dict(last_wood_labels)
            elif wood_labels_by_col:
                last_wood_labels = dict(wood_labels_by_col)

            price_cols = _bind_price_cols(i, wood_labels_by_col)
            if price_cols:
                pairs: list[str] = []
                for idx, (_j, sp, _fin) in enumerate(price_cols):
                    if idx % 2 == 0:
                        pairs.append(sp)
                last_pair_species = pairs
            continue

        if not price_cols:
            continue
        part = _norm(raw.iat[i, item_col]) if item_col < raw.shape[1] else ""
        if not part:
            part = title
        if not part or _is_item_header(part) or re.match(r"(?i)^dimension", part):
            continue
        any_price = any(
            _to_float(raw.iat[i, j]) is not None for j, _, _ in price_cols if j < raw.shape[1]
        )
        if not any_price:
            continue

        desc = part
        if desc_col is not None:
            labeled = _norm(raw.iat[i, desc_col])
            if labeled:
                desc = labeled
        elif "-" in part:
            bits = part.split("-", 1)
            if len(bits) == 2 and re.match(r"^[A-Za-z]", bits[1]):
                desc = bits[1].replace("-", " ")

        dims_parts = []
        for key in ("H", "W", "D", "HB H", "FB H"):
            if key in dim_cols:
                v = raw.iat[i, dim_cols[key]]
                if pd.notna(v):
                    dims_parts.append(f'{key}"{v}')
        dims = " × ".join(dims_parts) if dims_parts else None

        for tier_i, (j, species, finish) in enumerate(price_cols, start=1):
            if j >= raw.shape[1]:
                continue
            price = _to_float(raw.iat[i, j])
            if price is None:
                continue
            rows.append(
                {
                    "vendor": vendor,
                    "collection": current_collection,
                    "part_number": part,
                    "description": desc,
                    "dimensions": dims,
                    "option_key": None,
                    "species": species,
                    "species_tier": (tier_i + 1) // 2,
                    "finish_state": finish,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                }
            )

    return _clean_long_rows(pd.DataFrame(rows))


def import_windy_acres_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    from backend.workbook_sheets import read_all_sheets

    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or "Windy Acres Furniture"
    frames = []
    tried = []
    # Every visible tab is opened. Hidden Master / Braylon stay hidden.
    for view in read_all_sheets(data):
        name = view.name
        if sheet_filter is not None and name not in sheet_filter:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "filtered"})
            continue
        if view.role in {"cover", "markup", "empty", "error"}:
            tried.append(
                {
                    "sheet": name,
                    "layout": view.role,
                    "rows": 0,
                    "note": view.note or "non-product",
                }
            )
            continue
        long = parse_windy_acres_sheet(view.raw, vendor=vendor_name)
        n = len(long) if long is not None and not long.empty else 0
        tried.append(
            {
                "sheet": name,
                "layout": "windy_acres_wood_groups",
                "rows": n,
                "note": "wood groups above FINISHED/UNFINISHED",
            }
        )
        if n > 0:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out
        if not out.empty
        else pd.DataFrame(
            columns=[
                "vendor",
                "collection",
                "part_number",
                "description",
                "dimensions",
                "option_key",
                "species",
                "species_tier",
                "finish_state",
                "base_price",
                "price_basis",
                "unit",
                "notes",
            ]
        ),
        detected_markup=detect_markup_from_workbook(data, names),
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Windy Acres wood-group import · {len(out) if not out.empty else 0} rows",
    )
