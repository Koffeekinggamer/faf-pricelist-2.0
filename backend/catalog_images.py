"""Match builder-catalog PDF photos to pricebook SKUs.

Pure helpers are unit-tested without a real PDF. The CLI script drives
pdfplumber extraction and upserts into ``catalog_images``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

from backend.config import APP_DIR

# Caption left-of-pipe token must look like a catalog SKU (contains a digit).
SKU_TOKEN_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?$")
SKU_HAS_DIGIT_RE = re.compile(r"\d")

# Skip tiny icons / logos (PDF points).
MIN_IMAGE_WIDTH = 80.0
MIN_IMAGE_HEIGHT = 80.0

JM_VENDOR = "J & M Woodworking"
JM_SLUG = "j-and-m-woodworking"


@dataclass(frozen=True)
class CaptionHit:
    sku: str
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class ImageHit:
    name: str
    x0: float
    top: float
    x1: float
    bottom: float
    width: float
    height: float
    page: int


@dataclass(frozen=True)
class MatchedImage:
    sku: str
    image: ImageHit
    page: int
    match_method: str = "nearest_caption"


def catalog_image_dir(vendor_slug: str = JM_SLUG, *, root: Optional[Path] = None) -> Path:
    base = Path(root) if root else APP_DIR
    return base / "assets" / "catalog_images" / vendor_slug


def relative_image_path(sku: str, vendor_slug: str = JM_SLUG) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", (sku or "").strip())
    return f"assets/catalog_images/{vendor_slug}/{safe}.jpg"


def is_sku_token(token: str) -> bool:
    t = (token or "").strip()
    if not t or not SKU_TOKEN_RE.match(t):
        return False
    return bool(SKU_HAS_DIGIT_RE.search(t))


def _dedupe_captions_keep_first(hits: list[CaptionHit]) -> list[CaptionHit]:
    seen: set[tuple[str, int, int]] = set()
    out: list[CaptionHit] = []
    for h in hits:
        key = (h.sku, int(h.top), int(h.x0))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def captions_from_words(words: Sequence[dict]) -> list[CaptionHit]:
    """Find ``SKU | …`` captions from pdfplumber ``extract_words()`` output.

    A caption is a SKU-like word immediately left of a ``|`` on the same line.
    Uses geometric nearest-left (not list order) because PDF tops can differ by
    ~1pt between the SKU and the pipe.
    """
    if not words:
        return []
    hits: list[CaptionHit] = []
    for w in words:
        if (w.get("text") or "").strip() != "|":
            continue
        w_top = float(w.get("top", 0))
        w_x0 = float(w.get("x0", 0))
        best = None
        best_gap = float("inf")
        for prev in words:
            sku = (prev.get("text") or "").strip()
            if sku == "|" or not sku:
                continue
            if abs(float(prev.get("top", 0)) - w_top) > 4.0:
                continue
            prev_x1 = float(prev.get("x1", 0))
            if prev_x1 > w_x0 + 1.0:
                continue
            gap = w_x0 - prev_x1
            if gap < 0 or gap > 40.0:
                continue
            # Prefer product captions (taller) over "Shown in … | finish" lines.
            prev_h = float(prev.get("height") or 0) or (
                float(prev.get("bottom", 0)) - float(prev.get("top", 0))
            )
            if prev_h and prev_h < 9.0:
                continue
            if gap < best_gap:
                best_gap = gap
                best = prev
        if best is None:
            continue
        sku = (best.get("text") or "").strip()
        if not is_sku_token(sku):
            continue
        hits.append(
            CaptionHit(
                sku=sku,
                x0=float(best.get("x0", 0)),
                top=float(best.get("top", 0)),
                x1=float(w.get("x1", best.get("x1", 0))),
                bottom=float(max(float(best.get("bottom", 0)), float(w.get("bottom", 0)))),
            )
        )
    return _dedupe_captions_keep_first(hits)


def product_images_from_page(
    images: Sequence[dict], *, page_number: int
) -> list[ImageHit]:
    """Filter pdfplumber page images down to product-sized photos."""
    out: list[ImageHit] = []
    for im in images or []:
        w = float(im.get("width") or 0)
        h = float(im.get("height") or 0)
        if w < MIN_IMAGE_WIDTH or h < MIN_IMAGE_HEIGHT:
            continue
        out.append(
            ImageHit(
                name=str(im.get("name") or ""),
                x0=float(im.get("x0") or 0),
                top=float(im.get("top") or 0),
                x1=float(im.get("x1") or 0),
                bottom=float(im.get("bottom") or 0),
                width=w,
                height=h,
                page=int(page_number),
            )
        )
    return out


def primary_captions(captions: Sequence[CaptionHit]) -> list[CaptionHit]:
    """Drop secondary SKUs on the same caption line (e.g. ``w/ 2013 | Storage``).

    Two products side-by-side keep both captions when they are far apart horizontally.
    """
    ordered = sorted(captions, key=lambda c: (round(c.top, 1), c.x0))
    out: list[CaptionHit] = []
    for c in ordered:
        if (
            out
            and abs(out[-1].top - c.top) <= 3.0
            and (c.x0 - out[-1].x0) < 220.0
        ):
            continue
        out.append(c)
    return out


def match_captions_to_images(
    captions: Sequence[CaptionHit],
    images: Sequence[ImageHit],
) -> list[MatchedImage]:
    """Pair each primary caption with the nearest product image above it."""
    captions = primary_captions(captions)
    if not captions or not images:
        return []
    used: set[int] = set()
    matches: list[MatchedImage] = []
    for cap in sorted(captions, key=lambda c: (c.top, c.x0)):
        best_i: Optional[int] = None
        best_dist = float("inf")
        cx = (cap.x0 + cap.x1) / 2.0
        for i, im in enumerate(images):
            if i in used:
                continue
            # Image should sit above (or barely overlapping) the caption.
            if im.bottom > cap.top + 8.0:
                continue
            ix = (im.x0 + im.x1) / 2.0
            # Caption under image column (left-aligned labels OK for narrow photos).
            horiz_ok = (
                abs(ix - cx) <= max(im.width * 0.75, 140.0)
                or (im.x0 - 100.0 <= cap.x0 <= im.x1 + 20.0)
            )
            if not horiz_ok:
                continue
            dy = max(0.0, cap.top - im.bottom)
            if dy > 140.0:
                continue
            dist = dy * dy + (cx - ix) * (cx - ix)
            if dist < best_dist:
                best_dist = dist
                best_i = i
        if best_i is None:
            continue
        used.add(best_i)
        matches.append(
            MatchedImage(
                sku=cap.sku,
                image=images[best_i],
                page=images[best_i].page,
                match_method="nearest_caption",
            )
        )
    return matches


def plan_upserts(
    matched: Sequence[MatchedImage],
    *,
    known_part_numbers: Iterable[str],
    vendor: str = JM_VENDOR,
    vendor_slug: str = JM_SLUG,
    source_file: str = "",
) -> dict:
    """Decide which matched SKUs should upsert vs skip.

    Returns a coverage dict with ``upserts`` (list of row dicts), ``skipped_unknown``,
    and summary counts. Does not touch the DB or filesystem.
    """
    known = {str(p).strip() for p in known_part_numbers if str(p).strip()}
    # Case-insensitive lookup → canonical DB spelling.
    known_ci = {k.lower(): k for k in known}

    upserts: list[dict] = []
    skipped_unknown: list[str] = []
    seen_sku: set[str] = set()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for m in matched:
        sku_raw = (m.sku or "").strip()
        if not sku_raw:
            continue
        key = sku_raw.lower()
        if key in seen_sku:
            continue
        seen_sku.add(key)
        canon = known_ci.get(key)
        if canon is None:
            skipped_unknown.append(sku_raw)
            continue
        upserts.append(
            {
                "vendor": vendor,
                "part_number": canon,
                "image_path": relative_image_path(canon, vendor_slug),
                "source_file": source_file,
                "page": int(m.page),
                "match_method": m.match_method,
                "updated_at": now,
                "_matched_sku": sku_raw,
                "_image_name": m.image.name,
            }
        )

    matched_skus = {u["part_number"] for u in upserts}
    missing_photos = sorted(known - matched_skus)
    return {
        "vendor": vendor,
        "upserts": upserts,
        "skipped_unknown": sorted(set(skipped_unknown)),
        "matched_count": len(upserts),
        "unknown_count": len(set(skipped_unknown)),
        "db_sku_count": len(known),
        "missing_photo_skus": missing_photos,
        "missing_photo_count": len(missing_photos),
    }
