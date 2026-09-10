"""Exact catalog-key image binding (AGENTS.md R1–R5)."""

from __future__ import annotations

import re
from typing import Iterable, Optional, Sequence

from backend.catalog_images import is_sku_token
from backend.viztech_catalog_match import match_vendor_to_slug

_SKIP_PAGE = re.compile(
    r"(?i)\b(table of contents|contents|cover|price list cover|"
    r"wood species chart|finish chart|index)\b"
)
_KEY_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def normalize_catalog_key(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", (text or "")).upper()


def keys_match(
    *,
    part_number: str,
    item_number: str = "",
    extracted: Sequence[str],
) -> bool:
    """R1: exact normalized keys. Both fields must match when both exist."""
    got = {normalize_catalog_key(k) for k in extracted if normalize_catalog_key(k)}
    part = normalize_catalog_key(part_number)
    item = normalize_catalog_key(item_number)
    if part and item:
        return part in got and item in got
    want = part or item
    return bool(want) and want in got


def page_is_skipped_figure(text: str) -> bool:
    """R5: skip covers, contents, charts, and other unkeyed figures."""
    return bool(_SKIP_PAGE.search(text or ""))


def extract_sku_keys_from_text(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for token in _KEY_SPLIT.split(text or ""):
        if not is_sku_token(token):
            continue
        key = token.strip()
        low = key.lower()
        if low in seen:
            continue
        seen.add(low)
        out.append(key)
    return out


def viztech_image_policy(vendor: str, slugs: Optional[Iterable[str]] = None) -> dict:
    """R3/R4: scan VizTech identity; skip VizTech images only when absent."""
    slugs = list(slugs or [])
    if not slugs or match_vendor_to_slug(vendor, slugs) is None:
        return {
            "use_viztech": False,
            "log": "viztech_images_skipped: builder_not_on_viztech",
        }
    return {"use_viztech": True, "log": ""}
