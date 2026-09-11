"""Inventory of factory identity claims. Guards collisions before factory 49+.

``identify_reader`` remains the Drop runtime seam (profile lock first, else
guess). This module is the single read-only inventory of every map that can
name a factory — VENDOR_CANON, filename-hint leftovers, CATALOG_SPECS tokens,
profile filename_hints, and registry detect — so pytest fails when two
factories claim the same short token or detector path.

It does not become a fifth write-map. Callers still resolve identity through
``identify_reader``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

SHORT_TOKEN_MAX_LEN = 4
WATCHED_SHORT_TOKENS = (
    "ac",
    "ao",
    "fnc",
    "jmw",
    "tdc",
    "cvh",
    "dcd",
    "hts",
    "cwf",
    "mws",
    "lamb",
)

_DOWNLOAD_LEAF_RE = re.compile(r"(?i)^download(?:[\s_-]|$)")
_VIZTECH_NOISE_RE = re.compile(
    r"(?i)\b(download|pricelist|price\s*list|wholesale|retail|finished|"
    r"unfinished|markup|cover|catalog)\b|\b20\d{2}\b|\d{3,}"
)
_ANON_DOWNLOAD_LABEL_RE = re.compile(
    r"(?i)^download(?:\s+20\d{2})?(?:\s+(?:unfinished|finished))?(?:\s+\d+)?$"
)
_SHORT_TOKEN_RE = re.compile(r"^[a-z]{2,4}$")
_SHORT_TOKEN_PREFIX_RE = re.compile(r"^[a-z]{2,4}[_\s-]")


@dataclass(frozen=True)
class IdentityClaim:
    vendor: str
    token: str
    source: str
    parser_id: str = ""


@dataclass(frozen=True)
class ReaderHit:
    vendor: str
    parser_id: str


def is_viztech_download_stem(filename: str = "") -> bool:
    """True when the leaf is a Viztech Download_* stem with no factory token."""
    name = (filename or "").replace("\\", "/").strip()
    if not name:
        return False
    leaf = name.rsplit("/", 1)[-1]
    if not _DOWNLOAD_LEAF_RE.match(leaf) and not _DOWNLOAD_LEAF_RE.match(name):
        return False
    stem = Path(leaf).stem
    cleaned = _VIZTECH_NOISE_RE.sub(" ", stem.replace("_", " ").replace("-", " "))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned == ""


def is_anonymous_download_label(label: str = "") -> bool:
    """True for leftover vendor strings minted from a Download_* stem."""
    text = re.sub(r"[\s_-]+", " ", (label or "").strip()).strip()
    if not text:
        return False
    if _ANON_DOWNLOAD_LABEL_RE.fullmatch(text):
        return True
    return is_viztech_download_stem(text) or is_viztech_download_stem(f"{text}.xlsx")


def _norm_token(token: str) -> str:
    return re.sub(r"\s+", " ", (token or "").strip().lower())


def is_short_token(token: str) -> bool:
    text = _norm_token(token)
    if not text:
        return False
    if _SHORT_TOKEN_RE.fullmatch(text):
        return True
    return bool(_SHORT_TOKEN_PREFIX_RE.match(text))


def identity_claims() -> tuple[IdentityClaim, ...]:
    """Every discrete token the four identity maps currently claim."""
    from backend.builder_profiles import iter_locked_profiles
    from backend.builder_reader_registry import DEFAULT_READER_REGISTRY
    from backend.catalog_readers import CATALOG_SPECS
    from backend.standardize import VENDOR_CANON

    claims: list[IdentityClaim] = []
    for key, vendor in VENDOR_CANON.items():
        token = _norm_token(key)
        if token:
            claims.append(IdentityClaim(vendor, token, "vendor_canon"))

    for spec in CATALOG_SPECS:
        for token in spec.tokens():
            claims.append(
                IdentityClaim(spec.vendor, _norm_token(token), "catalog_token", spec.parser_id)
            )

    for profile in iter_locked_profiles():
        vendor = str(profile.get("vendor") or "").strip()
        parser = profile.get("parser") or {}
        importer = str(parser.get("importer") or "").strip().lower()
        for hint in parser.get("filename_hints") or []:
            token = _norm_token(str(hint))
            if token:
                claims.append(IdentityClaim(vendor, token, "profile_hint", importer))

    for entry in DEFAULT_READER_REGISTRY.entries:
        if not entry.specific or not entry.vendor:
            continue
        token = _norm_token(entry.parser_id)
        if token:
            claims.append(
                IdentityClaim(entry.vendor, token, "parser_id", entry.parser_id)
            )
    return tuple(claims)


def known_builders() -> frozenset[str]:
    """Canonical factory names currently claimed by any identity map."""
    return frozenset(claim.vendor for claim in identity_claims() if claim.vendor)


def short_token_claims(
    claims: Sequence[IdentityClaim] | None = None,
) -> tuple[IdentityClaim, ...]:
    items = claims if claims is not None else identity_claims()
    return tuple(claim for claim in items if is_short_token(claim.token))


def token_collisions(
    claims: Sequence[IdentityClaim] | None = None,
) -> dict[str, tuple[IdentityClaim, ...]]:
    """Tokens claimed by two or more distinct vendors."""
    items = claims if claims is not None else identity_claims()
    by_token: dict[str, list[IdentityClaim]] = defaultdict(list)
    for claim in items:
        if claim.token:
            by_token[claim.token].append(claim)
    return {
        token: tuple(group)
        for token, group in by_token.items()
        if len({claim.vendor for claim in group}) > 1
    }


def matching_filename_hint_vendors(filename: str) -> tuple[str, ...]:
    """Every VENDOR_FILENAME_HINTS canon that matches this path (not first-win)."""
    from backend.standardize import _VENDOR_FILENAME_HINTS, Path_stem_safe

    fn = (filename or "").strip()
    if not fn:
        return ()
    stem = Path_stem_safe(fn)
    vendors: list[str] = []
    seen: set[str] = set()
    for rx, canon in _VENDOR_FILENAME_HINTS:
        if rx.search(stem) or rx.search(fn):
            if canon not in seen:
                seen.add(canon)
                vendors.append(canon)
    return tuple(vendors)


def matching_readers(
    filename: str,
    *,
    sheet_names: Optional[Sequence[str]] = None,
    data: Optional[bytes] = None,
) -> tuple[ReaderHit, ...]:
    """Every specific registry detector that claims this filename."""
    from backend.builder_reader_registry import DEFAULT_READER_REGISTRY

    hits = DEFAULT_READER_REGISTRY.detect_all(
        filename,
        sheet_names=list(sheet_names or []),
        data=data,
    )
    return tuple(ReaderHit(vendor, parser_id) for vendor, parser_id in hits)


def next_year_probe_filenames(
    claims: Sequence[IdentityClaim] | None = None,
) -> tuple[str, ...]:
    """Synthetic next-year filenames derived from the live identity inventory."""
    items = claims if claims is not None else identity_claims()
    probes: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            probes.append(name)

    for vendor in sorted({claim.vendor for claim in items if claim.vendor}):
        _add(f"{vendor} 2028 Pricelist.xlsx")
    for claim in items:
        if _SHORT_TOKEN_RE.fullmatch(claim.token):
            _add(f"{claim.token.upper()}_2028_Pricelist.xlsx")
        elif is_short_token(claim.token):
            compact = re.sub(r"[\s]+", "_", claim.token)
            _add(f"{compact}_2028.xlsx")
    return tuple(probes)


def detector_path_collisions(
    filenames: Iterable[str] | None = None,
    *,
    sheet_names_for: Optional[dict[str, Sequence[str]]] = None,
) -> dict[str, tuple[ReaderHit, ...]]:
    """Filenames claimed by two or more specific readers."""
    paths = list(filenames if filenames is not None else next_year_probe_filenames())
    sheets = sheet_names_for or {}
    out: dict[str, tuple[ReaderHit, ...]] = {}
    for path in paths:
        hits = matching_readers(path, sheet_names=list(sheets.get(path) or []))
        if len({hit.parser_id for hit in hits}) > 1:
            out[path] = hits
    return out
