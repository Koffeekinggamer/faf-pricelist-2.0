"""
Wide species-matrix Excel import → long-form sellable rows.

Builders ship:
  Item # | Description | Dims | Oak/BM | Rustic tier | Cherry tier | Walnut | …

We store:
  one row per (part × species_tier × finish_state) with base_price.
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
    "oak", "maple", "cherry", "walnut", "hickory", "elm", "qswo", "pswo",
    "wormy", "rustic", "birch", "ash", "poplar", "pine", "alder", "beech",
    "mahogany", "sap cherry", "brown maple", "hard maple", "white oak",
    "red oak", "quarter", "1/4 sawn", "rough sawn", "ruff sawn", "barnwood",
    "species", "wood",
)

FINISH_TOKENS = (
    "finished", "unfinished", "glazed", "fin.", "unf.", "fin ", "unf ",
    "finshed",  # common HW typo
)

ID_TOKENS = (
    "item", "part", "sku", "model", "code", "style", "catalog", "stock",
    "item #", "item#", "part #", "part#", "model #", "sku #",
)

DESC_TOKENS = ("description", "descr", "desc.", "name", "product", "title", "item name")

DIM_TOKENS = (
    "dimension", "dims", "size", "w x d x h", "w×d×h", 'h"', 'w"', 'd"',
    "width", "height", "depth", "overall", "wxdxh",
)

SKIP_SHEET_RE = re.compile(
    r"""(?ix)
    ^(markup|mark\s*up|multiplier|multipliers|instructions?|cover|index|index_?|
      settings?|information(\s*sheet)?|customer\s*letter|notes?|toc|
      table\s*of\s*contents|percentage|controls?|options?\s*&\s*portal|
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
    if k in {"item", "item #", "item#", "item number", "item no", "item no.",
             "part", "part #", "part#", "part number", "part no", "sku", "model",
             "model #", "model#", "code", "style", "style #", "catalog #", "stock #",
             "item name", "search all items", "id", "id#", "id #", "item#",
             "item no", "no.", "no", "#"}:
        return True
    # Item# / Model# with optional spaces
    if re.match(r"(?i)^(item|model|part|style|sku|id)\s*#?\s*$", k):
        return True
    if re.match(r"(?i)^#\s*(item|model|part)?$", k):
        return True
    # FVWW-style: long header containing "search all items"
    if "search all items" in k or k.endswith(" items"):
        return True
    return any(k == t or k.startswith(t + " ") or k.endswith(" " + t) for t in ID_TOKENS) and len(k) < 40


def looks_like_desc_header(col: str) -> bool:
    k = _norm_key(col)
    return any(t in k for t in DESC_TOKENS) or k in {"description", "descr.", "desc"}


def looks_like_dim_header(col: str) -> bool:
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
    if looks_like_id_header(col):
        return "id"
    if looks_like_desc_header(col):
        return "desc"
    if looks_like_dim_header(col):
        return "dim"
    if looks_like_species_header(col):
        return "species"
    if looks_like_finish_header(col):
        return "finish"
    if k in {"price", "wholesale", "retail", "cost", "amount", "net", "dealer",
             "whsl. price", "whsl price", "list price", "regular"}:
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
                1 for s in peek
                if re.match(r"^[A-Z0-9][A-Z0-9\-_/]{1,24}$", s, re.I)
                and not MONEY_CELL_RE.match(s)
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
    bio = io.BytesIO(data)
    kwargs = {"sheet_name": sheet_name, "header": None}
    if engine:
        kwargs["engine"] = engine
    try:
        raw = pd.read_excel(bio, **kwargs)
    except Exception:
        bio.seek(0)
        raw = pd.read_excel(bio, sheet_name=sheet_name, header=None)

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
                    if not looks_like_id_header(top) and not looks_like_desc_header(top) and not looks_like_dim_header(top):
                        low = top.lower()
                        woodish = (
                            looks_like_species_header(top)
                            or any(t in low for t in WOOD_TOKENS)
                            or bool(re.search(
                                r"(?i)\b(oak|maple|cherry|walnut|hick(?:ory)?|qswo|qsw?|"
                                r"ch|hm|ro|bsm|rustic)\b",
                                top,
                            ))
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
    bio = io.BytesIO(data)
    try:
        xl = pd.ExcelFile(bio, engine="openpyxl")
    except Exception:
        bio.seek(0)
        try:
            xl = pd.ExcelFile(bio, engine="xlrd")
        except Exception:
            bio.seek(0)
            xl = pd.ExcelFile(bio)
    return list(xl.sheet_names)


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
        "markup", "mark-up", "mark up", "multiplier", "multipliers", "mark-up page",
    }


def detect_markup_from_workbook(data: bytes, sheet_names: list[str]) -> Optional[float]:
    """Scan Markup sheets for a plausible multiplier (0.5–20 or percent 50–2000)."""
    for name in sheet_names:
        if not _is_markup_control_sheet(str(name)):
            continue
        try:
            bio = io.BytesIO(data)
            df = pd.read_excel(bio, sheet_name=name, header=None)
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
            if looks_like_species_header(c) or sum(1 for t in WOOD_TOKENS if t in _norm_key(c)) >= 1:
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
            c for c in df.columns
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
                c for c in df.columns
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
            1 for s in sample
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
            1 for s in sample
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
            if name and price is None and not any(
                _to_float(row[p]) is not None for _, p in pairs if p in row.index
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
            rows.append({
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
            })
    return _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()


def _combine_dims(row: pd.Series, dim_cols: list[str]) -> Optional[str]:
    if not dim_cols:
        return None
    parts = []
    for c in dim_cols:
        v = _norm(row.get(c))
        if v:
            # label short dim cols
            label = _norm(c)
            if label.lower() in {'h"', 'w"', 'd"', "h", "w", "d"}:
                parts.append(f"{label}{v}" if v[-1] in '"\'' else f"{label}:{v}")
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
    moneys = [
        v for v in texts
        if (_to_float(v) is not None and float(_to_float(v)) > 1)
    ]
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
        r"plant\s*stand|pedestal|bookshelf|shaker|mission",
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
    id_col = layout.id_col or _guess_id_from_values(df) or _guess_product_name_col(df)
    desc_col = layout.desc_col
    wholesale_map = wholesale_map or {}
    # if no desc, sometimes description is second text col
    if not desc_col:
        for c in df.columns:
            if c != id_col and classify_column(c) in ("desc", "other"):
                if not is_price_column(df[c], min_hits=5):
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
        desc = _norm(row[desc_col]) if desc_col and desc_col in row.index else ""
        any_price = any(
            _to_float(row[price_src[c]]) is not None
            for c in species_cols
            if price_src[c] in row.index
        )

        if not any_price:
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
            rows.append({
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
            })

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
            rows.append({
                "vendor": vendor or None,
                "collection": current_collection,
                "part_number": part or None,
                "description": desc or None,
                "dimensions": dims,
                "option_key": None,
                "species": species,
                "species_tier": None,
                "finish_state": finish_state,
                "base_price": price,
                "price_basis": "wholesale",
                "unit": None,
                "notes": None,
            })

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
        rows.append({
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
        })
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
        bad = out["description"].astype(str).str.contains(
            r"(?i)subject to change|purchase order|lead time|please note|table of contents|"
            r"^new (?:january|february|march|april|may|june|july|august|september|october|"
            r"november|december)\b",
            na=False,
        )
        out = out[~bad]
    # junk part numbers from bad headers / section labels
    if "part_number" in out.columns:
        junk_part = out["part_number"].astype(str).str.fullmatch(
            r"(?i)(?:all|none|nan|null|item\s*#?|new|"
            r"new\s+(?:january|february|march|april|may|june|july|august|"
            r"september|october|november|december)(?:\s+\d{4})?)",
            na=False,
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


# ---------------------------------------------------------------------------
# Patio Kraft — outdoor poly color-tier sections (not wood species)
# ---------------------------------------------------------------------------
#
# Builders ship:
#   [Collection title]
#   [Standard Colors | Bright Colors | Woodgrain Colors]   ← row above header
#   Item # | Description | … | $ | $ | $
#   VECG   | Chair Glider | … | …
#
# Sections repeat down the sheet (Vienna, London, Accessories, …).
# We store long-form: one row per (SKU × color tier). Prefer Wholesale sheet.

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
        wh = next(s for s in names if str(s).strip().lower() == "wholesale")
        bio = io.BytesIO(data)
        raw = pd.read_excel(bio, sheet_name=wh, header=None)
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
                current_collection = re.sub(
                    r",?\s*continued\s*$", "", s0, flags=re.I
                ).strip() or s0
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
        for tier_i, (j, label, price) in enumerate(filled, start=1):
            if single_price or label.lower() == "price":
                species = None
                stier = None
            else:
                species = label
                stier = tier_i
            rows.append({
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
            })

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
            tried.append({
                "sheet": name,
                "layout": "skip",
                "rows": 0,
                "note": "Patio Kraft: prefer Wholesale; skipped",
            })
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue

        basis = "wholesale" if str(name).strip().lower() == "wholesale" else (
            "retail" if str(name).strip().lower() == "retail" else "wholesale"
        )
        long = parse_patio_kraft_sheet(
            raw,
            vendor=vendor_name,
            default_collection=default_collection,
            price_basis=basis,
        )
        n = len(long) if long is not None and not long.empty else 0
        tried.append({
            "sheet": name,
            "layout": "patio_kraft_color_tiers",
            "rows": n,
            "note": f"price_basis={basis}; multi-section Item# + color tiers",
            "species_cols": sorted({
                str(s) for s in (long["species"].dropna().unique().tolist() if n else [])
            })[:8],
            "id_col": "Item #",
            "desc_col": "Description",
        })
        if n > 0:
            if "collection" in long.columns:
                long["collection"] = long["collection"].fillna(default_collection or name)
            frames.append(long)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ])

    if vendor_name and not out.empty:
        out["vendor"] = vendor_name

    note = (
        f"{filename + ': ' if filename else ''}"
        f"Patio Kraft color-tier import · {len(out)} long rows · "
        f"sheets={ [t['sheet'] for t in tried if t.get('rows')] }"
    )
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,  # Retail "1.2" cell is not FAF mult; wholesale bases only
        sheet_names=names,
        notes=note,
    )


