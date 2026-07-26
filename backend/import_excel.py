"""Excel → long-form price rows (wide species matrix + flat fallback)."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .config import DEFAULT_MULTIPLIER
from .normalize import long_df_to_rows, map_columns, normalize_dataframe, to_float
from .pricing import retail_from_wholesale
from .standardize import resolve_builder_vendor
from .wide_import import import_workbook


def _guess_builder(filename: str, explicit: str = "") -> str:
    if (explicit or "").strip():
        resolved = resolve_builder_vendor(explicit, filename=filename)
        return (resolved or explicit).strip()
    resolved = resolve_builder_vendor("", filename=filename)
    if resolved:
        return resolved
    stem = Path(filename or "Builder").stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or "Builder"


def _simple_parse(data: bytes, filename: str, vendor: str, mult: float) -> dict[str, Any]:
    """Flat table fallback: first sheets with part/desc/price-like columns."""
    try:
        xl = pd.ExcelFile(io.BytesIO(data))
    except Exception as exc:
        return {
            "vendor": vendor,
            "rows": [],
            "error": f"Could not open Excel: {exc}",
            "row_count": 0,
            "detected_markup": None,
            "notes": "",
        }

    rows: list[dict] = []
    notes = []
    for sheet in xl.sheet_names[:12]:
        try:
            df = xl.parse(sheet, dtype=object)
        except Exception:
            continue
        if df.empty or len(df.columns) < 2:
            continue
        df = df.dropna(how="all")
        mapping = map_columns(df)
        if "base_price" not in mapping and len(mapping) < 2:
            # numeric last-column guess
            cols = [str(c).strip() for c in df.columns]
            df.columns = cols
            price_c = None
            for c in reversed(cols):
                sample = pd.to_numeric(df[c], errors="coerce")
                if sample.notna().sum() >= max(3, len(df) // 5):
                    price_c = c
                    break
            if not price_c:
                continue
            part_c = mapping.get("part_number")
            desc_c = mapping.get("description")
            wood_c = mapping.get("species")
            n_before = len(rows)
            for _, r in df.iterrows():
                bp = to_float(r.get(price_c))
                if bp is None or bp <= 0:
                    continue
                desc = str(r.get(desc_c) or "").strip() if desc_c else ""
                part = str(r.get(part_c) or "").strip() if part_c else ""
                if not desc and not part:
                    continue
                wood = str(r.get(wood_c) or "").strip() if wood_c else ""
                rows.append(
                    {
                        "vendor": vendor,
                        "collection": sheet,
                        "part_number": part or None,
                        "description": desc or part,
                        "species": wood or None,
                        "finish_state": "finished",
                        "base_price": bp,
                        "multiplier": mult,
                        "adjusted_price": retail_from_wholesale(bp, mult),
                        "source_file": filename,
                    }
                )
            if len(rows) > n_before:
                notes.append(f"{sheet}:{len(rows) - n_before}")
            continue

        sheet_rows = normalize_dataframe(
            df,
            source_file=filename,
            default_collection=sheet,
            multiplier=mult,
            vendor=vendor,
        )
        if sheet_rows:
            rows.extend(sheet_rows)
            notes.append(f"{sheet}:{len(sheet_rows)}")

    return {
        "vendor": vendor,
        "rows": rows,
        "error": "" if rows else "No price rows found (simple parser).",
        "row_count": len(rows),
        "detected_markup": None,
        "notes": "simple · " + ", ".join(notes) if notes else "simple",
    }


def _wide_parse(data: bytes, filename: str, vendor: str, mult: float) -> dict[str, Any]:
    """Primary path: wide species-matrix unpivot (vendored from v1)."""
    try:
        wb = import_workbook(
            data,
            vendor=vendor,
            filename=filename,
        )
    except Exception as exc:
        return {
            "vendor": vendor,
            "rows": [],
            "error": f"Wide import failed: {exc}",
            "row_count": 0,
            "detected_markup": None,
            "notes": "wide",
        }

    rows = long_df_to_rows(
        wb.long_df,
        source_file=filename,
        multiplier=mult,
        vendor=vendor,
    )
    return {
        "vendor": vendor,
        "rows": rows,
        "error": "" if rows else "No prices found in workbook.",
        "row_count": len(rows),
        "detected_markup": wb.detected_markup,
        "notes": (wb.notes or "wide_import")[:500],
    }


def parse_excel(
    data: bytes,
    *,
    filename: str = "",
    vendor: str = "",
    multiplier: Optional[float] = None,
) -> dict[str, Any]:
    """
    Returns:
      vendor, rows, error, row_count, detected_markup, notes, engine
    """
    name = filename or "upload.xlsx"
    builder = _guess_builder(name, vendor)
    mult = float(multiplier if multiplier is not None else DEFAULT_MULTIPLIER)

    wide = _wide_parse(data, name, builder, mult)
    if wide.get("rows"):
        wide["engine"] = "wide"
        return wide

    simple = _simple_parse(data, name, builder, mult)
    simple["engine"] = "simple"
    if wide.get("error") and not simple.get("rows"):
        simple["error"] = wide.get("error") or simple.get("error")
        simple["notes"] = f"wide miss; {simple.get('notes')}"
    return simple
