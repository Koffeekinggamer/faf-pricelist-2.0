"""Named per-builder parsers — lock after a good Drop, reuse on the next book.

ADR-0011: the profile stores durable parse rules only (which importer to run,
filename hints, layouts seen). Charges stay in the DB. Local Drop writes the
JSON; Fly reads shipped profiles and never writes the container FS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

from backend.builder_profiles import (
    filename_hints_for as _profile_filename_hints_for,
    iter_locked_profiles as _profile_iter_locked_profiles,
    list_locked_parsers as _profile_list_locked_parsers,
    load_builder_profile,
    match_profile_vendor,
    profile_writes_allowed as _profile_writes_allowed,
    save_parser_lock,
)
from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

PARSER_IDS = DEFAULT_READER_REGISTRY.parser_ids
GENERIC_PARSER_IDS = DEFAULT_READER_REGISTRY.generic_ids
SPECIFIC_PARSER_IDS = DEFAULT_READER_REGISTRY.specific_ids

def profile_writes_allowed() -> bool:
    """Local/Mac Drop may write profiles; Fly container FS is ephemeral."""
    return _profile_writes_allowed()


def infer_importer(
    detected_importer: str = "",
    layouts: Optional[list[str]] = None,
) -> str:
    """Pick a parser id from an explicit tag or sheet layouts."""
    return DEFAULT_READER_REGISTRY.infer(detected_importer, layouts)


def filename_hints_for(vendor: str, source_file: str = "") -> list[str]:
    """Stable tokens so next year's file still resolves to this builder."""
    return _profile_filename_hints_for(vendor, source_file)


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
    return DEFAULT_READER_REGISTRY.detect(
        filename, sheet_names=names, data=data
    )


def identify_reader(
    filename: str = "",
    *,
    sheet_names: Optional[Sequence[str]] = None,
    data: Optional[bytes] = None,
    vendor: str = "",
    vendor_override: str = "",
    preferred_parser: str = "",
    root: Optional[Path] = None,
    allow_guess: bool = True,
) -> tuple[str, str, str]:
    """One Drop identity seam: Builder + named parser + source (saved|guessed|'').

    Preview and import_workbook both call this so lock, filename hints, and
    content detect cannot drift.
    """
    from backend.standardize import resolve_builder_vendor

    name = filename or ""
    typed = (vendor_override or "").strip()
    vend = resolve_builder_vendor(typed or vendor or name, filename=name) or (vendor or "").strip()
    if not vend or not preferred_parser_for(vend, root=root):
        hinted = match_vendor_from_saved_parsers(name, root=root)
        if hinted:
            vend = hinted
    if typed and not preferred_parser_for(vend or "", root=root):
        vend = resolve_builder_vendor(typed, filename=name) or typed
    vend = vend or Path(name).stem

    chosen = (preferred_parser or "").strip().lower()
    source = ""
    if not chosen:
        locked = preferred_parser_for(vend, filename=name, root=root)
        if locked:
            chosen = locked
            source = "saved"
    else:
        source = "saved"
    if not chosen and allow_guess:
        det_vendor, det_id = guess_named_parser(
            name, sheet_names=list(sheet_names or []), data=data
        )
        if det_id:
            chosen = det_id
            source = "guessed"
            if not typed:
                vend = resolve_builder_vendor(det_vendor, filename=name) or det_vendor or vend
    return vend, chosen, source


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
    return match_profile_vendor(filename, root=root)


def iter_locked_profiles(*, root: Optional[Path] = None) -> list[dict[str, Any]]:
    """Raw profile dicts that have a named parser locked."""
    return _profile_iter_locked_profiles(root=root)


def list_locked_parsers(*, root: Optional[Path] = None) -> list[dict[str, str]]:
    """UI/status: [{vendor, importer, source_file}, ...]."""
    return _profile_list_locked_parsers(root=root)


def save_named_parser(
    vendor: str,
    *,
    importer: str,
    source_file: str = "",
    layouts: Optional[list[str]] = None,
    root: Optional[Path] = None,
) -> Optional[Path]:
    """Write/refresh that builder's named parser. No charges. Local only.

    A settled builder never loses its named parser to a fallthrough Load: an
    incoming `generic`/`pdf` cannot overwrite a specific importer.
    """
    return save_parser_lock(
        vendor,
        importer=importer,
        source_file=source_file,
        layouts=layouts,
        root=root,
    )


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
    return DEFAULT_READER_REGISTRY.run(
        parser_id,
        data,
        vendor=vendor,
        default_collection=default_collection,
        sheet_filter=sheet_filter,
        filename=filename,
    )
