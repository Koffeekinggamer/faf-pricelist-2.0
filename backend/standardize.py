"""
Canonical master-row standardization for FAF Pricebook.

Goal: every vendor row looks the same shape for search / quotes / export.
  - vendor: clean display name
  - collection: human section (not sheet filenames)
  - part_number / description: trimmed; description falls back to part
  - species: wood tier OR color/fabric option (never col_N / FINISHED)
  - finish_state: finished | unfinished | glazed | None
  - price_basis: wholesale
  - multiplier + adjusted_price: consistent math
"""

from __future__ import annotations

import re
from typing import Any, Optional


# ---------------------------------------------------------------------------
# finish_state
# ---------------------------------------------------------------------------

_FINISH_MAP = {
    "finished": "finished",
    "finshed": "finished",  # common typo
    "fin": "finished",
    "fin.": "finished",
    "unfinished": "unfinished",
    "unf": "unfinished",
    "unf.": "unfinished",
    "glazed": "glazed",
    "glaze": "glazed",
}


def standardize_finish(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if not s or s in {"nan", "none", "null"}:
        return None
    if s in _FINISH_MAP:
        return _FINISH_MAP[s]
    if "unf" in s:
        return "unfinished"
    if "glaz" in s:
        return "glazed"
    if "fin" in s:
        return "finished"
    return None


# ---------------------------------------------------------------------------
# species / option labels
# ---------------------------------------------------------------------------

# Strip trailing " (2)" de-dupe artifacts from pandas header collision
_TRAILING_INDEX_RE = re.compile(r"\s*\((\d+)\)\s*$")

# Junk species headers from bad wide unpivots
_JUNK_SPECIES_RE = re.compile(
    r"""(?ix)
    ^(col_\d+|unnamed.*|finished|unfinished|finshed|price|markup|
      windy\s+acres.*pricelist.*|
      \d+\.0)$
    """
)

# Longest-first wood phrases for splitting ALL-CAPS multi-wood headers
# e.g. "OAK BR. MAPLE SAP CHERRY" → Oak / Brown Maple / Sap Cherry
_WOOD_PHRASES = [
    "Brown Soft Maple", "Rustic Brown Maple", "Rustic Hard Maple",
    "Rustic White Oak", "Rustic Red Oak", "Rustic QSWO", "Rustic Cherry",
    "Rustic Walnut", "Rustic Hickory", "Rustic Maple",
    "Character White Oak", "Character Hickory", "Character Cherry",
    "Character Walnut", "Character QSWO", "Character Maple",
    "Plain White Oak", "QS White Oak", "White Qtrsawn", "Quarter Sawn White Oak",
    "Rough Sawn Wormy Maple", "Rough Sawn White Oak", "Rough Sawn Maple",
    "Wormy Maple", "Soft Maple", "Hard Maple", "Brown Maple", "Sap Cherry",
    "Red Oak", "White Oak", "QSWO", "PSWO",
    "Cherry", "Hickory", "Walnut", "Maple", "Oak", "Elm", "Ash",
    "Mahogany", "Pine", "Birch", "Alder", "Beech",
]

# Abbreviation → phrase (applied before phrase split)
_WOOD_ABBREV = [
    (re.compile(r"(?i)\bbr\.?\s*maple\b"), "Brown Maple"),
    (re.compile(r"(?i)\bbrown\s*soft\s*maple\b"), "Brown Soft Maple"),
    (re.compile(r"(?i)\bbrown\s*maple\b"), "Brown Maple"),
    (re.compile(r"(?i)\bhd\.?\s*maple\b"), "Hard Maple"),
    (re.compile(r"(?i)\bhard\s*maple\b"), "Hard Maple"),
    (re.compile(r"(?i)\bsap\s*cherry\b"), "Sap Cherry"),
    (re.compile(r"(?i)\bru\.?\s*qswo\b"), "Rustic QSWO"),
    (re.compile(r"(?i)\bru\.?\s*cherry\b"), "Rustic Cherry"),
    (re.compile(r"(?i)\bru\.?\s*walnut\b"), "Rustic Walnut"),
    (re.compile(r"(?i)\bru\.?\s*hickory\b"), "Rustic Hickory"),
    (re.compile(r"(?i)\brustic\s*qsw[o0]\b"), "Rustic QSWO"),
    (re.compile(r"(?i)\br\.?\s*walnut\b"), "Rustic Walnut"),
    (re.compile(r"(?i)\bqs\s*white\s*oak\b"), "QS White Oak"),
    (re.compile(r"(?i)\bwhite\s*qtrsawn\b"), "QS White Oak"),
    (re.compile(r"(?i)\bqsw[o0]\b"), "QSWO"),
    (re.compile(r"(?i)\bwormy\s*maple\b"), "Wormy Maple"),
    (re.compile(r"(?i)\brough\s*sawn\s*wormy\s*maple\b"), "Rough Sawn Wormy Maple"),
    (re.compile(r"(?i)\brough\s*sawn\s*white\s*oak\b"), "Rough Sawn White Oak"),
    (re.compile(r"(?i)\brough\s*sawn\b"), "Rough Sawn"),
    (re.compile(r"(?i)\bred\s*oak\b"), "Red Oak"),
    (re.compile(r"(?i)\bwhite\s*oak\b"), "White Oak"),
    (re.compile(r"(?i)\bstain\s*maple\b"), "Stain Maple"),
    (re.compile(r"(?i)\brustic\s*ch\b"), "Rustic Cherry"),
    (re.compile(r"(?i)\bcharacter\s*cherry\b"), "Character Cherry"),
    (re.compile(r"(?i)\bcharacter\s*hickory\b"), "Character Hickory"),
    (re.compile(r"(?i)\bcharacter\s*walnut\b"), "Character Walnut"),
    (re.compile(r"(?i)\bcharacter\s*qsw[o0]\b"), "Character QSWO"),
    (re.compile(r"(?i)\bcharacter\s*white\s*oak\b"), "Character White Oak"),
    (re.compile(r"(?i)\bplain\s*white\s*oak\b"), "Plain White Oak"),
    (re.compile(r"(?i)\brrs\.?\s*maple\b"), "Rough Sawn Maple"),
]


def _expand_wood_abbrevs(s: str) -> str:
    for rx, rep in _WOOD_ABBREV:
        s = rx.sub(rep, s)
    return s


def _extract_wood_list(s: str) -> list[str]:
    """
    Greedy longest-match parse of a multi-wood header into ordered woods.
    Works with or without / , separators.
    """
    s = _expand_wood_abbrevs(s)
    s = re.sub(r"[,;|]+", " ", s)
    s = re.sub(r"\s*/\s*", " / ", s)
    # If explicit slashes, split on them first
    if " / " in s or "/" in s:
        chunks = [c.strip() for c in re.split(r"\s*/\s*", s) if c.strip()]
        out = []
        for ch in chunks:
            sub = _extract_wood_list_flat(ch)
            out.extend(sub if sub else [ch.strip().title() if ch.isupper() else ch.strip()])
        return out
    return _extract_wood_list_flat(s)


def _extract_wood_list_flat(s: str) -> list[str]:
    s = _collapse_ws(_expand_wood_abbrevs(s))
    remaining = s
    found: list[str] = []
    phrases = sorted(_WOOD_PHRASES, key=len, reverse=True)
    guard = 0
    while remaining and guard < 40:
        guard += 1
        remaining = remaining.lstrip(" ,/-")
        if not remaining:
            break
        matched = False
        low = remaining.lower()
        for ph in phrases:
            pl = ph.lower()
            if low.startswith(pl):
                # boundary: end or space/punct
                end = len(ph)
                if end == len(remaining) or remaining[end] in " ,/-":
                    found.append(ph)
                    remaining = remaining[end:]
                    matched = True
                    break
        if not matched:
            # skip one token
            m = re.match(r"^(\S+)(\s+|$)", remaining)
            if not m:
                break
            tok = m.group(1)
            # keep unknown token as-is (title if shouty)
            if tok.isupper() and len(tok) > 1:
                tok = tok.title()
            found.append(tok)
            remaining = remaining[m.end() :]
    return found

# Full-string aliases (after collapse)
_SPECIES_ALIASES = {
    "oak / brown maple": "Oak / Brown Maple",
    "oak, brown maple": "Oak / Brown Maple",
    "oak brown maple": "Oak / Brown Maple",
    "oak br maple sap cherry": "Oak / Brown Maple / Sap Cherry",
    "oak / brown maple / sap cherry": "Oak / Brown Maple / Sap Cherry",
    "ru qswo / rustic cherry / wormy maple": "Rustic QSWO / Rustic Cherry / Wormy Maple",
    "rustic qswo / rustic cherry / wormy maple": "Rustic QSWO / Rustic Cherry / Wormy Maple",
    "white oak / hard maple / hickory": "White Oak / Hard Maple / Hickory",
    "qswo / cherry / elm": "QSWO / Cherry / Elm",
    "cherry / hard maple / hickory": "Cherry / Hard Maple / Hickory",
    "cherry,hard maple,hickory": "Cherry / Hard Maple / Hickory",
    "cherry hard maple hickory": "Cherry / Hard Maple / Hickory",
    "stain maple / rustic cherry": "Stain Maple / Rustic Cherry",
    "stain maple, rustic ch": "Stain Maple / Rustic Cherry",
    "br maple red oak rustic qswo rustic hickory": "Brown Maple / Red Oak / Rustic QSWO / Rustic Hickory",
    "brown maple / red oak / rustic qswo / rustic hickory": "Brown Maple / Red Oak / Rustic QSWO / Rustic Hickory",
    "cherry / qswo hickory / hard maple / rustic walnut": "Cherry / QSWO / Hickory / Hard Maple / Rustic Walnut",
    "cherry, qswo hickory, hard maple r walnut": "Cherry / QSWO / Hickory / Hard Maple / Rustic Walnut",
    "standard colors": "Standard Colors",
    "bright colors": "Bright Colors",
    "woodgrain colors": "Woodgrain Colors",
    "standard poly colors": "Standard Poly Colors",
    "ultra leather": "Ultra Leather",
    "genuine leather": "Genuine Leather",
    "standard": "Standard",
    "premium": "Premium",
    "black": "Black",
}


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def standardize_species(val: Any) -> Optional[str]:
    """Canonical species / color / fabric option label, or None if junk."""
    if val is None:
        return None
    # Reuse quote/dash normalization from standardize_text
    raw = standardize_text(val) or ""
    if not raw or raw.lower() in {"nan", "none", "null", "-"}:
        return None

    # Trailing (2) from pandas de-dupe — keep tier number for finish-only headers
    m_idx = _TRAILING_INDEX_RE.search(raw)
    index_n = int(m_idx.group(1)) if m_idx else None
    base = _TRAILING_INDEX_RE.sub("", raw).strip()

    # FINISHED / UNFINISHED used as species (Windy Acres) → Wood Tier N
    if re.match(r"(?i)^(finished|unfinished|finshed)$", base):
        tier = index_n or 1
        return f"Wood Tier {tier}"

    # Already-canonical tier labels (do not re-split "Wood Tier 2" into woods)
    m_tier = re.match(r"(?i)^wood(?:\s*/\s*|\s+)tier(?:\s*/\s*|\s+)(\d+)$", base)
    if m_tier:
        return f"Wood Tier {int(m_tier.group(1))}"
    if re.match(r"(?i)^wood\s+tier\s+\d+$", base):
        n = re.search(r"\d+", base)
        return f"Wood Tier {int(n.group())}" if n else base

    if _JUNK_SPECIES_RE.match(base) or _JUNK_SPECIES_RE.match(raw):
        return None
    if re.match(r"(?i)^col_\d+", base):
        return None
    if re.match(r"^\d+(\.\d+)?$", base):
        return None

    # Color / fabric / outdoor options — keep simple Title Case
    if re.search(
        r"(?i)color|leather|premium|standard|woodgrain|poly|fabric|black|bright",
        base,
    ) and not re.search(r"(?i)oak|maple|cherry|walnut|hickory|qswo", base):
        s = _collapse_ws(base)
        key = s.lower()
        if key in _SPECIES_ALIASES:
            return _SPECIES_ALIASES[key]
        return s.title() if s.islower() or s.isupper() else s

    # Mattress size columns
    if re.match(r"(?i)^(twinxl|twin|full|queen|king|cal\s*king)$", base):
        return {
            "twin": "Twin",
            "twinxl": "TwinXL",
            "full": "Full",
            "queen": "Queen",
            "king": "King",
            "cal king": "Cal King",
        }.get(base.lower().replace("  ", " "), base.title())

    # Clean parenthetical notes: "(Also Rustic)" → treat as Rustic variant flag
    work = re.sub(r"\((?i)also\s+([^)]+)\)", r"\1", base)
    work = re.sub(r"\([^)]*\)", " ", work)  # drop other parentheticals
    work = _collapse_ws(work)

    # Multi-wood / single wood
    woods = _extract_wood_list(work)
    if woods:
        # Drop useless leftover tokens
        woods = [
            w for w in woods
            if w.lower() not in {"and", "or", "also", "the", "with", "(", ")"}
            and not re.match(r"^\W+$", w)
        ]
        s = " / ".join(woods)
    else:
        s = _collapse_ws(_expand_wood_abbrevs(work))
        if s.isupper() and len(s) > 3:
            s = s.title()

    s = _collapse_ws(s)
    s = re.sub(r"(?i)\bQswo\b", "QSWO", s)
    s = re.sub(r"(?i)\bQs\b", "QS", s)

    key = re.sub(r"\s*/\s*", " / ", s.lower())
    key = re.sub(r"\s+", " ", key).strip()
    if key in _SPECIES_ALIASES:
        s = _SPECIES_ALIASES[key]
    else:
        key2 = re.sub(r"[^a-z0-9 /]+", "", key)
        key2 = re.sub(r"\s+", " ", key2).strip()
        if key2 in _SPECIES_ALIASES:
            s = _SPECIES_ALIASES[key2]

    return s or None


def is_junk_species_row(species: Any) -> bool:
    """True if species was unrecoverable junk (row may still keep if we null species)."""
    if species is None:
        return False
    raw = str(species).strip()
    if re.match(r"(?i)^col_\d+", raw):
        return True
    if re.match(r"(?i)^\d+(\.\d+)?(\s*\(\d+\))?$", raw):
        return True
    if re.search(r"(?i)pricelist|price list", raw) and len(raw) > 20:
        return True
    return False


# ---------------------------------------------------------------------------
# collection
# ---------------------------------------------------------------------------

_SHEET_COLLECTION_RE = re.compile(
    r"""(?ix)
    ^(master(_bk)?|pl\s*to\s*export|pl\s*print|pl\s*with\s*markup|
      \d{4}\s+hopewood\s+pricelist|wholesale|retail|sheet\d+|
      footer\s*summary|price|description|read\s*first!?|
      instructions?)$
    """
)

# Option notes / upcharges wrongly captured as "current collection"
_JUNK_COLLECTION_RE = re.compile(
    r"""(?ix)
    add\s+metal\s+leg|
    door\s+options?|
    inset\s+panel|
    replace\s+glass|
    adjustable\s+shelf|
    for\s+matching\s+bar\s+stools|
    see\s+seating|
    top\s+is\s+inset|
    two\s+tone|
    \$50/|
    markup|
    subject\s+to\s+change|
    please\s+note|
    ^price$|
    ^description$|
    ^options?$
    """
)

# Millers sheet-name noise
_MULT_PREFIX_RE = re.compile(r"(?i)^mult-?")

# Vendor defaults when collection is empty (floor-friendly)
_VENDOR_DEFAULT_COLLECTION = {
    "FN Chair": "Seating",
    "Genuine Oak": "Casegoods",
}


def standardize_collection(val: Any, *, vendor: str = "") -> Optional[str]:
    if val is None:
        # vendor default only when truly empty
        return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")

    s = _TRAILING_INDEX_RE.sub("", s).strip()
    s = re.sub(r",?\s*continued\s*$", "", s, flags=re.I).strip()

    if _SHEET_COLLECTION_RE.match(s):
        return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")
    if re.match(r"(?i)^col_\d+", s):
        return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")

    # Option / instruction lines stuck as collection (common on Hope Wood)
    if _JUNK_COLLECTION_RE.search(s):
        return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")
    if len(s) > 70:
        return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")

    # Mult-Gun → Gun Cabinets, Mult-Bookcases → Bookcases
    if _MULT_PREFIX_RE.match(s):
        rest = _MULT_PREFIX_RE.sub("", s).strip()
        aliases = {
            "gun": "Gun Cabinets",
            "guns": "Gun Cabinets",
            "bookcases": "Bookcases",
            "tvconsoles": "TV Consoles",
            "tv consoles": "TV Consoles",
        }
        key = rest.lower().replace(" ", "")
        s = aliases.get(key) or aliases.get(rest.lower()) or rest
        if s.lower() in {"tvconsoles", "tvconsole"}:
            s = "TV Consoles"

    # "Edgefield UNFINISHED" → "Edgefield"
    s = re.sub(r"(?i)\s*[-–]?\s*(unfinished|finished)\s*$", "", s).strip()
    # Wood species mistaken as collection (Millers nested headers)
    if re.match(
        r"(?i)^(oak|rustic|qswo|walnut|cherry|maple|hickory|elm|br/|chy/)",
        s,
    ) and not re.search(r"(?i)collection|series|suite", s):
        if not re.search(r"(?i)desk|cabinet|table|bed|chair", s):
            return _VENDOR_DEFAULT_COLLECTION.get(vendor or "")

    # Title Case short all-caps collections
    if s.isupper() and 3 < len(s) < 40:
        s = s.title()

    return s or _VENDOR_DEFAULT_COLLECTION.get(vendor or "")


# ---------------------------------------------------------------------------
# text fields
# ---------------------------------------------------------------------------

def standardize_text(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    # Normalize curly quotes / fancy dashes so matrix twins collapse
    s = (
        s.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u00a0", " ")
    )
    s = re.sub(r"\s+", " ", s)
    return s


# SKU-like tokens often land in description when id_col was missed
_SKU_LIKE_RE = re.compile(
    r"""(?ix)
    ^(
        [A-Z]{1,4}-[A-Z0-9][A-Z0-9\-_/.]{1,24}   # LA-ASH-3067-EX, GO-AVNNS, SU-BT10
      | [A-Z]{2,6}\d{2,}[A-Z0-9\-]*               # VECG, HW123, BB-GR-33
      | \d{3,6}                                   # short numeric item codes
    )$
    """
)

_JUNK_PART_RE = re.compile(
    r"(?i)^(item\s*\#?|description|price|unf|finished|all|none|nan|null|"
    r"new(\s*product|\s*items?)?|"
    r"new\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)(\s+\d{4})?)$"
)


def looks_like_sku(val: Any) -> bool:
    s = standardize_text(val)
    if not s or len(s) > 36:
        return False
    if _JUNK_PART_RE.match(s):
        return False
    # multi-word product names are not SKUs
    if " " in s and not re.match(r"(?i)^[A-Z0-9][A-Z0-9\-_/.]+$", s):
        return False
    return bool(_SKU_LIKE_RE.match(s))


def standardize_part(val: Any) -> Optional[str]:
    s = standardize_text(val)
    if not s:
        return None
    # drop pure junk parts
    if _JUNK_PART_RE.match(s):
        return None
    return s


# ---------------------------------------------------------------------------
# vendor names — ONE builder = ONE vendor (no year / filename twins)
# ---------------------------------------------------------------------------

VENDOR_CANON = {
    "hope wood": "Hope Wood",
    "hopewood": "Hope Wood",
    "genuine oak": "Genuine Oak",
    "millers woodshop": "Millers Woodshop",
    "miller's woodshop": "Millers Woodshop",
    "millers": "Millers Woodshop",
    "mws": "Millers Woodshop",
    "mws 2023": "Millers Woodshop",
    "windy acres furniture": "Windy Acres Furniture",
    "windy acres": "Windy Acres Furniture",
    "fn chair": "FN Chair",
    "fn chairs": "FN Chair",
    "rainbow bedding": "Rainbow Bedding",
    "rainbow": "Rainbow Bedding",
    "premier woodcraft": "Premier Woodcraft",
    "premier": "Premier Woodcraft",
    "charleston forge": "Charleston Forge",
    "luxhome": "LuxHome",
    "lux home": "LuxHome",
    "aj's luxhome": "LuxHome",
    "ajs luxhome": "LuxHome",
    "aj luxhome": "LuxHome",
    "patio kraft": "Patio Kraft",
    "patiokraft": "Patio Kraft",
    "beaverdam": "Beaverdam",
    "gvwi": "GVWI",
    "gable valley": "GVWI",
    "lamb": "LAMB",
}

# Substring matchers for messy filenames (order: more specific first)
_VENDOR_FILENAME_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(?i)genuine\s*oak"), "Genuine Oak"),
    (re.compile(r"(?i)millers?\s*woodshop|mws\b"), "Millers Woodshop"),
    (re.compile(r"(?i)windy\s*acres"), "Windy Acres Furniture"),
    (re.compile(r"(?i)\bfn\s*chairs?\b"), "FN Chair"),
    (re.compile(r"(?i)rainbow\s*bedding|jan\s*2026\s*wholesale"), "Rainbow Bedding"),
    (re.compile(r"(?i)premier\s*woodcraft|\bpremier\b"), "Premier Woodcraft"),
    (re.compile(r"(?i)charleston\s*forge"), "Charleston Forge"),
    (re.compile(r"(?i)lux\s*home|luxhome|aj'?s?\s*lux"), "LuxHome"),
    (re.compile(r"(?i)patio\s*kraft|patiokraft"), "Patio Kraft"),
    (re.compile(r"(?i)beaverdam"), "Beaverdam"),
    (re.compile(r"(?i)\bgvwi\b|gable\s*valley"), "GVWI"),
    (re.compile(r"(?i)\blamb\b"), "LAMB"),
    (re.compile(r"(?i)hope\s*wood|hopewood|\bhw_2025\b|\bhw_"), "Hope Wood"),
]


def resolve_builder_vendor(
    name: Any = "",
    *,
    filename: str = "",
) -> Optional[str]:
    """
    Map any vendor label or price-list filename to exactly one builder name.

    Policy: one builder → one vendor. Years, markup suffixes, and alternate
    filenames (MWS 2023 vs Millers 2026) collapse to the same name.
    """
    # Filename hints win when provided (clearest builder identity)
    fn = (filename or "").strip()
    if fn:
        stem = Path_stem_safe(fn)
        for rx, canon in _VENDOR_FILENAME_HINTS:
            if rx.search(stem) or rx.search(fn):
                return canon

    s = standardize_text(name)
    if not s:
        return None

    # Try filename-style noise strip on the name itself
    s_clean = re.sub(r"[_]+", " ", s)
    s_clean = re.sub(
        r"(?i)\s*(wholesale|retail)?\s*(price\s*list|pricelist|pricebook).*$",
        "",
        s_clean,
    )
    s_clean = re.sub(r"\s+\d{1,2}[-_/]\d{1,2}[-_/]\d{2,4}.*$", "", s_clean)
    s_clean = re.sub(r"(?i)\s*[-_]?\s*(revised|rep|digital|master).*$", "", s_clean)
    s_clean = re.sub(r"(?i)\s*20\d{2}\s*$", "", s_clean)
    s_clean = _collapse_ws(s_clean)

    for candidate in (s, s_clean, s_clean.lower()):
        key = candidate.lower().strip()
        if key in VENDOR_CANON:
            return VENDOR_CANON[key]

    for rx, canon in _VENDOR_FILENAME_HINTS:
        if rx.search(s) or rx.search(s_clean):
            return canon

    return s_clean or s


def Path_stem_safe(filename: str) -> str:
    """stem without importing pathlib at module top circular risk — local use."""
    from pathlib import Path

    p = Path(filename)
    return p.stem if p.suffix else filename


def standardize_vendor(val: Any) -> Optional[str]:
    return resolve_builder_vendor(val)


# ---------------------------------------------------------------------------
# full row
# ---------------------------------------------------------------------------

def standardize_row(row: dict, *, default_multiplier: float = 2.7) -> Optional[dict]:
    """
    Return a cleaned copy of a master row dict, or None if the row should be dropped.
    """
    out = dict(row)

    vendor = standardize_vendor(out.get("vendor"))
    part = standardize_part(out.get("part_number"))
    desc = standardize_text(out.get("description"))
    dims = standardize_text(out.get("dimensions"))
    raw_species = out.get("species")

    # Promote SKU-like description into part_number when id column was missed
    if not part and desc and looks_like_sku(desc):
        part = standardize_part(desc)
        desc = None

    # Drop unrecoverable junk-species rows that have no usable identity
    if is_junk_species_row(raw_species) and not part and not desc:
        return None

    species = standardize_species(raw_species)
    # If species was pure junk col_N, drop the whole row (bad matrix columns)
    if is_junk_species_row(raw_species) and species is None:
        return None

    # Species that is really dimensions / page numbers (e.g. "33 / 10")
    if species and re.fullmatch(r"[\d./\s×xX\-]+", species):
        if not dims:
            dims = species
        species = None

    finish = standardize_finish(out.get("finish_state"))
    # If finish embedded in old species label and finish empty
    if finish is None and raw_species and re.search(r"(?i)unfinished|unf\b", str(raw_species)):
        finish = "unfinished"
    elif finish is None and raw_species and re.search(r"(?i)\bfinished\b|\bfinshed\b", str(raw_species)):
        # only if not "Wood Tier" path — those already remapped
        if species and species.startswith("Wood Tier"):
            # Windy: FINISHED → finished, UNFINISHED → unfinished
            if re.match(r"(?i)^unfinished", str(raw_species).strip()):
                finish = "unfinished"
            else:
                finish = "finished"
        elif species is None:
            finish = "finished"

    # Windy remapped Wood Tier: set finish from original
    if species and species.startswith("Wood Tier"):
        if re.match(r"(?i)^unf", str(raw_species).strip()):
            finish = "unfinished"
        else:
            finish = finish or "finished"

    # Default finish when builder omitted it (most sellable rows are finished)
    if finish is None:
        finish = "finished"

    collection = standardize_collection(
        out.get("collection"), vendor=vendor or ""
    )
    # Drop sheet debris used as collection
    if collection and re.fullmatch(r"(?i)(price|sheet\d*|retail|wholesale)", collection):
        collection = None
    # If still empty, apply vendor default
    if not collection and vendor in _VENDOR_DEFAULT_COLLECTION:
        collection = _VENDOR_DEFAULT_COLLECTION[vendor]
    option_key = standardize_text(out.get("option_key"))
    notes = standardize_text(out.get("notes"))
    unit = standardize_text(out.get("unit"))
    source = standardize_text(out.get("source_file"))

    # Description fallback
    if not desc and part:
        desc = part

    # Must have price and something searchable
    base = out.get("base_price")
    try:
        base_f = float(base) if base is not None else None
    except (TypeError, ValueError):
        base_f = None
    if base_f is None or base_f <= 0:
        return None
    if not part and not desc:
        return None
    # Drop section banners that landed as product rows
    if desc and re.match(
        r"(?i)^new(\s*product|\s*items?)?$|"
        r"(?i)^new\s+(january|february|march|april|may|june|july|august|"
        r"september|october|november|december)\b",
        desc,
    ):
        return None

    mult = out.get("multiplier")
    try:
        mult_f = float(mult) if mult is not None else default_multiplier
    except (TypeError, ValueError):
        mult_f = default_multiplier
    if mult_f <= 0:
        mult_f = default_multiplier

    tier = out.get("species_tier")
    try:
        tier_i = int(tier) if tier is not None and str(tier).strip() != "" else None
    except (TypeError, ValueError):
        tier_i = None
    # Derive tier from Wood Tier N
    if tier_i is None and species and species.startswith("Wood Tier"):
        m = re.search(r"(\d+)$", species)
        if m:
            tier_i = int(m.group(1))

    out.update({
        "vendor": vendor,
        "collection": collection,
        "part_number": part,
        "description": desc,
        "dimensions": dims,
        "option_key": option_key,
        "species": species,
        "species_tier": tier_i,
        "finish_state": finish,
        "base_price": round(base_f, 4) if base_f != int(base_f) else float(int(base_f)) if abs(base_f - int(base_f)) < 1e-9 else round(base_f, 2),
        "price_basis": "wholesale",
        "multiplier": mult_f,
        "adjusted_price": None,  # set below via even-dollar rule
        "unit": unit,
        "notes": notes,
        "source_file": source,
    })
    # nicer base_price: 2 decimal for money; retail = even whole dollars
    from backend.pricing import retail_from_wholesale

    out["base_price"] = round(float(base_f), 2)
    out["adjusted_price"] = retail_from_wholesale(base_f, mult_f)
    return out


def standardize_rows(rows: list[dict], *, default_multiplier: float = 2.7) -> list[dict]:
    out = []
    for r in rows:
        cleaned = standardize_row(r, default_multiplier=default_multiplier)
        if cleaned is not None:
            out.append(cleaned)
    return out
