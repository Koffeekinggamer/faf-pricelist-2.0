#!/usr/bin/env python3
"""Attach Viztech digital-catalog JPGs to matching pricebook SKUs.

Uses the 44 builders already in the book. Source path on Viztech:
all-builders → builder → Dealer Files → Downloads (Catalog) and
Product Photos (Download All Photos). Photo zips are the image catalog;
a SKU with no photo is expected and left blank.

Usage:
  .venv/bin/python scripts/match_viztech_catalog_images.py --harvest PATH
  .venv/bin/python scripts/match_viztech_catalog_images.py --harvest PATH --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from io import BytesIO
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.builder_profiles import vendor_slug  # noqa: E402
from backend.config import DB_PATH  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.repository import PriceBookRepository  # noqa: E402
from backend.service import PriceBookService  # noqa: E402
from backend.viztech_catalog_match import (  # noqa: E402
    load_image,
    looks_like_negative,
    match_filename_to_part,
    match_vendor_to_slug,
    photo_clarity_score,
    relative_photo_path,
    restore_negative,
)

CACHE = Path("/tmp/viztech-catalog-photos")
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def _photo_url(row: dict) -> str:
    seen: set[str] = set()
    for f in row.get("photos") or []:
        href = str(f.get("href") or "")
        if "digitaloceanspaces.com" in href and href not in seen:
            seen.add(href)
            return href
    return ""


def _save_jpeg(data: bytes, dest: Path) -> bool:
    from PIL import Image

    try:
        img = Image.open(BytesIO(data))
        rgb = img.convert("RGB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(dest, format="JPEG", quality=88, optimize=True)
        return True
    except Exception:
        return False


def restore_remaining_negatives(assets_root: Path) -> int:
    """Invert leftover PDF-extract negatives when no clear zip photo exists."""
    root = Path(assets_root) / "assets" / "catalog_images"
    if not root.is_dir():
        return 0
    n = 0
    for path in root.rglob("*.jpg"):
        try:
            img = load_image(path)
        except Exception:
            continue
        if not looks_like_negative(img):
            continue
        dest_img = restore_negative(img)
        dest_img.save(path, format="JPEG", quality=88, optimize=True)
        n += 1
    return n


def download_zip(url: str, dest: Path) -> bool:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 1000:
        return True
    r = requests.get(url, timeout=180)
    if r.status_code != 200 or len(r.content) < 1000:
        return False
    dest.write_bytes(r.content)
    return True


def process_zip(
    *,
    zip_path: Path,
    vendor: str,
    repo: PriceBookRepository,
    assets_root: Path,
    dry_run: bool,
) -> dict:
    known = {
        p
        for p in repo.list_part_numbers_for_vendor(vendor)
        if p
    }
    # Prefer sellable items; addon labels rarely have catalog photos.
    slug = vendor_slug(vendor)
    written = 0
    matched = 0
    skipped = 0
    files = 0
    if not zipfile.is_zipfile(zip_path):
        return {"vendor": vendor, "error": "not a zip", "files": 0, "matched": 0, "written": 0}
    best: dict[str, tuple[float, zipfile.ZipInfo, str]] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if Path(name).suffix.lower() not in IMAGE_EXTS:
                continue
            files += 1
            part = match_filename_to_part(name, known)
            if not part:
                skipped += 1
                continue
            try:
                img = load_image(zf.read(info))
            except Exception:
                skipped += 1
                continue
            score = photo_clarity_score(img, name)
            prev = best.get(part)
            if prev is None or score > prev[0]:
                best[part] = (score, info, name)
        matched = len(best)
        for part, (score, info, name) in best.items():
            rel = relative_photo_path(vendor, part)
            dest = assets_root / rel
            if dry_run:
                continue
            existing_score = None
            if dest.is_file() and dest.stat().st_size > 500:
                try:
                    existing_score = photo_clarity_score(load_image(dest), dest.name)
                except Exception:
                    existing_score = -999.0
            if existing_score is not None and existing_score >= score:
                repo.upsert_catalog_image(
                    vendor=vendor,
                    part_number=part,
                    image_path=rel,
                    source_file=zip_path.name,
                    match_method="filename",
                )
                written += 1
                continue
            data = zf.read(info)
            if _save_jpeg(data, dest):
                repo.upsert_catalog_image(
                    vendor=vendor,
                    part_number=part,
                    image_path=rel,
                    source_file=zip_path.name,
                    match_method="clear_catalog",
                )
                written += 1
    return {
        "vendor": vendor,
        "slug": slug,
        "files": files,
        "matched": matched,
        "skipped_unmatched": skipped,
        "written": written,
        "db_skus": len(known),
    }


def run(*, harvest_path: Path, dry_run: bool = False, assets_root: Path | None = None) -> dict:
    payload = json.loads(harvest_path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or payload.get("result", {}).get("value", {}).get("rows") or []
    slugs = [r.get("slug") for r in rows if r.get("slug")]
    by_slug = {r["slug"]: r for r in rows if r.get("slug")}
    init_db(DB_PATH)
    svc = PriceBookService()
    svc.init()
    repo = PriceBookRepository(DB_PATH)
    vendors = list(svc.list_vendors())
    assets_root = Path(assets_root) if assets_root else _ROOT
    reports = []
    missing_slug = []
    CACHE.mkdir(parents=True, exist_ok=True)

    for vendor in vendors:
        slug = match_vendor_to_slug(vendor, slugs)
        if not slug or slug not in by_slug:
            missing_slug.append(vendor)
            reports.append({"vendor": vendor, "error": "no viztech slug"})
            continue
        url = _photo_url(by_slug[slug])
        if not url:
            reports.append({"vendor": vendor, "slug": slug, "error": "no photo zip"})
            continue
        dest = CACHE / slug / "product-photos.zip"
        print("  {0} ← {1}".format(vendor, slug), flush=True)
        if not dry_run:
            ok = download_zip(url, dest)
            if not ok:
                reports.append({"vendor": vendor, "slug": slug, "error": "download failed", "url": url})
                continue
        elif not dest.is_file():
            reports.append({"vendor": vendor, "slug": slug, "error": "zip not cached", "url": url})
            continue
        reports.append(
            process_zip(
                zip_path=dest,
                vendor=vendor,
                repo=repo,
                assets_root=assets_root,
                dry_run=dry_run,
            )
        )

    restored = 0
    if not dry_run:
        restored = restore_remaining_negatives(assets_root)

    return {
        "builders": len(vendors),
        "reports": reports,
        "missing_slug": missing_slug,
        "matched_builders": sum(1 for r in reports if r.get("matched", 0) > 0),
        "written": sum(int(r.get("written") or 0) for r in reports),
        "restored_negatives": restored,
        "dry_run": dry_run,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--harvest", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    report = run(harvest_path=args.harvest, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "builders",
                    "matched_builders",
                    "written",
                    "restored_negatives",
                    "missing_slug",
                    "dry_run",
                )
            },
            indent=2,
        )
    )
    for row in report["reports"]:
        if row.get("error"):
            print("  MISS {0}: {1}".format(row.get("vendor"), row["error"]))
        else:
            print(
                "  {0}: photos={1} matched={2} written={3} book_skus={4}".format(
                    row.get("vendor"),
                    row.get("files"),
                    row.get("matched"),
                    row.get("written"),
                    row.get("db_skus"),
                )
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
