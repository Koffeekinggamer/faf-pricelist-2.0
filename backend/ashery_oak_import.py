"""
Ashery Oak wholesale pricelist (AO_Pricelist_*.xlsx).

Workbook model:
  - ``Master`` Regular column is Oak / Rustic Cherry / Sap Cherry / Brown Maple.
  - ``Options&Portal`` wood table is the adder source (Hickory +10%, QSWO +30%, …).
    Master ``10% More`` / ``35% More`` columns are stale hardcoded figures — not
    used for pricing.
  - Every tab is opened (Cover, Markup, Options, backup Options, Master,
    Products). Products only adds SKUs Master does not have.

Generic long_flat import keeps Regular only and leaves ``species`` empty, so
Search Wood / Option never attach to items.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

import pandas as pd

_SKU_RE = re.compile(r"^[A-Za-z]{1,8}-[A-Za-z0-9][A-Za-z0-9\-]{0,24}$")
_MASTER = re.compile(r"(?i)^master$")
_OPTIONS = re.compile(r"(?i)options\s*&\s*portal")
_BANNER_SKIP = re.compile(
    r"(?i)available\s+with\s+doors|see\s+options|take\s+advantage|"
    r"3\s*piece|in-stock|continued|model\s*#"
)

# Regular prices are Oak / Rustic Cherry / Sap Cherry / Brown Maple.
REGULAR_WOODS = ("Oak", "Rustic Cherry", "Sap Cherry", "Brown Maple")

# Options&Portal wood adders over Regular (0.10 = +10%).
_WOOD_PCT_DEFAULTS: dict[str, float] = {
    "Rustic QSWO": 0.10,
    "Hickory": 0.10,
    "Rustic Hickory": 0.10,
    "Rustic Walnut": 0.10,
    "Wormy Maple": 0.10,
    "Hard Maple": 0.20,
    "Cherry": 0.20,
    "QSWO": 0.30,
    "Elm": 0.30,
    "Tiger Maple": 0.30,
    "Plain Sawn White Oak": 0.30,
    "Prime Walnut": 0.55,
}

_WOOD_NORM = {
    "oak": "Oak",
    "rustic cherry": "Rustic Cherry",
    "sap cherry": "Sap Cherry",
    "brown maple": "Brown Maple",
    "rustic qswo": "Rustic QSWO",
    "hickory": "Hickory",
    "rustic hickory": "Rustic Hickory",
    "elm": "Elm",
    "hard maple": "Hard Maple",
    "qswo": "QSWO",
    "cherry": "Cherry",
    "rustic walnut": "Rustic Walnut",
    "wormy maple": "Wormy Maple",
    "prime walnut": "Prime Walnut",
    "tiger maple": "Tiger Maple",
    "plain sawn white oak": "Plain Sawn White Oak",
    "walnut": "Walnut",
}

_OPTION_LIKE_WOOD = re.compile(
    r"(?i)reclaimed\s+oak|ruff\s*sawn|rough\s*sawn|case\s+with|top\s+only|"
    r"whole\s+piece|doors?\s+and\s+drawers"
)


def _cell(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).replace("\n", " ").strip()


def _to_price(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if pd.isna(v) or (isinstance(v, float) and math.isnan(v)):
            return None
        f = float(v)
        return f if f > 0 else None
    s = str(v).strip().replace("$", "").replace(",", "")
    if not s or s in {"-", "—"}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return f if f > 0 else None


def _to_pct_fraction(v: Any) -> Optional[float]:
    """0.10 or 10 → 0.10. Ignore dollar-like values (>= 1.5 after /100 check)."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        s = str(v).strip().replace("%", "")
        try:
            f = float(s)
        except ValueError:
            return None
    if isinstance(f, float) and (math.isnan(f) or math.isinf(f)):
        return None
    if f < 0:
        return None
    if f > 1.5:
        f = f / 100.0
    if f <= 0 or f > 1.2:
        return None
    return f


def _norm_wood(label: str) -> Optional[str]:
    s = re.sub(r"[.…]+$", "", _cell(label))
    s = re.sub(r"\s+", " ", s).strip()
    if not s or _OPTION_LIKE_WOOD.search(s):
        return None
    key = s.lower()
    if key in _WOOD_NORM:
        return _WOOD_NORM[key]
    if re.search(r"(?i)oak|maple|cherry|walnut|hickory|elm|qswo", s):
        return s.title()
    return None


