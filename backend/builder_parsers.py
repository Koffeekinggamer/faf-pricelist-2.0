"""Named per-builder parsers — lock after a good Drop, reuse on the next book.

ADR-0011: the profile stores durable parse rules only (which importer to run,
filename hints, layouts seen). Charges stay in the DB. Local Drop writes the
JSON; Fly reads shipped profiles and never writes the container FS.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from backend.builder_profiles import (
    PROFILES_DIR,
    clear_profile_cache,
    load_builder_profile,
    vendor_slug,
)

PARSER_IDS = (
    "fn_chair",
    "jmw",
    "ashery_oak",
    "patio_kraft",
    "amish_aspen",
    "hillside_chair",
    "maple_lane",
    "hw_chair_markup",
    "lamb",
    "luxhome",
    "windy_acres",
    "generic",
    "pdf",
)

# Sheet layout labels → named importer (fallback when detected_importer is empty).
LAYOUT_TO_PARSER: dict[str, str] = {
    "fn_chair": "fn_chair",
    "jmw": "jmw",
    "jmw_br_maple_expand": "jmw",
    "ashery_oak": "ashery_oak",
    "ashery_oak_master_wood_expand": "ashery_oak",
    "ao_master_wood_expand": "ashery_oak",
    "patio_kraft": "patio_kraft",
    "amish_aspen": "amish_aspen",
    "hillside_chair": "hillside_chair",
    "maple_lane": "maple_lane",
    "hw_chair": "hw_chair_markup",
    "hw_chair_markup": "hw_chair_markup",
    "lamb": "lamb",
    "luxhome": "luxhome",
    "windy_acres": "windy_acres",
    "wide_species": "generic",
    "wide_finish": "generic",
    "long_flat": "generic",
    "pdf": "pdf",
}

_YEAR_NOISE_RE = re.compile(
    r"(?i)[_-]?(20\d{2}|pricelist|price\s*list|pricebook|wholesale|retail|"
    r"revised|rep|digital|master).*$"
)


def profile_writes_allowed() -> bool:
    """Local/Mac Drop may write profiles; Fly container FS is ephemeral."""
    return not bool(
        os.environ.get("FLY_APP_NAME") or os.environ.get("FLY_ALLOC_ID")
    )


def infer_importer(
    detected_importer: str = "",
    layouts: Optional[list[str]] = None,
) -> str:
    """Pick a parser id from an explicit tag or sheet layouts."""
    raw = (detected_importer or "").strip().lower()
    if raw in PARSER_IDS:
        return raw
    for layout in layouts or []:
        key = str(layout or "").strip().lower()
        if key in LAYOUT_TO_PARSER:
            return LAYOUT_TO_PARSER[key]
        for prefix, parser_id in LAYOUT_TO_PARSER.items():
            if key.startswith(prefix):
                return parser_id
    return "generic"


def filename_hints_for(vendor: str, source_file: str = "") -> list[str]:
    """Stable tokens so next year's file still resolves to this builder."""
    hints: list[str] = []
    vend = (vendor or "").strip()
    if vend:
        hints.append(vend.lower())
        slug_words = vendor_slug(vend).replace("-", " ").strip()
        if slug_words:
            hints.append(slug_words)
        compact = re.sub(r"[^a-z0-9]+", "", vend.lower())
        if len(compact) >= 3:
            hints.append(compact)
    if source_file:
        stem = Path(source_file).stem
        raw = stem.lower()
        initials = re.match(r"^([a-z]{2,4})[_-]pricelist", raw)
        if initials:
            hints.append(f"{initials.group(1)}_pricelist")
        stem = _YEAR_NOISE_RE.sub("", stem)
        stem = re.sub(r"[_\-]+", " ", stem).strip().lower()
        if len(stem) >= 3:
            hints.append(stem)
    seen: set[str] = set()
    out: list[str] = []
    for h in hints:
        h = " ".join(h.split())
        if len(h) < 3 or h in seen:
            continue
        seen.add(h)
        out.append(h)
    return out


def guess_named_parser(
    filename: str = "",
    *,
    sheet_names: Optional[list[str]] = None,
    data: Optional[bytes] = None,
) -> tuple[str, str]:
    """Built-in Drop detectors. Returns (vendor, parser_id) or ('', '')."""
    names = list(sheet_names or [])
    if not names and data and not str(filename or "").lower().endswith(".pdf"):
        try:
            from wide_import import list_excel_sheets

            names = list_excel_sheets(data)
        except Exception:
            names = []
    from backend.ashery_oak_import import looks_like_ashery_oak

    if looks_like_ashery_oak(filename, names):
        return "Ashery Oak", "ashery_oak"
    from backend.jmw_import import looks_like_jmw

    if looks_like_jmw(filename, names):
        return "J & M Woodworking", "jmw"
    from backend.fn_chair_import import looks_like_fn_level_one

    if looks_like_fn_level_one(filename, names):
        return "FN Chair", "fn_chair"
    return "", ""


