"""
Wide species-matrix Excel import → long-form sellable rows.

Builders ship:
  Item # | Description | Dims | Oak/BM | Rustic tier | Cherry tier | Walnut | …

We store:
  one row per (part × species_tier × finish_state) with base_price.

Named factory readers live in ``backend/<id>_import.py`` and register once
in ``DEFAULT_READER_REGISTRY``. This module keeps the generic unpivot, shared
cell helpers (``_norm``, ``_to_float``, ``_clean_long_rows``), and
compatibility aliases for those extracted readers. LuxHome's leftover copy
here is not the dedicated module (``backend/luxhome_import.py``). Millers
enhancement still runs on a generic fallthrough so an MWS filename is not
lost if the named reader is skipped.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional, Union

import pandas as pd

# ---------------------------------------------------------------------------
# Species / finish detection
# ---------------------------------------------------------------------------

WOOD_TOKENS = (
    "oak",
    "maple",
    "cherry",
    "walnut",
    "hickory",
    "elm",
    "qswo",
    "pswo",
    "wormy",
    "rustic",
    "birch",
    "ash",
    "poplar",
    "pine",
    "alder",
    "beech",
    "mahogany",
    "sap cherry",
    "brown maple",
    "hard maple",
    "white oak",
    "red oak",
    "quarter",
    "1/4 sawn",
    "rough sawn",
    "ruff sawn",
    "barnwood",
    "species",
    "wood",
)

FINISH_TOKENS = (
    "finished",
    "unfinished",
    "glazed",
    "fin.",
    "unf.",
    "fin ",
    "unf ",
    "finshed",  # common HW typo
)

ID_TOKENS = (
    "item",
    "part",
    "sku",
    "model",
    "code",
    "style",
    "catalog",
    "stock",
    "item #",
    "item#",
    "part #",
    "part#",
    "model #",
    "sku #",
)

DESC_TOKENS = ("description", "descr", "desc.", "name", "product", "title", "item name")

DIM_TOKENS = (
    "dimension",
    "dims",
    "size",
    "w x d x h",
    "w×d×h",
    'h"',
    'w"',
    'd"',
    "width",
    "height",
    "depth",
    "overall",
    "wxdxh",
)

SKIP_SHEET_RE = re.compile(
    r"""(?ix)
    ^(markup|mark\s*up|multiplier|multipliers|instructions?|cover|index|index_?|
      settings?|information(\s*sheet)?|customer\s*letter|notes?|toc|
      table\s*of\s*contents|controls?|
      title\s*page|dealer\s*info.*)$
    """
)

# True markup control sheets — not product sheets like "PL With Markup"
MARKUP_SHEET_RE = re.compile(
    r"""(?ix)
    ^(mark\s*-?\s*up|multipliers?|price\s*manipulator)(\b|$)
    |wholesale\s*mark\s*-?\s*up
    |^mark\s*-?\s*up\s
    """
)

MONEY_CELL_RE = re.compile(r"^\$?\s*[\d,]+(?:\.\d{1,2})?$")


def _norm(s) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    t = str(s).replace("\n", " ").replace("\r", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _norm_key(s) -> str:
    return _norm(s).lower()


def _to_float(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        # Excel serials / huge junk
        f = float(val)
        if f <= 0 or f > 5_000_000:
            # allow small prices like 15; reject obvious non-prices later elsewhere
            if f <= 0:
                return None
        return f
    s = _norm(val)
    if not s or s.lower() in {"nan", "none", "-", "n/a", "na", "n\\a", "#n/a", "#value!", "#ref!"}:
        return None
    if re.fullmatch(r"N/?A", s, re.I):
        return None
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    # Do not pull a leading digit out of labels like "1/4 Sawn" or "36 x 48 Top"
    if re.search(r"[A-Za-z]", s):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if f <= 0 or f > 5_000_000:
        return None
    return f


def looks_like_species_header(col: str) -> bool:
    k = _norm_key(col)
    if not k or k.startswith("unnamed"):
        return False
    # pure finish without wood → not a species tier alone
    if any(t in k for t in WOOD_TOKENS):
        return True
    # column that is only "Finished"/"Unfinished" handled separately
    return False


def looks_like_finish_header(col: str) -> bool:
    k = _norm_key(col)
    return any(t in k for t in FINISH_TOKENS) and not any(
        w in k for w in ("finishing cost", "finish est", "est. finishing", "estimated finishing")
    )


def looks_like_id_header(col: str) -> bool:
    k = _norm_key(col)
    if k in {
        "item",
        "item #",
        "item#",
        "item number",
        "item no",
        "item no.",
        "part",
        "part #",
        "part#",
        "part number",
        "part no",
        "sku",
        "model",
        "model #",
        "model#",
        "code",
        "style",
        "style #",
        "catalog #",
        "stock #",
        "item name",
        "search all items",
        "id",
        "id#",
        "id #",
        "item#",
        "item no",
        "no.",
        "no",
        "#",
    }:
        return True
    # Item# / Model# with optional spaces
    if re.match(r"(?i)^(item|model|part|style|sku|id)\s*#?\s*$", k):
        return True
    if re.match(r"(?i)^#\s*(item|model|part)?$", k):
        return True
    # FVWW-style: long header containing "search all items"
    if "search all items" in k or k.endswith(" items"):
        return True
    return (
        any(k == t or k.startswith(t + " ") or k.endswith(" " + t) for t in ID_TOKENS)
        and len(k) < 40
    )


def looks_like_desc_header(col: str) -> bool:
    k = _norm_key(col)
    return any(t in k for t in DESC_TOKENS) or k in {"description", "descr.", "desc"}


def looks_like_dim_header(col: str) -> bool:
    from backend.standardize import dimension_axis

    if dimension_axis(col):
        return True
    k = _norm_key(col)
    if k in {"h", "w", "d", 'h"', 'w"', 'd"', "h'", "w'", "d'"}:
        return True
    return any(t in k for t in DIM_TOKENS)


def classify_column(col: str) -> str:
    """Return: id | desc | dim | species | finish | finish_est | price | other | skip."""
    k = _norm_key(col)
    if not k or k.startswith("unnamed") or k.startswith("skip_"):
        return "skip"
    if re.search(r"finish(ing)?\s*(cost|est|estimate)", k) or "estimated finishing" in k:
        return "finish_est"
    if looks_like_desc_header(col):
        return "desc"
    if looks_like_id_header(col):
        return "id"
    if looks_like_dim_header(col):
        return "dim"
    if looks_like_species_header(col):
        return "species"
    if looks_like_finish_header(col):
        return "finish"
    if k in {
        "price",
        "wholesale",
        "retail",
        "cost",
        "amount",
        "net",
        "dealer",
        "whsl. price",
        "whsl price",
        "list price",
        "regular",
    }:
        return "price"
    if k in {"unit", "uom", "notes", "note", "collection", "series"}:
        return "meta"
    # Multi-line wood blobs often contain newlines already normalized
    wood_hits = sum(1 for t in WOOD_TOKENS if t in k)
    if wood_hits >= 2:
        return "species"
    if wood_hits == 1 and len(k) < 80:
        return "species"
    return "other"


def is_price_column(series: pd.Series, min_hits: int = 3) -> bool:
    """True if a solid share of non-empty cells look like money (not labels)."""
    hits = 0
    nonempty = 0
    for v in series.head(50):
        s = _norm(v)
        if not s:
            continue
        nonempty += 1
        if _to_float(v) is not None:
            hits += 1
    if hits < min_hits:
        return False
    if nonempty == 0:
        return False
    return (hits / nonempty) >= 0.45


# ---------------------------------------------------------------------------
# Header detection & sheet loading
# ---------------------------------------------------------------------------


def find_header_row(raw: pd.DataFrame, max_scan: int = 200) -> int:
    """Pick row with best mix of id/desc/species labels or most wood-token cells.

    Prefer classic long-form headers (Model # + Description + price) over a
    pure species-banner row that often sits above the real header.

    Scan deep (default 200): many Amish books put calculators/options first
    and the real Item# × species matrix around row 90–120.
    """
    best_i, best_score = 0, -1
    limit = min(max_scan, len(raw))
    for i in range(limit):
        row = raw.iloc[i]
        cells = [_norm(v) for v in row.tolist()]
        nonempty = [c for c in cells if c]
        if len(nonempty) < 2:
            continue
        score = 0
        kinds = [classify_column(c) for c in nonempty]
        n_id = sum(1 for k in kinds if k == "id")
        n_desc = sum(1 for k in kinds if k == "desc")
        n_species = sum(1 for k in kinds if k == "species")
        n_price = sum(1 for k in kinds if k == "price")
        n_finish = sum(1 for k in kinds if k == "finish")
        n_dim = sum(1 for k in kinds if k == "dim")
        # Data rows have money values — headers almost never do
        n_numeric = sum(1 for c in nonempty if _to_float(c) is not None)
        score += n_id * 8 + n_desc * 6 + n_price * 4 + n_finish * 3 + n_dim * 2
        # Species columns are valuable only when we also have an id column
        # (true wide matrix). A banner of woods with no Model# must not win
        # over a true Item# header deeper in the sheet — but multi-wood
        # headers (Interior Hardwoods) are still real price matrices.
        if n_species >= 2 and n_id >= 1:
            score += 12
        elif n_species >= 3 and n_id == 0 and n_numeric == 0:
            score += 10  # Oak | Cherry | Maple price-matrix header
        elif n_species >= 2 and n_id == 0:
            score += 2  # weak: likely section/banner row above real header
        # Gold standard long-form: Model# + Description (+ price)
        if n_id >= 1 and n_desc >= 1:
            score += 30
        if n_id >= 1 and n_price >= 1:
            score += 12
        # Item # + multi-species (E&I / L&N style) even without "Description" token
        if n_id >= 1 and n_species >= 2:
            score += 20
        # Prefer headers that sit above real data (SKU-like cell in next rows)
        if n_id >= 1 and i + 1 < len(raw):
            peek = [_norm(v) for v in raw.iloc[i + 1].tolist()[:6] if _norm(v)]
            skuish = sum(
                1
                for s in peek
                if re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,24}$", s, re.I) and not MONEY_CELL_RE.match(s)
            )
            if skuish >= 1:
                score += 8
        if n_numeric >= 1:
            score -= n_numeric * 8
        # Footer / policy bullets near end of short sheets
        if i >= max(10, int(len(raw) * 0.75)) and n_id == 0 and n_species == 0:
            score -= 15
        for c in nonempty:
            # penalty for pure address/phone junk
            if re.search(r"@|phone|fax|http|township|road|street|email", c, re.I):
                score -= 6
            # long prose / notes rows are not headers
            if len(c) > 80:
                score -= 10
            # policy bullets
            if c.lstrip().startswith("·") or c.lstrip().startswith("•"):
                score -= 8
            # "Regular" / "Wholesale" as price-ish without id is weak
            if re.search(r"(?i)^(regular|list|net|your price)$", c) and n_id == 0:
                score -= 1
            # page labels alone are not headers
            if re.fullmatch(r"(?i)page\s*#?", c):
                score -= 2
        if score > best_score:
            best_score = score
            best_i = i
    # No credible header (catalogs with bare name/price columns, no Item#)
    if best_score < 6:
        return -1
    return best_i


def dataframe_from_sheet(
    data: bytes,
    sheet_name: Union[str, int],
    engine: Optional[str] = None,
) -> pd.DataFrame:
    from backend.workbook_sheets import read_sheet

    raw = read_sheet(data, sheet_name, header=None)
    return dataframe_from_raw(raw)


def dataframe_from_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """Promote headers from an already-read visible sheet."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all")
    if raw.empty:
        return raw

    # Reset index after drop
    raw = raw.reset_index(drop=True)
    hdr_i = find_header_row(raw)
    # No labeled header — keep synthetic col_N names; classify_sheet guesses id/price
    if hdr_i < 0:
        body = raw.copy()
        body.columns = [f"col_{j}" for j in range(body.shape[1])]
        body = body.dropna(how="all")
        return body.reset_index(drop=True)
    # Two-row headers: species on row hdr_i, Unfinished/Finished on hdr_i+1 (HW pattern)
    body_start = hdr_i + 1
    headers: list[str] = []
    if hdr_i + 1 < len(raw):
        next_cells = [_norm(v) for v in raw.iloc[hdr_i + 1].tolist()]
        finish_hits = sum(1 for c in next_cells if looks_like_finish_header(c))
        if finish_hits >= 2:
            species_carry = ""
            seen: dict[str, int] = {}
            provisional: list[str] = []
            past_markup = False
            for j in range(raw.shape[1]):
                top = _norm(raw.iat[hdr_i, j]) if j < raw.shape[1] else ""
                bot = next_cells[j] if j < len(next_cells) else ""
                if (top and re.search(r"(?i)mark\s*up|multiplier", top)) or (
                    bot and re.search(r"(?i)mark\s*up|multiplier", bot)
                ):
                    past_markup = True
                    species_carry = ""
                if past_markup:
                    # HopeWood / HW: columns after "Markup over" are calculator adders
                    provisional.append(f"skip_{j}")
                    continue
                if top and not looks_like_finish_header(top) and not top.lower().startswith("col_"):
                    if (
                        not looks_like_id_header(top)
                        and not looks_like_desc_header(top)
                        and not looks_like_dim_header(top)
                    ):
                        low = top.lower()
                        woodish = (
                            looks_like_species_header(top)
                            or any(t in low for t in WOOD_TOKENS)
                            or bool(
                                re.search(
                                    r"(?i)\b(oak|maple|cherry|walnut|hick(?:ory)?|qswo|qsw?|"
                                    r"ch|hm|ro|bsm|rustic)\b",
                                    top,
                                )
                            )
                        )
                        if woodish:
                            species_carry = top
                        elif not looks_like_finish_header(top):
                            # Non-wood label breaks the primary matrix block
                            species_carry = ""
                if bot and looks_like_finish_header(bot) and species_carry:
                    name = f"{species_carry} | {bot}"
                elif top:
                    name = top
                elif bot:
                    name = bot
                else:
                    name = f"col_{j}"
                provisional.append(name)

            # Keep primary species|finish groups.
            # HopeWood has unfinished+finished pairs; Premier has finished-only.
            # Require BOTH only when the sheet actually uses unfinished columns.
            species_order: list[str] = []
            species_finishes: dict[str, set[str]] = {}
            for name in provisional:
                if " | " not in name:
                    continue
                sp, fin = name.split(" | ", 1)
                if sp not in species_finishes:
                    species_order.append(sp)
                    species_finishes[sp] = set()
                species_finishes[sp].add(fin.lower())
            sheet_has_unfinished = any(
                any("unf" in f for f in fins) for fins in species_finishes.values()
            )
            complete_ordered = []
            for sp in species_order:
                fins = species_finishes[sp]
                has_fin = any("fin" in f and "unf" not in f for f in fins)
                has_unf = any("unf" in f for f in fins)
                if sheet_has_unfinished:
                    ok = has_fin and has_unf
                else:
                    ok = has_fin or has_unf
                if ok:
                    complete_ordered.append(sp)
                else:
                    break  # stop at first incomplete group (HW adder cols)
            complete = set(complete_ordered)

            headers = []
            for name in provisional:
                if name.startswith("skip_") or (
                    " | " in name and name.split(" | ", 1)[0] not in complete
                ):
                    base = f"skip_{name}" if not name.startswith("skip_") else name
                else:
                    base = name
                if base in seen:
                    seen[base] += 1
                    headers.append(f"{base} ({seen[base]})")
                else:
                    seen[base] = 1
                    headers.append(base)
            body_start = hdr_i + 2
        else:
            headers = []
    if not headers:
        seen = {}
        for j, v in enumerate(raw.iloc[hdr_i].tolist()):
            name = _norm(v) or f"col_{j}"
            base = name
            if base in seen:
                seen[base] += 1
                name = f"{base} ({seen[base]})"
            else:
                seen[base] = 1
            headers.append(name)
        body_start = hdr_i + 1

    body = raw.iloc[body_start:].copy()
    body.columns = headers
    body = body.dropna(how="all")
    return body.reset_index(drop=True)


