"""Smart Drop parse — inventory each builder's variants from the parsed book.

Builders do not share a layout. After the layout router + standardize, this
module reads the long-form rows and reports what that book actually contains:
items, woods, stains/finishes, upcharges, and customizations. Nothing here is
a static menu — it is derived from the file just parsed (plus optional
profile parse_hints).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from backend.builder_profiles import load_builder_profile

_WOOD_RE = re.compile(
    r"(?i)\b("
    r"oak|maple|cherry|walnut|hickory|elm|birch|ash|poplar|pine|alder|"
    r"beech|mahogany|qswo|pswo|wormy|rustic|brown\s*maple|hard\s*maple|"
    r"quarter\s*sawn|barnwood|cedar"
    r")\b"
)
_FABRIC_RE = re.compile(
    r"(?i)\b(fabric|leather|crypton|poly|color|com|upholster)\b"
)


def _norm_label(val: Any) -> str:
    s = str(val or "").strip()
    if not s or s.lower() in {"none", "nan", "null"}:
        return ""
    return " ".join(s.split())


def _uniq(values: Iterable[Any], *, limit: int = 40) -> list[str]:
    seen: dict[str, str] = {}
    for raw in values:
        s = _norm_label(raw)
        if not s:
            continue
        key = s.lower()
        if key not in seen:
            seen[key] = s
        if len(seen) >= limit:
            break
    return sorted(seen.values(), key=lambda x: x.lower())


def _is_wood_species(label: str) -> bool:
    if not label or _FABRIC_RE.search(label):
        return False
    return bool(_WOOD_RE.search(label))


def _token_hit(label: str, tokens: Iterable[str]) -> bool:
    low = label.lower()
    return any(t and t.lower() in low for t in tokens)


def layouts_from_sheets(sheets_tried: Optional[list[dict]]) -> list[str]:
    found: dict[str, str] = {}
    for sheet in sheets_tried or []:
        layout = _norm_label(sheet.get("layout"))
        if not layout or layout in {"skip", "empty", "error"}:
            continue
        found.setdefault(layout.lower(), layout)
    return sorted(found.values(), key=str.lower)


def summarize_parse_variants(
    rows: list[dict],
    *,
    vendor: str = "",
    sheets_tried: Optional[list[dict]] = None,
    profile: Optional[dict] = None,
) -> dict[str, Any]:
    """Return the variant inventory for one parsed builder file."""
    prof = profile if profile is not None else load_builder_profile(vendor)
    hints = prof.get("parse_hints") or {}
    stain_tokens = list(hints.get("stain_tokens") or [])
    custom_tokens = list(hints.get("custom_tokens") or [])
    addon_tokens = list(hints.get("addon_label_tokens") or [])

    items: list[Any] = []
    woods: list[Any] = []
    finishes: list[Any] = []
    addons: list[Any] = []
    stains: list[Any] = []
    customs: list[Any] = []
    collections: list[Any] = []

    for row in rows or []:
        kind = str(row.get("line_kind") or "item").strip().lower()
        opt = _norm_label(row.get("option_key") or row.get("description"))
        if kind == "addon":
            addons.append(opt or row.get("part_number"))
            if _token_hit(opt, stain_tokens):
                stains.append(opt)
            if _token_hit(opt, custom_tokens) or _token_hit(opt, addon_tokens):
                customs.append(opt)
            continue
        items.append(row.get("part_number") or row.get("description"))
        collections.append(row.get("collection"))
        species = _norm_label(row.get("species"))
        if _is_wood_species(species):
            woods.append(species)
        elif species:
            if _token_hit(species, stain_tokens):
                stains.append(species)
            else:
                customs.append(species)
        fin = _norm_label(row.get("finish_state"))
        if fin:
            finishes.append(fin)
        if opt:
            if _token_hit(opt, stain_tokens):
                stains.append(opt)
            else:
                customs.append(opt)

    layouts = layouts_from_sheets(sheets_tried)
    return {
        "layouts": layouts,
        "items": _uniq(items, limit=80),
        "item_count": len({_norm_label(x).lower() for x in items if _norm_label(x)}),
        "woods": _uniq(woods),
        "finishes": _uniq(finishes),
        "stains": _uniq(stains),
        "addons": _uniq(addons),
        "customizations": _uniq(customs),
        "collections": _uniq(collections),
    }


def variants_caption(summary: dict[str, Any]) -> str:
    """One-line Drop preview of what the smart parse found."""
    if not summary:
        return ""
    bits = []
    if summary.get("layouts"):
        bits.append("layout " + ", ".join(summary["layouts"][:3]))
    n_items = int(summary.get("item_count") or 0)
    if n_items:
        bits.append(f"{n_items} items")
    for key, label in (
        ("woods", "woods"),
        ("stains", "stains"),
        ("addons", "upcharges"),
        ("customizations", "options"),
        ("collections", "collections"),
    ):
        vals = summary.get(key) or []
        if vals:
            bits.append(f"{len(vals)} {label}")
    return " · ".join(bits)