def looks_like_ashery_oak(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    fn = (filename or "").lower()
    names = [str(n).strip() for n in (sheet_names or [])]
    has_master = any(_MASTER.match(n) for n in names)
    has_opt = any(_OPTIONS.search(n) for n in names)
    if has_master and has_opt:
        return True
    if re.search(r"(?i)ashery\s*oak|asheryoak|ao_pricelist", fn):
        return True
    return False


def parse_extra_wood_percentages(raw: pd.DataFrame) -> dict[str, float]:
    """Options&Portal wood table → fraction adder over Regular for each species."""
    out = dict(_WOOD_PCT_DEFAULTS)
    if raw is None or raw.empty:
        return out
    df = raw.dropna(how="all").reset_index(drop=True)
    in_wood = False
    for i in range(len(df)):
        row = [df.iat[i, j] if j < df.shape[1] else None for j in range(min(6, df.shape[1]))]
        c0 = _cell(row[0] if row else None)
        if re.search(r"(?i)wood\s*species\s*pricing", c0):
            in_wood = True
            continue
        if re.search(r"(?i)^options\b", c0) and in_wood:
            break
        if not in_wood or not c0:
            continue
        if re.search(r"(?i)regular\s+prices\s+listed", c0):
            continue
        wood = _norm_wood(c0)
        if wood is None or wood in REGULAR_WOODS:
            continue
        pct = None
        for v in row[1:]:
            pct = _to_pct_fraction(v)
            if pct is not None:
                break
        if pct is not None:
            out[wood] = pct
    return out


def parse_option_addons(raw: pd.DataFrame, *, vendor: str) -> list[dict]:
    """Finish % and flat $ adders from Options&Portal → line_kind=addon."""
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    rows: list[dict] = []
    in_options = False
    for i in range(len(df)):
        c0 = _cell(df.iat[i, 0] if df.shape[1] else None)
        if re.search(r"(?i)^options\b", c0) and not re.search(r"(?i)portal|bookcase", c0):
            in_options = True
            continue
        if not in_options or not c0:
            continue
        if re.search(r"(?i)fax\s+quote|call\s+for\s+quote|customize\s+bookcases", c0):
            continue
        label, kind, amount = _classify_option_line(c0, df, i)
        if not label or amount is None:
            continue
        rec: dict[str, Any] = {
            "vendor": vendor,
            "collection": "Addons",
            "part_number": label,
            "description": label,
            "option_key": label,
            "species": None,
            "finish_state": "finished",
            "price_basis": "wholesale",
            "line_kind": "addon",
            "notes": "Options&Portal",
        }
        if kind == "pct":
            rec["base_price"] = None
            rec["addon_pct"] = round(amount * 100.0, 4)
        else:
            rec["base_price"] = amount
            rec["addon_pct"] = None
        rows.append(rec)
    return rows


def _classify_option_line(
    text: str, df: pd.DataFrame, i: int
) -> tuple[Optional[str], Optional[str], Optional[float]]:
    blob = re.sub(r"[.…]+", " ", text)
    blob = re.sub(r"\s+", " ", blob).strip(" -:")
    if re.search(r"(?i)no\s+charge|glass\s+to\s+wood", blob):
        return None, None, None

    vals = [df.iat[i, j] if j < df.shape[1] else None for j in range(1, min(6, df.shape[1]))]
    pct = None
    dollars = None
    for v in vals:
        p = _to_pct_fraction(v)
        d = _to_price(v)
        if p is not None and pct is None:
            pct = p
        if d is not None and d >= 2 and dollars is None:
            dollars = d

    if re.search(r"(?i)for\s+painting", blob):
        return "Paint", "pct", pct or 0.35
    if re.search(r"(?i)2\s*tone\s+paint", blob):
        return "2-tone paint and stain", "pct", pct or 0.45
    if re.search(r"(?i)2\s*tone\s+stain", blob):
        return "2-tone stain", "pct", pct or 0.10
    if re.search(r"(?i)locks?\s+on\s+drawers|per\s+lock", blob):
        return "Drawer lock", "flat", dollars or 13.0
    if re.search(r"(?i)classic\s+flame|fireplace", blob):
        return "Classic Flame Fireplace", "flat", dollars or 350.0
    if re.search(r"(?i)keyboard\s+drawer", blob):
        return "Keyboard drawer", "flat", dollars or 40.0
    if re.search(r"(?i)castors?|casters?", blob):
        return "Casters", "flat", dollars or 15.0
    if re.search(r"(?i)grommet", blob):
        return "Grommet", "flat", dollars or 15.0
    return None, None, None


def parse_bookcase_door_addons(raw: pd.DataFrame, *, vendor: str) -> list[dict]:
    """Visible Options tab bookcase door matrix → flat addons on Bookcase items."""
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    rows: list[dict] = []
    in_doors = False
    for i in range(len(df)):
        c0 = _cell(df.iat[i, 0] if df.shape[1] else None)
        if re.search(r"(?i)bookcase\s+options", c0):
            in_doors = True
            continue
        if re.search(r"(?i)^options\b", c0) and in_doors:
            break
        if not in_doors or not c0:
            continue
        if re.search(r"(?i)sq\.?\s*ft|square\s*ft|top\s+part", c0):
            continue
        m = re.search(
            r"(?i)(\d+)\s*[-–]\s*(\d+)\"\s*high\s+doors?\s+on\s+(\d+)\"\s*wide",
            c0,
        )
        if not m:
            continue
        qty, height, width = m.group(1), m.group(2), m.group(3)
        price = None
        for j in range(1, min(7, df.shape[1])):
            price = _to_price(df.iat[i, j])
            if price is not None:
                break
        if price is None:
            continue
        label = f'{height}" bookcase door ({qty}) on {width}"'
        rows.append(
            {
                "vendor": vendor,
                "collection": "Addons",
                "part_number": f"Bookcase — {label}",
                "description": label,
                "option_key": label,
                "species": None,
                "finish_state": "finished",
                "base_price": price,
                "addon_pct": None,
                "price_basis": "wholesale",
                "line_kind": "addon",
                "notes": "Options&Portal bk · Regular-wood door adder",
            }
        )
    return rows


def _clean_collection(text: str) -> Optional[str]:
    s = re.sub(r"\s+", " ", _cell(text)).strip(" *")
    if not s or _BANNER_SKIP.search(s):
        return None
    if re.search(r"(?i)collection|tables|stands|bookcases|office|desks|cabinets", s):
        s = re.sub(r"(?i)\s*collection\s*$", "", s).strip()
        return s[:80] if s else None
    return None


def parse_master_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str,
    extra_woods: Optional[dict[str, float]] = None,
) -> list[dict]:
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    header_i = None
    for i in range(min(6, len(df))):
        row = [_cell(df.iat[i, j]) if j < df.shape[1] else "" for j in range(df.shape[1])]
        joined = " ".join(row).lower()
        if "model" in joined and "regular" in joined:
            header_i = i
            break
    if header_i is None:
        header_i = 1

    wood_pct = extra_woods if extra_woods is not None else dict(_WOOD_PCT_DEFAULTS)
    out: list[dict] = []
    collection = "Ashery Oak"
    section = collection

    for i in range(header_i + 1, len(df)):
        row = [df.iat[i, j] if j < df.shape[1] else None for j in range(df.shape[1])]
        sku = _cell(row[0] if row else None)
        desc = _cell(row[1] if len(row) > 1 else None)
        dims = _cell(row[2] if len(row) > 2 else None)
        regular = _to_price(row[3] if len(row) > 3 else None)

        if not sku:
            continue
        if not _SKU_RE.match(sku):
            banner = _clean_collection(sku)
            if banner:
                if re.search(r"(?i)collection$", sku.strip(" *")):
                    collection = banner
                section = banner
            continue

        if regular is None:
            continue

        if dims and not re.search(r'\d|"|′|”|in\b|w\s*x', dims, re.I):
            dims = None

        coll = section or collection
        for wood in REGULAR_WOODS:
            out.append(
                _item_row(
                    vendor=vendor,
                    collection=coll,
                    sku=sku,
                    desc=desc or sku,
                    dims=dims,
                    wood=wood,
                    price=regular,
                    notes=None,
                )
            )
        for wood, frac in wood_pct.items():
            if wood in REGULAR_WOODS:
                continue
            price = round(float(regular) * (1.0 + float(frac)), 2)
            out.append(
                _item_row(
                    vendor=vendor,
                    collection=coll,
                    sku=sku,
                    desc=desc or sku,
                    dims=dims,
                    wood=wood,
                    price=price,
                    notes=f"+{frac:.0%} over Regular",
                )
            )
    return out


