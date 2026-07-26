"""Map builder DataFrames into master row dicts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

import pandas as pd

from backend.config import DEFAULT_MULTIPLIER, DEFAULT_PRICE_BASIS
from backend.models import COLUMN_ALIASES
from backend.standardize import standardize_rows


def norm_col(name: str) -> str:
    s = str(name).strip().lower()
    return re.sub(r"\s+", " ", s)


def map_columns(df: pd.DataFrame) -> dict[str, str]:
    """Return mapping: canonical_field -> original column name."""
    originals = {norm_col(c): c for c in df.columns}
    mapping: dict[str, str] = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in originals:
                mapping[field] = originals[alias]
                break
    return mapping


def to_float(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "-", "n/a", "na"}:
        return None
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        return float(m.group()) if m else None


def normalize_dataframe(
    df: pd.DataFrame,
    *,
    source_file: str,
    default_collection: str = "",
    multiplier: float = DEFAULT_MULTIPLIER,
    column_map: Optional[dict[str, str]] = None,
    vendor: str = "",
    price_basis: str = DEFAULT_PRICE_BASIS,
) -> list[dict]:
    """Map a flat/long DataFrame into master insert dicts."""
    if df is None or df.empty:
        return []

    mapping = column_map or map_columns(df)
    for canon in (
        "part_number", "description", "base_price", "species", "collection",
        "unit", "notes", "dimensions", "vendor", "finish_state", "species_tier",
        "option_key", "price_basis",
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
        basis = _s(get("price_basis")) or price_basis or DEFAULT_PRICE_BASIS
        from backend.pricing import retail_from_wholesale

        adj = (
            retail_from_wholesale(base, multiplier) if base is not None else None
        )

        rows.append({
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
            "price_basis": basis,
            "multiplier": multiplier,
            "adjusted_price": adj,
            "unit": _s(get("unit")),
            "notes": _s(get("notes")),
            "source_file": source_file,
            "imported_at": now,
        })

    # Canonical shape for every import path
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


def read_excel_bytes(data: bytes) -> pd.DataFrame:
    """Read first usable sheet; try header detection for messy lists."""
    import io

    bio = io.BytesIO(data)
    try:
        df = pd.read_excel(bio, engine="openpyxl")
    except Exception:
        bio.seek(0)
        df = pd.read_excel(bio)

    if len(map_columns(df)) < 2:
        for header_row in range(0, 8):
            try:
                bio.seek(0)
                trial = pd.read_excel(bio, header=header_row, engine="openpyxl")
            except Exception:
                continue
            if len(map_columns(trial)) >= 2:
                return trial.dropna(how="all")
    return df.dropna(how="all")
