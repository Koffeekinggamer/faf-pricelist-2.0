"""Patio Kraft — outdoor poly color-tier sections (not wood species).

Builders ship:
  [Collection title]
  [Standard Colors | Bright Colors | Woodgrain Colors]   ← row above header
  Item # | Description | … | $ | $ | $
  VECG   | Chair Glider | … | …

Sections repeat down the sheet (Vienna, London, Accessories, …).
We store long-form: one row per (SKU × color tier). Prefer Wholesale sheet.
"""

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
)

PK_SKU_RE = re.compile(r"^[A-Za-z][A-Za-z0-9\-_/.]{1,14}$")
PK_ITEM_HEADER_RE = re.compile(r"(?i)^item\s*#?$|^item\s*(no\.?|number)$")
PK_COLLECTION_RE = re.compile(
    r"(?i)\bcollection\b|accessories|frame\s*systems|furniture\s*covers|"
    r"planters|benches|carts|add[\s\-]?ons?"
)
PK_TIER_LABEL_RE = re.compile(
    r"(?i)standard\s*(poly\s*)?colors?|bright\s*colors?|woodgrain|poly\s*colors?|"
    r"^black$|^price$"
)
PK_POLICY_RE = re.compile(
    r"(?i)cleaning|warranty|internet\s*dealer|shipping|cancellation|subject to|"
    r"please note|poly color list|prices effective|enter additional markup"
)


def looks_like_patio_kraft(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
    data: Optional[bytes] = None,
) -> bool:
    """Detect Patio Kraft outdoor price books by name or sheet signatures."""
    fn = (filename or "").lower().replace("_", " ").replace("-", " ")
    if "patio" in fn and "kraft" in fn:
        return True
    names = sheet_names or []
    lower = {str(s).strip().lower() for s in names}
    if not ({"retail", "wholesale"} <= lower):
        return False
    if data is None:
        return False
    # Confirm: deep Item # + color-tier headers (not a generic Retail/Wholesale book)
    try:
        from backend.workbook_sheets import read_sheet

        wh = next(s for s in names if str(s).strip().lower() == "wholesale")
        raw = read_sheet(data, wh, header=None)
    except Exception:
        return False
    item_hits = 0
    tier_hits = 0
    for i in range(min(len(raw), 400)):
        c0 = raw.iat[i, 0] if raw.shape[1] else None
        if pd.notna(c0) and PK_ITEM_HEADER_RE.match(_norm(c0)):
            item_hits += 1
        for j in range(min(raw.shape[1], 12)):
            v = raw.iat[i, j]
            if pd.notna(v) and PK_TIER_LABEL_RE.search(_norm(v)):
                tier_hits += 1
                break
    return item_hits >= 3 and tier_hits >= 3


def _pk_norm_tier(label: str) -> str:
    """Canonical color-tier names for search/quotes."""
    k = re.sub(r"\s+", " ", _norm(label).replace("\n", " ")).strip()
    low = k.lower()
    if "woodgrain" in low:
        return "Woodgrain Colors"
    if "bright" in low:
        return "Bright Colors"
    if "standard poly" in low or ("poly" in low and "standard" in low):
        return "Standard Poly Colors"
    if "standard" in low and "color" in low:
        return "Standard Colors"
    if low == "black":
        return "Black"
    if low == "price":
        return "Price"
    return k


def _pk_tier_map(raw: pd.DataFrame, header_i: int) -> dict[int, str]:
    """
    Map column index → color-tier label for a section headed by Item # at header_i.
    Labels usually sit on the row above Item # (cols 7–9); sometimes Price is on the header row.
    """
    labels: dict[int, str] = {}
    # Prefer the row *above* Item # (real color tiers). Only use header-row
    # labels for columns still empty — never let bare "Price" overwrite a tier.
    for src_i in (header_i - 1, header_i):
        if src_i < 0 or src_i >= len(raw):
            continue
        for j in range(2, raw.shape[1]):
            v = raw.iat[src_i, j]
            if pd.isna(v):
                continue
            t = _norm(v)
            if not t or t.startswith("•") or re.match(r"(?i)^catalog\b", t):
                continue
            if not PK_TIER_LABEL_RE.search(t):
                continue
            canon = _pk_norm_tier(t)
            if j in labels:
                # Keep existing color tier; ignore later "Price" overwrite
                if labels[j].lower() != "price":
                    continue
                if canon.lower() == "price":
                    continue
            labels[j] = canon
    # Prefer real color tiers over bare "Price" when both exist on the map
    if any(v.lower() != "price" for v in labels.values()):
        labels = {j: v for j, v in labels.items() if v.lower() != "price"}
    return labels


