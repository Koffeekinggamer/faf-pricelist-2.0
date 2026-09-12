"""Match Search Options to the piece of furniture being looked up.

Every builder's Options list is live catalog (ADR-0008). This module only
decides which of those labels apply to the current search — beds keep
headboard / footboard / underbed storage; casegoods keep slides and drawer
adders; finishes stay available on every wood piece.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

KIND_BED = "bed"
KIND_CASEGOOD = "casegood"
KIND_NIGHTSTAND = "nightstand"
KIND_WARDROBE = "wardrobe"
KIND_TABLE = "table"
KIND_ISLAND = "island"
KIND_DOOR = "door"
KIND_BUFFET = "buffet"
KIND_BENCH = "bench"
KIND_BARSTOOL = "barstool"
KIND_SEATING = "seating"

_ITEM_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        KIND_BED,
        re.compile(
            r"(?i)\b(?:beds?|headboards?|footboards?|daybeds?|bunks?|"
            r"underbeds?|mattress(?:es)?)\b"
        ),
    ),
    (
        KIND_CASEGOOD,
        re.compile(
            r"(?i)\b(?:dressers?|chests?|night\s*stands?|armoires?|"
            r"wardrobes?|credenzas?|sideboards?|buffets?|cabinets?|"
            r"vanit(?:y|ies)|hutches?|lingerie|chifferobes?|servers?|"
            r"drawer\s+units?|desks?)\b"
        ),
    ),
    (
        KIND_NIGHTSTAND,
        re.compile(r"(?i)\bnight\s*stands?\b"),
    ),
    (
        KIND_WARDROBE,
        re.compile(
            r"(?i)\b(?:wardrobes?|armoires?|chifferobes?|"
            r"gentleman'?s?\s+chests?|his\s*&\s*hers\s+chests?|"
            r"standing\s+chests?(?:\s+with\s+doors)?|"
            r"chests?\s+(?:with|w/)\s+doors)\b"
        ),
    ),
    (
        KIND_TABLE,
        re.compile(r"(?i)\b(?:tables?|pub\s+tables?|gathering)\b"),
    ),
    (
        KIND_ISLAND,
        re.compile(r"(?i)\bislands?\b"),
    ),
    (
        KIND_DOOR,
        re.compile(
            r"(?i)\bdoors?\b|hutches?|cabinets?|armoires?|wardrobes?|"
            r"buffets?|credenzas?|cupboards?|pie\s+safes?|china"
        ),
    ),
    (
        KIND_BUFFET,
        re.compile(r"(?i)\bbuffets?\b"),
    ),
    (
        KIND_BENCH,
        re.compile(r"(?i)\bbench(?:es)?\b"),
    ),
    (
        KIND_BARSTOOL,
        re.compile(r"(?i)bar\s*stools?|bar\s*chairs?"),
    ),
    (
        KIND_SEATING,
        re.compile(
            r"(?i)\b(?:chairs?|bench(?:es)?|stools?|rockers?|gliders?|"
            r"sofas?|loveseats?|barstools?)\b"
        ),
    ),
]

_OPTION_KIND_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        KIND_BED,
        re.compile(
            r"(?i)headboard|footboard|under[\s\-]*bed|storage\s+bed|"
            r"\bin\s+bed\b|platform(?:\s+bed)?|rail\s+height|"
            r"side\s+rails|storage\s+rails|hb\s*h\b|fb\s*h\b|"
            r"king\s+platform|queen\s+platform|gun\s+storage|"
            r"low\s+footboard|high\s+footboard|drawer\s+storage|"
            r"leather\s+in\s+headboard|drawer\s+unit|all\s+bed\s+sizes"
        ),
    ),
    (
        KIND_CASEGOOD,
        re.compile(
            r"(?i)undermount|side\s*mount|drawer\s+slides?|cedar|"
            r"dust\s+covers?|jewel(?:ry|ery)|drawer\s+lock|"
            r"drawer\s+bottom|extra\s+drawers?|"
            r"slide\s+out\s+tray|charging\s+station|"
            r"per\s+drawer|lingerie|pocket\s+doors?|hardware\s+pull|"
            r"shelv(?:es|ing)|shelf|plywood\s+back"
        ),
    ),
    (
        KIND_NIGHTSTAND,
        re.compile(r"(?i)night\s*stand|phone\s+charger|usb\s+outlet"),
    ),
    (
        KIND_WARDROBE,
        re.compile(
            r"(?i)garment\s+bar|hanging\s+rod|clothes\s+rod|coat\s+rod|"
            r"with\s+garment"
        ),
    ),
    (
        KIND_TABLE,
        re.compile(
            r"(?i)\blea(?:f|ves)\b|lazy\s+susan|table\s+lock|"
            r"extension\s+table|butterfly|gear\s+slides?"
        ),
    ),
    (
        KIND_ISLAND,
        re.compile(r"(?i)island\s+top|plank\s+island\s+top"),
    ),
    (
        KIND_DOOR,
        re.compile(r"(?i)\bhinges?\b|soft\s+close\s+hing"),
    ),
    (
        KIND_BUFFET,
        re.compile(r"(?i)buffet\s+top|square\s+corners\s+on\s+buffet"),
    ),
    (
        KIND_BENCH,
        re.compile(r"(?i)extenda\s+bench|shaker\s+bench"),
    ),
    (
        KIND_BARSTOOL,
        re.compile(r"(?i)bar\s*stools?\s+with\s+arms"),
    ),
    (
        KIND_SEATING,
        re.compile(
            r"(?i)fabric\s+seat|cushions?|footrest|"
            r"tufted\s+fabric|crypton|seat\s+rail"
        ),
    ),
]

_UNIVERSAL_OPTION_RE = re.compile(
    r"(?i)\bunfinished\b|\bpaint\b|\bglaze\b|two[\s\-]?tone|"
    r"distress|oil\s+finish|\bstain\b|\bcat\.\s*\d+\b|"
    r"fabric\s+tier|leather\s+tier"
)
_CEDAR_OPTION_RE = re.compile(r"(?i)\bcedar\b")
_SKU_LOCKED_OPTION_RE = re.compile(r"(?i)^\s*CWF\s*#?\s*(?P<sku>\d+)")
_BARSTOOL_ARMS_OPTION_RE = re.compile(r"(?i)bar\s*stools?\s+with\s+arms")
_BARSTOOL_SEARCH_RE = re.compile(r"(?i)bar\s*stools?|bar\s*chairs?")
_HIDDEN_SEARCH_OPTION_RE = re.compile(
    r"(?i)^hidden\s+compartment$|^hidden\s+gun\s+storage\b|"
    r"if\s+ordering\s+select|consist[ae]nt\s+color|"
    r"elm\s+also\s+available|if\s+seat\s+is\s+a\s+upgraded"
)


_CAT_OPTION_RE = re.compile(r"(?i)^cat\.?\s*(\d+)$")


def order_search_options(labels: Sequence[str]) -> list[str]:
    """Cat. 1, Cat. 2, Cat. 3 stay in numeric order at the front of Search."""
    cats: list[tuple[int, str]] = []
    unfinished: list[str] = []
    rest: list[str] = []
    for label in labels:
        raw = str(label or "").strip()
        if not raw:
            continue
        match = _CAT_OPTION_RE.fullmatch(raw)
        if match:
            cats.append((int(match.group(1)), raw))
            continue
        if raw.casefold() == "unfinished":
            unfinished.append(raw)
            continue
        rest.append(raw)
    cats.sort(key=lambda item: item[0])
    return [label for _number, label in cats] + unfinished + rest


def hidden_from_search_options(label: str) -> bool:
    """Floor-hidden Options. Catalog row may remain; Search does not list them."""
    return bool(_HIDDEN_SEARCH_OPTION_RE.search(str(label or "").strip()))


def furniture_kinds_from_text(text: str) -> set[str]:
    """Piece kinds named in a search query or catalog hit."""
    blob = str(text or "")
    if not blob.strip():
        return set()
    return {kind for kind, pattern in _ITEM_KIND_PATTERNS if pattern.search(blob)}


def option_unlocked_for_search(label: str, text: str) -> bool:
    """SKU-named Options (CWF 505 …) stay hidden until that piece is searched."""
    raw = str(label or "").strip()
    blob = str(text or "")
    if _BARSTOOL_ARMS_OPTION_RE.search(raw):
        return bool(_BARSTOOL_SEARCH_RE.search(blob))
    match = _SKU_LOCKED_OPTION_RE.search(raw)
    if not match:
        return True
    sku = match.group("sku")
    if re.search(rf"(?i)cwf\s*#?\s*{re.escape(sku)}\b", blob):
        return True
    if sku == "505" and re.search(r"(?i)\bmeridian\b", blob) and re.search(r"(?i)\bbeds?\b", blob):
        return True
    return False


def option_kinds(label: str) -> set[str]:
    """Piece kinds this Option belongs to. Empty means it applies to any piece."""
    raw = str(label or "").strip()
    if not raw:
        return set()
    if _UNIVERSAL_OPTION_RE.search(raw):
        return set()
    return {kind for kind, pattern in _OPTION_KIND_PATTERNS if pattern.search(raw)}


def filter_options_for_kinds(
    options: Sequence[str],
    kinds: Iterable[str],
    text: str = "",
) -> list[str]:
    """Keep universal Options plus those that fit the searched piece kinds.

    Unknown kinds (empty set) leave the builder's full list in place so a
    SKU we cannot classify does not hide Options. SKU-named Options still
    require that piece in the search text.
    """
    wanted = {str(kind) for kind in kinds if kind}
    out: list[str] = []
    for label in options:
        if hidden_from_search_options(label):
            continue
        if not option_unlocked_for_search(label, text):
            continue
        if not wanted:
            out.append(label)
            continue
        if _CEDAR_OPTION_RE.search(str(label or "")) and KIND_BED in wanted:
            continue
        fits = option_kinds(label)
        if not fits or fits & wanted:
            out.append(label)
    return out