def list_excel_sheets(data: bytes) -> list[str]:
    """Visible sheet titles only. Hidden tabs stay hidden."""
    from backend.workbook_sheets import excel_engine, hidden_sheet_names

    bio = io.BytesIO(data)
    try:
        xl = pd.ExcelFile(bio, engine=excel_engine(data))
    except Exception:
        bio.seek(0)
        xl = pd.ExcelFile(bio)
    names = list(xl.sheet_names)
    hidden = hidden_sheet_names(data)
    return [n for n in names if n not in hidden]


def _is_markup_control_sheet(name: str) -> bool:
    """True for Markup/Multiplier control tabs; false for 'PL With Markup' price sheets."""
    n = str(name).strip()
    low = n.lower()
    # Product sheets that already apply markup
    if re.search(r"(?i)\b(pl|price\s*list|export|print|to\s*export)\b", low) and re.search(
        r"(?i)mark\s*-?\s*up", low
    ):
        return False
    return bool(MARKUP_SHEET_RE.search(n)) or low in {
        "markup",
        "mark-up",
        "mark up",
        "multiplier",
        "multipliers",
        "mark-up page",
    }


def detect_markup_from_workbook(data: bytes, sheet_names: list[str]) -> Optional[float]:
    """Scan Markup sheets for a plausible multiplier (0.5–20 or percent 50–2000)."""
    for name in sheet_names:
        if not _is_markup_control_sheet(str(name)):
            continue
        try:
            from backend.workbook_sheets import read_sheet

            df = read_sheet(data, name, header=None)
        except Exception:
            continue
        candidates = []
        for v in df.to_numpy().ravel()[:200]:
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                f = float(v)
                if 1.0 <= f <= 10.0:
                    candidates.append(f)
                elif 100 <= f <= 400:  # percent form e.g. 270
                    candidates.append(f / 100.0)
        # also labeled cells nearby
        for i in range(min(30, len(df))):
            for j in range(min(10, df.shape[1])):
                cell = _norm_key(df.iat[i, j])
                if "markup" in cell or "multiplier" in cell or "mark up" in cell:
                    # look right / below
                    for di, dj in ((0, 1), (1, 0), (0, 2), (1, 1)):
                        ii, jj = i + di, j + dj
                        if 0 <= ii < len(df) and 0 <= jj < df.shape[1]:
                            f = _to_float(df.iat[ii, jj])
                            if f is not None and 0.5 <= f <= 20:
                                candidates.append(f)
                            elif f is not None and 50 <= f <= 400:
                                candidates.append(f / 100.0)
        if candidates:
            # Prefer real dealer mults (2.7, 1.7). Bare 1.0 often appears as
            # a placeholder / percent edge-case and must not win over 2.7.
            def _markup_rank(x: float) -> tuple:
                if abs(x - 2.7) < 0.05:
                    return (0, 0.0)
                if abs(x - 1.7) < 0.05:
                    return (1, 0.0)
                if abs(x - 1.0) < 0.02:
                    return (9, 0.0)  # last resort
                return (5, min(abs(x - 2.7), abs(x - 1.7)))

            candidates.sort(key=_markup_rank)
            return candidates[0]
    return None


