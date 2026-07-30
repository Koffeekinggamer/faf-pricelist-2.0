"""
J & M Woodworking wholesale pricelist (JMW_*.xlsx).

Workbook model:
  - Collection sheets list **Brown Maple** base prices only.
  - `` Percentage`` sheet: wood → % adder over Br. Maple.
  - ``Specialty Finish Options``: flat $ addons (2-tone, Paint, …).
  - Panel variants (Fabric / Crypton / Leather) are priced SKU rows with
    those labels in the description — stored as ``option_key``.

Generic wide_species import skips Percentage and leaves only Brown Maple,
and treats Crypton banners as Collection — hence empty Option / one wood.
"""

from __future__ import annotations

import io
import re
from typing import Any, Optional

import pandas as pd

_SKIP_SHEETS = re.compile(r"(?i)^(markup|cover|percentage|custom)$")
_PCT_SHEET = re.compile(r"(?i)percentage")
_FINISH_SHEET = re.compile(r"(?i)specialty\s*finish")
_ITEM_HDR = re.compile(r"(?i)^item\s*#?$|^item$")
_BR_MAPLE = re.compile(r"(?i)^br\.?\s*maple$|^brown\s*maple$")
_WOOD_SPECIE_HDR = re.compile(r"(?i)^wood\s*specie")
_PCT_HDR = re.compile(r"(?i)^percentage")
_PANEL_OPT = re.compile(r"(?i)\b(crypton|leather|fabric)\b(?:\s*panels?)?")
_FLAT_PANEL = re.compile(r"(?i)\bflat\s*panel\b")
_SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/]{0,24}$")

_WOOD_NORM = {
    "br. maple": "Brown Maple",
    "br maple": "Brown Maple",
    "brown maple": "Brown Maple",
    "rustic br. maple": "Rustic Brown Maple",
    "rustic br maple": "Rustic Brown Maple",
    "rustic brown maple": "Rustic Brown Maple",
    "sap cherry": "Sap Cherry",
    "rustic cherry": "Rustic Cherry",
    "cherry": "Cherry",
    "wormy maple": "Wormy Maple",
    "red oak": "Red Oak",
    "hard maple": "Hard Maple",
    "hickory": "Hickory",
    "rustic hickory": "Rustic Hickory",
    "grey elm": "Grey Elm",
    "gray elm": "Grey Elm",
    "rustic qswo": "Rustic QSWO",
    "qswo": "QSWO",
    "rustic red oak": "Rustic Red Oak",
    "rustic walnut": "Rustic Walnut",
    "walnut": "Walnut",
    "rustic white oak": "Rustic White Oak",
}


def _cell(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).replace("\n", " ").strip()


