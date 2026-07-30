"""
FN Chair Level One Blue — parse the authoritative PL Print matrix.

Workbook shape (per style block):
  Style name | | wood1 | wood2 | ... | | fabric1 | fabric2 | ...
  Side Chair | Unf | prices... | | fabric adders...
             | Cat. 1 | prices...
             | Cat. 2 | ...
             | Cat. 3 | ...
  Arm Chair  | Unf | ...

Cat. 1/2/3 are finish/stain tiers (see PCL Color List), not fabric grades.
Unf = unfinished wood chair. Fabric columns on Unf rows are flat $ upcharge
adders — imported as ``line_kind='addon'`` (ADR-0008), not sellable retail.
"""

from __future__ import annotations

import io
import re
from typing import Any, Optional

import pandas as pd

_FN_SHEET_PREFER = ("PL Print", "PL With Markup")
_FN_SKIP_SHEETS = re.compile(
    r"(?i)^(cover|retired|price\s*list\s*notes|internet|pcl\s*color|"
    r"pl\s*to\s*export|extra\s*blank|warranty)"
)

_CAT_RE = re.compile(r"(?i)^cat\.?\s*([123])$")
_UNF_RE = re.compile(r"(?i)^unf\.?$|^unfinished$")

_CHAIR_TYPE_RE = re.compile(
    r"(?i)^(side\s+chair|arm\s+chair|arm\s+desk\s+chair|"
    r'(?:\d+"?\s*)?(?:swivel|stationary)\s+bar\s+stool|'
    r"seat\s+only(?:\s+.*)?)$"
)

_WOODISH_RE = re.compile(r"(?i)oak|maple|cherry|walnut|hickory|qs|qtrsawn|rough\s*sawn|wormy")


def _norm_quotes(s: str) -> str:
    return (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .strip()
    )


