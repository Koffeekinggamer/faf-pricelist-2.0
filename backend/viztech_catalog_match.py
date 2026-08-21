"""Match Viztech digital-catalog photos to pricebook SKUs.

Photo zips and catalog PDFs show a subset of the book. A SKU without a
photo is expected — do not invent a match.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, Union

from backend.builder_profiles import vendor_slug
from backend.catalog_images import is_sku_token

_HASH_NAME = re.compile(r"^[0-9a-f]{16,}\.(webp|jpg|jpeg|png)$", re.I)
_SKIP_VIEW = re.compile(
    r"(?i)room[-_\s]?setting|lifestyle|back|rear|open|detail|proc_|_side|mid-tilt"
)
_CLEAR_VIEW = re.compile(r"(?i)front|hero|studio|white|catalog")

_TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")


def norm_key(text: str) -> str:
    s = (text or "").lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", s)


def match_vendor_to_slug(vendor: str, slugs: Iterable[str]) -> Optional[str]:
    """Best Viztech builder slug for a pricebook vendor name."""
    want = norm_key(vendor)
    if not want:
        return None
    slugs = [s for s in slugs if s]
    exact = {norm_key(s): s for s in slugs}
    if want in exact:
        return exact[want]
    # Book name vs slug extras: "Criswell Bedroom" ↔ criswell-furniture
    aliases = {
        "criswellbedroom": "criswell",
        "fnchair": "fnchairsllc",
        "genuineoak": "genuineoakdesigns",
        "jandmwoodworking": "jmwoodworking",
        "jtroyerandcompany": "jtroyercompany",
        "fivestartables": "weaverwoodcraft",
        "lamb": "lambwoodworking",
        "nisleycabinetllc": "nisleycabinetsllc",
        "patiokraft": "patiokraft",
        "stoneyacresfurniture": "stoneyacresfurniture2",
        "windyacresfurniture": "windyacres",
    }
    alias = aliases.get(want)
    if alias and alias in exact:
        return exact[alias]
    for key, slug in exact.items():
        if alias and (key.startswith(alias) or alias.startswith(key)):
            return slug
        if want.startswith(key) or key.startswith(want):
            if min(len(want), len(key)) >= 8:
                return slug
    return None


def filename_sku_candidates(filename: str) -> list[str]:
    """SKU-like tokens from a catalog photo filename."""
    stem = Path(filename).stem
    stem = re.sub(r"(?i)(copy|img|image|photo|dsc|img[-_]?)\d*$", "", stem)
    parts = [p for p in _TOKEN_SPLIT.split(stem) if p]
    out: list[str] = []
    if is_sku_token(stem):
        out.append(stem)
    # Re-join common SKU shapes: BF 1648 DS → BF-1648-DS
    if len(parts) >= 2:
        joined = "-".join(parts)
        if is_sku_token(joined):
            out.append(joined)
    for p in parts:
        if is_sku_token(p):
            out.append(p)
    # keep order, unique
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    return uniq


def match_filename_to_part(
    filename: str, known_part_numbers: Iterable[str]
) -> Optional[str]:
    """Return the canonical pricebook part_number for a photo file, or None."""
    known_ci = {str(p).strip().lower(): str(p).strip() for p in known_part_numbers if str(p).strip()}
    if not known_ci:
        return None
    stem = Path(filename).stem.strip().lower()
    if stem in known_ci:
        return known_ci[stem]
    compact = re.sub(r"[^a-z0-9]+", "", stem)
    compact_map = {re.sub(r"[^a-z0-9]+", "", k): v for k, v in known_ci.items()}
    if compact and compact in compact_map:
        return compact_map[compact]
    for cand in filename_sku_candidates(filename):
        hit = known_ci.get(cand.lower())
        if hit:
            return hit
        hit = compact_map.get(re.sub(r"[^a-z0-9]+", "", cand.lower()))
        if hit:
            return hit
    # Catalog files add view suffixes: BF-1648-DS-Front.jpg, AJF-5102-RM-Back.jpg
    best = None
    best_n = 0
    for key, canon in known_ci.items():
        ck = re.sub(r"[^a-z0-9]+", "", key)
        if len(ck) < 4 or not re.search(r"\d", ck):
            continue
        if compact.startswith(ck) or ck in compact:
            if len(ck) > best_n:
                best = canon
                best_n = len(ck)
    if best:
        return best
    words = re.sub(r"[^a-z0-9]+", " ", stem)
    for key, canon in known_ci.items():
        kn = re.sub(r"[^a-z0-9]+", " ", key).strip()
        if len(kn) < 8:
            continue
        if kn in words:
            return canon
    return None


def is_catalog_download_label(label: str) -> bool:
    t = (label or "").strip().lower()
    if not t:
        return False
    if re.search(r"pricelist|price\s*list|branding|logo|cover|color\s*tool", t):
        return False
    return bool(re.search(r"catalog", t))


def relative_photo_path(vendor: str, part_number: str) -> str:
    safe = re.sub(r"[^\w.\-]+", "_", part_number.strip())
    return "assets/catalog_images/{0}/{1}.jpg".format(vendor_slug(vendor), safe)


def _corner_mean(img) -> float:
    w, h = img.size
    cw, ch = max(8, w // 8), max(8, h // 8)
    boxes = (
        (0, 0, cw, ch),
        (w - cw, 0, w, ch),
        (0, h - ch, cw, h),
        (w - cw, h - ch, w, h),
    )
    from PIL import ImageStat

    vals = []
    for box in boxes:
        crop = img.crop(box)
        vals.append(sum(ImageStat.Stat(crop).mean) / 3.0)
    return sum(vals) / 4.0


def _pixel_means(img) -> tuple[float, float, float, float]:
    from PIL import ImageStat

    stat = ImageStat.Stat(img)
    r, g, b = stat.mean[:3]
    return r, g, b, (r + g + b) / 3.0


def looks_like_negative(img) -> bool:
    """True for inverted PDF extracts (black field, not a white studio shot)."""
    rgb = img.convert("RGB")
    _r, _g, _b, mean = _pixel_means(rgb)
    corners = _corner_mean(rgb)
    if corners > 70 or mean > 90:
        return False
    # Mid-tone pixels on a real photo stay warm wood; inverted reads cool.
    w, h = rgb.size
    step = max(1, (w * h) // 2500)
    lit = [p for p in list(rgb.getdata())[::step] if sum(p) > 50]
    if len(lit) < 8:
        return mean < 45
    lr = sum(p[0] for p in lit) / len(lit)
    lb = sum(p[2] for p in lit) / len(lit)
    return lb >= lr or (corners < 40 and mean < 70)


def photo_clarity_score(img, filename: str = "") -> float:
    """Higher = clearer floor catalog shot (white studio, natural color)."""
    rgb = img.convert("RGB")
    _r, _g, _b, mean = _pixel_means(rgb)
    corners = _corner_mean(rgb)
    score = corners * 0.45 + min(mean, 210.0) * 0.35
    name = Path(filename or "").name
    if _HASH_NAME.match(name):
        score -= 80.0
    if _SKIP_VIEW.search(name):
        score -= 35.0
    if _CLEAR_VIEW.search(name):
        score += 25.0
    if looks_like_negative(rgb):
        score -= 200.0
    elif mean < 55 and corners < 40:
        score -= 120.0
    return score


def load_image(source: Union[bytes, Path]):
    from PIL import Image

    if isinstance(source, Path):
        return Image.open(source).convert("RGB")
    return Image.open(BytesIO(source)).convert("RGB")


def restore_negative(img):
    """Flip inverted catalog art back to natural wood tones."""
    from PIL import ImageOps

    return ImageOps.invert(img.convert("RGB"))
