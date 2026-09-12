"""LAMB Woodworking — Wholesale matrix (prefer Wholesale over Retail sheets).

Layout: Item No. | Size | Description | Unfinished×4 wood groups |
        Finishing cost | Finished×4 wood groups
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd

from wide_import import (
    WOOD_TOKENS,
    WorkbookImportResult,
    _clean_long_rows,
    _norm,
    list_excel_sheets,
)

LAMB_SKU_RE = re.compile(r"(?i)^LA-[A-Z0-9][A-Z0-9\-_/.]*$")
LAMB_SKIP_SECTIONS = re.compile(
    r"(?i)^(furniture\s*options|power\s*outlets|hardware|lighting|materials|"
    r"lift\s*tops|glass\s*options|quick\s*ship\s*items|notes?|options)$"
)
_LAMB_OPT_HDR = re.compile(r"(?i)^furniture\s*options$")
_LAMB_OPT_STOP = re.compile(r"(?i)^(quick\s*ship|item\s*no\.?$|seating$)")
_LAMB_OPT_SKIP = re.compile(
    r"(?i)^(price|item\s*no\.?|size|description|notes?|most hardware|"
    r"lamb customization|note:|start with base|^[0-9]+$)$"
)
_LAMB_WALNUT_ADD = re.compile(r"(?i)for\s+walnut.*add\s+(\d+(?:\.\d+)?)\s*%")


def looks_like_lamb(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    fn = (filename or "").lower().replace("_", " ").replace("-", " ").replace("/", " ")
    if re.search(r"\blamb\b", fn):
        return True
    names = " ".join(str(s).lower() for s in (sheet_names or []))
    return "lamb" in names and "wholesale" in names


def _lamb_clean_wood_label(val) -> str:
    """Normalize wood-group header; keep multi-wood groups joined by ' / '."""
    s = _norm(val)
    # commas between woods → slash separator (do not split words)
    s = re.sub(r"\s*,\s*", " / ", s)
    s = re.sub(r"\s+", " ", s).strip(" /")
    return s


def _lamb_wood_header_from_row(vals: list) -> Optional[dict]:
    """
    Detect a true product wood-group header (unfinished groups | finishing cost | finished groups).
    Ignores OPTIONS-only side panels that lack a finishing-cost column.
    """
    finish_cost_col = None
    for j, v in enumerate(vals):
        t = _norm(v).lower()
        if "finish" in t and "cost" in t:
            finish_cost_col = j
            break
    if finish_cost_col is None:
        return None

    wood_cells: list[tuple[int, str]] = []
    for j, v in enumerate(vals):
        t = _norm(v)
        if not t or j == finish_cost_col:
            continue
        low = t.lower()
        if low in {"unfinished", "finished"} or ("finish" in low and "cost" in low):
            continue
        if any(w in low for w in WOOD_TOKENS) or "," in t or "/" in t:
            wood_cells.append((j, _lamb_clean_wood_label(t)))

    unf = [(j, lab) for j, lab in wood_cells if j < finish_cost_col]
    fin = [(j, lab) for j, lab in wood_cells if j > finish_cost_col]
    # Expect at least 2 wood groups unfinished and matching finished side
    if len(unf) < 2 or len(fin) < 2:
        return None
    return {"unf": unf, "fin": fin, "finish_cost_col": finish_cost_col}


def parse_lamb_wholesale_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = "LAMB",
    default_collection: str = "",
    price_basis: str = "wholesale",
) -> pd.DataFrame:
    """
    Parse LAMB Wholesale sheet into long-form rows.

    Emits unfinished + finished sellable prices per wood-group column when present.
    Oak-only / quick-ship lines (unfinished + finishing cost + finished) also work.
    Finishing-cost columns are never stored as product prices.
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    work = raw.copy().reset_index(drop=True)
    n_cols = work.shape[1]
    rows_out: list[dict] = []

    unf_cols: list[tuple[int, str]] = []
    fin_cols: list[tuple[int, str]] = []
    finish_cost_col: Optional[int] = None
    collection = (default_collection or "").strip() or None
    option_rows: list[dict] = []
    in_options = False

    def _to_price(v) -> Optional[float]:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            f = float(v)
            return f if f > 0 else None
        s = str(v).strip().replace("$", "").replace(",", "")
        if not s or s.lower() in {"nan", "none", "discontinued", "n/a", "-"}:
            return None
        try:
            f = float(s)
            return f if f > 0 else None
        except ValueError:
            return None

    def _emit(part, desc, dims, finish_state, price, species=None, tier=None):
        rows_out.append(
            {
                "vendor": vendor or "LAMB",
                "collection": collection,
                "part_number": part,
                "description": desc,
                "dimensions": dims or None,
                "option_key": None,
                "species": species,
                "species_tier": tier,
                "finish_state": finish_state,
                "base_price": float(price),
                "price_basis": price_basis,
                "unit": None,
                "notes": None,
            }
        )

    def _option_price(vals) -> Optional[float]:
        """Price column sits under the Options 'Price' header (usually col 6)."""
        for j in (6, 5, 7):
            if j < n_cols:
                p = _to_price(vals[j])
                if p is not None and 1 < p < 2000:
                    return p
        return None

    def _emit_option(label: str, price: Optional[float] = None, pct: Optional[float] = None):
        name = re.sub(r"\s+", " ", label).strip(" -:")
        if not name or _LAMB_OPT_SKIP.match(name) or LAMB_SKIP_SECTIONS.match(name):
            return
        if re.match(r"(?i)^most hardware", name):
            return
        option_rows.append(
            {
                "vendor": vendor or "LAMB",
                "collection": "Furniture Options",
                "part_number": name,
                "description": name,
                "dimensions": None,
                "option_key": name,
                "species": None,
                "species_tier": None,
                "finish_state": None,
                "base_price": float(price) if price else 0.0,
                "price_basis": price_basis,
                "unit": None,
                "notes": None,
                "line_kind": "addon",
                "addon_pct": pct,
            }
        )

    for i in range(len(work)):
        vals = [work.iat[i, j] if j < n_cols else None for j in range(n_cols)]
        v0 = _norm(vals[0]) if vals else ""

        hdr = _lamb_wood_header_from_row(vals)
        if hdr:
            unf_cols = hdr["unf"]
            fin_cols = hdr["fin"]
            finish_cost_col = hdr["finish_cost_col"]
            continue

        joined = " ".join(_norm(v) for v in vals if _norm(v))
        walnut = _LAMB_WALNUT_ADD.search(joined)
        if walnut:
            _emit_option("Walnut", pct=float(walnut.group(1)))
        if _LAMB_OPT_HDR.match(v0):
            in_options = True
            continue
        if in_options and (_LAMB_OPT_STOP.match(v0) or LAMB_SKU_RE.match(v0)):
            in_options = False
        if in_options and v0 and not LAMB_SKU_RE.match(v0) and not _LAMB_OPT_SKIP.match(v0):
            price = _option_price(vals)
            if price is not None:
                _emit_option(v0, price=price)
            continue

        # Section / collection header: ALEXIS, ARTS & CRAFTS, ASHTON, …
        if (
            v0
            and not LAMB_SKU_RE.match(v0)
            and not re.match(r"(?i)^item\s*no", v0)
            and len(v0) < 48
            and not _to_price(vals[0])
        ):
            prices_here = sum(
                1 for j in range(min(8, n_cols), n_cols) if _to_price(vals[j]) is not None
            )
            if prices_here == 0 and (v0.isupper() or re.match(r"^[A-Z][A-Za-z0-9 &/\-]+$", v0)):
                if not LAMB_SKIP_SECTIONS.match(v0):
                    collection = v0.title() if v0.isupper() else v0
                continue

        if not v0 or not LAMB_SKU_RE.match(v0):
            continue

        part = v0.upper() if v0.upper().startswith("LA-") else v0
        dims = _norm(vals[2]) if n_cols > 2 else ""
        desc = _norm(vals[3]) if n_cols > 3 else ""
        if not desc:
            maybe = _norm(vals[2]) if n_cols > 2 else ""
            if maybe and not re.match(r"^[\d½¾¼./xX\s\-]+$", maybe):
                desc = maybe
                dims = ""
        if not desc:
            desc = part

        # Count prices in matrix cols vs last-3 quick-ship style
        matrix_prices = 0
        for j, _ in unf_cols + fin_cols:
            if j < n_cols and _to_price(vals[j]) is not None:
                matrix_prices += 1

        last3 = [
            _to_price(vals[j]) if j < n_cols else None for j in (n_cols - 3, n_cols - 2, n_cols - 1)
        ]
        # Quick-ship / oak-only: unfinished | finishing cost | finished in last 3 cols
        # when full wood matrix is not populated on this row
        if matrix_prices <= 1 and last3[0] is not None and last3[2] is not None:
            _emit(part, desc, dims, "unfinished", last3[0], species="Oak", tier=None)
            _emit(part, desc, dims, "finished", last3[2], species="Oak", tier=None)
            continue

        if not unf_cols and not fin_cols:
            # Fall back to last3 if no matrix header seen yet
            if last3[0] is not None and last3[2] is not None:
                _emit(part, desc, dims, "unfinished", last3[0], species="Oak")
                _emit(part, desc, dims, "finished", last3[2], species="Oak")
            continue

        for finish_state, col_list in (
            ("unfinished", unf_cols),
            ("finished", fin_cols),
        ):
            for tier_i, (j, lab) in enumerate(col_list, start=1):
                if finish_cost_col is not None and j == finish_cost_col:
                    continue
                price = _to_price(vals[j]) if j < n_cols else None
                if price is None:
                    continue
                _emit(part, desc, dims, finish_state, price, species=lab or None, tier=tier_i)

    if not rows_out:
        return pd.DataFrame()

    # Prefer matrix rows (with species/collection) over quick-ship twins
    # for the same SKU × finish × price.
    best: dict[tuple, dict] = {}
    for r in rows_out:
        key = (
            str(r.get("part_number") or ""),
            str(r.get("finish_state") or ""),
            round(float(r.get("base_price") or 0), 2),
            str(r.get("species") or ""),
        )
        score = (
            1 if r.get("species") else 0,
            1 if r.get("collection") else 0,
            len(str(r.get("description") or "")),
        )
        prev = best.get(key)
        if prev is None:
            best[key] = r
            continue
        prev_score = (
            1 if prev.get("species") else 0,
            1 if prev.get("collection") else 0,
            len(str(prev.get("description") or "")),
        )
        if score > prev_score:
            best[key] = r

    # Collapse species="" and species=label duplicates at same price/finish
    # when one has no species (quick-ship) and another has the same price.
    by_pfp: dict[tuple, list[dict]] = {}
    for r in best.values():
        k = (
            str(r.get("part_number") or ""),
            str(r.get("finish_state") or ""),
            round(float(r.get("base_price") or 0), 2),
        )
        by_pfp.setdefault(k, []).append(r)
    final: list[dict] = []
    for group in by_pfp.values():
        if len(group) == 1:
            final.append(group[0])
            continue
        with_species = [g for g in group if g.get("species")]
        if with_species:
            final.extend(with_species)
        else:
            final.append(group[0])

    items = _clean_long_rows(pd.DataFrame(final))
    if not option_rows:
        return items
    opts = _clean_long_rows(pd.DataFrame(option_rows))
    if items.empty:
        return opts
    if opts.empty:
        return items
    return pd.concat([items, opts], ignore_index=True)


