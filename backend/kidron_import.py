"""Locked reader for Kidron Woodcraft's visible Prices sheet.

The left price bands are dealer retail formulas. The right bands are the
factory wholesale finished/unfinished twins used by Search.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from backend.workbook_sheets import read_all_sheets
from wide_import import WorkbookImportResult, tag_import_result

_SKU = re.compile(r"^(#[A-Za-z0-9][A-Za-z0-9./-]*)\s*(.*)$")


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _money(value: Any) -> Optional[float]:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def _species(value: Any) -> str:
    parts = [part.strip() for part in re.split(r"[\n,]+", str(value or "")) if part.strip()]
    combined: list[str] = []
    for part in parts:
        if part.casefold() == "cherry" and combined and combined[-1].casefold() == "rustic":
            combined[-1] = "Rustic Cherry"
        else:
            combined.append(part)
    parts = combined
    return " / ".join(parts)


def _parse_prices(raw: pd.DataFrame, vendor: str) -> list[dict[str, Any]]:
    rows = raw.values.tolist()
    header_index = None
    price_pairs: list[tuple[int, int, str]] = []
    collection = ""

    for row_index, row in enumerate(rows):
        for col in range(8, max(0, len(row) - 1)):
            if _text(row[col]).casefold() != "fin":
                continue
            if _text(row[col + 1]).casefold() != "unfin":
                continue
            species = _species(rows[row_index - 1][col] if row_index else "")
            if species:
                price_pairs.append((col, col + 1, species))
        if price_pairs:
            header_index = row_index
            collection = _text(row[0])
            break

    if header_index is None:
        return []

    out: list[dict[str, Any]] = []
    for row in rows[header_index + 1 :]:
        first = _text(row[0] if row else None)
        match = _SKU.match(first)
        if not match:
            if first and not any(_money(row[col]) for col, _, _ in price_pairs):
                collection = first
            continue
        part_number, description = match.groups()
        description = description.strip() or part_number
        for finished_col, unfinished_col, species in price_pairs:
            for col, finish_state in (
                (finished_col, "finished"),
                (unfinished_col, "unfinished"),
            ):
                price = _money(row[col] if col < len(row) else None)
                if price is None:
                    continue
                out.append(
                    {
                        "vendor": vendor,
                        "collection": collection,
                        "part_number": part_number,
                        "description": description,
                        "species": species,
                        "finish_state": finish_state,
                        "base_price": price,
                        "price_basis": "wholesale",
                        "line_kind": "item",
                    }
                )
    return out


def import_kidron_workbook(
    data: bytes,
    *,
    vendor: str = "Kidron Woodcraft",
    default_collection: str = "",
    sheet_filter: Optional[list[str]] = None,
    filename: str = "",
) -> WorkbookImportResult:
    views = read_all_sheets(data)
    names = [view.name for view in views]
    tried: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    for view in views:
        if sheet_filter and view.name not in sheet_filter:
            continue
        parsed = (
            _parse_prices(view.raw, vendor)
            if view.name.strip().casefold() == "prices" and view.raw is not None
            else []
        )
        tried.append({"sheet": view.name, "rows": len(parsed)})
        records.extend(parsed)

    frame = pd.DataFrame(records)
    if not frame.empty and default_collection:
        frame["collection"] = frame["collection"].replace("", default_collection)
    result = WorkbookImportResult(
        sheets_tried=tried,
        long_df=frame,
        detected_markup=None,
        sheet_names=names,
        notes="Kidron visible wholesale finished/unfinished bands",
        expected_option_lines=0,
    )
    return tag_import_result(result, "kidron_woodcraft")
