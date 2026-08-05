#!/usr/bin/env python3
"""Extract J&M portal catalog photos and match them to pricebook SKUs.

Default PDF: ~/Downloads/JM_Catalog_0326_PORTAL-compressed.pdf
Writes JPEGs under assets/catalog_images/j-and-m-woodworking/ (gitignored)
and upserts catalog_images rows for SKUs that exist in the local DB.

Usage:
  .venv/bin/python scripts/match_jm_catalog_images.py
  .venv/bin/python scripts/match_jm_catalog_images.py --pdf /path/to/file.pdf
  .venv/bin/python scripts/match_jm_catalog_images.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from io import BytesIO
from pathlib import Path

# Repo root on sys.path when run as scripts/...
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.catalog_images import (  # noqa: E402
    JM_SLUG,
    JM_VENDOR,
    catalog_image_dir,
    captions_from_words,
    match_captions_to_images,
    plan_upserts,
    product_images_from_page,
)
from backend.config import DB_PATH  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.repository import PriceBookRepository  # noqa: E402
from backend.standardize import resolve_builder_vendor  # noqa: E402

DEFAULT_PDF = (
    Path.home() / "Downloads" / "JM_Catalog_0326_PORTAL-compressed.pdf"
)


def _save_image_jpeg(stream_obj, dest: Path) -> bool:
    """Decode a pdfplumber image stream to RGB JPEG. Returns True on success."""
    from PIL import Image

    try:
        raw = stream_obj.get_data()
    except Exception:
        return False
    try:
        img = Image.open(BytesIO(raw))
        rgb = img.convert("RGB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(dest, format="JPEG", quality=88, optimize=True)
        return True
    except Exception:
        return False


def extract_page_matches(page, page_number: int):
    words = page.extract_words() or []
    captions = captions_from_words(words)
    images = product_images_from_page(page.images or [], page_number=page_number)
    matches = match_captions_to_images(captions, images)
    # Map image name → plumber image dict (for stream bytes)
    by_name = {str(im.get("name") or ""): im for im in (page.images or [])}
    return matches, by_name, len(captions), len(images)


def run(
    *,
    pdf_path: Path,
    db_path: Path,
    dry_run: bool = False,
    assets_root: Path | None = None,
) -> dict:
    import pdfplumber

    vendor = resolve_builder_vendor("jmw") or JM_VENDOR
    if vendor != JM_VENDOR:
        # Prefer the canonical pricebook name used in this catalog.
        vendor = JM_VENDOR
    init_db(db_path)
    repo = PriceBookRepository(db_path)
    known = repo.list_part_numbers_for_vendor(vendor)

    all_matches = []
    pages_processed = 0
    images_seen = 0
    captions_seen = 0
    page_streams: list[tuple] = []  # (MatchedImage, stream_dict)

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_number = i + 1
            matches, by_name, n_cap, n_img = extract_page_matches(page, page_number)
            pages_processed += 1
            captions_seen += n_cap
            images_seen += n_img
            for m in matches:
                stream_im = by_name.get(m.image.name)
                page_streams.append((m, stream_im))
                all_matches.append(m)

    plan = plan_upserts(
        all_matches,
        known_part_numbers=known,
        vendor=vendor,
        vendor_slug=JM_SLUG,
        source_file=pdf_path.name,
    )

    written = 0
    write_fail = 0
    if not dry_run:
        out_dir = catalog_image_dir(JM_SLUG, root=assets_root or _ROOT)
        out_dir.mkdir(parents=True, exist_ok=True)
        # Prefer first successful write per part_number
        written_parts: set[str] = set()
        upsert_by_sku = {
            str(u.get("_matched_sku") or u["part_number"]).lower(): u
            for u in plan["upserts"]
        }
        for m, stream_im in page_streams:
            key = m.sku.lower()
            row = upsert_by_sku.get(key)
            if row is None:
                continue
            part = row["part_number"]
            if part in written_parts:
                continue
            dest = _ROOT / row["image_path"]
            if assets_root is not None:
                dest = Path(assets_root) / row["image_path"]
            if stream_im is None or stream_im.get("stream") is None:
                write_fail += 1
                continue
            if _save_image_jpeg(stream_im["stream"], dest):
                written += 1
                written_parts.add(part)
                repo.upsert_catalog_image(
                    vendor=row["vendor"],
                    part_number=row["part_number"],
                    image_path=row["image_path"],
                    source_file=row.get("source_file"),
                    page=row.get("page"),
                    match_method=row.get("match_method"),
                    updated_at=row.get("updated_at"),
                )
            else:
                write_fail += 1

    report = {
        "pdf": str(pdf_path),
        "vendor": vendor,
        "pages_processed": pages_processed,
        "images_seen": images_seen,
        "captions_seen": captions_seen,
        "matched_pairs": len(all_matches),
        "db_sku_count": plan["db_sku_count"],
        "upserted": plan["matched_count"] if not dry_run else 0,
        "would_upsert": plan["matched_count"],
        "files_written": written,
        "write_failures": write_fail,
        "unknown_pdf_skus": plan["skipped_unknown"],
        "unknown_count": plan["unknown_count"],
        "missing_photo_count": plan["missing_photo_count"],
        "missing_photo_skus_sample": plan["missing_photo_skus"][:40],
        "dry_run": dry_run,
    }
    return report


def _print_report(report: dict) -> None:
    print(f"PDF: {report['pdf']}")
    print(f"Vendor: {report['vendor']}")
    print(f"Pages: {report['pages_processed']}")
    print(f"Product-sized images: {report['images_seen']}")
    print(f"SKU captions: {report['captions_seen']}")
    print(f"Caption↔image pairs: {report['matched_pairs']}")
    print(f"DB SKUs ({report['vendor']}): {report['db_sku_count']}")
    if report["dry_run"]:
        print(f"Would upsert: {report['would_upsert']}")
    else:
        print(f"Upserted catalog_images rows: {report['files_written']}")
        print(f"JPEG files written: {report['files_written']}")
        if report.get("would_upsert") and report["files_written"] != report["would_upsert"]:
            print(
                f"(matched known SKUs: {report['would_upsert']}; "
                f"write failures: {report['write_failures']})"
            )
    print(f"PDF SKUs with no DB row: {report['unknown_count']}")
    if report["unknown_pdf_skus"]:
        sample = ", ".join(report["unknown_pdf_skus"][:25])
        more = "" if report["unknown_count"] <= 25 else " …"
        print(f"  e.g. {sample}{more}")
    print(f"DB SKUs still missing photos: {report['missing_photo_count']}")
    if report["missing_photo_skus_sample"]:
        sample = ", ".join(report["missing_photo_skus_sample"][:25])
        more = "" if report["missing_photo_count"] <= 25 else " …"
        print(f"  e.g. {sample}{more}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--pdf",
        type=Path,
        default=DEFAULT_PDF,
        help=f"Portal catalog PDF (default: {DEFAULT_PDF})",
    )
    p.add_argument(
        "--db",
        type=Path,
        default=DB_PATH,
        help=f"SQLite path (default: {DB_PATH})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Match and report only; do not write files or DB rows",
    )
    args = p.parse_args(argv)
    if not args.pdf.is_file():
        print(f"PDF not found: {args.pdf}", file=sys.stderr)
        return 1
    report = run(pdf_path=args.pdf, db_path=args.db, dry_run=args.dry_run)
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