def import_lamb_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """
    LAMB: store **Wholesale** only (Retail Finished is builder retail ~2.7× wholesale —
    multiplying again would double-count markup).
    """
    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or "LAMB"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    wholesale = next((n for n in names if str(n).strip().lower() == "wholesale"), None)
    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]
    elif wholesale:
        targets = [wholesale]
    else:
        # No wholesale tab — fall back to non-retail sheets only
        targets = [n for n in names if not re.search(r"(?i)\bretail\b", str(n))] or list(names)

    for name in names:
        if name not in targets:
            tried.append(
                {
                    "sheet": name,
                    "layout": "skip",
                    "rows": 0,
                    "note": "LAMB: prefer Wholesale; skipped retail/other",
                }
            )
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue

        long = parse_lamb_wholesale_sheet(
            raw,
            vendor=vendor_name,
            default_collection=default_collection,
            price_basis="wholesale",
        )
        n = len(long) if long is not None and not long.empty else 0
        tried.append(
            {
                "sheet": name,
                "layout": "lamb_wholesale_matrix",
                "rows": n,
                "note": "Item No + wood groups unfinished/finished",
                "species_cols": sorted(
                    {str(s) for s in (long["species"].dropna().unique().tolist() if n else [])}
                )[:8],
                "id_col": "Item No.",
                "desc_col": "Description",
            }
        )
        if n > 0:
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
        f"LAMB wholesale matrix · {len(out)} long rows · "
        f"sheets={[t['sheet'] for t in tried if t.get('rows')]}"
    )
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,
        sheet_names=names,
        notes=note,
    )