# ---------------------------------------------------------------------------
# LAMB Woodworking — Wholesale matrix (prefer Wholesale over Retail sheets)
# Layout: Item No. | Size | Description | Unfinished×4 wood groups |
#         Finishing cost | Finished×4 wood groups
# ---------------------------------------------------------------------------

LAMB_SKU_RE = re.compile(r"(?i)^LA-[A-Z0-9][A-Z0-9\-_/.]*$")
LAMB_SKIP_SECTIONS = re.compile(
    r"(?i)^(furniture\s*options|power\s*outlets|hardware|lighting|materials|"
    r"lift\s*tops|glass\s*options|quick\s*ship\s*items|notes?|options)$"
)


def looks_like_lamb(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    fn = (filename or "").lower().replace("_", " ")
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
        rows_out.append({
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
        })

    for i in range(len(work)):
        vals = [work.iat[i, j] if j < n_cols else None for j in range(n_cols)]
        v0 = _norm(vals[0]) if vals else ""

        hdr = _lamb_wood_header_from_row(vals)
        if hdr:
            unf_cols = hdr["unf"]
            fin_cols = hdr["fin"]
            finish_cost_col = hdr["finish_cost_col"]
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
                1 for j in range(min(8, n_cols), n_cols)
                if _to_price(vals[j]) is not None
            )
            if prices_here == 0 and (
                v0.isupper() or re.match(r"^[A-Z][A-Za-z0-9 &/\-]+$", v0)
            ):
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
            _to_price(vals[j]) if j < n_cols else None
            for j in (n_cols - 3, n_cols - 2, n_cols - 1)
        ]
        # Quick-ship / oak-only: unfinished | finishing cost | finished in last 3 cols
        # when full wood matrix is not populated on this row
        if matrix_prices <= 1 and last3[0] is not None and last3[2] is not None:
            _emit(part, desc, dims, "unfinished", last3[0], species=None, tier=None)
            _emit(part, desc, dims, "finished", last3[2], species=None, tier=None)
            continue

        if not unf_cols and not fin_cols:
            # Fall back to last3 if no matrix header seen yet
            if last3[0] is not None and last3[2] is not None:
                _emit(part, desc, dims, "unfinished", last3[0])
                _emit(part, desc, dims, "finished", last3[2])
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

    return _clean_long_rows(pd.DataFrame(final))


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

    wholesale = next(
        (n for n in names if str(n).strip().lower() == "wholesale"), None
    )
    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]
    elif wholesale:
        targets = [wholesale]
    else:
        # No wholesale tab — fall back to non-retail sheets only
        targets = [
            n for n in names if not re.search(r"(?i)\bretail\b", str(n))
        ] or list(names)

    for name in names:
        if name not in targets:
            tried.append({
                "sheet": name,
                "layout": "skip",
                "rows": 0,
                "note": "LAMB: prefer Wholesale; skipped retail/other",
            })
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
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
        tried.append({
            "sheet": name,
            "layout": "lamb_wholesale_matrix",
            "rows": n,
            "note": "Item No + wood groups unfinished/finished",
            "species_cols": sorted({
                str(s) for s in (
                    long["species"].dropna().unique().tolist() if n else []
                )
            })[:8],
            "id_col": "Item No.",
            "desc_col": "Description",
        })
        if n > 0:
            frames.append(long)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ])

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


