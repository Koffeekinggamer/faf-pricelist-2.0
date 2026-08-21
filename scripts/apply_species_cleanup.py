"""Re-apply the wood-species contract to the live catalog.

Only ``species`` changes. Identity, prices, options, and row count are proved
untouched before the write commits, so a bad run cannot quietly reshape the
book. Read-only by default; pass ``--apply`` to write.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DB_PATH
from backend.standardize import standardize_species

def _digest(conn: sqlite3.Connection) -> tuple[int, int]:
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(COALESCE(adjusted_price, 0)), 0) FROM pricebook"
    ).fetchone()
    return int(row[0]), round(float(row[1]), 2)


def plan_changes(conn: sqlite3.Connection) -> list[tuple[int, Optional[str]]]:
    conn.row_factory = sqlite3.Row
    changes: list[tuple[int, Optional[str]]] = []
    for row in conn.execute(
        "SELECT id, species FROM pricebook WHERE TRIM(COALESCE(species, '')) != ''"
    ):
        current = row["species"]
        cleaned = standardize_species(current)
        if cleaned != current:
            changes.append((int(row["id"]), cleaned))
    return changes


def _report(conn: sqlite3.Connection, changes: list[tuple[int, Optional[str]]]) -> None:
    conn.row_factory = sqlite3.Row
    by_vendor: Counter[str] = Counter()
    blanked = 0
    ids = {cid for cid, _ in changes}
    for row in conn.execute("SELECT id, vendor FROM pricebook"):
        if int(row["id"]) in ids:
            by_vendor[str(row["vendor"])] += 1
    for _, value in changes:
        if value is None:
            blanked += 1
    print(f"rows to update: {len(changes):,} (species cleared on {blanked:,})")
    for vendor, count in by_vendor.most_common(20):
        print(f"  {vendor[:34]:34} {count:,}")


def run(path: Path, *, apply: bool) -> int:
    conn = sqlite3.connect(path)
    try:
        before = _digest(conn)
        changes = plan_changes(conn)
        _report(conn, changes)
        if not apply:
            print("\ndry run — no changes written. Pass --apply to write.")
            return 0
        conn.executemany(
            "UPDATE pricebook SET species = ? WHERE id = ?",
            [(value, cid) for cid, value in changes],
        )
        after = _digest(conn)
        if before != after:
            conn.rollback()
            raise SystemExit(f"refused: catalog digest moved {before} -> {after}")
        conn.commit()
        print(f"\napplied to {len(changes):,} rows · rows and prices unchanged {after}")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    return run(Path(args.db), apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