def _item_row(
    *,
    vendor: str,
    collection: str,
    sku: str,
    desc: str,
    dims: Optional[str],
    wood: str,
    price: float,
    notes: Optional[str],
) -> dict:
    return {
        "vendor": vendor,
        "collection": collection,
        "part_number": sku,
        "description": desc,
        "dimensions": dims,
        "option_key": None,
        "species": wood,
        "finish_state": "finished",
        "base_price": price,
        "price_basis": "wholesale",
        "line_kind": "item",
        "notes": notes,
    }


def import_ashery_oak_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
):
    from backend.workbook_sheets import read_all_sheets, sheets_tried_from_views
    from wide_import import WorkbookImportResult

    views = read_all_sheets(data)
    if sheet_filter is not None:
        allow = set(sheet_filter)
        views = [v for v in views if v.name in allow]
    vendor_name = vendor or "Ashery Oak"
    extra: dict[str, dict] = {}
    frames: list[pd.DataFrame] = []

    wood_pct = dict(_WOOD_PCT_DEFAULTS)
    addons: list[dict] = []
    seen_opt: set[str] = set()

    def _add_addons(rows: list[dict]) -> int:
        n = 0
        for r in rows:
            key = str(r.get("option_key") or "")
            if not key or key in seen_opt:
                continue
            seen_opt.add(key)
            addons.append(r)
            n += 1
        return n

    for view in views:
        if view.role != "options" or view.raw is None:
            continue
        wood_pct = parse_extra_wood_percentages(view.raw)
        n_opt = _add_addons(parse_option_addons(view.raw, vendor=vendor_name))
        n_doors = _add_addons(parse_bookcase_door_addons(view.raw, vendor=vendor_name))
        extra[view.name] = {
            "layout": "ashery_oak_options",
            "rows": n_opt + n_doors,
            "note": (
                f"viewed · {len(wood_pct)} wood adders · {n_opt} addons"
                + (f" · {n_doors} bookcase doors" if n_doors else "")
            ),
        }

    seen_skus: set[str] = set()
    for view in views:
        if view.raw is None:
            continue
        key = view.name.strip()
        is_master = bool(_MASTER.match(key))
        is_products = bool(re.match(r"(?i)^products$", key))
        if not is_master and not is_products:
            continue
        rows = parse_master_sheet(view.raw, vendor=vendor_name, extra_woods=wood_pct)
        if is_products:
            rows = [r for r in rows if r.get("part_number") not in seen_skus]
        else:
            seen_skus.update(str(r.get("part_number") or "") for r in rows)
        if default_collection:
            for r in rows:
                if not r.get("collection"):
                    r["collection"] = default_collection
        extra[view.name] = {
            "layout": "ashery_oak_master_wood_expand"
            if is_master
            else "ashery_oak_products_fill",
            "rows": len(rows),
            "note": (
                f"viewed · {len(rows)} rows · {len(REGULAR_WOODS) + len(wood_pct)} woods"
                if is_master
                else f"viewed · {len(rows)} SKUs not already on Master"
            ),
        }
        if rows:
            frames.append(pd.DataFrame(rows))

    if addons:
        frames.append(pd.DataFrame(addons))

    for view in views:
        if view.name in extra:
            continue
        extra[view.name] = {
            "layout": f"viewed_{view.role}",
            "rows": 0,
            "note": f"viewed · {view.role} · {view.n_rows}×{view.n_cols}",
        }

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    n_woods = len(REGULAR_WOODS) + len(wood_pct)
    names = [v.name for v in views]
    return WorkbookImportResult(
        sheets_tried=sheets_tried_from_views(views, extra=extra),
        long_df=out,
        detected_markup=None,
        sheet_names=names,
        notes=(
            f"{filename + ': ' if filename else ''}"
            f"Ashery Oak · {0 if out.empty else len(out)} rows · "
            f"{n_woods} woods · viewed {len(views)} tabs: {', '.join(names)}"
        ),
    )