# ---------------------------------------------------------------------------
# LuxHome / AJ's seating — fabric-grade price columns
# ---------------------------------------------------------------------------

LUX_FABRIC_RE = re.compile(
    r"(?i)^(standard|premium|ultra\s*leather|genuine\s*leather|leather)\s*$"
)
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
            rows.append({
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
            })

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
    wholesale = next(
        (n for n in names if str(n).strip().lower() == "wholesale"), None
    )
    if sheet_filter is not None:
        targets = [n for n in names if n in sheet_filter]
    elif wholesale:
        targets = [wholesale]
    else:
        targets = [
            n for n in names
            if not re.search(r"(?i)markup|mark\s*up|instruction", str(n))
        ] or list(names)

    for name in names:
        if name not in targets:
            tried.append({
                "sheet": name, "layout": "skip", "rows": 0,
                "note": "LuxHome: prefer Wholesale sheet",
            })
            continue
        try:
            bio = io.BytesIO(data)
            # .xls may need xlrd
            try:
                raw = pd.read_excel(bio, sheet_name=name, header=None, engine="xlrd")
            except Exception:
                bio.seek(0)
                raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue

        long = parse_luxhome_sheet(
            raw, vendor=vendor_name, default_collection=default_collection,
            price_basis="wholesale",
        )
        n = len(long) if long is not None and not long.empty else 0
        tried.append({
            "sheet": name,
            "layout": "luxhome_fabric_grades",
            "rows": n,
            "note": "Standard/Premium/Ultra/Genuine leather tiers",
            "species_cols": sorted({
                str(s) for s in (long["species"].dropna().unique().tolist() if n else [])
            }),
            "id_col": "model",
            "desc_col": "description",
        })
        if n > 0:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=[
        "vendor", "collection", "part_number", "description", "dimensions",
        "option_key", "species", "species_tier", "finish_state", "base_price",
        "price_basis", "unit", "notes",
    ])
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name

    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}LuxHome fabric-grade · {len(out)} rows",
    )


# ---------------------------------------------------------------------------
# Windy Acres — multi-section wood groups above FINISHED/UNFINISHED pairs
# ---------------------------------------------------------------------------

def looks_like_windy_acres(filename: str = "") -> bool:
    fn = (filename or "").lower().replace("_", " ")
    return "windy" in fn and "acres" in fn


_WINDY_WOOD_HINT = re.compile(
    r"(?i)oak|maple|cherry|walnut|hickory|elm|ash|qswo|qsw|wormy|rustic|sap\s*cherry"
)


def _windy_species_label(cell) -> str:
    """Turn multi-line wood group cell into slash-separated species label."""
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    t = str(cell).replace("\r", "\n")
    # Reject section titles / non-wood cells
    flat = re.sub(r"\s+", " ", t).strip()
    if re.search(r"(?i)collection|dimension|item\s*#|finished|unfinished|two\s*tone", flat):
        if not _WINDY_WOOD_HINT.search(flat):
            return ""
    if not _WINDY_WOOD_HINT.search(t):
        return ""
    parts = []
    for line in t.split("\n"):
        line = re.sub(r"\s+", " ", line).strip(" \t-•")
        if not line or not _WINDY_WOOD_HINT.search(line):
            continue
        line = re.sub(r"(?i)\bru\.?\s*qswo\b", "Rustic QSWO", line)
        line = re.sub(r"(?i)\br\.?\s*hickory\b", "Rustic Hickory", line)
        line = re.sub(r"(?i)\br\.?\s*wal(?:nut)?\b", "Rustic Walnut", line)
        line = re.sub(r"(?i)cherry-hickory", "Cherry / Hickory", line)
        parts.append(line)
    seen = set()
    out = []
    for p in parts:
        k = p.lower()
        if k not in seen:
            seen.add(k)
            out.append(p)
    return " / ".join(out)


