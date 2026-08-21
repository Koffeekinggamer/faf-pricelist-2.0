"""Build human-facing product descriptions from canonical catalog rows.

The importer keeps SKU, collection, dimensions, woods, finishes, and Options in
separate fields.  This module uses the visible human context without making
callers understand each builder's spreadsheet layout.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional


_PLACEHOLDER = re.compile(
    r"(?i)^(?:nan|nat|none|null|options?|finished|unfinished|finish|price|"
    r"wholesale|retail)$"
)
_GENERIC_COLLECTION = re.compile(
    r"(?i)^(?:addons?|casegoods|catalog|furniture|prices?|price\s*list|pricelist|"
    r"products?|seating|standard|wholesale|retail)$"
)
_MACHINE_NOTE = re.compile(
    r"(?i)(?:^|[;\s])(?:finish_est|source|parser|imported_at|layout|"
    r"sheet|markup|multiplier)\s*="
)
_JUNK_CONTEXT = re.compile(
    r"(?i)(?:\b(?:wholesale|retail|prices?|price\s*list|pricelist|matrix)\b|"
    r"^item\s*(?:no\.?|#)$|^master\s+in\s+progress$|"
    r"^unfinished\s+from\b|^additional\s+shapes?\s+available\b)"
)
_DIMENSION = re.compile(
    r"""(?ix)^
    (?:
        \d+(?:[./\s½¼¾⅛⅜⅝⅞-]+\d*)?["']?
        (?:\s*(?:x|×)\s*
            \d+(?:[./\s½¼¾⅛⅜⅝⅞-]+\d*)?["']?
        ){0,3}
        (?:\s*(?:w|d|h|wide|deep|high|tv\s*opening))?
    )$
    """
)
_WORD = re.compile(r"[a-z0-9]+")


def _text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value).strip())
    if not text or _PLACEHOLDER.fullmatch(text):
        return None
    return text


def _tokens(value: str) -> set[str]:
    tokens = set()
    for token in _WORD.findall(value.lower()):
        if len(token) <= 1:
            continue
        if token.endswith("s") and len(token) > 3:
            token = token[:-1]
        tokens.add(token)
    return tokens


def _human_name(value: str) -> bool:
    words = re.findall(r"[A-Za-z]{3,}", value or "")
    return len(words) >= 2


def _same_or_contained(candidate: str, existing: list[str]) -> bool:
    cand = re.sub(r"[^a-z0-9]+", " ", candidate.lower()).strip()
    if not cand:
        return True
    for value in existing:
        current = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
        if cand == current or cand in current or current in cand:
            return True
        cand_tokens = _tokens(candidate)
        current_tokens = _tokens(value)
        if cand_tokens and cand_tokens.issubset(current_tokens):
            return True
    return False


def _human_note(value: Any) -> Optional[str]:
    note = _text(value)
    if not note or _MACHINE_NOTE.search(note) or _JUNK_CONTEXT.search(note):
        return None
    if re.fullmatch(r"(?i)(?:no\s+)?upcharge|n/?a", note):
        return None
    return note


def human_description(row: Mapping[str, Any]) -> Optional[str]:
    """Return one readable description using only canonical visible-source fields.

    Structured filter values (wood, finish, Option) are deliberately excluded.
    Addon labels are already purpose-built and pass through unchanged.
    """

    description = _text(row.get("description"))
    part = _text(row.get("part_number"))
    if str(row.get("line_kind") or "item").strip().lower() == "addon":
        return description or part

    collection = _text(row.get("collection"))
    dimensions = _text(row.get("dimensions"))
    note = _human_note(row.get("notes"))

    desc_is_part = bool(
        description
        and part
        and re.sub(r"\W+", "", description.lower())
        == re.sub(r"\W+", "", part.lower())
        and not _human_name(description)
    )
    desc_is_dimension = bool(description and _DIMENSION.fullmatch(description))

    pieces: list[str] = []
    if description and not desc_is_part and not desc_is_dimension:
        pieces.append(description)

    if (
        collection
        and not _GENERIC_COLLECTION.fullmatch(collection)
        and not _JUNK_CONTEXT.search(collection)
    ):
        if not _same_or_contained(collection, pieces):
            pieces.append(collection)

    dimension_context = dimensions
    if not dimension_context and desc_is_dimension:
        dimension_context = description
    if dimension_context and not _same_or_contained(dimension_context, pieces):
        pieces.append(dimension_context)

    if note and not _same_or_contained(note, pieces):
        pieces.append(note)

    if not pieces:
        fallback = description or collection or dimensions or part
        if fallback:
            return fallback
        vendor = _text(row.get("vendor"))
        return f"{vendor} catalog item" if vendor else None
    return " — ".join(pieces)
