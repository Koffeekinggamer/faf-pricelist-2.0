"""Map long/flat DataFrames into master row dicts for FAF Pricelist 2.0."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pandas as pd

from .config import DEFAULT_MULTIPLIER
from .pricing import retail_from_wholesale
from .standardize import standardize_rows

COLUMN_ALIASES = {
    "part_number": [
        "part_number", "part number", "part #", "part#", "part no", "part no.",
        "sku", "item", "item #", "item number", "item no", "item no.",
        "style", "style #", "style number", "model", "model #", "code",
        "catalog #", "catalog number", "stock #", "item name",
    ],
    "description": [
        "description", "desc", "item description", "product", "product name",
        "name", "title", "product description", "descr.",
    ],
    "species": [
        "species", "wood", "wood species", "finish wood", "material",
        "wood type", "species/finish",
    ],
    "base_price": [
        "base_price", "base price", "price", "wholesale", "wholesale price",
        "net price", "net", "dealer price", "dealer", "cost", "unit price",
        "list price", "your price", "amount", "retail", "msrp",
        "wholesale $", "price $", "net $", "whsl. price", "regular",
    ],
    "unit": ["unit", "uom", "um", "each", "units"],
    "collection": [
        "collection", "series", "line", "product line", "category",
        "group", "family", "brand", "manufacturer",
    ],
    "notes": ["notes", "note", "comments", "comment", "remarks", "options"],
    "dimensions": [
        "dimensions", "dimension", "dims", "size", "w x d x h", "overall size",
    ],
    "vendor": ["vendor", "builder", "supplier", "manufacturer name"],
    "finish_state": ["finish", "finish_state", "finish state", "finished"],
}


def norm_col(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Return canonical_field → actual column name."""
    out: dict[str, str] = {}
    lower = {c: norm_col(c) for c in df.columns}
    for canon, aliases in COLUMN_ALIASES.items():
        for c, lc in lower.items():
            if lc == canon or lc in aliases:
                out[canon] = c
                break
    return out


def to_float(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("$", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_dataframe(
    df: pd.DataFrame,
    *,
    source_file: str,
    default_collection: str = "",
    multiplier: float = DEFAULT_MULTIPLIER,
    column_map: Optional[dict[str, str]] = None,
    vendor: str = "",
) -> list[dict]:
    """Map a flat/long DataFrame into master insert dicts."""
    if df is None or df.empty:
        return []

    mapping = column_map or map_columns(df)
    for canon in (
        "part_number",
        "description",
        "base_price",
        "species",
        "collection",
        "unit",
        "notes",
        "dimensions",
        "vendor",
        "finish_state",
        "species_tier",
        "option_key",
    ):
        if canon in df.columns:
            mapping.setdefault(canon, canon)

    now = datetime.now().isoformat(timespec="seconds")
    rows: list[dict] = []

    for _, raw in df.iterrows():
        def get(field: str, default=None):
            col = mapping.get(field)
            if col and col in raw.index:
                v = raw[col]
            elif field in raw.index:
                v = raw[field]
            else:
                return default
            if pd.isna(v):
                return default
            return v

        base = to_float(get("base_price"))
        desc = get("description")
        part = get("part_number")
        if base is None and not (desc or part):
            continue

        collection = get("collection") or default_collection or None
        if collection is not None:
            collection = str(collection).strip() or None

        def _s(v):
            if v is None:
                return None
            t = str(v).strip()
            return t or None

        tier = get("species_tier")
        try:
            tier_i = int(tier) if tier is not None and str(tier).strip() != "" else None
        except (TypeError, ValueError):
            tier_i = None

        vend = _s(get("vendor")) or _s(vendor)
        adj = retail_from_wholesale(base, multiplier) if base is not None else None

        rows.append(
            {
                "vendor": vend,
                "collection": collection,
                "part_number": _s(part),
                "description": _s(desc),
                "dimensions": _s(get("dimensions")),
                "option_key": _s(get("option_key")),
                "species": _s(get("species")),
                "species_tier": tier_i,
                "finish_state": _s(get("finish_state")),
                "base_price": base,
                "multiplier": multiplier,
                "adjusted_price": adj,
                "unit": _s(get("unit")),
                "notes": _s(get("notes")),
                "source_file": source_file,
                "imported_at": now,
            }
        )

    return standardize_rows(rows, default_multiplier=multiplier)


def long_df_to_rows(
    long_df: pd.DataFrame,
    *,
    source_file: str,
    multiplier: float = DEFAULT_MULTIPLIER,
    vendor: str = "",
    default_collection: str = "",
) -> list[dict]:
    if long_df is None or long_df.empty:
        return []
    return normalize_dataframe(
        long_df,
        source_file=source_file,
        default_collection=default_collection,
        multiplier=multiplier,
        vendor=vendor,
    )
