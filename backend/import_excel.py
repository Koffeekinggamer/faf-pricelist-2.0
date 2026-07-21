"""Excel → long-form price rows.

Uses v1 wide_import engine when ~/FAF-pricebook is present; otherwise a simple
pandas fallback for flat tables.
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .config import DEFAULT_MULTIPLIER, V1_ROOT
from .pricing import retail_from_wholesale


def _guess_builder(filename: str, explicit: str = "") -> str:
    if (explicit or "").strip():
        return explicit.strip()
    stem = Path(filename or "Builder").stem
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or "Builder"


def _simple_parse(data: bytes, filename: str, vendor: str, mult: float) -> dict[str, Any]:
    """Flat table fallback: first sheet with part/desc/price-like columns."""
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
        cols = [str(c).strip() for c in df.columns]
        df.columns = cols
        lower = {c: c.lower() for c in cols}

        def find(*keys):
            for c, lc in lower.items():
                if any(k in lc for k in keys):
                    return c
            return None

        part_c = find("part", "sku", "item #", "item#", "item no")
        desc_c = find("desc", "description", "name", "item")
        price_c = find("price", "wholesale", "cost", "amount", "list")
        wood_c = find("wood", "species", "material")
        if not price_c:
            # last numeric-ish column
            for c in reversed(cols):
                sample = pd.to_numeric(df[c], errors="coerce")
                if sample.notna().sum() >= max(3, len(df) // 5):
                    price_c = c
                    break
        if not price_c:
            continue
        if not desc_c and not part_c:
            continue
        n_before = len(rows)
        for _, r in df.iterrows():
            try:
                bp = float(pd.to_numeric(r.get(price_c), errors="coerce"))
            except (TypeError, ValueError):
                continue
            if bp != bp or bp <= 0:  # NaN
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

    return {
        "vendor": vendor,
        "rows": rows,
        "error": "" if rows else "No price rows found (simple parser).",
        "row_count": len(rows),
        "detected_markup": None,
        "notes": "simple · " + ", ".join(notes) if notes else "simple",
    }


def _v1_parse(data: bytes, filename: str, vendor: str, mult: float) -> Optional[dict[str, Any]]:
    if not V1_ROOT.is_dir():
        return None
    root = str(V1_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from backend.import_service import ImportService  # type: ignore
        from backend.standardize import resolve_builder_vendor  # type: ignore
    except Exception:
        return None

    vend = resolve_builder_vendor(vendor or filename, filename=filename) or vendor
    try:
        prev = ImportService().preview_excel(
            data,
            filename=filename,
            vendor=vend,
            multiplier=mult,
            use_workbook_markup=False,
        )
    except Exception as exc:
        return {
            "vendor": vend,
            "rows": [],
            "error": f"v1 import failed: {exc}",
            "row_count": 0,
            "detected_markup": None,
            "notes": "v1",
        }

    rows = []
    for r in prev.rows or []:
        item = dict(r)
        item["vendor"] = vend
        item["multiplier"] = mult
        bp = item.get("base_price")
        item["adjusted_price"] = retail_from_wholesale(bp, mult)
        item["source_file"] = filename
        rows.append(item)

    return {
        "vendor": vend,
        "rows": rows,
        "error": "" if rows else "No prices found in workbook.",
        "row_count": len(rows),
        "detected_markup": prev.detected_markup,
        "notes": (prev.notes or "v1 wide_import")[:500],
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

    v1 = _v1_parse(data, name, builder, mult)
    if v1 and v1.get("rows"):
        v1["engine"] = "v1"
        return v1

    simple = _simple_parse(data, name, builder, mult)
    simple["engine"] = "simple"
    if v1 and v1.get("error") and not simple.get("rows"):
        simple["error"] = v1.get("error") or simple.get("error")
        simple["notes"] = f"v1 miss; {simple.get('notes')}"
    return simple