# ---------------------------------------------------------------------------
# Layout classification & unpivot
# ---------------------------------------------------------------------------


@dataclass
class SheetLayout:
    sheet_name: str
    layout: str  # wide_species | wide_finish | long_flat | unknown | skip
    id_col: Optional[str] = None
    desc_col: Optional[str] = None
    dim_cols: list[str] = field(default_factory=list)
    species_cols: list[str] = field(default_factory=list)
    finish_cols: list[str] = field(default_factory=list)
    price_cols: list[str] = field(default_factory=list)
    finish_est_col: Optional[str] = None
    notes: str = ""


def classify_sheet(df: pd.DataFrame, sheet_name: str) -> SheetLayout:
    if SKIP_SHEET_RE.match(str(sheet_name).strip()):
        return SheetLayout(sheet_name, "skip", notes="Non-product sheet")

    if df is None or df.empty or len(df.columns) < 2:
        return SheetLayout(sheet_name, "unknown", notes="Empty sheet")

    kinds = {c: classify_column(c) for c in df.columns}
    # promote "other" columns that are mostly prices
    # Never promote explicit skip_ columns (HW markup-adder orphans).
    for c, k in list(kinds.items()):
        if str(c).lower().startswith("skip_"):
            kinds[c] = "skip"
            continue
        if k in ("other", "meta") and is_price_column(df[c], min_hits=4):
            # if header has wood → species; else price
            if (
                looks_like_species_header(c)
                or sum(1 for t in WOOD_TOKENS if t in _norm_key(c)) >= 1
            ):
                kinds[c] = "species"
            elif not looks_like_id_header(c) and not looks_like_desc_header(c):
                kinds[c] = "price"

    id_cols = [c for c, k in kinds.items() if k == "id"]
    desc_cols = [c for c, k in kinds.items() if k == "desc"]
    dim_cols = [c for c, k in kinds.items() if k == "dim"]
    species_cols = [c for c, k in kinds.items() if k == "species"]
    finish_cols = [c for c, k in kinds.items() if k == "finish"]
    price_cols = [c for c, k in kinds.items() if k == "price"]
    finish_est = next((c for c, k in kinds.items() if k == "finish_est"), None)

    # If multiple species-like price columns, it's wide_species
    pricey_species = [c for c in species_cols if is_price_column(df[c], min_hits=2)]
    if len(pricey_species) >= 2:
        layout = "wide_species"
        species_cols = pricey_species
    elif len(finish_cols) >= 2 and any(is_price_column(df[c], min_hits=2) for c in finish_cols):
        layout = "wide_finish"
    elif (id_cols or desc_cols) and price_cols:
        layout = "long_flat"
    elif (id_cols or desc_cols) and len(pricey_species) == 1:
        layout = "long_flat"
        price_cols = pricey_species
        species_cols = []
    else:
        # last chance: numeric columns without labels — require a real id column
        numericish = [
            c
            for c in df.columns
            if kinds.get(c) in ("other", "price", "species") and is_price_column(df[c], min_hits=4)
        ]
        guessed_id = _guess_id_from_values(df)
        if len(numericish) >= 2 and (id_cols or guessed_id):
            layout = "wide_species"
            species_cols = numericish
            if not id_cols and guessed_id:
                id_cols = [guessed_id]
        elif len(numericish) == 1 and (id_cols or desc_cols or guessed_id):
            layout = "long_flat"
            price_cols = numericish
            if not id_cols and guessed_id:
                id_cols = [guessed_id]
        else:
            layout = "unknown"

    # Name-only sheets (Interior Hardwoods): species matrix + product titles, no Item#
    if not id_cols and not desc_cols:
        guessed_id = _guess_id_from_values(df)
        guessed_name = _guess_product_name_col(df)
        if guessed_id:
            id_cols = [guessed_id]
        elif guessed_name and (layout == "wide_species" or len(pricey_species) >= 2):
            id_cols = [guessed_name]
            desc_cols = [guessed_name]
            if layout == "unknown" and len(pricey_species) >= 2:
                layout = "wide_species"
                species_cols = pricey_species
        elif guessed_name and layout == "unknown":
            # try promote numeric cols to species when we have product names
            numericish = [
                c
                for c in df.columns
                if c != guessed_name
                and kinds.get(c) in ("other", "price", "species")
                and is_price_column(df[c], min_hits=3)
            ]
            if len(numericish) >= 2:
                layout = "wide_species"
                species_cols = numericish
                id_cols = [guessed_name]
                desc_cols = [guessed_name]

    return SheetLayout(
        sheet_name=sheet_name,
        layout=layout,
        id_col=id_cols[0] if id_cols else None,
        desc_col=desc_cols[0] if desc_cols else None,
        dim_cols=dim_cols,
        species_cols=species_cols,
        finish_cols=[c for c in finish_cols if is_price_column(df[c], min_hits=2)],
        price_cols=price_cols,
        finish_est_col=finish_est,
        notes=f"kinds: id={len(id_cols)} desc={len(desc_cols)} species={len(species_cols)} finish={len(finish_cols)} price={len(price_cols)}",
    )


