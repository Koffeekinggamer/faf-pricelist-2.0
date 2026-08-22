"""Read-only Options proof for every builder in the master price book.

This is the catalog-side half of the quality gate. It uses the same
``PriceBookService.list_option_keys`` contract as Search, then proves every
stored add-on has a known charge shape and the correct stored retail. Source
workbook evidence is compared separately by ``scripts/finalreview_inspect.py``.
"""

from __future__ import annotations

import sqlite3
import re
from typing import Any

from backend.pricing import catalog_retail


_QUOTE_NOTE = re.compile(
    r"(?i)quote\s+required|call\s+for\s+(?:pricing|price|quote)|\btbd\b"
)


def _money(value: Any) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _finish_state_gaps(conn, vendor: str, search_options: list[str]) -> list[str]:
    """Finish states a source file promised but the loaded rows never show.

    A Finished and an Unfinished book are two prices for the same piece. If both
    land under one finish_state the floor cannot tell them apart.
    """
    from backend.import_service import source_finish_states

    rows = conn.execute(
        """
        SELECT DISTINCT COALESCE(source_file, '') AS src,
                        lower(COALESCE(finish_state, '')) AS state
        FROM pricebook WHERE vendor=?
        """,
        (vendor,),
    ).fetchall()
    expected: set[str] = set()
    present: set[str] = set()
    for row in rows:
        expected.update(source_finish_states(str(row["src"]), []))
        if row["state"]:
            present.add(str(row["state"]))
    labels = " ".join(search_options).lower()
    return [
        state
        for state in ("finished", "unfinished")
        if state in expected and state not in present and state not in labels
    ]


def audit_catalog_options(service) -> dict[str, Any]:
    """Return one deterministic, JSON-safe Options audit for every builder."""
    service.ensure_ready()
    conn = sqlite3.connect(service.path)
    conn.row_factory = sqlite3.Row
    try:
        vendors = [
            str(row[0])
            for row in conn.execute(
                """
                SELECT DISTINCT vendor
                FROM pricebook
                WHERE TRIM(COALESCE(vendor, '')) != ''
                ORDER BY vendor COLLATE NOCASE
                """
            )
        ]
        builders: list[dict[str, Any]] = []
        for vendor in vendors:
            counts = conn.execute(
                """
                SELECT
                  SUM(CASE WHEN lower(COALESCE(line_kind, 'item')) != 'addon'
                           THEN 1 ELSE 0 END) AS items,
                  SUM(CASE WHEN lower(COALESCE(line_kind, 'item')) = 'addon'
                           THEN 1 ELSE 0 END) AS addons,
                  SUM(CASE WHEN lower(COALESCE(line_kind, 'item')) != 'addon'
                                AND lower(COALESCE(finish_state, '')) = 'unfinished'
                           THEN 1 ELSE 0 END) AS unfinished
                FROM pricebook WHERE vendor=?
                """,
                (vendor,),
            ).fetchone()
            addon_rows = conn.execute(
                """
                SELECT option_key, description, part_number, base_price,
                       adjusted_price, addon_pct, multiplier, notes
                FROM pricebook
                WHERE vendor=?
                  AND lower(COALESCE(line_kind, 'item'))='addon'
                ORDER BY option_key COLLATE NOCASE, id
                """,
                (vendor,),
            ).fetchall()

            shapes = {"dollar": 0, "percent": 0, "zero": 0, "quote": 0}
            mismatches: list[dict[str, Any]] = []
            deduction_sign_mismatches: list[str] = []
            blank_labels = 0
            for row in addon_rows:
                label = str(
                    row["option_key"] or row["description"] or row["part_number"] or ""
                ).strip()
                if not label:
                    blank_labels += 1
                if (
                    re.search(r"(?i)\b(deduct(?:ion)?|less|credit)\b", label)
                    and _money(row["base_price"]) > 0
                ):
                    deduction_sign_mismatches.append(label)
                has_dollars = bool(_money(row["base_price"]) or _money(row["adjusted_price"]))
                has_percent = bool(_money(row["addon_pct"]))
                if has_dollars:
                    shapes["dollar"] += 1
                elif has_percent:
                    shapes["percent"] += 1
                elif _QUOTE_NOTE.search(str(row["notes"] or "")):
                    # The factory publishes no price. Not the same as free.
                    shapes["quote"] += 1
                else:
                    # Explicit no-charge choices are valid catalog Options.
                    shapes["zero"] += 1

                if has_dollars:
                    expected = catalog_retail(
                        row["base_price"],
                        row["multiplier"],
                        line_kind="addon",
                        option_key=label,
                    )
                    stored = row["adjusted_price"]
                    if expected is not None and abs(_money(expected) - _money(stored)) > 0.01:
                        mismatches.append(
                            {
                                "option": label,
                                "stored_retail": _money(stored),
                                "expected_retail": _money(expected),
                            }
                        )

            search_options = list(service.list_option_keys(vendor) or [])
            finish_state_gaps = _finish_state_gaps(conn, vendor, search_options)
            quantity_options = [
                label
                for label in search_options
                if service._option_qty_allowed(label)
            ]
            issues: list[str] = []
            if not search_options:
                issues.append("Search Options empty")
            if blank_labels:
                issues.append(
                    f"{blank_labels} add-on row"
                    + ("" if blank_labels == 1 else "s")
                    + " missing an Option label"
                )
            if mismatches:
                issues.append(
                    f"{len(mismatches)} add-on retail calculation mismatch"
                    + ("" if len(mismatches) == 1 else "es")
                )
            if deduction_sign_mismatches:
                issues.append(
                    f"{len(deduction_sign_mismatches)} deduction"
                    + ("" if len(deduction_sign_mismatches) == 1 else "s")
                    + " stored as a positive charge"
                )
            for state in finish_state_gaps:
                issues.append(
                    f"{state} promised by the source but not captured"
                )

            builders.append(
                {
                    "vendor": vendor,
                    "item_rows": int(counts["items"] or 0),
                    "addon_rows": int(counts["addons"] or 0),
                    "unfinished_rows": int(counts["unfinished"] or 0),
                    "search_options": search_options,
                    "quantity_options": quantity_options,
                    "charge_shapes": shapes,
                    "retail_mismatches": mismatches,
                    "deduction_sign_mismatches": deduction_sign_mismatches,
                    "finish_state_gaps": finish_state_gaps,
                    "issues": issues,
                }
            )

        return {
            "builder_count": len(builders),
            "builders_with_options": sum(bool(row["search_options"]) for row in builders),
            "builders_with_quantity_options": sum(
                bool(row["quantity_options"]) for row in builders
            ),
            "addon_rows": sum(row["addon_rows"] for row in builders),
            "retail_mismatch_count": sum(
                len(row["retail_mismatches"]) for row in builders
            ),
            "builders": builders,
        }
    finally:
        conn.close()
