"""Load builders corrected by the all-source Options audit.

Read-only by default. Pass ``--apply`` after reviewing row and Option counts.
Hidden sheets/rows are never read by the locked parser path.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import PriceBookService
from backend.config import DB_PATH
from backend.import_service import ImportService

VIZTECH = Path(
    "/Users/lordjudsonmiller/Documents/viztech-downloads/all-20260717"
)

SOURCES = {
    "Black Horse Furniture": (
        "black_horse_furniture",
        (
            VIZTECH
            / "Black_Horse_Furniture"
            / "Download_2026_Pricelist_286628.xlsx",
        ),
    ),
    "INTEG Wood Products": (
        "integ_wood_products",
        (
            VIZTECH
            / "INTEG_Wood_Products"
            / "Download_2026_Pricelist_8630.xls",
        ),
    ),
    "Kidron Woodcraft": (
        "kidron_woodcraft",
        (
            VIZTECH
            / "Kidron_Woodcraft"
            / "Download_2026_Pricelists_3224_unzipped"
            / "Solo Galaxy.xlsx",
        ),
    ),
    "Mirror Lake Woodworks": (
        "mirror_lake_woodworks",
        (
            VIZTECH
            / "Mirror_Lake_Woodworks"
            / "Download_2026_Finished_Pricelist_695517.xls",
            VIZTECH
            / "Mirror_Lake_Woodworks"
            / "Download_2026_Unfinished_Pricelist_695524.xls",
        ),
    ),
    "Old Town Oak": (
        "old_town_oak",
        (VIZTECH / "Old_Town_Oak" / "Download_2026_Pricelist_9411.xlsx",),
    ),
    "Signature Designs": (
        "signature_designs",
        (
            VIZTECH
            / "Signature_Designs"
            / "Download_2025_Pricelist_478597.xlsx",
        ),
    ),
    "Criswell Bedroom": (
        "criswell",
        tuple(
            Path("/Users/lordjudsonmiller/Downloads/CWF_Pricelists_2025_1224")
            / name
            for name in (
                "Wholesale Price List.xlsx",
                "Beds A-F.xlsx",
                "Beds H-W.xlsx",
                "Living Rooms Price List.xlsx",
            )
        ),
    ),
}

EXPECT_OPTIONS = {
    "Black Horse Furniture",
    "INTEG Wood Products",
    "Mirror Lake Woodworks",
    "Old Town Oak",
    "Signature Designs",
    "Criswell Bedroom",
}

MIN_ROWS = {
    "Black Horse Furniture": 300,
    "INTEG Wood Products": 1_000,
    "Kidron Woodcraft": 40,
    "Mirror Lake Woodworks": 9_000,
    "Old Town Oak": 800,
    "Signature Designs": 75,
    "Criswell Bedroom": 1_300,
}


def _live_counts(service: PriceBookService, vendor: str) -> tuple[int, int]:
    with service.repo._conn() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*),
                   SUM(CASE WHEN TRIM(COALESCE(option_key, '')) != '' THEN 1 ELSE 0 END)
            FROM pricebook WHERE vendor = ?
            """,
            (vendor,),
        ).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def _semantic_key(row: dict) -> tuple:
    return tuple(
        row.get(field)
        for field in (
            "vendor",
            "collection",
            "part_number",
            "description",
            "dimensions",
            "species",
            "species_tier",
            "finish_state",
            "base_price",
            "adjusted_price",
            "addon_pct",
            "option_key",
            "line_kind",
        )
    )


def _parse(vendor: str, parser_id: str, files: tuple[Path, ...]) -> list[dict]:
    service = ImportService()
    rows: list[dict] = []
    for path in files:
        if not path.is_file():
            raise SystemExit(f"missing locked source: {path}")
        preview = service.preview_excel(
            path.read_bytes(),
            filename=path.name,
            vendor=vendor,
            preferred_parser=parser_id,
        )
        print(f"  {path.name}: {len(preview.rows):,} rows")
        rows.extend(preview.rows)
    unique: dict[tuple, dict] = {}
    for row in rows:
        unique.setdefault(_semantic_key(row), row)
    return list(unique.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    service = PriceBookService()
    prepared: dict[str, list[dict]] = {}
    for vendor, (parser_id, files) in SOURCES.items():
        print(f"\n{vendor}")
        rows = _parse(vendor, parser_id, files)
        before_count, _ = _live_counts(service, vendor)
        options = [row for row in rows if row.get("line_kind") == "addon"]
        unfinished = [row for row in rows if row.get("finish_state") == "unfinished"]
        print(
            f"  live {before_count:,} -> parsed {len(rows):,}"
            f" · Options {len(options):,} · unfinished {len(unfinished):,}"
        )
        if before_count == 0 or len(rows) < MIN_ROWS[vendor]:
            raise SystemExit(f"refused {vendor}: parsed below verified visible minimum")
        if vendor in EXPECT_OPTIONS and not options:
            raise SystemExit(f"refused {vendor}: no Options survived")
        if vendor == "Kidron Woodcraft" and not unfinished:
            raise SystemExit("refused Kidron: unfinished twins did not survive")
        prepared[vendor] = rows

    if not args.apply:
        print("\ndry run — no changes written. Pass --apply to load.")
        return 0

    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / (
        f"master_pricebook.before_options_{datetime.now():%Y%m%d_%H%M%S}.db"
    )
    shutil.copy2(DB_PATH, backup)
    print(f"\nbackup: {backup}")

    for vendor, rows in prepared.items():
        result = service.repo.replace_vendor_rows(vendor, rows)
        after_count, options = _live_counts(service, vendor)
        print(f"{vendor}: {result} · live {after_count:,} · Options {options:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