def preferred_parser_for(
    vendor: str = "",
    *,
    filename: str = "",
    root: Optional[Path] = None,
) -> str:
    """Return the locked importer id for this builder, or empty if none."""
    vend = (vendor or "").strip()
    if not vend and filename:
        vend = match_vendor_from_saved_parsers(filename, root=root) or ""
    if not vend:
        return ""
    prof = load_builder_profile(vend, root=root)
    parser = prof.get("parser") or {}
    importer = str(parser.get("importer") or "").strip().lower()
    if importer in PARSER_IDS:
        return importer
    return ""


def match_vendor_from_saved_parsers(
    filename: str,
    *,
    root: Optional[Path] = None,
) -> Optional[str]:
    """Best vendor whose locked filename_hints appear in this file name."""
    fn = (filename or "").lower()
    if not fn:
        return None
    best: Optional[tuple[int, str]] = None
    for prof in iter_locked_profiles(root=root):
        vendor = str(prof.get("vendor") or "").strip()
        if not vendor:
            continue
        for hint in (prof.get("parser") or {}).get("filename_hints") or []:
            h = str(hint).lower().strip()
            if len(h) < 3 or h not in fn:
                continue
            cand = (len(h), vendor)
            if best is None or cand[0] > best[0]:
                best = cand
    return best[1] if best else None


def iter_locked_profiles(*, root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Raw profile dicts that have a named parser locked."""
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
        importer = str((raw.get("parser") or {}).get("importer") or "").strip()
        if importer:
            if not raw.get("vendor"):
                raw["vendor"] = path.stem.replace("-", " ").title()
            out.append(raw)
    return out


def list_locked_parsers(*, root: Optional[Path] = None) -> list[dict[str, str]]:
    """UI/status: [{vendor, importer, source_file}, ...]."""
    rows = []
    for prof in iter_locked_profiles(root=root):
        parser = prof.get("parser") or {}
        rows.append(
            {
                "vendor": str(prof.get("vendor") or ""),
                "importer": str(parser.get("importer") or ""),
                "source_file": str(parser.get("source_file") or ""),
            }
        )
    return rows


def save_named_parser(
    vendor: str,
    *,
    importer: str,
    source_file: str = "",
    layouts: Optional[list[str]] = None,
    root: Optional[Path] = None,
) -> Optional[Path]:
    """Write/refresh that builder's named parser. No charges. Local only."""
    vend = (vendor or "").strip()
    if not vend:
        return None
    importer_id = infer_importer(importer, layouts)
    base = root if root is not None else PROFILES_DIR
    if root is None and not profile_writes_allowed():
        return None
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{vendor_slug(vend)}.json"
    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (OSError, json.JSONDecodeError):
            existing = {}
    prev = existing.get("parser") if isinstance(existing.get("parser"), dict) else {}
    hints = list(prev.get("filename_hints") or [])
    for h in filename_hints_for(vend, source_file):
        if h not in hints:
            hints.append(h)
    existing["version"] = int(existing.get("version") or 1)
    existing["vendor"] = vend
    existing["parser"] = {
        "importer": importer_id,
        "source_file": source_file or str(prev.get("source_file") or ""),
        "filename_hints": hints,
        "layouts": [str(x) for x in (layouts or prev.get("layouts") or []) if x],
        "locked": True,
    }
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    clear_profile_cache()
    return path


def run_named_parser(
    parser_id: str,
    data: bytes,
    *,
    vendor: str = "",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
):
    """Run a locked importer. Returns None for generic (caller falls through)."""
    pid = (parser_id or "").strip().lower()
    if pid in {"", "generic", "pdf"}:
        return None
    kwargs = {
        "vendor": vendor,
        "default_collection": default_collection,
        "sheet_filter": sheet_filter,
        "filename": filename,
    }
    if pid == "fn_chair":
        from backend.fn_chair_import import import_fn_chair_workbook

        return import_fn_chair_workbook(data, **kwargs)
    if pid == "jmw":
        from backend.jmw_import import import_jmw_workbook

        return import_jmw_workbook(data, **kwargs)
    if pid == "ashery_oak":
        from backend.ashery_oak_import import import_ashery_oak_workbook

        return import_ashery_oak_workbook(data, **kwargs)

    from wide_import import (
        import_amish_aspen_workbook,
        import_hillside_chair_workbook,
        import_hw_chair_workbook,
        import_lamb_workbook,
        import_luxhome_workbook,
        import_maple_lane_workbook,
        import_patio_kraft_workbook,
        import_windy_acres_workbook,
    )

    dispatch = {
        "patio_kraft": import_patio_kraft_workbook,
        "amish_aspen": import_amish_aspen_workbook,
        "hillside_chair": import_hillside_chair_workbook,
        "maple_lane": import_maple_lane_workbook,
        "hw_chair_markup": import_hw_chair_workbook,
        "lamb": import_lamb_workbook,
        "luxhome": import_luxhome_workbook,
        "windy_acres": import_windy_acres_workbook,
    }
    fn = dispatch.get(pid)
    if fn is None:
        return None
    return fn(data, **kwargs)