def parse_windy_acres_sheet(raw: pd.DataFrame, *, vendor: str = "Windy Acres Furniture") -> pd.DataFrame:
    """
    Walk Windy Master-style sheet:
      [collection title]
      DIMENSIONS | woodgroup1 | woodgroup2 | …
      ITEM# | H | W | D | FINISHED | UNFINISHED | FINISHED | UNFINISHED | …
      630-Coffee-TD | 19 | 40 | 20 | 267 | 227 | …
    """
    if raw is None or raw.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    current_collection: Optional[str] = None
    # active map: list of (col_idx, species_label, finish_state)
    price_cols: list[tuple[int, str, str]] = []
    dim_cols: dict[str, int] = {}  # h/w/d -> col

    def _is_item_header(s: str) -> bool:
        return bool(re.match(r"(?i)^item\s*#?$", s.strip()))

    def _is_finish(s: str) -> bool:
        k = s.strip().lower()
        return k in {"finished", "finshed", "unfinished", "unf"}

    for i in range(len(raw)):
        c0 = raw.iat[i, 0] if raw.shape[1] else None
        s0 = _norm(c0) if pd.notna(c0) else ""

        # Collection / section titles (short, no prices)
        if s0 and not _is_item_header(s0) and len(s0) < 80:
            nums = [
                _to_float(raw.iat[i, j])
                for j in range(1, min(raw.shape[1], 12))
            ]
            if not any(n is not None for n in nums):
                if re.search(
                    r"(?i)collection|bedroom|occasionals|with one drawer|without drawers|solid color",
                    s0,
                ) or (s0[0].isupper() and " " in s0 and len(s0) > 8):
                    if not re.search(r"(?i)dimension|markup|instruction|read first", s0):
                        current_collection = s0

        # ITEM# header → bind wood labels from row above + finish from this row
        if s0 and _is_item_header(s0):
            price_cols = []
            dim_cols = {}
            wood_row = raw.iloc[i - 1] if i > 0 else None
            # sometimes wood is two rows above (DIMENSIONS row)
            wood_row2 = raw.iloc[i - 2] if i > 1 else None

            # detect H/W/D columns on header row
            for j in range(1, min(raw.shape[1], 6)):
                lab = _norm(raw.iat[i, j]).lower().replace('"', "")
                if lab in {"h", "h'", "hb h"} or lab.startswith("h"):
                    if "w" not in lab and "d" not in lab:
                        dim_cols["h"] = j
                elif lab in {"w", "w'"} or (lab.startswith("w") and "hb" not in lab):
                    dim_cols["w"] = j
                elif lab in {"d", "d'"} or lab.startswith("d"):
                    dim_cols["d"] = j

            # Build species labels per finish column
            # Prefer wood labels from DIMENSIONS row (i-1 or i-2)
            wood_labels_by_col: dict[int, str] = {}
            for src in (wood_row2, wood_row):
                if src is None:
                    continue
                for j in range(raw.shape[1]):
                    lab = _windy_species_label(src.iloc[j] if j < len(src) else None)
                    if lab and not re.match(r"(?i)^dimension", lab):
                        wood_labels_by_col[j] = lab

            # Walk finish columns on ITEM# row; carry last wood label from left
            carry_species = ""
            for j in range(1, raw.shape[1]):
                cell = _norm(raw.iat[i, j])
                if not cell:
                    # empty header but might still be price col under a wood group
                    continue
                if _is_finish(cell):
                    # find wood label: this col or nearest left wood-labeled col
                    sp = wood_labels_by_col.get(j) or carry_species
                    if not sp:
                        # look left for wood label on wood rows
                        for k in range(j, -1, -1):
                            if k in wood_labels_by_col:
                                sp = wood_labels_by_col[k]
                                break
                    if not sp or not _WINDY_WOOD_HINT.search(sp):
                        sp = f"Wood Tier {len(price_cols) // 2 + 1}"
                    else:
                        carry_species = sp
                    fin = "unfinished" if "unf" in cell.lower() else "finished"
                    price_cols.append((j, sp, fin))
                elif j in wood_labels_by_col and _WINDY_WOOD_HINT.search(
                    wood_labels_by_col[j]
                ):
                    carry_species = wood_labels_by_col[j]
            # Bedroom-style: wood names sit on ITEM# row as price headers (no FIN/UNF)
            if not price_cols:
                for j in range(1, raw.shape[1]):
                    lab = _windy_species_label(raw.iat[i, j])
                    if lab:
                        price_cols.append((j, lab, "finished"))
            continue

        # Data rows
        if not price_cols or not s0:
            continue
        if _is_item_header(s0) or re.match(r"(?i)^dimension", s0):
            continue
        # skip pure section rows without prices
        any_price = any(
            _to_float(raw.iat[i, j]) is not None for j, _, _ in price_cols if j < raw.shape[1]
        )
        if not any_price:
            continue

        # description: humanize part if it has hyphens
        part = s0
        desc = part
        # 630-Coffee-TD → Coffee TD style
        if "-" in part:
            bits = part.split("-", 1)
            if len(bits) == 2 and re.match(r"^[A-Za-z]", bits[1]):
                desc = bits[1].replace("-", " ")

        dims_parts = []
        for key in ("h", "w", "d"):
            if key in dim_cols:
                v = raw.iat[i, dim_cols[key]]
                if pd.notna(v):
                    dims_parts.append(f'{key.upper()}"{v}')
        dims = " × ".join(dims_parts) if dims_parts else None

        for tier_i, (j, species, finish) in enumerate(price_cols, start=1):
            if j >= raw.shape[1]:
                continue
            price = _to_float(raw.iat[i, j])
            if price is None:
                continue
            rows.append({
                "vendor": vendor,
                "collection": current_collection,
                "part_number": part,
                "description": desc,
                "dimensions": dims,
                "option_key": None,
                "species": species,
                "species_tier": (tier_i + 1) // 2,
                "finish_state": finish,
                "base_price": price,
                "price_basis": "wholesale",
                "unit": None,
                "notes": None,
            })

    return _clean_long_rows(pd.DataFrame(rows))


def import_windy_acres_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    names = list_excel_sheets(data)
    vendor_name = (vendor or "").strip() or "Windy Acres Furniture"
    frames = []
    tried = []
    targets = sheet_filter if sheet_filter is not None else [
        n for n in names
        if not re.search(r"(?i)instruction|mark\s*up|read\s*first", str(n))
    ]
    # Prefer Master
    if sheet_filter is None and any(str(n).lower() == "master" for n in names):
        targets = [n for n in names if str(n).lower() == "master"]

    for name in names:
        if name not in targets:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "non-product"})
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        long = parse_windy_acres_sheet(raw, vendor=vendor_name)
        n = len(long) if long is not None and not long.empty else 0
        tried.append({
            "sheet": name,
            "layout": "windy_acres_wood_groups",
            "rows": n,
            "note": "wood groups above FINISHED/UNFINISHED",
        })
        if n > 0:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out if not out.empty else pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ]),
        detected_markup=detect_markup_from_workbook(data, names),
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Windy Acres wood-group import · {len(out) if not out.empty else 0} rows",
    )


# ---------------------------------------------------------------------------
# Millers Woodshop — section titles + SKU-only rows → better descriptions
# ---------------------------------------------------------------------------

def looks_like_millers(filename: str = "") -> bool:
    fn = (filename or "").lower().replace("_", " ")
    return "miller" in fn or re.search(r"\bmws\b", fn) is not None


def enhance_millers_long_df(df: pd.DataFrame) -> pd.DataFrame:
    """Fill descriptions from collection/section when builder only ships SKUs."""
    if df is None or df.empty:
        return df
    out = df.copy()
    for i, row in out.iterrows():
        part = _norm(row.get("part_number"))
        desc = _norm(row.get("description"))
        coll = _norm(row.get("collection"))
        if not part:
            continue
        # description missing or same as part
        if not desc or desc == part:
            if re.match(r"^\d+(\.\d+)?\s*x\s*\d+", part, re.I):
                # bookcase-style dimension SKU
                label = coll or "Bookcase"
                # strip Mult- prefix noise
                label = re.sub(r"(?i)^mult-?", "", label).strip() or "Bookcase"
                out.at[i, "description"] = f"{label} {part}"
            elif coll:
                coll_clean = re.sub(r"(?i)^mult-?", "", coll).strip()
                out.at[i, "description"] = f"{coll_clean} {part}".strip()
            else:
                out.at[i, "description"] = part
    return out


