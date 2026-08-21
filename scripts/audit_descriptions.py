#!/usr/bin/env python3
"""Read-only description-quality audit for every builder in the master book."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import DB_PATH


_PLACEHOLDER = re.compile(
    r"(?i)^(?:nan|nat|none|null|options?|finished|unfinished|finish|"
    r"price|wholesale|retail)$"
)
_DIMENSION_ONLY = re.compile(
    r"""(?ix)^
    \d+(?:[./\s½¼¾⅛⅜⅝⅞-]+\d*)?["']?
    (?:\s*(?:x|×)\s*\d+(?:[./\s½¼¾⅛⅜⅝⅞-]+\d*)?["']?){0,3}
    (?:\s*(?:w|d|h|wide|deep|high|tv\s*opening))?
    $
    """
)


def _same_text(left: Any, right: Any) -> bool:
    def key(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    text = str(left or "")
    human_words = re.findall(r"[A-Za-z]{3,}", text)
    return (
        bool(key(left))
        and key(left) == key(right)
        and len(human_words) < 2
    )


def audit_connection(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT vendor, part_number, description, collection, dimensions, notes
        FROM pricebook
        WHERE lower(COALESCE(line_kind, 'item')) != 'addon'
        ORDER BY vendor
        """
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["vendor"] or ""), []).append(row)

    builders = []
    totals = {
        "items": 0,
        "blank": 0,
        "placeholder": 0,
        "sku_only": 0,
        "dimension_only": 0,
    }
    for vendor, items in grouped.items():
        counts = {
            "items": len(items),
            "blank": 0,
            "placeholder": 0,
            "sku_only": 0,
            "dimension_only": 0,
            "with_collection": 0,
            "with_dimensions": 0,
            "with_notes": 0,
        }
        samples = []
        for row in items:
            desc = str(row["description"] or "").strip()
            if not desc:
                counts["blank"] += 1
            if desc and _PLACEHOLDER.fullmatch(desc):
                counts["placeholder"] += 1
            if _same_text(desc, row["part_number"]):
                counts["sku_only"] += 1
            if desc and _DIMENSION_ONLY.fullmatch(desc):
                counts["dimension_only"] += 1
            for field, metric in (
                ("collection", "with_collection"),
                ("dimensions", "with_dimensions"),
                ("notes", "with_notes"),
            ):
                if str(row[field] or "").strip():
                    counts[metric] += 1
            weak = (
                not desc
                or bool(_PLACEHOLDER.fullmatch(desc))
                or _same_text(desc, row["part_number"])
                or bool(_DIMENSION_ONLY.fullmatch(desc))
            )
            if weak and len(samples) < 5:
                samples.append(
                    {
                        "part_number": row["part_number"],
                        "description": row["description"],
                        "collection": row["collection"],
                        "dimensions": row["dimensions"],
                    }
                )
        weak_count = max(
            counts["blank"],
            counts["placeholder"],
            counts["sku_only"],
            counts["dimension_only"],
        )
        weak_pct = round((weak_count / len(items) * 100) if items else 0.0, 2)
        status = "poor" if weak_pct >= 35 else "moderate" if weak_pct >= 15 else "good"
        builders.append(
            {
                "vendor": vendor,
                **counts,
                "weak_pct": weak_pct,
                "status": status,
                "samples": samples,
            }
        )
        for key in totals:
            totals[key] += counts[key]

    return {
        "db_builders": len(builders),
        **totals,
        "status_counts": {
            status: sum(1 for builder in builders if builder["status"] == status)
            for status in ("good", "moderate", "poor")
        },
        "builders": builders,
    }


def audit_database(path: Path) -> dict[str, Any]:
    uri = f"file:{path.resolve()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        return audit_connection(conn)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_database(args.db)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