def parse_patio_kraft_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = "",
    default_collection: str = "",
    price_basis: str = "wholesale",
) -> pd.DataFrame:
    """
    Walk a Patio Kraft Retail/Wholesale sheet: multi-section Item # tables with
    Standard / Bright / Woodgrain (or Black / Poly) price columns → long rows.
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    current_collection: Optional[str] = default_collection or None
    tier_map: dict[int, str] = {}

    for i in range(len(raw)):
        c0 = raw.iat[i, 0] if raw.shape[1] else None
        s0 = _norm(c0) if pd.notna(c0) else ""

        # Section / collection title (short single-cell headers)
        if s0 and PK_COLLECTION_RE.search(s0) and not PK_POLICY_RE.search(s0):
            # Reject multi-line policy blobs that mention "collection"
            raw0 = str(c0) if pd.notna(c0) else ""
            if "\n" not in raw0 and len(s0) <= 70:
                # "Furniture Covers, continued" → "Furniture Covers"
                current_collection = re.sub(r",?\s*continued\s*$", "", s0, flags=re.I).strip() or s0
                continue

        # Repeated Item # header starts a new price-column mapping
        if s0 and PK_ITEM_HEADER_RE.match(s0):
            tier_map = _pk_tier_map(raw, i)
            continue

        # SKU data row
        if not s0 or not PK_SKU_RE.match(s0):
            continue
        if PK_ITEM_HEADER_RE.match(s0) or s0.lower() in {"price", "description"}:
            continue

        desc = ""
        if raw.shape[1] > 1 and pd.notna(raw.iat[i, 1]):
            desc = _norm(raw.iat[i, 1])
        if not desc or desc.lower() in {"description", "item #", "item"}:
            continue
        if PK_POLICY_RE.search(desc):
            continue

        # Resolve price columns for this row
        col_labels: list[tuple[int, str]] = []
        if tier_map:
            col_labels = sorted(tier_map.items())
        else:
            for j in range(2, raw.shape[1]):
                if _to_float(raw.iat[i, j]) is not None:
                    col_labels.append((j, "Price"))

        if not col_labels:
            continue

        # Collect filled price cells for this SKU
        filled: list[tuple[int, str, float]] = []
        for j, label in col_labels:
            if j >= raw.shape[1]:
                continue
            price = _to_float(raw.iat[i, j])
            if price is None:
                continue
            filled.append((j, label, price))

        # Fallback: scan any numeric cols if mapped cols empty
        if not filled:
            for j in range(2, raw.shape[1]):
                price = _to_float(raw.iat[i, j])
                if price is None:
                    continue
                label = tier_map.get(j, "Price") if tier_map else "Price"
                filled.append((j, label, price))

        if not filled:
            continue

        # One filled price → single list price (frames, covers, pillows).
        # Color headers on the sheet often linger above single-price sections;
        # do not invent a woodgrain/black tier for those SKUs.
        # Two+ filled prices → real color-tier matrix.
        single_price = len(filled) == 1
        from backend.standardize import base_material_label

        for tier_i, (j, label, price) in enumerate(filled, start=1):
            if single_price or label.lower() == "price":
                species = base_material_label(desc) or base_material_label(current_collection or "")
                stier = None
            else:
                species = label
                stier = tier_i
            rows.append(
                {
                    "vendor": vendor or None,
                    "collection": current_collection,
                    "part_number": s0,
                    "description": desc,
                    "dimensions": None,
                    "option_key": None,
                    "species": species,
                    "species_tier": stier,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": price_basis,
                    "unit": None,
                    "notes": None,
                }
            )

    return _clean_long_rows(pd.DataFrame(rows))


def import_patio_kraft_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """
    Patio Kraft specialized import.

    Standard FAF rule: store **Wholesale** as base_price (price_basis=wholesale),
    then apply the store multiplier (default 2.7). Retail sheet is skipped unless
    explicitly requested via sheet_filter — list retail is ~2.2× wholesale.
    """
    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or "Patio Kraft"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    wholesale = next((n for n in names if str(n).strip().lower() == "wholesale"), None)
    retail = next((n for n in names if str(n).strip().lower() == "retail"), None)

    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]
    elif wholesale:
        targets = [wholesale]
    elif retail:
        targets = [retail]
    else:
        targets = list(names)

    for name in names:
        if name not in targets:
            tried.append(
                {
                    "sheet": name,
                    "layout": "skip",
                    "rows": 0,
                    "note": "Patio Kraft: prefer Wholesale; skipped",
                }
            )
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue

        basis = (
            "wholesale"
            if str(name).strip().lower() == "wholesale"
            else ("retail" if str(name).strip().lower() == "retail" else "wholesale")
        )
        long = parse_patio_kraft_sheet(
            raw,
            vendor=vendor_name,
            default_collection=default_collection,
            price_basis=basis,
        )
        n = len(long) if long is not None and not long.empty else 0
        tried.append(
            {
                "sheet": name,
                "layout": "patio_kraft_color_tiers",
                "rows": n,
                "note": f"price_basis={basis}; multi-section Item# + color tiers",
                "species_cols": sorted(
                    {str(s) for s in (long["species"].dropna().unique().tolist() if n else [])}
                )[:8],
                "id_col": "Item #",
                "desc_col": "Description",
            }
        )
        if n > 0:
            if "collection" in long.columns:
                long["collection"] = long["collection"].fillna(default_collection or name)
            frames.append(long)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(
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
        )

    if vendor_name and not out.empty:
        out["vendor"] = vendor_name

    note = (
        f"{filename + ': ' if filename else ''}"
        f"Patio Kraft color-tier import · {len(out)} long rows · "
        f"sheets={[t['sheet'] for t in tried if t.get('rows')]}"
    )
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,  # Retail "1.2" cell is not FAF mult; wholesale bases only
        sheet_names=names,
        notes=note,
    )