def _to_price(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if pd.isna(v):
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


def _to_pct(v: Any) -> Optional[float]:
    """Workbook stores 0.06 for 6% (also accept 6 as 6%)."""
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
    if f < 0:
        return None
    # 6 means 6% if someone typed whole numbers > 1
    if f > 1.5:
        f = f / 100.0
    return f


def _norm_wood(label: str) -> Optional[str]:
    s = _cell(label)
    if not s:
        return None
    key = re.sub(r"\s+", " ", s.lower().replace(".", ". ").replace("  ", " ")).strip()
    key = key.replace(". ", ".")
    # normalize "br. maple" style
    key2 = re.sub(r"\s+", " ", s.lower())
    key2 = re.sub(r"\bbr\.?\s*maple\b", "br. maple", key2)
    return (
        _WOOD_NORM.get(key)
        or _WOOD_NORM.get(key2)
        or (s.title() if re.search(r"(?i)oak|maple|cherry|walnut|hickory|elm|qswo", s) else None)
    )


def looks_like_jmw(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    fn = (filename or "").lower()
    names = [str(n).strip() for n in (sheet_names or [])]
    has_pct = any(_PCT_SHEET.search(n) for n in names)
    has_finish = any(_FINISH_SHEET.search(n) for n in names)
    if has_pct and has_finish:
        return True
    if re.search(r"(?i)\bjmw\b|j\s*&\s*m|j\s*and\s*m", fn) and has_pct:
        return True
    return False


def parse_wood_percentages(raw: pd.DataFrame) -> dict[str, float]:
    """Wood → fraction adder over Brown Maple (0.0 = base)."""
    out: dict[str, float] = {"Brown Maple": 0.0}
    if raw is None or raw.empty:
        return out
    df = raw.dropna(how="all").reset_index(drop=True)
    for i in range(len(df)):
        row = [df.iat[i, j] if j < df.shape[1] else None for j in range(min(6, df.shape[1]))]
        wood = None
        pct = None
        for v in row:
            s = _cell(v)
            if not s:
                continue
            w = _norm_wood(s)
            if (
                w
                and wood is None
                and not _PCT_HDR.match(s)
                and not re.match(r"(?i)^wood\s*specie", s)
            ):
                wood = w
                continue
            p = _to_pct(v)
            if p is not None and wood is not None:
                pct = p
                break
        if wood is not None and pct is not None:
            out[wood] = pct
    if "Brown Maple" not in out:
        out["Brown Maple"] = 0.0
    return out


def parse_specialty_finish_addons(raw: pd.DataFrame, *, vendor: str) -> list[dict]:
    """Flat $ specialty finishes → line_kind=addon rows."""
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    if len(df) < 2:
        return []
    header = [_cell(df.iat[0, j]) if j < df.shape[1] else "" for j in range(df.shape[1])]
    # Row0 may be title; row1 headers
    hdr_i = 0
    if header and re.search(r"(?i)specialty\s*finish", header[0]) and len(df) > 1:
        hdr_i = 1
        header = [_cell(df.iat[hdr_i, j]) if j < df.shape[1] else "" for j in range(df.shape[1])]

    finish_cols: list[tuple[int, str]] = []
    seen: set[str] = set()
    for j, h in enumerate(header):
        if j == 0 or not h:
            continue
        label = re.sub(r"\s+", " ", h).strip()
        if label.lower() in seen:
            continue
        if re.search(r"(?i)2-?tone|paint|glaze|rub\s*through|stain", label):
            seen.add(label.lower())
            finish_cols.append((j, label))

    rows: list[dict] = []
    for i in range(hdr_i + 1, len(df)):
        item = _cell(df.iat[i, 0] if df.shape[1] else None)
        if not item or re.search(r"(?i)custom\s*color|all\s+(keim|ocs|premier)", item):
            continue
        for j, finish in finish_cols:
            price = _to_price(df.iat[i, j] if j < df.shape[1] else None)
            if price is None:
                continue
            rows.append(
                {
                    "vendor": vendor,
                    "collection": "Addons",
                    "part_number": f"{item} — {finish}",
                    "description": f"{finish} adder ({item})",
                    "option_key": finish,
                    "species": None,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "addon",
                    "notes": "specialty finish",
                }
            )
    return rows


def parse_custom_addons(*, vendor: str) -> list[dict]:
    """Fixed Custom-sheet adders called out in the book."""
    specs = [
        ("Undermount Drawer Slides", 20.0, "per drawer"),
        ("Extra Drawers or Doors", 50.0, None),
    ]
    out = []
    for label, price, note in specs:
        out.append(
            {
                "vendor": vendor,
                "collection": "Addons",
                "part_number": label,
                "description": label,
                "option_key": label,
                "species": None,
                "finish_state": "finished",
                "base_price": price,
                "price_basis": "wholesale",
                "line_kind": "addon",
                "notes": note,
            }
        )
    return out


def _panel_option(*texts: str) -> Optional[str]:
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    m = _PANEL_OPT.search(blob)
    if m:
        return m.group(1).title()  # Crypton / Leather / Fabric
    if _FLAT_PANEL.search(blob):
        return "Flat Panel"
    return None


def _collection_from_sheet(sheet_name: str, title: str = "") -> str:
    for cand in (title, sheet_name):
        s = _cell(cand)
        if not s:
            continue
        s = re.sub(r"(?i)\s*collection\s*$", "", s).strip()
        if s and not re.search(r"(?i)available\s+in|we\s*carry", s):
            return s[:80]
    return _cell(sheet_name) or "Casegoods"


def parse_jmw_product_sheet(
    raw: pd.DataFrame,
    *,
    sheet_name: str,
    vendor: str,
    wood_pct: dict[str, float],
) -> list[dict]:
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    title = _cell(df.iat[0, 0]) if len(df) and df.shape[1] else ""
    collection = _collection_from_sheet(sheet_name, title)

    # Find a header row with Item #
    header_i = None
    price_cols: list[int] = []
    for i in range(min(8, len(df))):
        row = [_cell(df.iat[i, j]) if j < df.shape[1] else "" for j in range(df.shape[1])]
        if not any(_ITEM_HDR.match(c) for c in row[:3]):
            continue
        header_i = i
        # price cols = Br. Maple labels before Wood Specie column
        specie_at = None
        for j, c in enumerate(row):
            if _WOOD_SPECIE_HDR.match(c) or (_PCT_HDR.match(c) and j > 4):
                specie_at = j
                break
        limit = specie_at if specie_at is not None else len(row)
        for j in range(2, limit):
            if _BR_MAPLE.match(row[j]) or (
                row[j] == "" and j > 2 and any(_BR_MAPLE.match(row[k]) for k in range(2, j))
            ):
                # include unlabeled numeric twin cols between maple headers later via scan
                pass
            if _BR_MAPLE.match(row[j]):
                price_cols.append(j)
        if not price_cols:
            # fallback: columns 2..limit-1 that look like price home
            price_cols = list(range(2, min(limit, 7)))
        break

    if header_i is None:
        # no Item # header — still try scanning
        header_i = 0
        price_cols = [2, 3, 4, 5, 6]

    out: list[dict] = []
    section = collection

    for i in range(header_i + 1, len(df)):
        row = [df.iat[i, j] if j < df.shape[1] else None for j in range(df.shape[1])]
        c0 = _cell(row[0] if row else None)
        c1 = _cell(row[1] if len(row) > 1 else None)
        c2 = _cell(row[2] if len(row) > 2 else None)

        # Section / banner lines
        if not c0 and c1 and not _to_price(row[2] if len(row) > 2 else None):
            continue
        if c0 and not _SKU_RE.match(c0) and not _to_price(row[2] if len(row) > 2 else None):
            if re.search(r"(?i)bed|collection|available|set", c0) and not _to_price(
                row[3] if len(row) > 3 else None
            ):
                if not re.search(r"(?i)available\s+in|we\s*carry", c0):
                    section = _collection_from_sheet(sheet_name, c0)
                continue
            if _ITEM_HDR.match(c0):
                continue
            continue

        if not c0 or not _SKU_RE.match(c0):
            continue
        if _ITEM_HDR.match(c0):
            continue

        # Brown Maple base price: first positive among price_cols
        base = None
        for j in price_cols:
            base = _to_price(row[j] if j < len(row) else None)
            if base is not None:
                break
        if base is None:
            # scan cols 2-6
            for j in range(2, min(7, len(row))):
                # skip if this col is in the side wood-% table (string wood name)
                if _norm_wood(_cell(row[j])):
                    continue
                base = _to_price(row[j])
                if base is not None:
                    break
        if base is None:
            continue

        desc = c1 or c0
        dims = None
        if c2 and not _to_price(row[2]) and not re.search(r"(?i)^with\s+", c2):
            if re.search(r'\d|"|′|”|in\b|w\s*x', c2, re.I):
                dims = c2
        # Panel option may live in desc or dimensions-ish col
        opt = _panel_option(desc, c2)
        # "King Fabric Bed" already covered; "With Fabric Panel" in c2 for Wyndham
        if not opt and c2:
            opt = _panel_option(c2)

        for wood, pct in wood_pct.items():
            price = round(float(base) * (1.0 + float(pct)), 2)
            out.append(
                {
                    "vendor": vendor,
                    "collection": section,
                    "part_number": c0,
                    "description": desc,
                    "dimensions": dims,
                    "option_key": opt,
                    "species": wood,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "line_kind": "item",
                    "notes": None if pct == 0 else f"+{pct:.0%} over Brown Maple",
                }
            )
    return out


def import_jmw_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
):
    from wide_import import WorkbookImportResult, list_excel_sheets

    names = list_excel_sheets(data)
    vendor_name = vendor or "J & M Woodworking"
    tried: list[dict] = []
    frames: list[pd.DataFrame] = []

    # Percentage sheet
    wood_pct = {"Brown Maple": 0.0}
    pct_name = next((n for n in names if _PCT_SHEET.search(str(n).strip())), None)
    if pct_name:
        try:
            raw = pd.read_excel(
                io.BytesIO(data), sheet_name=pct_name, header=None, engine="openpyxl"
            )
            wood_pct = parse_wood_percentages(raw)
            tried.append(
                {
                    "sheet": pct_name,
                    "layout": "jmw_wood_percentages",
                    "rows": len(wood_pct),
                    "note": f"{len(wood_pct)} woods over Br. Maple",
                }
            )
        except Exception as e:
            tried.append({"sheet": pct_name, "layout": "error", "rows": 0, "note": str(e)[:200]})

    targets = list(names)
    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]

    for name in names:
        if name not in targets:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "filtered out"})
            continue
        key = str(name).strip()
        if _SKIP_SHEETS.match(key) or _PCT_SHEET.search(key):
            if not any(t.get("sheet") == name for t in tried):
                tried.append(
                    {"sheet": name, "layout": "skip", "rows": 0, "note": "jmw non-product"}
                )
            continue

        try:
            raw = pd.read_excel(io.BytesIO(data), sheet_name=name, header=None, engine="openpyxl")
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)[:200]})
            continue

        if _FINISH_SHEET.search(key):
            rows = parse_specialty_finish_addons(raw, vendor=vendor_name)
            layout = "jmw_specialty_finish_addons"
        else:
            rows = parse_jmw_product_sheet(
                raw, sheet_name=key, vendor=vendor_name, wood_pct=wood_pct
            )
            layout = "jmw_br_maple_expand"

        if default_collection:
            for r in rows:
                if not r.get("collection"):
                    r["collection"] = default_collection

        long = pd.DataFrame(rows)
        tried.append(
            {
                "sheet": name,
                "layout": layout,
                "rows": 0 if long.empty else len(long),
                "note": f"{len(wood_pct)} woods" if layout.startswith("jmw_br") else "addons",
            }
        )
        if not long.empty:
            frames.append(long)

    # Custom-sheet flat adders
    custom_rows = parse_custom_addons(vendor=vendor_name)
    if custom_rows:
        frames.append(pd.DataFrame(custom_rows))
        tried.append(
            {
                "sheet": "Custom",
                "layout": "jmw_custom_addons",
                "rows": len(custom_rows),
                "note": "fixed adders",
            }
        )

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    n_woods = len(wood_pct)
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,
        sheet_names=names,
        notes=(
            f"{filename + ': ' if filename else ''}"
            f"J & M Woodworking · {0 if out.empty else len(out)} rows · "
            f"{n_woods} woods from Percentage · specialty finishes as addons"
        ),
    )