def _guess_id_from_values(df: pd.DataFrame) -> Optional[str]:
    """Pick first column that looks like part numbers."""
    for c in df.columns:
        if looks_like_species_header(c) or str(c).lower().startswith("skip_"):
            continue
        sample = [_norm(v) for v in df[c].head(25).tolist() if _norm(v)]
        if len(sample) < 3:
            continue
        # codes like A591-Q, 100K, SU-BT10, 5885
        hits = sum(
            1
            for s in sample
            if re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,20}$", s, re.I) and not MONEY_CELL_RE.match(s)
        )
        if hits >= 3 and not looks_like_species_header(c):
            return c
    return None


def _guess_product_name_col(df: pd.DataFrame) -> Optional[str]:
    """Pick a text column of product names when the builder has no SKU column.

    Interior Hardwoods / HW Chair / name-only sheets use the product title as
    the identifier (STANDARDS: part_number may be the full item name).
    """
    best_c: Optional[str] = None
    best_hits = 0
    for c in df.columns:
        ck = _norm_key(c)
        if (
            looks_like_species_header(c)
            or looks_like_finish_header(c)
            or looks_like_dim_header(c)
            or ck.startswith("skip_")
            or classify_column(c) in ("species", "finish", "finish_est", "price")
        ):
            continue
        if is_price_column(df[c], min_hits=6):
            continue
        sample = [_norm(v) for v in df[c].head(50).tolist() if _norm(v)]
        if len(sample) < 5:
            continue
        hits = 0
        for s in sample:
            if MONEY_CELL_RE.match(s) or re.fullmatch(r"[\d.]+", s):
                continue
            if len(s) < 3:
                continue
            # Product titles usually have spaces or are longer labels
            if " " in s or len(s) >= 8 or re.match(r"^[A-Za-z].*[A-Za-z]$", s):
                # skip pure section ALL-CAPS banners without prices on same row handled later
                if re.fullmatch(r"(?i)page\s*#?|item\s*#?|description|size", s):
                    continue
                hits += 1
        if hits >= 5 and hits > best_hits:
            best_hits = hits
            best_c = c
    return best_c


def extract_multi_name_price_catalog(
    df: pd.DataFrame,
    *,
    vendor: str = "",
    default_collection: str = "",
) -> pd.DataFrame:
    """
    Catalogs laid out as repeated name|price blocks across the sheet
    (Amish Aspen, M&M outdoor, two- or three-column price flyers).

    No Item# / species matrix — each product is a label next to a dollar amount.
    """
    if df is None or df.empty or df.shape[1] < 2:
        return pd.DataFrame()

    text_cols: list[str] = []
    price_cols: list[str] = []
    for c in df.columns:
        sample = [_norm(v) for v in df[c].head(60).tolist() if _norm(v)]
        if len(sample) < 3:
            continue
        n_price = sum(1 for s in sample if _to_float(s) is not None)
        n_text = sum(
            1
            for s in sample
            if _to_float(s) is None
            and len(s) >= 3
            and not re.fullmatch(r"(?i)d\s*w\s*h|phone|fax|email|qty|\$", s)
        )
        if n_price >= 3 and n_price >= max(2, n_text):
            price_cols.append(c)
        elif n_text >= 3 and n_price <= n_text:
            text_cols.append(c)

    if not text_cols or not price_cols:
        return pd.DataFrame()

    col_idx = {c: i for i, c in enumerate(list(df.columns))}
    pairs: list[tuple[str, str]] = []
    used_prices: set[str] = set()
    for tc in text_cols:
        ti = col_idx[tc]
        candidates = sorted(
            (col_idx[pc] - ti, pc)
            for pc in price_cols
            if col_idx[pc] > ti and pc not in used_prices
        )
        if not candidates:
            continue
        dist, pc = candidates[0]
        if dist <= 4:
            pairs.append((tc, pc))
            used_prices.add(pc)

    if not pairs:
        return pd.DataFrame()

    rows = []
    current_collection: Optional[str] = default_collection or None
    for _, row in df.iterrows():
        # section banner if a text cell alone has no price on any pair
        for tc, pc in pairs:
            name = _norm(row[tc]) if tc in row.index else ""
            price = _to_float(row[pc]) if pc in row.index else None
            if (
                name
                and price is None
                and not any(_to_float(row[p]) is not None for _, p in pairs if p in row.index)
            ):
                if 3 <= len(name) <= 50 and not re.search(
                    r"(?i)phone|fax|email|@|subject to|price list|wholesale|from:|order date",
                    name,
                ):
                    current_collection = name
                break
        for tc, pc in pairs:
            name = _norm(row[tc]) if tc in row.index else ""
            price = _to_float(row[pc]) if pc in row.index else None
            if not name or price is None:
                continue
            if price < 5 or price > 50_000:
                continue
            if re.search(
                r"(?i)phone|fax|email|@|subject to|price list|wholesale|from:|"
                r"order date|due date|sealer|subtract|finished lasered|"
                r"^d\s*w\s*h$|joel martin|m\s*&\s*m enterprises",
                name,
            ):
                continue
            if len(name) > 80:
                continue
            # skip pure sizes used as "names"
            if re.fullmatch(r"\d+(\.\d+)?\s*[x×]\s*\d+", name, re.I):
                continue
            rows.append(
                {
                    "vendor": vendor or None,
                    "collection": current_collection,
                    "part_number": name,
                    "description": name,
                    "dimensions": None,
                    "option_key": None,
                    "species": None,
                    "species_tier": None,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                }
            )
    return _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()


def _combine_dims(row: pd.Series, dim_cols: list[str]) -> Optional[str]:
    if not dim_cols:
        return None
    parts = []
    for c in dim_cols:
        v = _norm(row.get(c))
        if v:
            # label short dim cols
            from backend.standardize import dimension_axis

            label = _norm(c)
            axis = dimension_axis(c) or dimension_axis(label)
            if axis:
                parts.append(f'{axis}"{v}')
            elif label.lower() in {'h"', 'w"', 'd"', "h", "w", "d"}:
                parts.append(f"{label}{v}" if v[-1] in "\"'" else f"{label}:{v}")
            else:
                parts.append(v)
    if not parts:
        return None
    return " × ".join(parts) if len(parts) > 1 else parts[0]


_SECTION_JUNK_RE = re.compile(
    r"""(?ix)
    add\s+(metal|\$)|door\s+options?|inset\s+panel|replace\s+glass|
    adjustable\s+shelf|markup|subtract\s+\d|subject\s+to\s+change|
    please\s+note|for\s+matching|see\s+page|upcharge|option:|
    \$50|finished\s*prices|unfinished\s*using
    """
)


