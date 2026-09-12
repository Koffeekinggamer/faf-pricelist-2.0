"""Hope Wood / HW Chair — Markup Calculator: product name × paired species columns."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.visible_addons import visible_addon
from wide_import import (
    WorkbookImportResult,
    _clean_long_rows,
    _norm,
    _norm_key,
    _to_float,
    detect_markup_from_workbook,
    list_excel_sheets,
    looks_like_species_header,
)


def _hope_wood_visible_options(raw: pd.DataFrame, vendor: str) -> pd.DataFrame:
    """Milano seat/back charges printed as prose below the product rows."""
    text = "\n".join(
        " ".join(_norm(value) for value in row if _norm(value)) for row in raw.values.tolist()
    )
    if not re.search(r"(?i)fabric\s+seat\s*/\s*wood\s+back.*add\s*\$20", text):
        return pd.DataFrame()
    options = [
        ("Fabric seat / wood back", 20.0),
        ("Leather seat / wood back", 45.0),
        ("Fabric seat and back", 75.0),
        ("Leather seat and back", 125.0),
    ]
    return pd.DataFrame(
        [
            visible_addon(
                vendor,
                label,
                amount=amount,
                notes="per chair from visible Milano option note",
            )
            for label, amount in options
        ]
    )


def looks_like_hw_chair_markup(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    fn = (filename or "").lower().replace("_", " ")
    # Path or download folder often contains HW_Chair
    if re.search(r"\bhw\s*chair\b", fn) or "hw_chair" in (filename or "").lower():
        return True
    names = sheet_names or []
    # Single-sheet markup calculator workbooks (HW Chair Viztech export)
    if names and all(re.search(r"(?i)markup\s*calculator", str(n)) for n in names):
        return True
    return False


def import_hw_chair_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """
    HW Chair 2026 Markup Calculator layout:
      row0: calculator chrome
      row1: species labels (often duplicated pairs: unf/fin or cost/markup)
      row2: letter labels C,D,E… (skip)
      row3+: product name | price pairs per species
    Seat options (Fabric/Leather) are ignored — not wood species.
    """
    names = list_excel_sheets(data)
    vendor_name = vendor or "HW Chair"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    targets = sheet_filter if sheet_filter is not None else list(names)
    for name in names:
        if name not in targets:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "filtered"})
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        if raw.empty or raw.shape[1] < 3:
            tried.append({"sheet": name, "layout": "empty", "rows": 0, "note": ""})
            continue

        # Find species header row (most wood tokens)
        best_i, best_woods = 0, -1
        for i in range(min(8, len(raw))):
            cells = [_norm(v) for v in raw.iloc[i].tolist()]
            woods = sum(1 for c in cells if c and looks_like_species_header(c))
            if woods > best_woods:
                best_woods = woods
                best_i = i
        if best_woods < 2:
            tried.append(
                {
                    "sheet": name,
                    "layout": "unknown",
                    "rows": 0,
                    "note": f"no species header (best_woods={best_woods})",
                }
            )
            continue

        species_row = [_norm(v) for v in raw.iloc[best_i].tolist()]
        # Map col → species; collapse duplicate adjacent pairs to one species
        col_species: list[tuple[int, str]] = []
        seen_pair: set[str] = set()
        j = 1  # col 0 is product name
        while j < len(species_row):
            lab = species_row[j]
            if not lab or not looks_like_species_header(lab):
                # seat options / non-wood
                j += 1
                continue
            # skip fabric/leather seat adders
            if re.search(r"(?i)fabric|leather|seat|premium", lab):
                j += 1
                continue
            # take this column as price source; skip immediate duplicate label next col
            key = lab.lower()
            if key not in seen_pair:
                col_species.append((j, lab))
                seen_pair.add(key)
            # if next col has same species label, skip it (paired unf/fin or cost/copy)
            if j + 1 < len(species_row) and _norm_key(species_row[j + 1]) == key:
                j += 2
            else:
                j += 1

        body_start = best_i + 1
        # skip letter-label row (C, D, E…)
        if body_start < len(raw):
            peek = [_norm(v) for v in raw.iloc[body_start].tolist()[1:8] if _norm(v)]
            if peek and all(re.fullmatch(r"[A-Z]", p) for p in peek[:4]):
                body_start += 1

        rows = []
        current_collection: Optional[str] = default_collection or None
        for i in range(body_start, len(raw)):
            name_cell = _norm(raw.iat[i, 0]) if raw.shape[1] else ""
            if not name_cell:
                continue
            # section banner: text only, no prices
            prices_here = [_to_float(raw.iat[i, j]) for j, _sp in col_species if j < raw.shape[1]]
            if not any(p is not None for p in prices_here):
                if 3 <= len(name_cell) <= 60 and not re.match(
                    r"(?i)markup|formula|enter percent", name_cell
                ):
                    current_collection = name_cell
                continue
            if re.fullmatch(r"(?i)page\s*#?|item\s*#?|description", name_cell):
                continue
            for tier_i, (j, sp) in enumerate(col_species, start=1):
                if j >= raw.shape[1]:
                    continue
                price = _to_float(raw.iat[i, j])
                if price is None:
                    # try pair sibling
                    if j + 1 < raw.shape[1]:
                        price = _to_float(raw.iat[i, j + 1])
                if price is None or price < 5:
                    continue
                rows.append(
                    {
                        "vendor": vendor_name,
                        "collection": current_collection,
                        "part_number": name_cell,
                        "description": name_cell,
                        "dimensions": None,
                        "option_key": None,
                        "species": sp,
                        "species_tier": tier_i,
                        "finish_state": "unfinished",
                        "base_price": price,
                        "price_basis": "wholesale",
                        "unit": None,
                        "notes": None,
                    }
                )

        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        option_rows = _hope_wood_visible_options(raw, vendor_name)
        if not option_rows.empty:
            long = pd.concat([long, option_rows], ignore_index=True)
        n = len(long)
        tried.append(
            {
                "sheet": name,
                "layout": "hw_chair_markup",
                "rows": n,
                "note": f"species_cols={len(col_species)} header_i={best_i}",
                "id_col": "col_0",
                "desc_col": "col_0",
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
        notes=f"{filename + ': ' if filename else ''}HW Chair markup calculator · {len(out) if not out.empty else 0} rows",
    )