# ---------------------------------------------------------------------------
# HW Chair — "Markup Calculator" sheet: product name × paired species columns
# ---------------------------------------------------------------------------

def looks_like_hw_chair_markup(
    filename: str = "",
    sheet_names: Optional[list[str]] = None,
) -> bool:
    fn = (filename or "").lower().replace("_", " ")
    # Path or download folder often contains HW_Chair
    if re.search(r"\bhw\s*chair\b", fn) or "hw_chair" in (filename or "").lower():
        return True
    names = sheet_names or []
    # Single-sheet markup calculator workbooks (HW Chair Viztech export)
    if names and all(re.search(r"(?i)markup\s*calculator", str(n)) for n in names):
        return True
    return False


def import_hw_chair_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """
    HW Chair 2026 Markup Calculator layout:
      row0: calculator chrome
      row1: species labels (often duplicated pairs: unf/fin or cost/markup)
      row2: letter labels C,D,E… (skip)
      row3+: product name | price pairs per species
    Seat options (Fabric/Leather) are ignored — not wood species.
    """
    names = list_excel_sheets(data)
    vendor_name = vendor or "HW Chair"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    targets = sheet_filter if sheet_filter is not None else list(names)
    for name in names:
        if name not in targets:
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "filtered"})
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
        if raw.empty or raw.shape[1] < 3:
            tried.append({"sheet": name, "layout": "empty", "rows": 0, "note": ""})
            continue

        # Find species header row (most wood tokens)
        best_i, best_woods = 0, -1
        for i in range(min(8, len(raw))):
            cells = [_norm(v) for v in raw.iloc[i].tolist()]
            woods = sum(1 for c in cells if c and looks_like_species_header(c))
            if woods > best_woods:
                best_woods = woods
                best_i = i
        if best_woods < 2:
            tried.append({
                "sheet": name, "layout": "unknown", "rows": 0,
                "note": f"no species header (best_woods={best_woods})",
            })
            continue

        species_row = [_norm(v) for v in raw.iloc[best_i].tolist()]
        # Map col → species; collapse duplicate adjacent pairs to one species
        col_species: list[tuple[int, str]] = []
        seen_pair: set[str] = set()
        j = 1  # col 0 is product name
        while j < len(species_row):
            lab = species_row[j]
            if not lab or not looks_like_species_header(lab):
                # seat options / non-wood
                j += 1
                continue
            # skip fabric/leather seat adders
            if re.search(r"(?i)fabric|leather|seat|premium", lab):
                j += 1
                continue
            # take this column as price source; skip immediate duplicate label next col
            key = lab.lower()
            if key not in seen_pair:
                col_species.append((j, lab))
                seen_pair.add(key)
            # if next col has same species label, skip it (paired unf/fin or cost/copy)
            if j + 1 < len(species_row) and _norm_key(species_row[j + 1]) == key:
                j += 2
            else:
                j += 1

        body_start = best_i + 1
        # skip letter-label row (C, D, E…)
        if body_start < len(raw):
            peek = [_norm(v) for v in raw.iloc[body_start].tolist()[1:8] if _norm(v)]
            if peek and all(re.fullmatch(r"[A-Z]", p) for p in peek[:4]):
                body_start += 1

        rows = []
        current_collection: Optional[str] = default_collection or None
        for i in range(body_start, len(raw)):
            name_cell = _norm(raw.iat[i, 0]) if raw.shape[1] else ""
            if not name_cell:
                continue
            # section banner: text only, no prices
            prices_here = [
                _to_float(raw.iat[i, j])
                for j, _sp in col_species
                if j < raw.shape[1]
            ]
            if not any(p is not None for p in prices_here):
                if 3 <= len(name_cell) <= 60 and not re.match(
                    r"(?i)markup|formula|enter percent", name_cell
                ):
                    current_collection = name_cell
                continue
            if re.fullmatch(r"(?i)page\s*#?|item\s*#?|description", name_cell):
                continue
            for tier_i, (j, sp) in enumerate(col_species, start=1):
                if j >= raw.shape[1]:
                    continue
                price = _to_float(raw.iat[i, j])
                if price is None:
                    # try pair sibling
                    if j + 1 < raw.shape[1]:
                        price = _to_float(raw.iat[i, j + 1])
                if price is None or price < 5:
                    continue
                rows.append({
                    "vendor": vendor_name,
                    "collection": current_collection,
                    "part_number": name_cell,
                    "description": name_cell,
                    "dimensions": None,
                    "option_key": None,
                    "species": sp,
                    "species_tier": tier_i,
                    "finish_state": "unfinished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                })

        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        n = len(long)
        tried.append({
            "sheet": name,
            "layout": "hw_chair_markup",
            "rows": n,
            "note": f"species_cols={len(col_species)} header_i={best_i}",
            "id_col": "col_0",
            "desc_col": "col_0",
        })
        if n > 0:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out if not out.empty else pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ]),
        detected_markup=detect_markup_from_workbook(data, names),
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}HW Chair markup calculator · {len(out) if not out.empty else 0} rows",
    )


# ---------------------------------------------------------------------------
# Thin-catalog specialists: Amish Aspen flyer, Hillside Chair Unf/Fin matrix,
# Maple Lane pet (SKU row + price on next row under species)
# ---------------------------------------------------------------------------

def looks_like_amish_aspen(filename: str = "") -> bool:
    fn = (filename or "").lower().replace("_", " ")
    return "amish aspen" in fn or "aspen and rustic" in fn


