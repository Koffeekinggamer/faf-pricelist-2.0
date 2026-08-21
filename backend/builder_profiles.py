"""Builder Profiles — durable per-builder rules (ADR-0011).

Profiles live as versioned JSON under config/builder_profiles/<slug>.json.
Charges and live category lists stay in the DB; this module loads only durable
rules (keywords, synonym overrides, parse hints, charge shapes).
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, Sequence

from backend.config import APP_DIR

PROFILES_DIR = APP_DIR / "config" / "builder_profiles"
_YEAR_NOISE_RE = re.compile(
    r"(?i)[_-]?(20\d{2}|pricelist|price\s*list|pricebook|wholesale|retail|"
    r"revised|rep|digital|master).*$"
)

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
    # Alternative option families render as one choice and must never stack.
    # Builders without groups retain the generic stackable checkbox behavior.
    "option_groups": [],
    # When set, finished/unfinished is an Options checkbox, not a Finish dropdown.
    # Search defaults to `default`; checking `option_key` switches to `selects`.
    # Catalog-driven: any builder with unfinished sellable rows gets this spec
    # unless the profile already names one.
    "finish_as_option": None,
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
    "parse_hints": {
        "addon_label_tokens": [
            "option",
            "upcharge",
            "addon",
            "custom",
            "extra",
            "upgrade",
        ],
        "stain_tokens": [
            "stain",
            "paint",
            "glaze",
            "2-tone",
            "two tone",
            "rub through",
        ],
        "custom_tokens": ["custom", "special", "extra", "upgrade"],
    },
    # Named Drop parser — empty until a successful Load locks one (ADR-0011).
    "parser": {},
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
        "option_groups",
        "category_synonym_overrides",
    ):
        if key not in raw or raw[key] is None:
            out[key] = list(DEFAULT_PROFILE[key])
        else:
            out[key] = raw[key]
    if "parse_hints" not in raw or raw["parse_hints"] is None:
        out["parse_hints"] = dict(DEFAULT_PROFILE["parse_hints"])
    else:
        out["parse_hints"] = {**DEFAULT_PROFILE["parse_hints"], **raw["parse_hints"]}
    if "parser" not in raw or raw["parser"] is None:
        out["parser"] = {}
    else:
        out["parser"] = dict(raw["parser"])
    if "finish_as_option" not in raw:
        out["finish_as_option"] = DEFAULT_PROFILE["finish_as_option"]
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
        out["option_groups"] = list(DEFAULT_PROFILE["option_groups"])
        out["parse_hints"] = dict(DEFAULT_PROFILE["parse_hints"])
        out["parser"] = {}
        out["finish_as_option"] = DEFAULT_PROFILE["finish_as_option"]
        return out
    raw = json.loads(cached[0])
    return _merge_profile(raw, vend)


def clear_profile_cache() -> None:
    _load_cached.cache_clear()


def _group_matches(group: dict[str, Any], label: str) -> bool:
    pattern = str(group.get("match") or "").strip()
    if not pattern or not label:
        return False
    try:
        return bool(re.search(pattern, label, re.IGNORECASE))
    except re.error:
        return False


def single_select_group(
    profile: dict[str, Any],
    label: str,
) -> Optional[dict[str, Any]]:
    """The alternatives family a label belongs to, or None if it stacks freely."""
    for group in profile.get("option_groups") or []:
        if not isinstance(group, dict):
            continue
        if str(group.get("selection") or "single").strip().lower() != "single":
            continue
        if _group_matches(group, label):
            return group
    return None


def exclusive_option_conflicts(
    profile: dict[str, Any],
    label: str,
    selected: list[str],
) -> list[str]:
    """Options that must drop when ``label`` is picked (same single-select group)."""
    group = single_select_group(profile, label)
    if group is None:
        return []
    return [
        other
        for other in selected
        if other != label and _group_matches(group, other)
    ]


def resolve_option_groups(
    profile: dict[str, Any],
    selected: list[str],
) -> list[str]:
    """Keep at most one option per single-select group; the last pick wins."""
    kept: list[str] = []
    for label in reversed(list(selected)):
        if exclusive_option_conflicts(profile, label, kept):
            continue
        kept.append(label)
    kept.reverse()
    return kept


def finish_option_label(profile: dict[str, Any]) -> str:
    spec = profile.get("finish_as_option") or {}
    return str(spec.get("option_key") or "").strip()


CATALOG_UNFINISHED_OPTION = {
    "option_key": "Unfinished",
    "selects": "unfinished",
    "default": "finished",
}


def effective_finish_as_option(
    profile: dict[str, Any],
    *,
    finish_states: Sequence[str] = (),
) -> dict[str, Any]:
    """Profile spec wins; otherwise Unfinished is an option whenever the catalog lists it.

    Search defaults to finished when that state exists, even if unfinished is listed.
    """
    spec = profile.get("finish_as_option") or {}
    if spec and str(spec.get("option_key") or "").strip():
        return dict(spec)
    states = {str(s).strip().lower() for s in finish_states if str(s).strip()}
    if "unfinished" not in states:
        return {}
    out = dict(CATALOG_UNFINISHED_OPTION)
    if "finished" not in states:
        out["default"] = "unfinished"
    return out


def apply_finish_as_option(
    profile: dict[str, Any],
    selected: list[str],
    finish_state: Optional[str],
) -> tuple[Optional[str], list[str]]:
    """Turn the Unfinished option into a finish_state switch; it never stacks as $.

    Checking the profile's finish option selects `selects` (unfinished). Leaving
    it off uses `default` (finished), even when the UI still passes finished.
    """
    spec = profile.get("finish_as_option") or {}
    option = str(spec.get("option_key") or "").strip()
    if not option:
        return finish_state, list(selected)
    default = str(spec.get("default") or "finished").strip().lower() or "finished"
    selects = str(spec.get("selects") or "unfinished").strip().lower() or "unfinished"
    picked = False
    kept: list[str] = []
    for label in selected:
        if str(label).strip().lower() == option.lower():
            picked = True
            continue
        kept.append(label)
    if picked:
        return selects, kept
    return default, kept


def profile_writes_allowed() -> bool:
    """Local/Mac may persist learned metadata; Fly reads shipped profiles."""
    return not bool(os.environ.get("FLY_APP_NAME") or os.environ.get("FLY_ALLOC_ID"))


def filename_hints_for(vendor: str, source_file: str = "") -> list[str]:
    """Stable profile hints so next year's file resolves to the same Builder.

    Viztech ``Download_20xx_Pricelist_NNNNN`` stems are not hints — they would
    match every factory's next Drop.
    """
    hints: list[str] = []
    vend = (vendor or "").strip()
    if vend:
        hints.extend(
            [
                vend.lower(),
                vendor_slug(vend).replace("-", " ").strip(),
                re.sub(r"[^a-z0-9]+", "", vend.lower()),
            ]
        )
        try:
            from backend.catalog_readers import spec_for_vendor

            spec = spec_for_vendor(vend)
            if spec:
                hints.extend(spec.tokens())
        except Exception:
            pass
    if source_file:
        for part in re.split(r"\s+\+\s+", source_file):
            stem = Path(part).stem
            raw = stem.lower()
            initials = re.match(r"^([a-z]{2,4})[_-]pricelist", raw)
            if initials:
                hints.append(f"{initials.group(1)}_pricelist")
            stem = _YEAR_NOISE_RE.sub("", stem)
            cleaned = re.sub(r"[_\-]+", " ", stem).strip().lower()
            cleaned = re.sub(
                r"\b(download|pricelist|price list|wholesale|retail|"
                r"finished|unfinished|markup|cover)\b",
                " ",
                cleaned,
            )
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if _keep_filename_hint(cleaned):
                hints.append(cleaned)
    return list(
        dict.fromkeys(h for h in (_norm_hint(h) for h in hints) if _keep_filename_hint(h))
    )


def _norm_hint(h: str) -> str:
    return " ".join((h or "").split()).strip().lower()


def _keep_filename_hint(h: str) -> bool:
    t = _norm_hint(h)
    if len(t) < 3:
        return False
    if t in {
        "download",
        "pricelist",
        "price list",
        "wholesale",
        "retail",
        "finished",
        "unfinished",
        "markup",
        "cover",
        "catalog",
        "solo galaxy",
    }:
        return False
    if t.startswith("download "):
        return False
    if t.isdigit():
        return False
    return True


def iter_locked_profiles(*, root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Merged profiles whose parser metadata contains an importer."""
    base = root if root is not None else PROFILES_DIR
    if not base.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(base.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        vendor = str(raw.get("vendor") or path.stem.replace("-", " ").title())
        merged = _merge_profile(raw, vendor)
        if str((merged.get("parser") or {}).get("importer") or "").strip():
            out.append(merged)
    return out


def match_profile_vendor(filename: str, *, root: Optional[Path] = None) -> Optional[str]:
    """Best locked Builder whose saved filename hint appears in filename."""
    fn = (filename or "").lower()
    best: Optional[tuple[int, str]] = None
    for profile in iter_locked_profiles(root=root):
        vendor = str(profile.get("vendor") or "").strip()
        for hint in (profile.get("parser") or {}).get("filename_hints") or []:
            text = str(hint).lower().strip()
            if len(text) < 3 or text not in fn:
                continue
            candidate = (len(text), vendor)
            if best is None or candidate[0] > best[0]:
                best = candidate
    return best[1] if best else None


def list_locked_parsers(*, root: Optional[Path] = None) -> list[dict[str, str]]:
    return [
        {
            "vendor": str(profile.get("vendor") or ""),
            "importer": str((profile.get("parser") or {}).get("importer") or ""),
            "source_file": str((profile.get("parser") or {}).get("source_file") or ""),
        }
        for profile in iter_locked_profiles(root=root)
    ]


def save_parser_lock(
    vendor: str,
    *,
    importer: str,
    source_file: str = "",
    layouts: Optional[list[str]] = None,
    root: Optional[Path] = None,
) -> Optional[Path]:
    """Atomically persist safe parser metadata without weakening a settled lock."""
    from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

    vend = (vendor or "").strip()
    if not vend:
        return None
    importer_id = DEFAULT_READER_REGISTRY.infer(importer, layouts)
    base = root if root is not None else PROFILES_DIR
    if root is None and not profile_writes_allowed():
        return None
    base.mkdir(parents=True, exist_ok=True)
    path = profile_path(vend, root=base)
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}
    previous = existing.get("parser") if isinstance(existing.get("parser"), dict) else {}
    previous_id = str(previous.get("importer") or "").strip().lower()
    if (
        previous_id in DEFAULT_READER_REGISTRY.specific_ids
        and importer_id in DEFAULT_READER_REGISTRY.generic_ids
    ):
        importer_id = previous_id
    hints = [
        h
        for h in (previous.get("filename_hints") or [])
        if _keep_filename_hint(str(h))
    ]
    for hint in filename_hints_for(vend, source_file):
        if hint not in hints:
            hints.append(hint)
    existing["version"] = int(existing.get("version") or 1)
    existing["vendor"] = vend
    existing["parser"] = {
        "importer": importer_id,
        "source_file": source_file or str(previous.get("source_file") or ""),
        "filename_hints": hints,
        "layouts": [str(x) for x in (layouts or previous.get("layouts") or []) if x],
        "locked": True,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    clear_profile_cache()
    return path


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
