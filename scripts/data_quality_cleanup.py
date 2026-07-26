#!/usr/bin/env python3
"""One-shot data quality: fill empty part_numbers, collapse exact dups."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "master_pricebook.db"

_SKU_LIKE = re.compile(
    r"(?ix)^([A-Z]{1,4}-[A-Z0-9][A-Z0-9\-_/.]{1,24}|[A-Z]{2,6}\d{2,}[A-Z0-9\-]*|\d{3,6})$"
)


def main() -> int:
    if not DB.is_file():
        print(f"No DB at {DB}")
        return 1

    con = sqlite3.connect(str(DB))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    before_rows = cur.execute("SELECT COUNT(*) FROM pricebook").fetchone()[0]
    empty_before = cur.execute(
        "SELECT COUNT(*) FROM pricebook WHERE part_number IS NULL OR TRIM(part_number)=''"
    ).fetchone()[0]
    dup_before = cur.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT 1 FROM pricebook
          GROUP BY vendor,
                   COALESCE(part_number,''),
                   COALESCE(species,''),
                   COALESCE(finish_state,''),
                   COALESCE(description,''),
                   ROUND(COALESCE(base_price,0), 2)
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    # 1) Fill empty part_number from SKU-like description, else short description token
    filled = 0
    rows = cur.execute(
        """
        SELECT id, description FROM pricebook
        WHERE part_number IS NULL OR TRIM(part_number)=''
        """
    ).fetchall()
    for r in rows:
        desc = (r["description"] or "").strip()
        if not desc:
            continue
        part = None
        if _SKU_LIKE.match(desc):
            part = desc.upper() if desc.upper().startswith("LA-") else desc
        else:
            # Use cleaned description as part for options (Bunkie board, etc.)
            cleaned = re.sub(r"\s+", " ", desc)[:48].strip()
            if cleaned:
                part = cleaned
        if part:
            cur.execute(
                "UPDATE pricebook SET part_number=? WHERE id=?",
                (part, r["id"]),
            )
            filled += 1

    # 2) Collapse exact duplicates: keep highest id (newest) per identity+price
    keep_ids = {
        r[0]
        for r in cur.execute(
            """
            SELECT MAX(id) FROM pricebook
            GROUP BY vendor,
                     COALESCE(part_number,''),
                     COALESCE(species,''),
                     COALESCE(finish_state,''),
                     COALESCE(description,''),
                     ROUND(COALESCE(base_price,0), 2)
            """
        )
    }
    all_ids = [r[0] for r in cur.execute("SELECT id FROM pricebook")]
    delete_ids = [i for i in all_ids if i not in keep_ids]
    deleted = 0
    for i in range(0, len(delete_ids), 400):
        chunk = delete_ids[i : i + 400]
        placeholders = ",".join("?" * len(chunk))
        cur.execute(f"DELETE FROM pricebook WHERE id IN ({placeholders})", chunk)
        deleted += len(chunk)

    con.commit()

    empty_after = cur.execute(
        "SELECT COUNT(*) FROM pricebook WHERE part_number IS NULL OR TRIM(part_number)=''"
    ).fetchone()[0]
    after_rows = cur.execute("SELECT COUNT(*) FROM pricebook").fetchone()[0]
    dup_after = cur.execute(
        """
        SELECT COUNT(*) FROM (
          SELECT 1 FROM pricebook
          GROUP BY vendor,
                   COALESCE(part_number,''),
                   COALESCE(species,''),
                   COALESCE(finish_state,''),
                   COALESCE(description,''),
                   ROUND(COALESCE(base_price,0), 2)
          HAVING COUNT(*) > 1
        )
        """
    ).fetchone()[0]

    # Vendor breakdown
    print("=== DATA QUALITY CLEANUP ===")
    print(f"rows: {before_rows:,} → {after_rows:,}  (deleted {deleted:,} exact dups)")
    print(f"empty part_number: {empty_before} → {empty_after}  (filled {filled})")
    print(f"exact-dup groups: {dup_before} → {dup_after}")
    print("by vendor after:")
    for r in cur.execute(
        "SELECT vendor, COUNT(*) n FROM pricebook GROUP BY vendor ORDER BY n DESC"
    ):
        print(f"  {r[0]}: {r[1]:,}")

    # Retail = next even whole dollar up from base × mult
    mism = cur.execute(
        """
        SELECT COUNT(*) FROM pricebook
        WHERE base_price IS NOT NULL AND multiplier IS NOT NULL AND adjusted_price IS NOT NULL
          AND ABS(
                adjusted_price
                - (2 * CEIL((base_price * multiplier) / 2.0 - 1e-12))
              ) > 0.02
        """
    ).fetchone()[0]
    print(f"retail mismatches after (even-dollar rule): {mism}")
    con.close()
    return 0 if mism == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