def import_amish_aspen_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """3-column flyer: name | price | dims blocks across the sheet."""
    names = list_excel_sheets(data)
    vendor_name = vendor or "Amish Aspen and Rustic"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []
    targets = sheet_filter if sheet_filter is not None else names

    # name-col, price-col pairs observed in sheet (0-indexed)
    pairs = [(0, 3), (5, 7), (9, 10), (1, 2), (1, 4), (6, 9), (7, 9)]

    for name in names:
        if name not in targets:
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").reset_index(drop=True)
        if raw.empty:
            tried.append({"sheet": name, "layout": "empty", "rows": 0, "note": ""})
            continue
        rows = []
        current_collection: Optional[str] = default_collection or None
        seen: set[tuple] = set()
        for i in range(len(raw)):
            for name_c, price_c in pairs:
                if name_c >= raw.shape[1] or price_c >= raw.shape[1]:
                    continue
                nm = _norm(raw.iat[i, name_c])
                price = _to_float(raw.iat[i, price_c])
                if not nm or price is None or price < 20:
                    # section banners
                    if nm and price is None and 3 <= len(nm) <= 50:
                        if re.search(
                            r"(?i)bedroom|table|bed|dining|book|living|white cedar",
                            nm,
                        ):
                            current_collection = nm
                    continue
                if re.search(
                    r"(?i)phone|fax|email|@|subject to|price list|joel martin|"
                    r"hillsboro|walnut tops|d\s*w\s*h|table only|add a sceen",
                    nm,
                ):
                    continue
                if re.fullmatch(r"\d+(\.\d+)?\s*[x×]\s*\d+", nm, re.I):
                    continue
                if len(nm) > 70:
                    continue
                key = (nm.lower(), round(price, 2))
                if key in seen:
                    continue
                seen.add(key)
                # optional dims: col after price
                dims = None
                for dc in (price_c + 1, name_c + 1, 4, 8, 11):
                    if dc < raw.shape[1] and dc != price_c and dc != name_c:
                        d = _norm(raw.iat[i, dc])
                        if d and re.search(r"\d", d) and re.search(r"[x×]", d, re.I):
                            dims = d
                            break
                rows.append({
                    "vendor": vendor_name,
                    "collection": current_collection,
                    "part_number": nm,
                    "description": nm,
                    "dimensions": dims,
                    "option_key": None,
                    "species": None,
                    "species_tier": None,
                    "finish_state": "finished",
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                })
        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        tried.append({
            "sheet": name, "layout": "amish_aspen_flyer",
            "rows": len(long), "note": f"pairs={len(pairs)}",
        })
        if not long.empty:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out if not out.empty else pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ]),
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Amish Aspen flyer · {len(out) if not out.empty else 0} rows",
    )


def looks_like_hillside_chair(filename: str = "", sheet_names: Optional[list[str]] = None) -> bool:
    fn = (filename or "").lower().replace("_", " ")
    if "hillside chair" in fn or "hillside_chair" in (filename or "").lower():
        return True
    names = sheet_names or []
    return bool(names) and names[0].lower() == "master" and any(
        re.fullmatch(r"(?i)sheet\d+", str(n)) for n in names
    ) and len(names) >= 8


def import_hillside_chair_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """Hillside: multi-section Unf/Fin under Oak/Brown Maple/Cherry/Elm/Walnut."""
    names = list_excel_sheets(data)
    vendor_name = vendor or "Hillside Chair"
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []
    # Product sheets only (skip Master index, finishing adders Sheet2)
    product_sheets = [
        n for n in names
        if re.fullmatch(r"(?i)sheet\s*\d+", str(n).replace(" ", ""))
        or re.fullmatch(r"(?i)sheet\d+", str(n))
    ]
    # Sheet1=index, Sheet2=finish adders — start product pages at Sheet3
    product_sheets = [
        n for n in names
        if re.match(r"(?i)^sheet\s*\d+$", str(n).strip())
        and int(re.search(r"\d+", str(n)).group()) >= 3
    ]
    if sheet_filter is not None:
        product_sheets = [n for n in product_sheets if n in sheet_filter]

    for name in names:
        if name not in product_sheets:
            if sheet_filter is None or name not in (sheet_filter or []):
                tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "index/adders"})
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").reset_index(drop=True)
        rows = []
        current_style = default_collection or None
        # species groups: col pairs starting at 2: (unf, fin) per species block
        species_labels: list[str] = []
        col_map: list[tuple[int, str, str]] = []  # col, species, finish

        for i in range(len(raw)):
            c0 = _norm(raw.iat[i, 0]) if raw.shape[1] else ""
            c1 = _norm(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
            # Style header row: "Small Avon: AC364 Side | ..."
            if c0 and re.search(r"(?i)side\s*chair|arm\s*chair|:.*AC\d|:\s*AC", c0 + " " + c1):
                # may be style on col0 with species on same row
                style_m = re.match(r"^([^:]+):", c0)
                if style_m:
                    current_style = style_m.group(1).strip()
                elif ":" in c0:
                    current_style = c0.split(":")[0].strip()
                # rebuild species map from this row
                species_labels = []
                for j in range(2, raw.shape[1]):
                    lab = _norm(raw.iat[i, j])
                    if lab and looks_like_species_header(lab):
                        # collapse multi-wood cell to first wood token group
                        species_labels.append((j, lab.split()[0] if lab else lab))
                continue
            # Unf/Fin header row
            cells = [_norm(raw.iat[i, j]) if j < raw.shape[1] else "" for j in range(raw.shape[1])]
            unf_hits = sum(1 for c in cells if re.fullmatch(r"(?i)unf\.?", c))
            fin_hits = sum(1 for c in cells if re.fullmatch(r"(?i)fin\.?", c))
            if unf_hits >= 2 and fin_hits >= 2:
                col_map = []
                # walk columns; carry species from previous non-empty top
                # species names sit on prior row — re-read previous
                if i > 0:
                    tops = [_norm(raw.iat[i - 1, j]) if j < raw.shape[1] else "" for j in range(raw.shape[1])]
                else:
                    tops = [""] * raw.shape[1]
                carry = ""
                for j in range(2, raw.shape[1]):
                    top = tops[j] if j < len(tops) else ""
                    bot = cells[j]
                    if top and looks_like_species_header(top):
                        # first word of multi-wood banner
                        carry = re.split(r"\s{2,}|\s+(?=Rustic|QSWO)", top)[0].strip()
                        # better: take known woods
                        m = re.search(
                            r"(?i)(brown\s*maple|red\s*oak|white\s*oak|rustic\s*wo|"
                            r"oak|maple|cherry|hickory|elm|qswo|walnut)",
                            top,
                        )
                        if m:
                            carry = m.group(1).title().replace("Qswo", "QSWO")
                    if re.fullmatch(r"(?i)unf\.?", bot) and carry:
                        col_map.append((j, carry, "unfinished"))
                    elif re.fullmatch(r"(?i)fin\.?", bot) and carry:
                        col_map.append((j, carry, "finished"))
                continue

            # Product row: desc in col1, optional suffix in col0
            desc = c1 or c0
            if not desc or not col_map:
                continue
            if re.search(r"(?i)profile comfort|fabric seat|add \$|hardwood xx", desc):
                continue
            suffix = c0 if c0.startswith("-") or re.match(r"^-", c0.replace("\xa0", "").strip()) else ""
            suffix = re.sub(r"[\xa0\s]+", "", suffix)
            part = f"{current_style or ''} {desc} {suffix}".strip()
            part = re.sub(r"\s+", " ", part)
            any_p = False
            for j, sp, fin in col_map:
                if j >= raw.shape[1]:
                    continue
                price = _to_float(raw.iat[i, j])
                if price is None or price < 20:
                    continue
                any_p = True
                rows.append({
                    "vendor": vendor_name,
                    "collection": current_style,
                    "part_number": part,
                    "description": part,
                    "dimensions": None,
                    "option_key": suffix or None,
                    "species": sp,
                    "species_tier": None,
                    "finish_state": fin,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                })
            if not any_p and c0 and not c1 and len(c0) < 60:
                # bare style line without colon
                if not re.search(r"(?i)add |seat", c0):
                    current_style = c0

        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        tried.append({
            "sheet": name, "layout": "hillside_unf_fin",
            "rows": len(long), "note": f"style={current_style}",
        })
        if not long.empty:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out if not out.empty else pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ]),
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Hillside Chair Unf/Fin · {len(out) if not out.empty else 0} rows",
    )