def _section_collection(row_vals: list, prev: Optional[str]) -> Optional[str]:
    """If a row is a section header (text label, no real prices), treat as collection."""
    texts = [_norm(v) for v in row_vals if _norm(v)]
    if not texts:
        return prev
    # Ignore tiny 0 prices from blank matrix cells on section rows
    moneys = [v for v in texts if (_to_float(v) is not None and float(_to_float(v)) > 1)]
    if moneys:
        return prev
    joined = texts[0]
    if len(joined) > 70 or _SECTION_JUNK_RE.search(joined):
        # Option/instruction line — clear sticky collection
        return None if _SECTION_JUNK_RE.search(joined) else prev
    if not (3 <= len(joined) <= 60):
        return prev
    # ALL-CAPS category banners (SOFA MATE, CONTEMPORARY) or named collections
    if re.search(
        r"(?i)collection|series|bedroom|dining|chairs?|tables?|suite|"
        r"consoles?|desks?|bookcases?|entertainment|seating|occasional|"
        r"plant\s*stand|pedestal|bookshelf|shaker|mission|wall\s*units?|tv\s*stands?",
        joined,
    ):
        return joined.title() if joined.isupper() else joined
    if joined.isupper() and re.search(r"[A-Z]{3,}", joined):
        # SOFA MATE / CONTEMPORARY / DELUXE SHAKER
        if not re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,16}$", joined):
            return joined.title()
    if (
        joined[0].isupper()
        and not re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,16}$", joined)
        and not re.search(r"(?i)add |option|door |shelf|bracket|round rout", joined)
    ):
        return joined
    return prev


def _is_species_header_row(row_vals: list) -> bool:
    texts = [_norm(v) for v in row_vals if _norm(v)]
    if len(texts) < 2:
        return False
    species = sum(1 for value in texts if looks_like_species_header(value))
    return species >= 2 and species / len(texts) >= 0.5


def _is_finish_state_series(series: pd.Series) -> bool:
    values = series.dropna().astype(str).str.strip().str.lower()
    if values.empty:
        return False
    finish = values.str.fullmatch(r"(?:unf(?:inished)?|fin(?:ished)?|finshed|glaz(?:e|ed))")
    return bool(finish.mean() >= 0.6)


def _is_ditto_part(value: str) -> bool:
    return bool(re.fullmatch(r'(?:""|“”|″|〃)', (value or "").strip()))


def unpivot_wide_species(
    df: pd.DataFrame,
    layout: SheetLayout,
    *,
    default_collection: str = "",
    vendor: str = "",
    wholesale_map: Optional[dict[str, str]] = None,
) -> pd.DataFrame:
    """Expand species columns into long rows."""
    rows = []
    current_collection = default_collection or None
    current_part: Optional[str] = None
    id_col = layout.id_col or _guess_id_from_values(df) or _guess_product_name_col(df)
    desc_col = layout.desc_col
    wholesale_map = wholesale_map or {}
    # if no desc, sometimes description is second text col
    if not desc_col:
        for c in df.columns:
            if c != id_col and classify_column(c) in ("desc", "other"):
                if not is_price_column(df[c], min_hits=5) and not _is_finish_state_series(df[c]):
                    desc_col = c
                    break
    if not desc_col and id_col:
        # Name-only sheets: same column is both part and description
        desc_col = id_col

    species_cols = layout.species_cols
    if not species_cols:
        return pd.DataFrame()

    # price source columns (wholesale sibling when markup formulas sit on headers)
    price_src = {c: wholesale_map.get(c, c) for c in species_cols}

    # Skip estimated-finished twin columns when an unfinished block exists
    # (Interior Hardwoods: Oak / Oak (2) where (2) is estimated finished cost).
    primary_species = []
    for c in species_cols:
        base = re.sub(r"\s*\(\d+\)\s*$", "", _norm(c)).strip()
        twin = None
        for c2 in species_cols:
            if c2 != c and re.sub(r"\s*\(\d+\)\s*$", "", _norm(c2)).strip() == base:
                # Prefer column without (2) suffix as unfinished wholesale
                if re.search(r"\(\d+\)$", _norm(c)):
                    twin = c2
                    break
        if twin is not None and re.search(r"\(\d+\)$", _norm(c)):
            continue  # skip estimated twin; keep primary
        primary_species.append(c)
    if primary_species:
        species_cols = primary_species

    for _, row in df.iterrows():
        vals = row.tolist()
        # section header?
        part = _norm(row[id_col]) if id_col and id_col in row.index else ""
        if _is_ditto_part(part):
            part = current_part or ""
        desc = _norm(row[desc_col]) if desc_col and desc_col in row.index else ""
        if _is_ditto_part(desc):
            desc = part
        any_price = any(
            _to_float(row[price_src[c]]) is not None
            for c in species_cols
            if price_src[c] in row.index
        )

        if not any_price:
            if not _is_species_header_row(vals):
                current_collection = _section_collection(vals, current_collection)
            continue

        if not part and not desc:
            continue
        # skip if part looks like a header repeated
        if part and classify_column(part) in ("species", "id", "desc", "dim"):
            continue
        if part and re.fullmatch(
            r"(?i)(?:page\s*#?|item\s*#?|description|size|model\s*#?|part\s*#?)",
            part,
        ):
            continue
        if part and part.lower() not in {"option", "options"}:
            current_part = part

        dims = _combine_dims(row, layout.dim_cols)
        finish_est = None
        if layout.finish_est_col and layout.finish_est_col in row.index:
            finish_est = _to_float(row[layout.finish_est_col])

        for tier_i, col in enumerate(species_cols, start=1):
            src = price_src.get(col, col)
            if src not in row.index:
                continue
            price = _to_float(row[src])
            if price is None:
                continue
            notes_parts = []
            if finish_est is not None:
                notes_parts.append(f"finish_est={finish_est}")
            # "Oak, Brown Maple | Finished" two-row header form
            species_name = _norm(col)
            finish_state = "finished"
            if " | " in species_name:
                left, right = species_name.split(" | ", 1)
                species_name = left.strip()
                rk = right.lower()
                if "unf" in rk:
                    finish_state = "unfinished"
                elif "glaz" in rk:
                    finish_state = "glazed"
                else:
                    finish_state = "finished"
            rows.append(
                {
                    "vendor": vendor or None,
                    "collection": current_collection,
                    "part_number": part or None,
                    # FN Chair etc.: Item # column is the full product name
                    "description": desc or part or None,
                    "dimensions": dims,
                    "option_key": None,
                    "species": species_name,
                    "species_tier": tier_i,
                    "finish_state": finish_state,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": "; ".join(notes_parts) if notes_parts else None,
                }
            )

    return pd.DataFrame(rows)


def unpivot_wide_finish(
    df: pd.DataFrame,
    layout: SheetLayout,
    *,
    default_collection: str = "",
    vendor: str = "",
) -> pd.DataFrame:
    """
    Finished/Unfinished columns — optionally interleaved under species groups.
    Heuristic: pair consecutive Fin/Unf columns; if only finish cols, species unknown.
    """
    rows = []
    current_collection = default_collection or None
    id_col = layout.id_col or _guess_id_from_values(df)
    desc_col = layout.desc_col
    cols = layout.finish_cols or [
        c for c in df.columns if is_price_column(df[c], min_hits=2) and looks_like_finish_header(c)
    ]
    if not cols:
        return pd.DataFrame()

    for _, row in df.iterrows():
        part = _norm(row[id_col]) if id_col and id_col in row.index else ""
        desc = _norm(row[desc_col]) if desc_col and desc_col in row.index else ""
        any_price = any(_to_float(row[c]) is not None for c in cols if c in row.index)
        if not any_price:
            current_collection = _section_collection(row.tolist(), current_collection)
            continue
        if not part and not desc:
            continue
        dims = _combine_dims(row, layout.dim_cols)

        for col in cols:
            price = _to_float(row[col]) if col in row.index else None
            if price is None:
                continue
            k = _norm_key(col)
            if "unf" in k or "unfinished" in k:
                finish_state = "unfinished"
            elif "glaz" in k:
                finish_state = "glazed"
            else:
                finish_state = "finished"
            # species may be encoded in multi-line header above — keep column name
            species = _norm(col)
            rows.append(
                {
                    "vendor": vendor or None,
                    "collection": current_collection,
                    "part_number": part or None,
                    "description": desc or part or None,
                    "dimensions": dims,
                    "option_key": None,
                    "species": species,
                    "species_tier": None,
                    "finish_state": finish_state,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                }
            )

    return pd.DataFrame(rows)


