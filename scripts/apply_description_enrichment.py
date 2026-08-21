#!/usr/bin/env python3
"""Apply only the shared human-description contract to the live catalog.

This migration cannot add, delete, or alter sellable identity, prices, woods,
finishes, Options, or source metadata.  It exists for locked source files that
cannot yet pass a lossless replace-vendor re-import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DB_PATH
from backend.product_descriptions import human_description
from scripts.backup_db import backup_now


ROW_FIELDS = (
    "id",
    "vendor",
    "collection",
    "part_number",
    "description",
    "dimensions",
    "option_key",
    "species",
    "species_tier",
    "finish_state",
    "base_price",
    "price_basis",
    "multiplier",
    "adjusted_price",
    "unit",
    "notes",
    "source_file",
    "imported_at",
    "line_kind",
    "addon_pct",
)
STRUCTURAL_FIELDS = tuple(field for field in ROW_FIELDS if field != "description")


def _digest(rows: list[sqlite3.Row]) -> str:
    payload = [
        [row[field] for field in STRUCTURAL_FIELDS]
        for row in rows
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def enrich_database(path: Path, *, apply: bool) -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"SELECT {', '.join(ROW_FIELDS)} FROM pricebook ORDER BY id"
    ).fetchall()
    before_digest = _digest(rows)
    updates = []
    by_vendor: dict[str, int] = {}
    for row in rows:
        new_description = human_description(dict(row))
        if not new_description or new_description == row["description"]:
            continue
        updates.append((new_description, int(row["id"])))
        vendor = str(row["vendor"] or "")
        by_vendor[vendor] = by_vendor.get(vendor, 0) + 1

    if not apply:
        conn.close()
        return {
            "apply": False,
            "rows": len(rows),
            "updates": len(updates),
            "vendors": by_vendor,
        }

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executemany(
            "UPDATE pricebook SET description=? WHERE id=?",
            updates,
        )
        after = conn.execute(
            f"SELECT {', '.join(ROW_FIELDS)} FROM pricebook ORDER BY id"
        ).fetchall()
        if len(after) != len(rows):
            raise RuntimeError("row count changed during description migration")
        if _digest(after) != before_digest:
            raise RuntimeError("non-description catalog fields changed")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        raise
    conn.close()
    return {
        "apply": True,
        "rows": len(rows),
        "updates": len(updates),
        "vendors": by_vendor,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply:
        print(f"backup={backup_now()}", flush=True)
    result = enrich_database(args.db, apply=args.apply)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
