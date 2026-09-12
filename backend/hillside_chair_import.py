"""Hillside Chair — multi-section Unf/Fin under Oak/Brown Maple/Cherry/Elm/Walnut."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from wide_import import (
    WorkbookImportResult,
    _clean_long_rows,
    _norm,
    _to_float,
    list_excel_sheets,
    looks_like_species_header,
)


def looks_like_hillside_chair(filename: str = "", sheet_names: Optional[list[str]] = None) -> bool:
    fn = (filename or "").lower().replace("_", " ")
    if "hillside chair" in fn or "hillside_chair" in (filename or "").lower():
        return True
    names = sheet_names or []
    return (
        bool(names)
        and names[0].lower() == "master"
        and any(re.fullmatch(r"(?i)sheet\d+", str(n)) for n in names)
        and len(names) >= 8
    )


def import_hillside_chair_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """Hillside: multi-section Unf/Fin under Oak/Brown Maple/Cherry/Elm/Walnut."""
    names = list_excel_sheets(data)
    vendor_name = vendor or "Hillside Chair"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []
    # Product sheets only (skip Master index, finishing adders Sheet2)
    product_sheets = [
        n
        for n in names
        if re.fullmatch(r"(?i)sheet\s*\d+", str(n).replace(" ", ""))
        or re.fullmatch(r"(?i)sheet\d+", str(n))
    ]
    # Sheet1=index, Sheet2=finish adders — start product pages at Sheet3
    product_sheets = [
        n
        for n in names
        if re.match(r"(?i)^sheet\s*\d+$", str(n).strip())
        and int(re.search(r"\d+", str(n)).group()) >= 3
    ]
    if sheet_filter is not None:
        product_sheets = [n for n in product_sheets if n in sheet_filter]

    for name in names:
        if name not in product_sheets:
            if sheet_filter is None or name not in (sheet_filter or []):
                tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "index/adders"})
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").reset_index(drop=True)
        rows = []
        current_style = default_collection or None
        # species groups: col pairs starting at 2: (unf, fin) per species block
        species_labels: list[str] = []
        col_map: list[tuple[int, str, str]] = []  # col, species, finish

        for i in range(len(raw)):
            c0 = _norm(raw.iat[i, 0]) if raw.shape[1] else ""
            c1 = _norm(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
            # Style header row: "Small Avon: AC364 Side | ..."
            if c0 and re.search(r"(?i)side\s*chair|arm\s*chair|:.*AC\d|:\s*AC", c0 + " " + c1):
                # may be style on col0 with species on same row
                style_m = re.match(r"^([^:]+):", c0)
                if style_m:
                    current_style = style_m.group(1).strip()
                elif ":" in c0:
                    current_style = c0.split(":")[0].strip()
                # rebuild species map from this row
                species_labels = []
                for j in range(2, raw.shape[1]):
                    lab = _norm(raw.iat[i, j])
                    if lab and looks_like_species_header(lab):
                        # collapse multi-wood cell to first wood token group
                        species_labels.append((j, lab.split()[0] if lab else lab))
                continue
            # Unf/Fin header row
            cells = [_norm(raw.iat[i, j]) if j < raw.shape[1] else "" for j in range(raw.shape[1])]
            unf_hits = sum(1 for c in cells if re.fullmatch(r"(?i)unf\.?", c))
            fin_hits = sum(1 for c in cells if re.fullmatch(r"(?i)fin\.?", c))
            if unf_hits >= 2 and fin_hits >= 2:
                col_map = []
                # walk columns; carry species from previous non-empty top
                # species names sit on prior row — re-read previous
                if i > 0:
                    tops = [
                        _norm(raw.iat[i - 1, j]) if j < raw.shape[1] else ""
                        for j in range(raw.shape[1])
                    ]
                else:
                    tops = [""] * raw.shape[1]
                carry = ""
                for j in range(2, raw.shape[1]):
                    top = tops[j] if j < len(tops) else ""
                    bot = cells[j]
                    if top and looks_like_species_header(top):
                        # first word of multi-wood banner
                        carry = re.split(r"\s{2,}|\s+(?=Rustic|QSWO)", top)[0].strip()
                        # better: take known woods
                        m = re.search(
                            r"(?i)(brown\s*maple|red\s*oak|white\s*oak|rustic\s*wo|"
                            r"oak|maple|cherry|hickory|elm|qswo|walnut)",
                            top,
                        )
                        if m:
                            carry = m.group(1).title().replace("Qswo", "QSWO")
                    if re.fullmatch(r"(?i)unf\.?", bot) and carry:
                        col_map.append((j, carry, "unfinished"))
                    elif re.fullmatch(r"(?i)fin\.?", bot) and carry:
                        col_map.append((j, carry, "finished"))
                continue

            # Product row: desc in col1, optional suffix in col0
            desc = c1 or c0
            if not desc or not col_map:
                continue
            if re.search(r"(?i)profile comfort|fabric seat|add \$|hardwood xx", desc):
                continue
            suffix = (
                c0 if c0.startswith("-") or re.match(r"^-", c0.replace("\xa0", "").strip()) else ""
            )
            suffix = re.sub(r"[\xa0\s]+", "", suffix)
            part = f"{current_style or ''} {desc} {suffix}".strip()
            part = re.sub(r"\s+", " ", part)
            any_p = False
            for j, sp, fin in col_map:
                if j >= raw.shape[1]:
                    continue
                price = _to_float(raw.iat[i, j])
                if price is None or price < 20:
                    continue
                any_p = True
                rows.append(
                    {
                        "vendor": vendor_name,
                        "collection": current_style,
                        "part_number": part,
                        "description": part,
                        "dimensions": None,
                        "option_key": suffix or None,
                        "species": sp,
                        "species_tier": None,
                        "finish_state": fin,
                        "base_price": price,
                        "price_basis": "wholesale",
                        "unit": None,
                        "notes": None,
                    }
                )
            if not any_p and c0 and not c1 and len(c0) < 60:
                # bare style line without colon
                if not re.search(r"(?i)add |seat", c0):
                    current_style = c0

        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        tried.append(
            {
                "sheet": name,
                "layout": "hillside_unf_fin",
                "rows": len(long),
                "note": f"style={current_style}",
            }
        )
        if not long.empty:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not out.empty:
        # Hillside repeats each visible wholesale band in place. The repeated
        # rows are identical across the full sellable record; keep one without
        # merging rows that differ by SKU, wood, finish, or price.
        out = out.drop_duplicates().reset_index(drop=True)
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
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Hillside Chair Unf/Fin · {len(out) if not out.empty else 0} rows",
    )