def extract_long_flat(
    df: pd.DataFrame,
    layout: SheetLayout,
    *,
    default_collection: str = "",
    vendor: str = "",
) -> pd.DataFrame:
    rows = []
    current_collection = default_collection or None
    id_col = layout.id_col or _guess_id_from_values(df)
    desc_col = layout.desc_col
    price_col = layout.price_cols[0] if layout.price_cols else None
    if not price_col:
        # single species col used as price
        for c in layout.species_cols:
            if is_price_column(df[c], min_hits=2):
                price_col = c
                break
    if not price_col:
        for c in df.columns:
            if is_price_column(df[c], min_hits=3) and c != id_col and c != desc_col:
                price_col = c
                break
    if not price_col:
        return pd.DataFrame()

    for _, row in df.iterrows():
        part = _norm(row[id_col]) if id_col and id_col in row.index else ""
        desc = _norm(row[desc_col]) if desc_col and desc_col in row.index else ""
        price = _to_float(row[price_col]) if price_col in row.index else None
        if price is None:
            current_collection = _section_collection(row.tolist(), current_collection)
            continue
        if not part and not desc:
            continue
        dims = _combine_dims(row, layout.dim_cols)
        rows.append(
            {
                "vendor": vendor or None,
                "collection": current_collection,
                "part_number": part or None,
                "description": desc or part or None,
                "dimensions": dims,
                "option_key": None,
                "species": None,
                "species_tier": None,
                "finish_state": None,
                "base_price": price,
                "price_basis": "wholesale",
                "unit": None,
                "notes": None,
            }
        )
    return pd.DataFrame(rows)


def wholesale_col_for_species(
    df: pd.DataFrame,
    layout: "SheetLayout",
    markup: Optional[float],
) -> dict[str, str]:
    """
    Premier-style: species headers sit on marked-up formula columns; true
    wholesale lives in neighboring unlabeled price cols (species ≈ wholesale × markup).
    Returns map species_col → wholesale_col (only when swap is safe).
    """
    out: dict[str, str] = {}
    if not markup or markup < 1.2 or not layout.species_cols:
        return out
    used: set[str] = set()
    for sc in layout.species_cols:
        if sc not in df.columns:
            continue
        best = None
        best_err = 1.0
        for c in df.columns:
            if c == sc or c in used or c in layout.species_cols:
                continue
            if c == layout.id_col or c == layout.desc_col or c in layout.dim_cols:
                continue
            if not is_price_column(df[c], min_hits=2):
                continue
            ratios = []
            for a, b in zip(df[sc].head(40), df[c].head(40)):
                fa, fb = _to_float(a), _to_float(b)
                if fa and fb and fb > 0:
                    ratios.append(fa / fb)
            if len(ratios) < 3:
                continue
            ratios.sort()
            med = ratios[len(ratios) // 2]
            err = abs(med - markup) / markup
            if err < 0.08 and err < best_err:
                best = c
                best_err = err
        if best is not None:
            out[sc] = best
            used.add(best)
    return out


def _clean_long_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Remove info-sheet debris and empty configs."""
    if df.empty:
        return df
    out = df.copy()
    # require a price
    out = out[out["base_price"].notna()]
    # drop absurd micro-prices without a part number (lead-time weeks, etc.)
    has_part = out["part_number"].notna() & (out["part_number"].astype(str).str.strip() != "")
    tiny = out["base_price"] < 20
    out = out[~(tiny & ~has_part)]
    # drop rows where description is clearly instructional
    if "description" in out.columns:
        bad = (
            out["description"]
            .astype(str)
            .str.contains(
                r"(?i)subject to change|purchase order|lead time|please note|table of contents|"
                r"^new (?:january|february|march|april|may|june|july|august|september|october|"
                r"november|december)\b",
                na=False,
            )
        )
        out = out[~bad]
    # junk part numbers from bad headers / section labels
    if "part_number" in out.columns:
        junk_part = (
            out["part_number"]
            .astype(str)
            .str.fullmatch(
                r"(?i)(?:all|none|nan|null|item\s*#?|new|"
                r"new\s+(?:january|february|march|april|may|june|july|august|"
                r"september|october|november|december)(?:\s+\d{4})?)",
                na=False,
            )
        )
        # Always drop pure junk part tokens
        out = out[~junk_part]
    return out.reset_index(drop=True)


@dataclass
class WorkbookImportResult:
    sheets_tried: list[dict]
    long_df: pd.DataFrame
    detected_markup: Optional[float]
    sheet_names: list[str]
    notes: str = ""
    detected_importer: str = ""
    parser_source: str = ""  # "saved" | "guessed"
    # Priced option lines this reader saw in the source. Counted on its own
    # pass so the Drop gate can catch a reader that stopped emitting addons.
    expected_option_lines: int = 0


def tag_import_result(
    result: WorkbookImportResult,
    importer: str,
    *,
    source: str = "guessed",
) -> WorkbookImportResult:
    result.detected_importer = importer
    result.parser_source = source
    return result


# ---------------------------------------------------------------------------
# Compatibility aliases — implementations live in backend/*_import.py
# ---------------------------------------------------------------------------
#
# ``from wide_import import looks_like_*`` and monkeypatches on these names
# keep working. __getattr__ returns the real function so detector signatures
# stay intact for the registry.


def __getattr__(name: str):
    mapping = {
        "looks_like_patio_kraft": ("backend.patio_kraft_import", "looks_like_patio_kraft"),
        "parse_patio_kraft_sheet": ("backend.patio_kraft_import", "parse_patio_kraft_sheet"),
        "import_patio_kraft_workbook": ("backend.patio_kraft_import", "import_patio_kraft_workbook"),
        "looks_like_lamb": ("backend.lamb_import", "looks_like_lamb"),
        "parse_lamb_wholesale_sheet": ("backend.lamb_import", "parse_lamb_wholesale_sheet"),
        "import_lamb_workbook": ("backend.lamb_import", "import_lamb_workbook"),
        "looks_like_windy_acres": ("backend.windy_acres_import", "looks_like_windy_acres"),
        "parse_windy_acres_sheet": ("backend.windy_acres_import", "parse_windy_acres_sheet"),
        "import_windy_acres_workbook": ("backend.windy_acres_import", "import_windy_acres_workbook"),
        "looks_like_hw_chair_markup": ("backend.hw_chair_import", "looks_like_hw_chair_markup"),
        "import_hw_chair_workbook": ("backend.hw_chair_import", "import_hw_chair_workbook"),
        "looks_like_amish_aspen": ("backend.amish_aspen_import", "looks_like_amish_aspen"),
        "import_amish_aspen_workbook": ("backend.amish_aspen_import", "import_amish_aspen_workbook"),
        "looks_like_artisan_chairs": ("backend.artisan_chairs_import", "looks_like_artisan_chairs"),
        "artisan_chairs_option_addons": ("backend.artisan_chairs_import", "artisan_chairs_option_addons"),
        "artisan_chairs_product_rows": ("backend.artisan_chairs_import", "artisan_chairs_product_rows"),
        "count_artisan_option_lines": ("backend.artisan_chairs_import", "count_artisan_option_lines"),
        "count_priced_option_lines": ("backend.artisan_chairs_import", "count_priced_option_lines"),
        "import_artisan_chairs_workbook": ("backend.artisan_chairs_import", "import_artisan_chairs_workbook"),
        "looks_like_hillside_chair": ("backend.hillside_chair_import", "looks_like_hillside_chair"),
        "import_hillside_chair_workbook": ("backend.hillside_chair_import", "import_hillside_chair_workbook"),
        "looks_like_maple_lane": ("backend.maple_lane_import", "looks_like_maple_lane"),
        "import_maple_lane_workbook": ("backend.maple_lane_import", "import_maple_lane_workbook"),
        "looks_like_millers": ("backend.millers_import", "looks_like_millers"),
        "enhance_millers_long_df": ("backend.millers_import", "enhance_millers_long_df"),
        "import_millers_workbook": ("backend.millers_import", "import_millers_workbook"),
        "looks_like_five_star": ("backend.five_star_import", "looks_like_five_star"),
        "apply_five_star_oak_tables": ("backend.five_star_import", "apply_five_star_oak_tables"),
        "import_five_star_workbook": ("backend.five_star_import", "import_five_star_workbook"),
    }
    target = mapping.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(target[0]), target[1])


# ---------------------------------------------------------------------------
# LuxHome / AJ's seating — fabric-grade price columns
# ---------------------------------------------------------------------------

LUX_FABRIC_RE = re.compile(r"(?i)^(standard|premium|ultra\s*leather|genuine\s*leather|leather)\s*$")
LUX_SKU_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/. ]{1,20}$")


def looks_like_luxhome(filename: str = "", sheet_names: Optional[list[str]] = None) -> bool:
    fn = (filename or "").lower().replace("_", " ")
    if "luxhome" in fn or "lux home" in fn or "aj's lux" in fn or "ajs lux" in fn:
        return True
    if "luxhome" in " ".join(str(s).lower() for s in (sheet_names or [])):
        return True
    return False


def parse_luxhome_sheet(
    raw: pd.DataFrame,
    *,
    vendor: str = "",
    default_collection: str = "",
    price_basis: str = "wholesale",
) -> pd.DataFrame:
    """
    Multi-section seating book:
      Standard | Premium | Ultra Leather | Genuine Leather
      10 SC-FA | Serene Chair ... | 602 | 635 | 800 | 916.6
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    current_collection: Optional[str] = default_collection or None
    tier_map: dict[int, str] = {}  # col -> fabric grade

    def _norm_fabric(label: str) -> str:
        k = re.sub(r"\s+", " ", _norm(label)).strip()
        low = k.lower()
        if "ultra" in low:
            return "Ultra Leather"
        if "genuine" in low or (low.startswith("leather") and "ultra" not in low):
            return "Genuine Leather"
        if "premium" in low:
            return "Premium"
        if "standard" in low:
            return "Standard"
        return k

    for i in range(len(raw)):
        # Fabric-tier header row (2+ grade labels, little else)
        grade_cols = []
        for j in range(raw.shape[1]):
            v = raw.iat[i, j]
            if pd.isna(v):
                continue
            t = _norm(v)
            if LUX_FABRIC_RE.match(t):
                grade_cols.append((j, _norm_fabric(t)))
        if len(grade_cols) >= 2:
            tier_map = {j: lab for j, lab in grade_cols}
            continue

        c0 = raw.iat[i, 0] if raw.shape[1] else None
        s0 = _norm(c0) if pd.notna(c0) else ""

        # Collection titles often in col 0 or 2
        for j in range(min(3, raw.shape[1])):
            v = raw.iat[i, j]
            if pd.isna(v):
                continue
            t = _norm(v)
            if re.search(r"(?i)\bcollection\b", t) and len(t) <= 80 and "\n" not in str(v):
                current_collection = t
                break

        if not s0 or not LUX_SKU_RE.match(s0):
            continue
        if re.search(r"(?i)wholesale|warranty|please note|luxhome seating", s0):
            continue

        desc = ""
        if raw.shape[1] > 1 and pd.notna(raw.iat[i, 1]):
            desc = _norm(raw.iat[i, 1])
        if not desc or len(desc) < 2:
            continue

        if not tier_map:
            # invent from numeric cols 2+
            for j in range(2, min(raw.shape[1], 8)):
                if _to_float(raw.iat[i, j]) is not None:
                    tier_map[j] = f"Tier{j}"

        for tier_i, (j, label) in enumerate(sorted(tier_map.items()), start=1):
            if j >= raw.shape[1]:
                continue
            price = _to_float(raw.iat[i, j])
            if price is None:
                continue
            # skip yardage/sq.ft style tiny junk already filtered by _to_float floor
            rows.append(
                {
                    "vendor": vendor or None,
                    "collection": current_collection,
                    "part_number": s0,
                    "description": desc,
                    "dimensions": None,
                    "option_key": None,
                    "species": label if not label.startswith("Tier") else None,
                    "species_tier": tier_i,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": price_basis,
                    "unit": None,
                    "notes": None,
                }
            )

    return _clean_long_rows(pd.DataFrame(rows))


def import_luxhome_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or "LuxHome"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    # Prefer plain Wholesale over MARKUP (markup sheet may already be retailized)
    wholesale = next((n for n in names if str(n).strip().lower() == "wholesale"), None)
    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]
    elif wholesale:
        targets = [wholesale]
    else:
        targets = [
            n for n in names if not re.search(r"(?i)markup|mark\s*up|instruction", str(n))
        ] or list(names)

    for name in names:
        if name not in targets:
            tried.append(
                {
                    "sheet": name,
                    "layout": "skip",
                    "rows": 0,
                    "note": "LuxHome: prefer Wholesale sheet",
                }
            )
            continue
        try:
            from backend.workbook_sheets import read_sheet

            raw = read_sheet(data, name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue

        long = parse_luxhome_sheet(
            raw,
            vendor=vendor_name,
            default_collection=default_collection,
            price_basis="wholesale",
        )
        n = len(long) if long is not None and not long.empty else 0
        tried.append(
            {
                "sheet": name,
                "layout": "luxhome_fabric_grades",
                "rows": n,
                "note": "Standard/Premium/Ultra/Genuine leather tiers",
                "species_cols": sorted(
                    {str(s) for s in (long["species"].dropna().unique().tolist() if n else [])}
                ),
                "id_col": "model",
                "desc_col": "description",
            }
        )
        if n > 0:
            frames.append(long)

    out = (
        pd.concat(frames, ignore_index=True)
        if frames
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
        )
    )
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name

    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}LuxHome fabric-grade · {len(out)} rows",
    )


