"""Maple Lane — CODE + desc on row N, prices on N+1 under species columns."""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from backend.visible_addons import visible_addon
from wide_import import (
    WorkbookImportResult,
    _clean_long_rows,
    _norm,
    _to_float,
    list_excel_sheets,
    looks_like_species_header,
)


def _maple_lane_visible_options(raw: pd.DataFrame, vendor: str) -> pd.DataFrame:
    """Named color/material choices printed in Maple Lane's visible notes."""
    text = "\n".join(
        " ".join(_norm(value) for value in row if _norm(value)) for row in raw.values.tolist()
    )
    labels: list[str] = []
    if "Maui Quartz = MQ" in text:
        labels.extend(
            [
                "Corian top — Maui Quartz",
                "Corian top — Silver Birch",
                "Corian top — Hazelnut",
                "Stain — Earth Tone",
                "Stain — Smoke",
                "Stain — Ebony",
            ]
        )
    if re.search(r"(?i)crypton\s+fabric\s+pads?.*three\s+colors", text):
        labels.extend(
            [
                "Crypton fabric pad — Breeze",
                "Crypton fabric pad — Home",
                "Crypton fabric pad — Arrow",
            ]
        )
    if re.search(r"(?i)carpet\s+optional\s*\(same\s+price\)", text):
        labels.extend(["Carpet insert — Coal", "Carpet insert — Apex"])
    return pd.DataFrame(
        [
            visible_addon(
                vendor,
                label,
                amount=0.0,
                notes="no upcharge — named choice from visible source note",
            )
            for label in dict.fromkeys(labels)
        ]
    )


def looks_like_maple_lane(filename: str = "") -> bool:
    fn = (filename or "").lower().replace("_", " ")
    return "maple lane" in fn or "maple_lane" in (filename or "").lower()


def import_maple_lane_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """Maple Lane: CODE + desc on row N, prices on N+1 under species columns."""
    names = list_excel_sheets(data)
    vendor_name = vendor or "Maple Lane Woodshop"
    # Prefer wholesale
    prefer = [n for n in names if re.search(r"(?i)wholesale", str(n))]
    targets = sheet_filter if sheet_filter is not None else (prefer or names)
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    for name in names:
        if name not in targets:
            if sheet_filter is None and re.search(r"(?i)retail", str(name)) and prefer:
                tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "retail"})
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").reset_index(drop=True)
        rows = []
        current_collection = default_collection or None
        species_cols: list[tuple[int, str]] = []  # col, species

        for i in range(len(raw)):
            c0 = _norm(raw.iat[i, 0]) if raw.shape[1] else ""
            # Collection banner
            row_vals = [
                _norm(raw.iat[i, j]) if j < raw.shape[1] else ""
                for j in range(min(raw.shape[1], 8))
            ]
            joined = " ".join(v for v in row_vals if v)
            if (
                joined
                and not c0
                and re.search(
                    r"(?i)pet diner|dining station|cabinet|end table|coffee|ramp|gate|toy box|lormel",
                    joined,
                )
            ):
                current_collection = joined[:60]
            # Species header: CODE ... RED OAK | BR. MAPLE | ...
            if re.fullmatch(r"(?i)code", c0) or (
                any(looks_like_species_header(v) for v in row_vals[3:10])
                and sum(1 for v in row_vals if looks_like_species_header(v)) >= 2
            ):
                species_cols = []
                for j in range(raw.shape[1]):
                    lab = _norm(raw.iat[i, j])
                    if lab and looks_like_species_header(lab):
                        species_cols.append((j, lab))
                continue
            # Unfinished/Finished subheader
            if sum(1 for v in row_vals if re.fullmatch(r"(?i)unfinished|finished", v)) >= 2:
                # remap: pair finish under previous species carry
                new_map = []
                carry = ""
                # need previous species row - use current species_cols as anchors
                for j in range(raw.shape[1]):
                    lab = _norm(raw.iat[i, j])
                    if j > 0 and species_cols:
                        # find nearest species col <= j
                        for sc, sn in reversed(species_cols):
                            if sc <= j:
                                carry = sn
                                break
                    if re.fullmatch(r"(?i)unfinished", lab) and carry:
                        new_map.append((j, carry, "unfinished"))
                    elif re.fullmatch(r"(?i)finished", lab) and carry:
                        new_map.append((j, carry, "finished"))
                if new_map:
                    species_cols = [(j, f"{sp} | {fin}") for j, sp, fin in new_map]
                continue

            # SKU row
            if not c0 or not re.match(r"^[A-Z]{2,8}\d", c0, re.I):
                continue
            desc = _norm(raw.iat[i, 1]) if raw.shape[1] > 1 else c0
            # prices often on next row
            price_row = i
            # if this row has no numeric prices, use i+1
            has_here = any(
                _to_float(raw.iat[i, j]) is not None for j, _ in species_cols if j < raw.shape[1]
            )
            if not has_here and i + 1 < len(raw):
                price_row = i + 1
                # also dims may be on next row col1
                if not desc or len(desc) < 3:
                    desc = _norm(raw.iat[i + 1, 1]) if raw.shape[1] > 1 else desc
                d2 = _norm(raw.iat[i + 1, 1]) if raw.shape[1] > 1 else ""
                dims = d2 if d2 and re.search(r"\d", d2) and re.search(r"[x×]", d2, re.I) else None
            else:
                dims = None
                d2 = _norm(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
                if d2 and re.search(r"[x×]", d2, re.I):
                    dims = d2

            for tier_i, (j, sp) in enumerate(species_cols, start=1):
                if j >= raw.shape[1]:
                    continue
                price = _to_float(raw.iat[price_row, j])
                if price is None or price < 5:
                    continue
                finish = "unfinished"
                species_name = sp
                if " | " in sp:
                    species_name, fin = sp.split(" | ", 1)
                    finish = (
                        "finished"
                        if "fin" in fin.lower() and "unf" not in fin.lower()
                        else ("unfinished" if "unf" in fin.lower() else fin.lower())
                    )
                rows.append(
                    {
                        "vendor": vendor_name,
                        "collection": current_collection,
                        "part_number": c0,
                        "description": desc or c0,
                        "dimensions": dims,
                        "option_key": None,
                        "species": species_name,
                        "species_tier": tier_i,
                        "finish_state": finish,
                        "base_price": price,
                        "price_basis": "wholesale",
                        "unit": None,
                        "notes": None,
                    }
                )

        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        option_rows = _maple_lane_visible_options(raw, vendor_name)
        if not option_rows.empty:
            long = pd.concat([long, option_rows], ignore_index=True)
        tried.append(
            {
                "sheet": name,
                "layout": "maple_lane_sku_next_price",
                "rows": len(long),
                "note": f"species_cols={len(species_cols)}",
            }
        )
        if not long.empty:
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
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Maple Lane · {len(out) if not out.empty else 0} rows",
    )
