"""Builder Profiles — durable per-builder rules (ADR-0011).

Profiles live as versioned JSON under config/builder_profiles/<slug>.json.
Charges and live category lists stay in the DB; this module loads only durable
rules (keywords, synonym overrides, parse hints, charge shapes).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from backend.config import APP_DIR

PROFILES_DIR = APP_DIR / "config" / "builder_profiles"

# Fallback when no vendor-specific profile exists — same vocabulary that lived
# hardcoded in PriceBookService before ADR-0011 (search behavior unchanged).
DEFAULT_PROFILE: dict[str, Any] = {
    "version": 1,
    "vendor": None,
    "item_upcharge_option_keywords": ["drawer", "door", "slide"],
    "drawer_door_item_keywords": [
        "drawer",
        "dresser",
        "chest",
        "night stand",
        "nightstand",
        "lingerie",
        "armoire",
        "wardrobe",
        "credenza",
        "sideboard",
        "buffet",
        "cabinet",
        "vanity",
        "hutch",
        "server",
        "console",
        "door",
    ],
    # Items matching these are never charged drawer/door options (even if they
    # also match an include keyword, e.g. "console mirror").
    "drawer_door_exclude_keywords": ["mirror"],
    "compound_item_markers": ["piece set", "pc set", "piece bedroom"],
    "category_synonym_overrides": [
        {
            "when_all": ["man", "chest"],
            "match_category_any": ["manschest"],
            "match_category_all": ["man", "chest"],
        },
        {
            "when_any": ["chifferobe", "wardrobe"],
            "match_category_any": ["armoire"],
        },
        {
            "when_any": ["tri-view", "triview", "tri view"],
            "match_category_any": ["triview"],
            "match_category_all": ["tri", "view"],
        },
        {
            "when_any": ["lingerie"],
            "match_category_any": ["lingerie"],
        },
        {
            "when_all": ["studio", "chest"],
            "match_category_any": ["studio"],
        },
    ],
}


def vendor_slug(vendor: str) -> str:
    """Canonical vendor display name → profile filename stem."""
    s = (vendor or "").lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def profile_path(vendor: str, *, root: Optional[Path] = None) -> Path:
    base = root if root is not None else PROFILES_DIR
    return base / f"{vendor_slug(vendor)}.json"


def _merge_profile(raw: dict[str, Any], vendor: str) -> dict[str, Any]:
    out = {**DEFAULT_PROFILE, **raw}
    out["vendor"] = raw.get("vendor") or vendor
    # Nested lists: prefer file when present and non-empty.
    for key in (
        "item_upcharge_option_keywords",
        "drawer_door_item_keywords",
        "drawer_door_exclude_keywords",
        "compound_item_markers",
        "category_synonym_overrides",
    ):
        if key not in raw or raw[key] is None:
            out[key] = list(DEFAULT_PROFILE[key])
        else:
            out[key] = raw[key]
    return out


@lru_cache(maxsize=64)
def _load_cached(slug: str, root_str: str) -> tuple[Any, ...]:
    """Cache by slug + root; returns a hashable-ish frozen structure via json dump."""
    root = Path(root_str)
    path = root / f"{slug}.json"
    if not path.is_file():
        return ()
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        return ()
    return (json.dumps(raw, sort_keys=True),)


def load_builder_profile(
    vendor: Optional[str],
    *,
    root: Optional[Path] = None,
) -> dict[str, Any]:
    """Load durable rules for a builder; falls back to DEFAULT_PROFILE."""
    if not vendor or not str(vendor).strip():
        return {**DEFAULT_PROFILE, "category_synonym_overrides": list(DEFAULT_PROFILE["category_synonym_overrides"])}

    vend = str(vendor).strip()
    base = root if root is not None else PROFILES_DIR
    slug = vendor_slug(vend)
    cached = _load_cached(slug, str(base.resolve()))
    if not cached:
        out = {**DEFAULT_PROFILE}
        out["vendor"] = vend
        out["category_synonym_overrides"] = list(DEFAULT_PROFILE["category_synonym_overrides"])
        out["item_upcharge_option_keywords"] = list(DEFAULT_PROFILE["item_upcharge_option_keywords"])
        out["drawer_door_item_keywords"] = list(DEFAULT_PROFILE["drawer_door_item_keywords"])
        out["drawer_door_exclude_keywords"] = list(DEFAULT_PROFILE["drawer_door_exclude_keywords"])
        out["compound_item_markers"] = list(DEFAULT_PROFILE["compound_item_markers"])
        return out
    raw = json.loads(cached[0])
    return _merge_profile(raw, vend)


def clear_profile_cache() -> None:
    _load_cached.cache_clear()


def override_applies(item_low: str, rule: dict) -> bool:
    """True when a category_synonym_overrides rule's when_* matches item text."""
    when_all = rule.get("when_all") or []
    when_any = rule.get("when_any") or []
    if when_all and not all(t in item_low for t in when_all):
        return False
    if when_any and not any(t in item_low for t in when_any):
        return False
    return bool(when_all or when_any)


def category_matches_override(cat_low: str, rule: dict) -> bool:
    """True when category label satisfies match_category_any OR match_category_all."""
    any_toks = rule.get("match_category_any") or []
    all_toks = rule.get("match_category_all") or []
    if any_toks and any(t in cat_low for t in any_toks):
        return True
    if all_toks and all(t in cat_low for t in all_toks):
        return True
    return False