def looks_like_maple_lane(filename: str = "") -> bool:
    fn = (filename or "").lower().replace("_", " ")
    return "maple lane" in fn or "maple_lane" in (filename or "").lower()


def import_maple_lane_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """Maple Lane: CODE + desc on row N, prices on N+1 under species columns."""
    names = list_excel_sheets(data)
    vendor_name = vendor or "Maple Lane Woodshop"
    # Prefer wholesale
    prefer = [n for n in names if re.search(r"(?i)wholesale", str(n))]
    targets = sheet_filter if sheet_filter is not None else (prefer or names)
    frames: list[pd.DataFrame] = []
    tried: list[dict] = []

    for name in names:
        if name not in targets:
            if sheet_filter is None and re.search(r"(?i)retail", str(name)) and prefer:
                tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "retail"})
            continue
        try:
            bio = io.BytesIO(data)
            raw = pd.read_excel(bio, sheet_name=name, header=None)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        raw = raw.dropna(how="all").reset_index(drop=True)
        rows = []
        current_collection = default_collection or None
        species_cols: list[tuple[int, str]] = []  # col, species
        finish_row_mode = False

        for i in range(len(raw)):
            c0 = _norm(raw.iat[i, 0]) if raw.shape[1] else ""
            # Collection banner
            row_vals = [_norm(raw.iat[i, j]) if j < raw.shape[1] else "" for j in range(min(raw.shape[1], 8))]
            joined = " ".join(v for v in row_vals if v)
            if joined and not c0 and re.search(
                r"(?i)pet diner|dining station|cabinet|end table|coffee|ramp|gate|toy box|lormel",
                joined,
            ):
                current_collection = joined[:60]
            # Species header: CODE ... RED OAK | BR. MAPLE | ...
            if re.fullmatch(r"(?i)code", c0) or (
                any(looks_like_species_header(v) for v in row_vals[3:10])
                and sum(1 for v in row_vals if looks_like_species_header(v)) >= 2
            ):
                species_cols = []
                for j in range(raw.shape[1]):
                    lab = _norm(raw.iat[i, j])
                    if lab and looks_like_species_header(lab):
                        species_cols.append((j, lab))
                finish_row_mode = False
                continue
            # Unfinished/Finished subheader
            if sum(1 for v in row_vals if re.fullmatch(r"(?i)unfinished|finished", v)) >= 2:
                # remap: pair finish under previous species carry
                new_map = []
                carry = ""
                # need previous species row - use current species_cols as anchors
                for j in range(raw.shape[1]):
                    lab = _norm(raw.iat[i, j])
                    if j > 0 and species_cols:
                        # find nearest species col <= j
                        for sc, sn in reversed(species_cols):
                            if sc <= j:
                                carry = sn
                                break
                    if re.fullmatch(r"(?i)unfinished", lab) and carry:
                        new_map.append((j, carry, "unfinished"))
                    elif re.fullmatch(r"(?i)finished", lab) and carry:
                        new_map.append((j, carry, "finished"))
                if new_map:
                    species_cols = [(j, f"{sp} | {fin}") for j, sp, fin in new_map]
                    finish_row_mode = True
                continue

            # SKU row
            if not c0 or not re.match(r"^[A-Z]{2,8}\d", c0, re.I):
                continue
            desc = _norm(raw.iat[i, 1]) if raw.shape[1] > 1 else c0
            # prices often on next row
            price_row = i
            # if this row has no numeric prices, use i+1
            has_here = any(
                _to_float(raw.iat[i, j]) is not None
                for j, _ in species_cols
                if j < raw.shape[1]
            )
            if not has_here and i + 1 < len(raw):
                price_row = i + 1
                # also dims may be on next row col1
                if not desc or len(desc) < 3:
                    desc = _norm(raw.iat[i + 1, 1]) if raw.shape[1] > 1 else desc
                d2 = _norm(raw.iat[i + 1, 1]) if raw.shape[1] > 1 else ""
                dims = d2 if d2 and re.search(r"\d", d2) and re.search(r"[x×]", d2, re.I) else None
            else:
                dims = None
                d2 = _norm(raw.iat[i, 1]) if raw.shape[1] > 1 else ""
                if d2 and re.search(r"[x×]", d2, re.I):
                    dims = d2

            for tier_i, (j, sp) in enumerate(species_cols, start=1):
                if j >= raw.shape[1]:
                    continue
                price = _to_float(raw.iat[price_row, j])
                if price is None or price < 5:
                    continue
                finish = "unfinished"
                species_name = sp
                if " | " in sp:
                    species_name, fin = sp.split(" | ", 1)
                    finish = "finished" if "fin" in fin.lower() and "unf" not in fin.lower() else (
                        "unfinished" if "unf" in fin.lower() else fin.lower()
                    )
                rows.append({
                    "vendor": vendor_name,
                    "collection": current_collection,
                    "part_number": c0,
                    "description": desc or c0,
                    "dimensions": dims,
                    "option_key": None,
                    "species": species_name,
                    "species_tier": tier_i,
                    "finish_state": finish,
                    "base_price": price,
                    "price_basis": "wholesale",
                    "unit": None,
                    "notes": None,
                })

        long = _clean_long_rows(pd.DataFrame(rows)) if rows else pd.DataFrame()
        tried.append({
            "sheet": name, "layout": "maple_lane_sku_next_price",
            "rows": len(long), "note": f"species_cols={len(species_cols)}",
        })
        if not long.empty:
            frames.append(long)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if vendor_name and not out.empty:
        out["vendor"] = vendor_name
    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out if not out.empty else pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ]),
        detected_markup=None,
        sheet_names=names,
        notes=f"{filename + ': ' if filename else ''}Maple Lane · {len(out) if not out.empty else 0} rows",
    )