def _cell(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return _norm_quotes(str(v).strip())


def _to_price(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
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


def looks_like_fn_level_one(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    """Detect FN Chair Level One Blue (or similar) workbooks."""
    fn = (filename or "").lower().replace("-", "_")
    names = [str(n) for n in (sheet_names or [])]
    has_pl_print = any(n.strip().lower() == "pl print" for n in names)
    if has_pl_print and any(
        re.search(r"(?i)pcl\s*color|pl\s*to\s*export|pl\s*with\s*markup", n) for n in names
    ):
        return True
    if re.search(r"(?i)\bfnc?\b|\bfn[\s_]*chair", fn) and has_pl_print:
        return True
    if re.search(r"(?i)fn[\s_]*chair.*level[\s_]*one|level[\s_]*one.*fn", fn):
        return True
    if has_pl_print and re.search(r"(?i)fn|fnc", fn):
        return True
    return False


def _is_style_header(row: list[Any]) -> bool:
    label = _cell(row[0] if row else None)
    if not label or label.lower() in {"special notes", "special note"}:
        return False
    if _CHAIR_TYPE_RE.match(label) or _CAT_RE.match(label) or _UNF_RE.match(label):
        return False
    wood_hits = sum(1 for v in row[2:9] if _cell(v) and _WOODISH_RE.search(_cell(v)))
    return wood_hits >= 2


def _finish_token(val: Any) -> Optional[tuple[str, str, Optional[str]]]:
    """
    Return (finish_state, option_key_or_empty, display_token) or None.
    """
    s = _cell(val)
    if not s:
        return None
    if _UNF_RE.match(s):
        return ("unfinished", None, "Unf")
    m = _CAT_RE.match(s)
    if m:
        tok = f"Cat. {int(m.group(1))}"
        return ("finished", tok, tok)
    return None


def parse_fn_pl_print_rows(
    raw: pd.DataFrame,
    *,
    vendor: str = "FN Chair",
) -> list[dict]:
    """Unpivot one PL Print / PL With Markup sheet into long row dicts."""
    if raw is None or raw.empty:
        return []
    df = raw.dropna(how="all").reset_index(drop=True)
    out: list[dict] = []
    style: Optional[str] = None
    woods: list[tuple[int, str]] = []
    fabrics: list[tuple[int, str]] = []
    chair: Optional[str] = None

    for i in range(len(df)):
        row = [df.iat[i, j] if j < df.shape[1] else None for j in range(df.shape[1])]
        if _is_style_header(row):
            style = _cell(row[0])
            woods = []
            for j in range(2, min(9, len(row))):
                lab = _cell(row[j])
                if lab and _WOODISH_RE.search(lab):
                    woods.append((j, lab))
            fabrics = []
            max_wood_j = max((j for j, _ in woods), default=1)
            for j in range(max_wood_j + 1, len(row)):
                lab = _cell(row[j])
                if lab and not _WOODISH_RE.search(lab):
                    fabrics.append((j, lab))
            chair = None
            continue

        if not style or not woods:
            continue

        c0 = _cell(row[0])
        if c0 and _CHAIR_TYPE_RE.match(c0):
            chair = c0
        elif c0 and re.search(r"(?i)chair|stool|seat", c0):
            # Allow slight naming variants (e.g. 18" Swivel Bar Stool)
            chair = c0

        fin = _finish_token(row[1] if len(row) > 1 else None)
        if not chair or not fin:
            continue
        finish_state, option_key, fin_disp = fin
        part = f"{style} {chair}"
        desc = f"{part} — {fin_disp}" if option_key else part

        for j, species in woods:
            price = _to_price(row[j] if j < len(row) else None)
            if price is None:
                continue
            out.append(
                {
                    "vendor": vendor,
                    "collection": "Seating",
                    "part_number": part,
                    "description": desc,
                    "dimensions": None,
                    "option_key": option_key,
                    "species": species,
                    "species_tier": None,
                    "finish_state": finish_state,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                    "line_kind": "item",
                }
            )

        # Fabric columns = flat $ addon charges (ADR-0008), not chair retail
        for j, fabric in fabrics:
            adder = _to_price(row[j] if j < len(row) else None)
            if adder is None:
                continue
            out.append(
                {
                    "vendor": vendor,
                    "collection": "Addons",
                    "part_number": f"{part} — {fabric}",
                    "description": f"{fabric} adder ({part})",
                    "dimensions": None,
                    "option_key": fabric,
                    "species": None,
                    "species_tier": None,
                    # Floor Finish defaults to finished; addons are not Unf chairs
                    "finish_state": "finished",
                    "base_price": adder,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": "fabric adder",
                    "line_kind": "addon",
                    "addon_pct": None,
                }
            )
    return out


def import_fn_chair_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
):
    """Import FN Chair Level One from PL Print (prefer) or PL With Markup."""
    from wide_import import WorkbookImportResult, list_excel_sheets

    names = list_excel_sheets(data)
    vendor_name = vendor or "FN Chair"
    tried: list[dict] = []
    frames: list[pd.DataFrame] = []

    # Prefer PL Print; fall back to PL With Markup (same wholesale grid).
    prefer = [n for n in _FN_SHEET_PREFER if n in names]
    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]
    elif prefer:
        targets = prefer[:1]  # one sheet only — avoid double count
    else:
        targets = [
            n
            for n in names
            if not _FN_SKIP_SHEETS.search(str(n)) and re.search(r"(?i)\bpl\b|price", str(n))
        ]

    for name in names:
        if name not in targets:
            tried.append(
                {
                    "sheet": name,
                    "layout": "skip",
                    "rows": 0,
                    "note": "fn level-one non-product or duplicate sheet",
                }
            )
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None, engine="openpyxl")
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        rows = parse_fn_pl_print_rows(raw, vendor=vendor_name)
        if default_collection:
            for r in rows:
                if not r.get("collection"):
                    r["collection"] = default_collection
        long = pd.DataFrame(rows)
        tried.append(
            {
                "sheet": name,
                "layout": "fn_level_one_pl_print",
                "rows": 0 if long.empty else len(long),
                "note": f"styles/chairs × Unf/Cat.N × woods from {name}",
            }
        )
        if not long.empty:
            frames.append(long)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame()

    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,
        sheet_names=names,
        notes=(
            f"{filename + ': ' if filename else ''}"
            f"FN Chair Level One PL Print · "
            f"{0 if out.empty else len(out)} rows "
            f"(wood prices + fabric adders as line_kind=addon)"
        ),
    )