def import_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
    preferred_parser: str = "",
    force_layout_guess: bool = False,
) -> WorkbookImportResult:
    """
    Read all product sheets from an Excel workbook, unpivot wide matrices,
    return long-form DataFrame ready for master insert.

    If this builder already has a locked named parser, try that first.
    Zero rows falls through to the filename/sheet guesser.
    """
    names = list_excel_sheets(data)
    common = {
        "vendor": vendor,
        "default_collection": default_collection,
        "sheet_filter": sheet_filter,
        "filename": filename,
    }

    from backend.builder_parsers import identify_reader, run_named_parser
    from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

    if not force_layout_guess:
        vend, chosen, source = identify_reader(
            filename,
            sheet_names=names,
            data=data,
            vendor=vendor,
            preferred_parser=preferred_parser,
        )
        if vend:
            common["vendor"] = vend
        if chosen and chosen not in DEFAULT_READER_REGISTRY.generic_ids:
            locked = run_named_parser(chosen, data, **common)
            if locked is not None and not locked.long_df.empty:
                tagged = tag_import_result(locked, chosen, source=source or "saved")
                from backend.book_options import merge_book_options

                return merge_book_options(tagged, data, vendor=common.get("vendor") or vendor)

        detected_vendor, detected_id = DEFAULT_READER_REGISTRY.detect(
            filename, sheet_names=names, data=data
        )
        if detected_id:
            detected = DEFAULT_READER_REGISTRY.run(
                detected_id,
                data,
                vendor=common.get("vendor") or detected_vendor,
                default_collection=default_collection,
                sheet_filter=sheet_filter,
                filename=filename,
            )
            if detected is not None and not detected.long_df.empty:
                tagged = tag_import_result(detected, detected_id)
                from backend.book_options import merge_book_options

                return merge_book_options(
                    tagged, data, vendor=common.get("vendor") or detected_vendor or vendor
                )

    from backend.workbook_sheets import read_all_sheets

    sheet_views = {v.name: v for v in read_all_sheets(data)}
    markup = detect_markup_from_workbook(data, names)
    frames = []
    tried = []

    # Prefer Wholesale when both Retail and Wholesale product sheets exist.
    # Builder "Retail" already includes their markup — FAF multiplies wholesale again.
    retail_sheets = {n for n in names if re.search(r"(?i)\bretail\b", str(n).strip())}
    wholesale_sheets = {n for n in names if re.search(r"(?i)\bwholesale\b", str(n).strip())}
    skip_retail = bool(retail_sheets and wholesale_sheets and sheet_filter is None)

    # Prefer plain price list over "… MARKUP" / "with Markup" twins
    markup_dup_sheets = {
        n
        for n in names
        if re.search(r"(?i)\bmark\s*-?\s*up\b", str(n)) and not _is_markup_control_sheet(str(n))
    }
    plain_price_sheets = {
        n
        for n in names
        if re.search(r"(?i)price\s*list|pricelist", str(n))
        and not re.search(r"(?i)mark\s*-?\s*up", str(n))
    }
    skip_markup_dup = bool(markup_dup_sheets and plain_price_sheets and sheet_filter is None)

    for name in names:
        if sheet_filter is not None and name not in sheet_filter:
            continue
        view = sheet_views.get(name)
        if skip_retail and name in retail_sheets:
            tried.append(
                {
                    "sheet": name,
                    "layout": "viewed_retail",
                    "rows": 0,
                    "note": "viewed · not imported (wholesale sheet present)",
                }
            )
            continue
        if skip_markup_dup and name in markup_dup_sheets:
            tried.append(
                {
                    "sheet": name,
                    "layout": "viewed_markup_twin",
                    "rows": 0,
                    "note": "viewed · not imported (plain price list present)",
                }
            )
            continue
        if view is not None and view.role in {"cover", "markup", "empty", "error"}:
            tried.append(
                {
                    "sheet": name,
                    "layout": f"viewed_{view.role}",
                    "rows": 0,
                    "note": view.note or f"viewed · {view.role} · {view.n_rows}×{view.n_cols}",
                }
            )
            continue
        if view is not None and view.role == "options" and view.raw is not None:
            from backend.book_options import extract_from_frame

            opt_rows, _woods = extract_from_frame(view.raw, vendor=vendor or "")
            long_opt = pd.DataFrame(opt_rows)
            tried.append(
                {
                    "sheet": name,
                    "layout": "viewed_options",
                    "rows": 0 if long_opt.empty else len(long_opt),
                    "note": f"viewed · options · {0 if long_opt.empty else len(long_opt)} addons",
                }
            )
            if not long_opt.empty:
                frames.append(long_opt)
            continue
        try:
            df = (
                dataframe_from_raw(view.raw)
                if view is not None and view.raw is not None
                else dataframe_from_sheet(data, name)
            )
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        if df.empty:
            tried.append({"sheet": name, "layout": "empty", "rows": 0, "note": ""})
            continue

        layout = classify_sheet(df, name)
        long = pd.DataFrame()
        wmap = (
            wholesale_col_for_species(df, layout, markup) if layout.layout == "wide_species" else {}
        )
        if wmap:
            layout.notes = (layout.notes or "") + f" | wholesale-under-markup×{markup:g}"
        if layout.layout == "wide_species":
            long = unpivot_wide_species(
                df,
                layout,
                default_collection=default_collection or name,
                vendor=vendor,
                wholesale_map=wmap,
            )
        elif layout.layout == "wide_finish":
            long = unpivot_wide_finish(
                df, layout, default_collection=default_collection or name, vendor=vendor
            )
        elif layout.layout == "long_flat":
            long = extract_long_flat(
                df, layout, default_collection=default_collection or name, vendor=vendor
            )
        elif layout.layout == "skip":
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": layout.notes})
            continue
        else:
            # Conservative fallback: only if we can identify part numbers
            guessed = _guess_id_from_values(df)
            numericish = [c for c in df.columns if is_price_column(df[c], min_hits=4)]
            if guessed and len(numericish) >= 2:
                layout_try = SheetLayout(
                    name,
                    "wide_species",
                    id_col=layout.id_col or guessed,
                    desc_col=layout.desc_col,
                    dim_cols=layout.dim_cols,
                    species_cols=numericish,
                )
                wmap2 = wholesale_col_for_species(df, layout_try, markup)
                long = unpivot_wide_species(
                    df,
                    layout_try,
                    default_collection=default_collection or name,
                    vendor=vendor,
                    wholesale_map=wmap2,
                )
            elif guessed and len(numericish) == 1:
                layout_try = SheetLayout(
                    name,
                    "long_flat",
                    id_col=layout.id_col or guessed,
                    desc_col=layout.desc_col,
                    price_cols=numericish,
                )
                long = extract_long_flat(
                    df, layout_try, default_collection=default_collection or name, vendor=vendor
                )

        # Drop obvious junk rows (tiny prices with no SKU on info pages)
        if long is not None and not long.empty:
            long = _clean_long_rows(long)

        # Multi-block name|price flyers (Amish Aspen, M&M) — synthetic cols or
        # bad wide matrix (dims used as SKU, micro med price, col_N species).
        def _looks_low_quality(frame: pd.DataFrame) -> bool:
            if frame is None or frame.empty:
                return True
            try:
                med = float(frame["base_price"].median())
            except Exception:
                return True
            if med < 30:
                return True
            parts = frame["part_number"].astype(str)
            dim_like = (
                parts.str.match(r"(?i)^\d+(\.\d+)?(\s*[x×]\s*\d+(\.\d+)?)+$").fillna(False).mean()
            )
            if dim_like > 0.3:
                return True
            if "species" in frame.columns:
                sp = frame["species"].astype(str)
                if sp.str.match(r"(?i)^col_\d+$").fillna(False).mean() > 0.5:
                    return True
            return False

        def _has_real_species(frame: pd.DataFrame) -> bool:
            if frame is None or frame.empty or "species" not in frame.columns:
                return False
            sp = frame["species"].dropna().astype(str)
            if sp.empty:
                return False
            hits = sp.apply(
                lambda s: bool(
                    looks_like_species_header(s) or any(t in s.lower() for t in WOOD_TOKENS)
                )
            )
            return float(hits.mean()) > 0.4

        # Only fall back to name|price catalogs when the matrix parse is junk
        # AND we did not already recover real wood-species prices.
        if _looks_low_quality(long) and not _has_real_species(long):
            catalog = extract_multi_name_price_catalog(
                df,
                vendor=vendor,
                default_collection=default_collection or name,
            )
            if (
                catalog is not None
                and not catalog.empty
                and not _looks_low_quality(catalog)
                and len(catalog) >= 8
            ):
                long = catalog
                layout.layout = "multi_name_price"
                layout.notes = (layout.notes or "") + " | multi_name_price catalog"

        n = len(long) if long is not None and not long.empty else 0
        tried.append(
            {
                "sheet": name,
                "layout": layout.layout,
                "rows": n,
                "note": layout.notes,
                "species_cols": layout.species_cols[:8],
                "id_col": layout.id_col,
                "desc_col": layout.desc_col,
            }
        )
        if n > 0:
            # if collection empty, use sheet name
            if "collection" in long.columns:
                long["collection"] = long["collection"].fillna(name)
                long.loc[long["collection"].astype(str).str.strip() == "", "collection"] = name
            from backend.book_options import apply_sheet_base_material

            long = apply_sheet_base_material(long, str(name))
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

    # attach vendor default
    if vendor and not out.empty:
        out["vendor"] = out["vendor"].fillna(vendor)
        out.loc[out["vendor"].isna() | (out["vendor"].astype(str).str.strip() == ""), "vendor"] = (
            vendor
        )

    # Millers ships SKU-only rows — synthesize floor-friendly descriptions
    from backend.millers_import import enhance_millers_long_df, looks_like_millers

    if looks_like_millers(filename) and not out.empty:
        out = enhance_millers_long_df(out)

    note = f"{len(names)} sheets · {len(out)} long rows · markup={markup}"
    if filename:
        note = f"{filename}: " + note

    tagged = tag_import_result(
        WorkbookImportResult(
            sheets_tried=tried,
            long_df=out,
            detected_markup=markup,
            sheet_names=names,
            notes=note,
        ),
        "generic",
    )
    from backend.book_options import merge_book_options

    return merge_book_options(tagged, data, vendor=vendor)