def import_workbook(
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    """
    Read all product sheets from an Excel workbook, unpivot wide matrices,
    return long-form DataFrame ready for master insert.
    """
    names = list_excel_sheets(data)

    # Specialized outdoor poly layout (multi-section color tiers)
    if looks_like_patio_kraft(filename, names, data):
        return import_patio_kraft_workbook(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )

    if looks_like_amish_aspen(filename):
        return import_amish_aspen_workbook(
            data, vendor=vendor, default_collection=default_collection,
            sheet_filter=sheet_filter, filename=filename,
        )
    if looks_like_hillside_chair(filename, names):
        return import_hillside_chair_workbook(
            data, vendor=vendor, default_collection=default_collection,
            sheet_filter=sheet_filter, filename=filename,
        )
    if looks_like_maple_lane(filename):
        return import_maple_lane_workbook(
            data, vendor=vendor, default_collection=default_collection,
            sheet_filter=sheet_filter, filename=filename,
        )

    if looks_like_hw_chair_markup(filename, names):
        return import_hw_chair_workbook(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )

    if looks_like_lamb(filename, names):
        return import_lamb_workbook(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )

    if looks_like_luxhome(filename, names):
        return import_luxhome_workbook(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )

    if looks_like_windy_acres(filename):
        return import_windy_acres_workbook(
            data,
            vendor=vendor,
            default_collection=default_collection,
            sheet_filter=sheet_filter,
            filename=filename,
        )

    markup = detect_markup_from_workbook(data, names)
    frames = []
    tried = []

    # Prefer Wholesale when both Retail and Wholesale product sheets exist.
    # Builder "Retail" already includes their markup — FAF multiplies wholesale again.
    retail_sheets = {
        n for n in names if re.search(r"(?i)\bretail\b", str(n).strip())
    }
    wholesale_sheets = {
        n for n in names if re.search(r"(?i)\bwholesale\b", str(n).strip())
    }
    skip_retail = bool(retail_sheets and wholesale_sheets and sheet_filter is None)

    # Prefer plain price list over "… MARKUP" / "with Markup" twins
    markup_dup_sheets = {
        n for n in names
        if re.search(r"(?i)\bmark\s*-?\s*up\b", str(n))
        and not _is_markup_control_sheet(str(n))
    }
    plain_price_sheets = {
        n for n in names
        if re.search(r"(?i)price\s*list|pricelist", str(n))
        and not re.search(r"(?i)mark\s*-?\s*up", str(n))
    }
    skip_markup_dup = bool(markup_dup_sheets and plain_price_sheets and sheet_filter is None)

    for name in names:
        if sheet_filter is not None and name not in sheet_filter:
            continue
        if skip_retail and name in retail_sheets:
            tried.append({
                "sheet": name,
                "layout": "skip",
                "rows": 0,
                "note": "skipped retail (wholesale sheet present)",
            })
            continue
        if skip_markup_dup and name in markup_dup_sheets:
            tried.append({
                "sheet": name,
                "layout": "skip",
                "rows": 0,
                "note": "skipped markup twin (plain price list present)",
            })
            continue
        if SKIP_SHEET_RE.match(str(name).strip()) and (
            sheet_filter is None or name not in (sheet_filter or [])
        ):
            tried.append({"sheet": name, "layout": "skip", "rows": 0, "note": "skipped"})
            continue
        try:
            df = dataframe_from_sheet(data, name)
        except Exception as e:
            tried.append({"sheet": name, "layout": "error", "rows": 0, "note": str(e)})
            continue
        if df.empty:
            tried.append({"sheet": name, "layout": "empty", "rows": 0, "note": ""})
            continue

        layout = classify_sheet(df, name)
        long = pd.DataFrame()
        wmap = wholesale_col_for_species(df, layout, markup) if layout.layout == "wide_species" else {}
        if wmap:
            layout.notes = (layout.notes or "") + f" | wholesale-under-markup×{markup:g}"
        if layout.layout == "wide_species":
            long = unpivot_wide_species(
                df, layout,
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
                    name, "wide_species",
                    id_col=layout.id_col or guessed,
                    desc_col=layout.desc_col,
                    dim_cols=layout.dim_cols,
                    species_cols=numericish,
                )
                wmap2 = wholesale_col_for_species(df, layout_try, markup)
                long = unpivot_wide_species(
                    df, layout_try,
                    default_collection=default_collection or name,
                    vendor=vendor,
                    wholesale_map=wmap2,
                )
            elif guessed and len(numericish) == 1:
                layout_try = SheetLayout(
                    name, "long_flat",
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
            dim_like = parts.str.match(
                r"(?i)^\d+(\.\d+)?(\s*[x×]\s*\d+(\.\d+)?)+$"
            ).fillna(False).mean()
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
                    looks_like_species_header(s)
                    or any(t in s.lower() for t in WOOD_TOKENS)
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
        tried.append({
            "sheet": name,
            "layout": layout.layout,
            "rows": n,
            "note": layout.notes,
            "species_cols": layout.species_cols[:8],
            "id_col": layout.id_col,
            "desc_col": layout.desc_col,
        })
        if n > 0:
            # if collection empty, use sheet name
            if "collection" in long.columns:
                long["collection"] = long["collection"].fillna(name)
                long.loc[long["collection"].astype(str).str.strip() == "", "collection"] = name
            frames.append(long)

    if frames:
        out = pd.concat(frames, ignore_index=True)
    else:
        out = pd.DataFrame(columns=[
            "vendor", "collection", "part_number", "description", "dimensions",
            "option_key", "species", "species_tier", "finish_state", "base_price",
            "price_basis", "unit", "notes",
        ])

    # attach vendor default
    if vendor and not out.empty:
        out["vendor"] = out["vendor"].fillna(vendor)
        out.loc[out["vendor"].isna() | (out["vendor"].astype(str).str.strip() == ""), "vendor"] = vendor

    # Millers ships SKU-only rows — synthesize floor-friendly descriptions
    if looks_like_millers(filename) and not out.empty:
        out = enhance_millers_long_df(out)

    note = f"{len(names)} sheets · {len(out)} long rows · markup={markup}"
    if filename:
        note = f"{filename}: " + note

    return WorkbookImportResult(
        sheets_tried=tried,
        long_df=out,
        detected_markup=markup,
        sheet_names=names,
        notes=note,
    )
